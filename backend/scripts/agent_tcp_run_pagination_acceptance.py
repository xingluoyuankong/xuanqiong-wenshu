"""Real TCP/JWT acceptance for Agent Run history pagination."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import delete

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models import AgentRun, AgentSession  # noqa: E402


class AcceptanceFailure(RuntimeError):
    pass


def _json(response: httpx.Response, expected: int, phase: str) -> dict[str, Any]:
    if response.status_code != expected:
        try:
            detail = response.json()
        except Exception:
            detail = response.text[:300]
        raise AcceptanceFailure(f"phase={phase} status={response.status_code} detail={detail}")
    payload = response.json()
    if not isinstance(payload, dict):
        raise AcceptanceFailure(f"phase={phase} response is not an object")
    return payload


async def _seed(user_id: int, count: int) -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:12]
    async with AsyncSessionLocal() as db:
        session = AgentSession(user_id=user_id, project_id=None, title=f"TCP run pagination fixture {suffix}")
        db.add(session)
        await db.flush()
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for index in range(count):
            created_at = base + timedelta(seconds=index)
            db.add(AgentRun(
                id=str(uuid.uuid4()),
                session_id=session.id,
                user_id=user_id,
                project_id=None,
                status="succeeded",
                current_step=1,
                progress=100.0,
                context_json={"fixture": "tcp-run-pagination"},
                latest_public_summary_json={},
                created_at=created_at,
                started_at=created_at,
                finished_at=created_at,
                updated_at=created_at,
            ))
        await db.commit()
        return {"session_id": session.id}


async def _cleanup(fixture: dict[str, Any]) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentRun).where(AgentRun.session_id == fixture["session_id"]))
        await db.execute(delete(AgentSession).where(AgentSession.id == fixture["session_id"]))
        await db.commit()


async def _collect(client: httpx.AsyncClient, session_id: str, headers: dict[str, str], limit: int, expected_count: int) -> dict[str, Any]:
    collected: list[str] = []
    cursor: tuple[str, str] | None = None
    pages = 0
    while True:
        params: dict[str, Any] = {"limit": limit}
        if cursor:
            params["before_created_at"], params["before_id"] = cursor
        page = _json(await client.get(f"/api/agent/sessions/{session_id}/runs", params=params, headers=headers), 200, f"run_page_{pages + 1}")
        items = page.get("items")
        if not isinstance(items, list):
            raise AcceptanceFailure(f"phase=run_page_{pages + 1} items is not a list")
        keys = [(str(item["created_at"]), str(item["id"])) for item in items]
        if keys != sorted(keys):
            raise AcceptanceFailure(f"phase=run_page_{pages + 1} order is not ascending")
        collected.extend(str(item["id"]) for item in items)
        pages += 1
        next_created = page.get("next_before_created_at")
        next_id = page.get("next_before_id")
        has_more = bool(page.get("has_more"))
        if has_more != bool(next_created and next_id):
            raise AcceptanceFailure(f"phase=run_page_{pages} cursor contract invalid")
        if not has_more:
            break
        cursor = (str(next_created), str(next_id))
        if pages > (expected_count // limit) + 3:
            raise AcceptanceFailure("run pagination did not converge")
    if len(collected) != expected_count or len(collected) != len(set(collected)):
        raise AcceptanceFailure(f"run sequence mismatch expected={expected_count} got={len(collected)} duplicates={len(collected)-len(set(collected))}")
    return {"pages": pages, "run_count": len(collected), "duplicate_count": len(collected) - len(set(collected))}


async def run(base_url: str, username: str, password: str, count: int, limit: int) -> dict[str, Any]:
    fixture: dict[str, Any] | None = None
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0, follow_redirects=True) as client:
        login = _json(await client.post("/api/auth/login", data={"username": username, "password": password}), 200, "jwt_login")
        token = str(login.get("access_token") or "")
        if not token:
            raise AcceptanceFailure("phase=jwt_login missing access_token")
        headers = {"Authorization": f"Bearer {token}"}
        profile = _json(await client.get("/api/novels/current-user", headers=headers), 200, "jwt_profile")
        fixture = await _seed(int(profile["id"]), count)
        try:
            compact = _json(await client.get(f"/api/agent/sessions/{fixture['session_id']}", params={"include_messages": "false", "include_runs": "false"}, headers=headers), 200, "compact_detail")
            if compact.get("messages") != [] or compact.get("runs") != []:
                raise AcceptanceFailure("phase=compact_detail expected empty arrays")
            result = await _collect(client, fixture["session_id"], headers, limit, count)
            return {"status": "TCP_JWT_RUN_PAGINATION_PASSED", "base_url": base_url, "session_id": fixture["session_id"], "page_limit": limit, **result}
        finally:
            await _cleanup(fixture)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("AGENT_TCP_BASE_URL", "http://127.0.0.1:8013"))
    parser.add_argument("--username", default=os.getenv("ADMIN_DEFAULT_USERNAME", ""))
    parser.add_argument("--password", default=os.getenv("ADMIN_DEFAULT_PASSWORD", ""))
    parser.add_argument("--count", type=int, default=125)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    if not args.username or not args.password:
        print(json.dumps({"status": "TCP_JWT_RUN_PAGINATION_FAILED", "error": "ADMIN_DEFAULT_USERNAME and ADMIN_DEFAULT_PASSWORD are required"}, ensure_ascii=False), file=sys.stderr)
        return 1
    try:
        print(json.dumps(await run(args.base_url.rstrip("/"), args.username, args.password, args.count, args.limit), ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "TCP_JWT_RUN_PAGINATION_FAILED", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

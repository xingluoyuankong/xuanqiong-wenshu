"""Real TCP/JWT acceptance for Agent session message pagination.

The fixture rows are inserted through the same configured database used by the
running service; all assertions under test use TCP requests to 127.0.0.1:8013.
The created projectless session is deleted in the finally block.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

import httpx
from sqlalchemy import delete, select

# Allow execution as `python backend/scripts/...` from the repository root.
BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models import AgentMessage, AgentSession  # noqa: E402


class AcceptanceFailure(RuntimeError):
    pass


def _detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
        return str(payload.get("detail", payload))[:300] if isinstance(payload, dict) else str(payload)[:300]
    except Exception:
        return response.text[:300]


def _expect(response: httpx.Response, status_code: int, phase: str) -> dict[str, Any]:
    if response.status_code != status_code:
        raise AcceptanceFailure(f"phase={phase} status={response.status_code} detail={_detail(response)}")
    try:
        return response.json()
    except Exception as exc:
        raise AcceptanceFailure(f"phase={phase} invalid_json={response.text[:300]}") from exc


async def _seed_messages(session_id: str, user_id: int, count: int) -> None:
    async with AsyncSessionLocal() as db:
        row = await db.scalar(select(AgentSession).where(AgentSession.id == session_id))
        if row is None:
            raise AcceptanceFailure(f"fixture session missing: {session_id}")
        for sequence in range(1, count + 1):
            db.add(
                AgentMessage(
                    session_id=session_id,
                    user_id=user_id,
                    role="assistant" if sequence % 2 == 0 else "user",
                    content=f"TCP pagination fixture message {sequence}",
                    sequence=sequence,
                )
            )
        await db.commit()


async def _delete_fixture(session_id: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AgentMessage).where(AgentMessage.session_id == session_id))
        await db.execute(delete(AgentSession).where(AgentSession.id == session_id))
        await db.commit()


async def run(base_url: str, username: str, password: str, count: int, limit: int) -> dict[str, Any]:
    if count < 1 or limit < 1 or limit > 200:
        raise AcceptanceFailure("count must be >= 1 and limit must be in 1..200")
    session_id: str | None = None
    primary_error: BaseException | None = None
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=30.0, follow_redirects=True) as client:
            login = await client.post("/api/auth/login", data={"username": username, "password": password})
            token_payload = _expect(login, 200, "jwt_login")
            token = str(token_payload.get("access_token") or "")
            if not token:
                raise AcceptanceFailure("phase=jwt_login missing access_token")
            headers = {"Authorization": f"Bearer {token}"}

            profile = _expect(await client.get("/api/novels/current-user", headers=headers), 200, "jwt_profile")
            user_id = int(profile["id"])
            created = _expect(
                await client.post(
                    "/api/agent/sessions",
                    headers=headers,
                    json={"title": "TCP pagination acceptance fixture"},
                ),
                201,
                "create_projectless_session",
            )
            created_id = created.get("id")
            if not isinstance(created_id, str) or not created_id.strip():
                raise AcceptanceFailure("phase=create_projectless_session missing valid session id")
            session_id = created_id
            await _seed_messages(session_id, user_id, count)

            detail = _expect(
                await client.get(
                    f"/api/agent/sessions/{session_id}",
                    params={"include_messages": "false", "include_runs": "false"},
                    headers=headers,
                ),
                200,
                "compact_session_detail",
            )
            if detail.get("messages") != [] or detail.get("runs") != []:
                raise AcceptanceFailure("phase=compact_session_detail expected empty arrays")

            collected: list[int] = []
            cursor: int | None = None
            pages = 0
            while True:
                params: dict[str, Any] = {"limit": limit}
                if cursor is not None:
                    params["before_sequence"] = cursor
                page = _expect(
                    await client.get(f"/api/agent/sessions/{session_id}/messages", params=params, headers=headers),
                    200,
                    f"message_page_{pages + 1}",
                )
                items = page.get("items")
                if not isinstance(items, list):
                    raise AcceptanceFailure(f"phase=message_page_{pages + 1} items is not a list")
                sequences = [int(item["sequence"]) for item in items]
                if sequences != sorted(sequences):
                    raise AcceptanceFailure(f"phase=message_page_{pages + 1} page is not ascending: {sequences}")
                if cursor is not None and any(sequence >= cursor for sequence in sequences):
                    raise AcceptanceFailure(f"phase=message_page_{pages + 1} cursor was not exclusive")
                collected.extend(sequences)
                pages += 1
                next_cursor = page.get("next_cursor")
                has_more = bool(page.get("has_more"))
                if has_more != bool(next_cursor):
                    raise AcceptanceFailure(f"phase=message_page_{pages} inconsistent has_more/next_cursor")
                if not has_more:
                    break
                if next_cursor is None:
                    raise AcceptanceFailure(f"phase=message_page_{pages} missing next_cursor")
                cursor = int(next_cursor)
                if pages > (count // limit) + 3:
                    raise AcceptanceFailure("pagination did not converge")

            expected = list(range(1, count + 1))
            ordered = sorted(collected)
            if ordered != expected or len(collected) != len(set(collected)):
                raise AcceptanceFailure(
                    f"sequence mismatch expected_count={len(expected)} got_count={len(collected)} "
                    f"first={ordered[:5]} last={ordered[-5:]} duplicates={len(collected) - len(set(collected))}"
                )
            return {
                "status": "TCP_MESSAGE_PAGINATION_PASSED",
                "base_url": base_url,
                "session_id": session_id,
                "user_id": user_id,
                "message_count": count,
                "page_limit": limit,
                "pages": pages,
                "first_sequence": ordered[0],
                "last_sequence": ordered[-1],
                "duplicate_count": len(collected) - len(set(collected)),
            }
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        # Ownership is established only by the successful create response.
        # Never discover a cleanup target by title or another shared attribute.
        if session_id is not None:
            try:
                await _delete_fixture(session_id)
            except Exception as cleanup_error:
                if primary_error is None:
                    raise
                primary_error.add_note(
                    f"fixture cleanup failed session_id={session_id}: {cleanup_error}"
                )


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("AGENT_TCP_BASE_URL", "http://127.0.0.1:8013"))
    parser.add_argument("--username", default=os.getenv("ADMIN_DEFAULT_USERNAME", ""))
    parser.add_argument("--password", default=os.getenv("ADMIN_DEFAULT_PASSWORD", ""))
    parser.add_argument("--count", type=int, default=180)
    parser.add_argument("--limit", type=int, default=60)
    args = parser.parse_args()
    if not args.username or not args.password:
        raise AcceptanceFailure("ADMIN_DEFAULT_USERNAME and ADMIN_DEFAULT_PASSWORD are required")
    try:
        result = await run(args.base_url.rstrip("/"), args.username, args.password, args.count, args.limit)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        error: dict[str, Any] = {"status": "TCP_MESSAGE_PAGINATION_FAILED", "error": str(exc)}
        if notes := getattr(exc, "__notes__", None):
            error["notes"] = notes
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

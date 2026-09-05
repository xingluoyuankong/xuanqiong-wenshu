"""Real TCP/JWT member-scope acceptance for Agent message pagination."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from typing import Any

import httpx
from sqlalchemy import delete

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.core.security import hash_password  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.models import AgentMessage, AgentSession, NovelProject, ProjectMember, User  # noqa: E402
from app.models.project_member import ProjectMemberRole  # noqa: E402


class AcceptanceFailure(RuntimeError):
    pass


def _json(response: httpx.Response, expected: int, phase: str) -> dict[str, Any]:
    if response.status_code != expected:
        try:
            detail = response.json()
        except Exception:
            detail = response.text[:300]
        raise AcceptanceFailure(f"phase={phase} status={response.status_code} detail={detail}")
    return response.json()


async def _seed(count: int) -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:12]
    project_id = f"tcp-member-{suffix}"
    usernames = {role: f"tcp_{role}_{suffix}" for role in ("owner", "viewer", "outsider")}
    password = f"TcpFixture!{uuid.uuid4().hex[:16]}"
    async with AsyncSessionLocal() as db:
        users = {
            role: User(username=username, email=f"{username}@example.test", hashed_password=hash_password(password), is_active=True)
            for role, username in usernames.items()
        }
        db.add_all(users.values())
        await db.flush()
        project = NovelProject(id=project_id, user_id=users["owner"].id, title="TCP member pagination fixture")
        db.add(project)
        db.add_all([
            ProjectMember(project_id=project_id, user_id=users["owner"].id, role=ProjectMemberRole.owner.value),
            ProjectMember(project_id=project_id, user_id=users["viewer"].id, role=ProjectMemberRole.viewer.value),
        ])
        shared = AgentSession(user_id=users["owner"].id, project_id=project_id, title="TCP member shared fixture")
        private = AgentSession(user_id=users["owner"].id, project_id=None, title="TCP member private fixture")
        db.add_all([shared, private])
        await db.flush()
        for sequence in range(1, count + 1):
            db.add(AgentMessage(session_id=shared.id, user_id=users["owner"].id, role="assistant", content=f"member fixture {sequence}", sequence=sequence))
        db.add(AgentMessage(session_id=private.id, user_id=users["owner"].id, role="user", content="private fixture", sequence=1))
        await db.commit()
        return {
            "project_id": project_id,
            "session_id": shared.id,
            "private_session_id": private.id,
            "usernames": usernames,
            "password": password,
            "user_ids": {role: users[role].id for role in users},
        }


async def _cleanup(fixture: dict[str, Any]) -> None:
    async with AsyncSessionLocal() as db:
        user_ids = list(fixture.get("user_ids", {}).values())
        session_ids = [fixture["session_id"], fixture["private_session_id"]]
        await db.execute(delete(AgentMessage).where(AgentMessage.session_id.in_(session_ids)))
        await db.execute(delete(AgentSession).where(AgentSession.id.in_(session_ids)))
        await db.execute(delete(ProjectMember).where(ProjectMember.project_id == fixture["project_id"]))
        await db.execute(delete(NovelProject).where(NovelProject.id == fixture["project_id"]))
        if user_ids:
            await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()


async def _login(client: httpx.AsyncClient, username: str, password: str, role: str) -> dict[str, str]:
    payload = _json(await client.post("/api/auth/login", data={"username": username, "password": password}), 200, f"login_{role}")
    token = str(payload.get("access_token") or "")
    if not token:
        raise AcceptanceFailure(f"phase=login_{role} missing access_token")
    return {"Authorization": f"Bearer {token}"}


async def _collect_pages(client: httpx.AsyncClient, session_id: str, headers: dict[str, str], limit: int, expected_count: int, phase: str) -> list[int]:
    collected: list[int] = []
    cursor: int | None = None
    pages = 0
    while True:
        params: dict[str, Any] = {"limit": limit}
        if cursor is not None:
            params["before_sequence"] = cursor
        page = _json(await client.get(f"/api/agent/sessions/{session_id}/messages", params=params, headers=headers), 200, f"{phase}_page_{pages + 1}")
        items = page.get("items")
        if not isinstance(items, list):
            raise AcceptanceFailure(f"phase={phase} items is not a list")
        sequences = [int(item["sequence"]) for item in items]
        if sequences != sorted(sequences):
            raise AcceptanceFailure(f"phase={phase} page order invalid")
        collected.extend(sequences)
        pages += 1
        next_cursor = page.get("next_cursor")
        has_more = bool(page.get("has_more"))
        if has_more != bool(next_cursor):
            raise AcceptanceFailure(f"phase={phase} cursor contract invalid")
        if not has_more:
            break
        cursor = int(next_cursor)
        if pages > (expected_count // limit) + 3:
            raise AcceptanceFailure(f"phase={phase} pagination did not converge")
    expected = list(range(1, expected_count + 1))
    if sorted(collected) != expected or len(collected) != len(set(collected)):
        raise AcceptanceFailure(f"phase={phase} expected={len(expected)} got={len(collected)} duplicates={len(collected)-len(set(collected))}")
    return collected


async def run(base_url: str, count: int, limit: int) -> dict[str, Any]:
    fixture = await _seed(count)
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=30.0, follow_redirects=True) as client:
            headers = {role: await _login(client, fixture["usernames"][role], fixture["password"], role) for role in ("owner", "viewer", "outsider")}
            compact = _json(await client.get(
                f"/api/agent/sessions/{fixture['session_id']}",
                params={"include_messages": "false", "include_runs": "false"},
                headers=headers["owner"],
            ), 200, "owner_compact_detail")
            if compact.get("messages") != [] or compact.get("runs") != []:
                raise AcceptanceFailure("phase=owner_compact_detail expected empty arrays")
            viewer_sequences = await _collect_pages(client, fixture["session_id"], headers["viewer"], limit, count, "viewer_shared")
            owner_page = _json(await client.get(f"/api/agent/sessions/{fixture['session_id']}/messages?limit=1", headers=headers["owner"]), 200, "owner_shared")
            if owner_page.get("items", [{}])[0].get("sequence") != count:
                raise AcceptanceFailure("phase=owner_shared newest page mismatch")
            shared_denied = await client.get(f"/api/agent/sessions/{fixture['session_id']}/messages?limit=60", headers=headers["outsider"])
            if shared_denied.status_code != 403:
                raise AcceptanceFailure(f"phase=outsider_shared expected=403 got={shared_denied.status_code}")
            private_denied = await client.get(f"/api/agent/sessions/{fixture['private_session_id']}/messages?limit=60", headers=headers["outsider"])
            if private_denied.status_code != 404:
                raise AcceptanceFailure(f"phase=outsider_private expected=404 got={private_denied.status_code}")
            private_owner = await client.get(f"/api/agent/sessions/{fixture['private_session_id']}/messages?limit=60", headers=headers["owner"])
            _json(private_owner, 200, "owner_private")
        return {"status": "TCP_MEMBER_PAGINATION_PASSED", "message_count": count, "page_limit": limit, "pages": (count + limit - 1) // limit, "viewer_first": viewer_sequences[0], "viewer_last": viewer_sequences[-1], "shared_outsider_status": shared_denied.status_code, "private_outsider_status": private_denied.status_code}
    finally:
        await _cleanup(fixture)


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("AGENT_TCP_BASE_URL", "http://127.0.0.1:8013"))
    parser.add_argument("--count", type=int, default=125)
    parser.add_argument("--limit", type=int, default=60)
    args = parser.parse_args()
    try:
        print(json.dumps(await run(args.base_url.rstrip("/"), args.count, args.limit), ensure_ascii=False, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "TCP_MEMBER_PAGINATION_FAILED", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

"""Project-wide clue/knowledge-graph sync lease.

Serializes full ledger rebuilds across finalize pipelines and independent
clue/graph API endpoints so concurrent writers cannot interleave partial state.
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, Optional, Tuple

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError

from ..db.session import AsyncSessionLocal
from ..models.novel import ProjectLedgerSyncLease

logger = logging.getLogger(__name__)

PROJECT_LEDGER_LEASE_TTL = timedelta(minutes=10)
PROJECT_LEDGER_LEASE_WAIT_SECONDS = 15 * 60
PROJECT_LEDGER_LEASE_POLL_SECONDS = 1.0
PROJECT_LEDGER_LEASE_HEARTBEAT_SECONDS = 30.0
# Independent API reads should not block the UI for the full finalize budget.
PROJECT_LEDGER_API_WAIT_SECONDS = 60.0


def lease_owner_id() -> str:
    return f"{os.getpid()}:{id(asyncio.get_running_loop())}"


async def acquire_project_ledger_lease(
    *,
    project_id: str,
    chapter_number: int = 0,
    selected_version_id: Optional[int] = None,
) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
    lease_token = str(uuid.uuid4())
    owner_id = lease_owner_id()
    now = datetime.now(timezone.utc)
    expires_at = now + PROJECT_LEDGER_LEASE_TTL
    async with AsyncSessionLocal() as lease_session:
        insert_stmt = ProjectLedgerSyncLease.__table__.insert().values(
            project_id=project_id,
            chapter_number=int(chapter_number or 0),
            selected_version_id=selected_version_id,
            lease_token=lease_token,
            owner_id=owner_id,
            acquired_at=now,
            expires_at=expires_at,
        )
        dialect_name = lease_session.bind.dialect.name if lease_session.bind is not None else ""
        if dialect_name == "sqlite":
            insert_stmt = insert_stmt.prefix_with("OR IGNORE")
        elif dialect_name == "mysql":
            insert_stmt = insert_stmt.prefix_with("IGNORE")
        try:
            insert_result = await lease_session.execute(insert_stmt)
        except IntegrityError:
            await lease_session.rollback()
            insert_result = None
        if insert_result is not None and int(insert_result.rowcount or 0) == 1:
            await lease_session.commit()
            return lease_token, None

        takeover_result = await lease_session.execute(
            update(ProjectLedgerSyncLease)
            .where(
                ProjectLedgerSyncLease.project_id == project_id,
                ProjectLedgerSyncLease.expires_at <= now,
            )
            .values(
                chapter_number=int(chapter_number or 0),
                selected_version_id=selected_version_id,
                lease_token=lease_token,
                owner_id=owner_id,
                acquired_at=now,
                expires_at=expires_at,
            )
        )
        if int(takeover_result.rowcount or 0) == 1:
            await lease_session.commit()
            return lease_token, None
        active = (
            await lease_session.execute(
                select(
                    ProjectLedgerSyncLease.chapter_number,
                    ProjectLedgerSyncLease.selected_version_id,
                    ProjectLedgerSyncLease.owner_id,
                    ProjectLedgerSyncLease.expires_at,
                ).where(ProjectLedgerSyncLease.project_id == project_id)
            )
        ).first()
        await lease_session.rollback()
        if active is None:
            return None, None
        return None, {
            "chapter_number": int(active[0] or 0),
            "selected_version_id": int(active[1]) if active[1] is not None else None,
            "owner_id": active[2],
            "expires_at": active[3].isoformat() if active[3] is not None else None,
        }


async def renew_project_ledger_lease(*, project_id: str, lease_token: str) -> bool:
    now = datetime.now(timezone.utc)
    async with AsyncSessionLocal() as lease_session:
        renew_result = await lease_session.execute(
            update(ProjectLedgerSyncLease)
            .where(
                ProjectLedgerSyncLease.project_id == project_id,
                ProjectLedgerSyncLease.lease_token == lease_token,
            )
            .values(expires_at=now + PROJECT_LEDGER_LEASE_TTL)
        )
        if int(renew_result.rowcount or 0) != 1:
            await lease_session.rollback()
            return False
        await lease_session.commit()
        return True


async def heartbeat_project_ledger_lease(*, project_id: str, lease_token: str) -> None:
    while True:
        await asyncio.sleep(PROJECT_LEDGER_LEASE_HEARTBEAT_SECONDS)
        if not await renew_project_ledger_lease(project_id=project_id, lease_token=lease_token):
            logger.warning("Project ledger lease heartbeat lost ownership: project=%s", project_id)
            return


async def release_project_ledger_lease(*, project_id: str, lease_token: str) -> None:
    async with AsyncSessionLocal() as lease_session:
        await lease_session.execute(
            delete(ProjectLedgerSyncLease).where(
                ProjectLedgerSyncLease.project_id == project_id,
                ProjectLedgerSyncLease.lease_token == lease_token,
            )
        )
        await lease_session.commit()


async def wait_for_project_ledger_lease(
    *,
    project_id: str,
    chapter_number: int = 0,
    selected_version_id: Optional[int] = None,
    wait_seconds: float = PROJECT_LEDGER_LEASE_WAIT_SECONDS,
    poll_seconds: float = PROJECT_LEDGER_LEASE_POLL_SECONDS,
) -> Tuple[str, Optional[asyncio.Task[Any]]]:
    """Block until the project ledger lease is acquired or raise TimeoutError."""
    lease_token: Optional[str] = None
    active_ledger: Optional[Dict[str, Any]] = None
    wait_deadline = asyncio.get_running_loop().time() + float(wait_seconds)
    while lease_token is None:
        lease_token, active_ledger = await acquire_project_ledger_lease(
            project_id=project_id,
            chapter_number=chapter_number,
            selected_version_id=selected_version_id,
        )
        if lease_token is not None:
            break
        if asyncio.get_running_loop().time() >= wait_deadline:
            active_chapter = active_ledger.get("chapter_number") if active_ledger else "unknown"
            raise TimeoutError(
                f"等待同项目线索/知识图谱同步超时（活动章节 {active_chapter}）"
            )
        await asyncio.sleep(poll_seconds)
    heartbeat_task = asyncio.create_task(
        heartbeat_project_ledger_lease(project_id=project_id, lease_token=lease_token)
    )
    return lease_token, heartbeat_task


@asynccontextmanager
async def project_ledger_lease(
    project_id: str,
    *,
    chapter_number: int = 0,
    selected_version_id: Optional[int] = None,
    wait_seconds: float = PROJECT_LEDGER_API_WAIT_SECONDS,
) -> AsyncIterator[str]:
    """Context manager for API/read-path ledger sync serialization."""
    lease_token, heartbeat_task = await wait_for_project_ledger_lease(
        project_id=project_id,
        chapter_number=chapter_number,
        selected_version_id=selected_version_id,
        wait_seconds=wait_seconds,
    )
    try:
        yield lease_token
    finally:
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
        try:
            await release_project_ledger_lease(project_id=project_id, lease_token=lease_token)
        except Exception:
            logger.exception("Release project ledger lease failed: project=%s", project_id)

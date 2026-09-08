"""Bounded, per-worker round-robin maintenance scans (not job claim ordering)."""
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.agent import AgentJob


@dataclass
class ContinuationScanCursor:
    last_id: str | None = None


async def scan_candidates(session: AsyncSession, statement, *, limit: int,
                          cursor: ContinuationScanCursor | None):
    # Maintenance eligibility is re-evaluated for every page. UUID ordering
    # avoids timestamp precision differences across SQLite/MySQL and survives
    # deletion of the previous anchor. Job claiming keeps its existing order.
    ordered = statement.order_by(None).order_by(AgentJob.id)
    if cursor is None:
        rows = list((await session.execute(ordered.limit(limit))).all())
        cursor = None
        return rows
    query = ordered.where(AgentJob.id > cursor.last_id) if cursor.last_id else ordered
    rows = list((await session.execute(query.limit(limit))).all())
    if not rows and cursor.last_id is not None:
        rows = list((await session.execute(ordered.limit(limit))).all())
    cursor.last_id = rows[-1][0] if len(rows) == limit else None
    return rows

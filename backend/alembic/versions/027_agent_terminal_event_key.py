"""Fence terminal Agent events to one durable record per Run and event type."""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "027_agent_terminal_event_key"
down_revision: Union[str, None] = "026_agent_quality_same_run_fence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "agent_events"
COLUMN = "terminal_key"
INDEX = "uq_agent_event_terminal_key"

def _tables() -> set[str]:
    return set(inspect(op.get_bind()).get_table_names())

def _columns(table: str) -> set[str]:
    return {str(item.get("name")) for item in inspect(op.get_bind()).get_columns(table)}

def _indexes(table: str) -> dict[str, dict]:
    return {str(item.get("name")): item for item in inspect(op.get_bind()).get_indexes(table) if item.get("name")}

def upgrade() -> None:
    if TABLE not in _tables():
        return
    if COLUMN not in _columns(TABLE):
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(length=120), nullable=True))
    if INDEX not in _indexes(TABLE):
        op.create_index(INDEX, TABLE, [COLUMN], unique=True)

def downgrade() -> None:
    if TABLE not in _tables():
        return
    if INDEX in _indexes(TABLE):
        op.drop_index(INDEX, table_name=TABLE)
    if COLUMN in _columns(TABLE):
        op.drop_column(TABLE, COLUMN)

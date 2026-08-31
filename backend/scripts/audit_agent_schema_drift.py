"""Audit the P0-B Agent relational schema baseline without broad project drift noise.

The project has historical Alembic differences outside the Agent Catalog / Quality /
Lineage slice.  This script intentionally filters Alembic autogeneration to the nine
P0-B tables so a zero result is a precise, machine-readable proof for this scope.
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any
import sys

# Direct ``python scripts/audit_agent_schema_drift.py`` execution sets sys.path to
# ``backend/scripts``.  Add the backend package root so the application models load
# exactly as they do under pytest and ``python -m``.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Column, MetaData, String, Table, create_engine
from sqlalchemy.engine import URL, make_url

from app.core.config import settings
from app.db.base import Base
import app.models  # noqa: F401  # Register all model metadata before comparison.

P0_B_TABLES = (
    "agent_catalog_releases",
    "agent_provider_releases",
    "agent_capability_definitions",
    "agent_run_capability_snapshots",
    "agent_capability_executions",
    "agent_quality_results",
    "agent_quality_findings",
    "agent_quality_gates",
    "agent_artifact_lineages",
)
P0_B_TABLE_SET = frozenset(P0_B_TABLES)


def _p0_b_metadata() -> MetaData:
    """Copy only P0-B tables and minimal FK targets to avoid unrelated metadata cycles."""
    metadata = MetaData()
    for name in ("agent_runs", "agent_run_steps", "agent_artifact_refs"):
        Table(name, metadata, Column("id", String(36), primary_key=True))
    for name in P0_B_TABLES:
        Base.metadata.tables[name].to_metadata(metadata)
    return metadata


def _synchronous_url(database_url: str) -> URL:
    """Convert configured async SQLAlchemy driver URLs for local inspection."""
    url = make_url(database_url)
    driver = url.drivername
    replacements = {
        "sqlite+aiosqlite": "sqlite",
        "postgresql+asyncpg": "postgresql+psycopg",
        "mysql+aiomysql": "mysql+pymysql",
    }
    return url.set(drivername=replacements.get(driver, driver))


def _belongs_to_scope(object_: Any, type_: str) -> bool:
    if type_ == "table":
        return getattr(object_, "name", None) in P0_B_TABLE_SET
    table = getattr(object_, "table", None)
    if table is None and type_ == "foreign_key_constraint":
        columns = list(getattr(object_, "columns", ()) or ())
        table = columns[0].table if columns else None
    return getattr(table, "name", None) in P0_B_TABLE_SET


def _include_object(object_: Any, name: str | None, type_: str, reflected: bool, compare_to: Any) -> bool:
    del name, reflected, compare_to
    return _belongs_to_scope(object_, type_)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "to_diff_tuple"):
        return _jsonable(value.to_diff_tuple())
    return str(value)


def _describe_diff(diff: Any) -> dict[str, Any]:
    return {"diff": _jsonable(diff), "rendered": str(diff)}


def audit_p0_b_schema_drift(database_url: str) -> dict[str, Any]:
    """Return only the selected Agent relational metadata/database differences."""
    metadata = _p0_b_metadata()
    engine = create_engine(_synchronous_url(database_url))
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(
                connection=connection,
                opts={
                    "target_metadata": metadata,
                    "include_object": _include_object,
                    "compare_type": True,
                    "compare_server_default": True,
                },
            )
            differences = compare_metadata(context, metadata)
    finally:
        engine.dispose()

    return {
        "schema": "xuanqiong.agent-schema-drift.v1",
        "scope": "P0-B Agent Catalog / Resolver Snapshot / Quality / Lineage",
        "tables": list(P0_B_TABLES),
        "drift_count": len(differences),
        "clean": not differences,
        "drift": [_describe_diff(diff) for diff in differences],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=settings.sqlalchemy_database_uri,
        help="SQLAlchemy database URL; defaults to the configured application database.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON (the default output format).")
    parser.add_argument("--output", type=Path, help="Optional path to write the JSON report.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = audit_p0_b_schema_drift(args.database_url)
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(f"{payload}\n", encoding="utf-8")
    print(payload)
    return 0 if report["clean"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

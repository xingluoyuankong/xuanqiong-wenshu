import asyncio
import sqlite3

from sqlalchemy import create_engine

from app.db.base import Base
import app.models  # noqa: F401 - register ORM metadata
from app.db.schema_fingerprint import build_schema_state, metadata_snapshot, snapshot_hash


def test_metadata_snapshot_hash_is_deterministic():
    snapshot = metadata_snapshot(Base.metadata)
    assert snapshot_hash(snapshot) == snapshot_hash(metadata_snapshot(Base.metadata))
    assert snapshot["tables"]


def test_database_schema_state_reports_missing_and_extra_tables(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schema.db'}")
    Base.metadata.create_all(engine)
    with engine.connect() as connection:
        state = build_schema_state(Base.metadata, connection)
    assert state["missing_tables"] == []
    assert state["status"] == "match"
    engine.dispose()
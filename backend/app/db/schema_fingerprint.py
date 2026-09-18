# AIMETA P=数据库schema指纹_ORM与实际表结构对照|R=版本观测_drift摘要|NR=不执行迁移|E=metadata_fingerprint_database_snapshot|X=internal|A=schema audit|D=sqlalchemy|S=db|RD=./README.ai
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.sql.schema import MetaData


def metadata_snapshot(metadata: MetaData) -> dict[str, Any]:
    tables: dict[str, Any] = {}
    for table_name in sorted(metadata.tables):
        table = metadata.tables[table_name]
        tables[table_name] = {
            "columns": [
                {
                    "name": column.name,
                    "type": str(column.type),
                    "nullable": bool(column.nullable),
                    "primary_key": bool(column.primary_key),
                }
                for column in sorted(table.columns, key=lambda item: item.name)
            ],
        }
    return {"tables": tables}


def database_snapshot(connection: Any) -> dict[str, Any]:
    inspector = inspect(connection)
    tables: dict[str, Any] = {}
    for table_name in sorted(inspector.get_table_names()):
        if table_name.startswith("sqlite_"):
            continue
        columns = inspector.get_columns(table_name)
        tables[table_name] = {
            "columns": [
                {
                    "name": column["name"],
                    "type": str(column.get("type")),
                    "nullable": bool(column.get("nullable", True)),
                    "primary_key": bool(column.get("primary_key", False)),
                }
                for column in sorted(columns, key=lambda item: item["name"])
            ],
        }
    return {"tables": tables}


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def schema_diff(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    expected_tables = set(expected.get("tables", {}))
    actual_tables = set(actual.get("tables", {}))
    missing_tables = sorted(expected_tables - actual_tables)
    extra_tables = sorted(actual_tables - expected_tables)
    missing_columns: dict[str, list[str]] = {}
    extra_columns: dict[str, list[str]] = {}
    for table_name in sorted(expected_tables & actual_tables):
        expected_columns = {item["name"] for item in expected["tables"][table_name]["columns"]}
        actual_columns = {item["name"] for item in actual["tables"][table_name]["columns"]}
        if expected_columns - actual_columns:
            missing_columns[table_name] = sorted(expected_columns - actual_columns)
        if actual_columns - expected_columns:
            extra_columns[table_name] = sorted(actual_columns - expected_columns)
    return {
        "missing_tables": missing_tables,
        "extra_tables": extra_tables,
        "missing_columns": missing_columns,
        "extra_columns": extra_columns,
    }


def build_schema_state(metadata: MetaData, connection: Any) -> dict[str, Any]:
    expected = metadata_snapshot(metadata)
    actual = database_snapshot(connection)
    diff = schema_diff(expected, actual)
    return {
        "version": 1,
        "orm_metadata_sha256": snapshot_hash(expected),
        "database_schema_sha256": snapshot_hash(actual),
        "expected_table_count": len(expected["tables"]),
        "actual_table_count": len(actual["tables"]),
        "status": "match" if not any(diff.values()) else "drift",
        **diff,
    }
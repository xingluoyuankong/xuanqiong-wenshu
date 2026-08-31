from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


def _load_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "audit_dialogue_state_marker_categories.py"
    spec = importlib.util.spec_from_file_location("dialogue_state_marker_categories_test", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_marker_category_audit_is_redacted_and_tracks_three_categories(tmp_path):
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE chapter_versions (content TEXT, metadata TEXT)")
    content = "“你必须选择。”她决定交换名单，发现门外的危险已经逼近。" * 80
    connection.execute(
        "INSERT INTO chapter_versions VALUES (?, ?)",
        (content, json.dumps({"chapter_mission": {"dialogue_strategy": {"purpose": ["试探"]}}}, ensure_ascii=False)),
    )
    connection.commit()
    connection.close()

    result = _load_module().audit_database(database)
    assert result["eligible_rows"] == 1
    assert result["expected_dialogue_true_rows"] == 1
    assert result["expected_dialogue_false_rows"] == 0
    assert set(result["category_marker_counts"]) == {"choice", "external_pressure", "revelation"}
    assert result["redaction"]["content_emitted"] is False
    assert result["redaction"]["marker_examples_emitted"] is False
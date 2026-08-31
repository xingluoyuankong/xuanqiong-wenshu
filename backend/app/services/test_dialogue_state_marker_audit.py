from __future__ import annotations

import json
import sqlite3

from scripts.audit_dialogue_state_markers import audit_database


def test_dialogue_marker_audit_is_redacted_and_tracks_expected_dialogue(tmp_path):
    database = tmp_path / "audit.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE chapter_versions (content TEXT, metadata TEXT)")
    connection.executemany(
        "INSERT INTO chapter_versions(content, metadata) VALUES (?, ?)",
        [
            ("“逼问”" + "动作" * 500, json.dumps({"chapter_mission": {"dialogue_strategy": {"purpose": ["试探"]}}})),
            ("平静叙述" * 500, json.dumps({"chapter_mission": {"scene_list": []}})),
            ("短文", json.dumps({"chapter_mission": {"dialogue_strategy": {"purpose": ["试探"]}}})),
        ],
    )
    connection.commit()
    connection.close()

    result = audit_database(database)
    assert result["source_rows"] == 3
    assert result["eligible_rows"] == 2
    assert result["expected_dialogue_observed_rows"] == 2
    assert result["expected_dialogue_true_rows"] == 1
    assert result["expected_dialogue_false_rows"] == 1
    assert set(result) >= {"source_rows", "eligible_rows", "state_change_markers"}
    assert all(isinstance(value, (int, float, type(None), dict, str)) for value in result.values())

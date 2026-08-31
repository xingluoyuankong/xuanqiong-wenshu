from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path


def _load_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "audit_historical_scorer_delta.py"
    spec = importlib.util.spec_from_file_location("historical_scorer_delta_test", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_historical_scorer_delta_rescores_without_emitting_prose(tmp_path):
    database = tmp_path / "history.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE chapter_versions (id INTEGER, content TEXT, metadata TEXT)")
    prose = "顾沉推开门，发现账簿被换成空白纸。门外脚步停在第三阶，他决定带着钥匙离开。" * 40
    connection.execute(
        "INSERT INTO chapter_versions VALUES (?, ?, ?)",
        (1, prose, json.dumps({"chapter_mission": {"scene_list": [{"goal": "找账簿", "conflict": "门卫阻拦", "turn": "账簿被换", "end_hook": "脚步停下"}]}, "quality_metrics": {"target_word_count": 1200, "min_word_count": 900}}, ensure_ascii=False)),
    )
    connection.commit(); connection.close()

    module = _load_module()
    payload = module.audit(database)
    rendered = json.dumps(payload, ensure_ascii=False)
    assert payload["kind"] == "historical_scorer_behavior_delta_not_quality_ground_truth"
    assert payload["source_rows"] == payload["comparable_rows"] == 1
    assert payload["failed_rows"] == []
    assert prose not in rendered
    assert len(payload["rows"][0]["content_sha256"]) == 64

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path


def _load_module():
    script = Path(__file__).resolve().parents[2] / "scripts" / "quality_metric_corpus_calibration.py"
    spec = importlib.util.spec_from_file_location("quality_metric_corpus_calibration_test", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_quality_metric_corpus_calibration_tracks_current_keyword_only_contract(tmp_path):
    database = tmp_path / "corpus.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE chapter_versions (content TEXT)")
    connection.execute(
        "INSERT INTO chapter_versions VALUES (?)",
        ("林七推开门，发现账簿被换成空白纸。\n\n‘谁拿走了它？’她问。" * 30,),
    )
    connection.commit()
    connection.close()

    payload = _load_module().run(database)
    assert payload["record_count"] == 1
    assert payload["redaction"]["content_emitted"] is False
    assert payload["E04_content_balance"]["dialogue_ratio"]["p50"] is not None

def test_quality_metric_corpus_calibration_passes_mission_focus_names_to_balance(tmp_path):
    database = tmp_path / "corpus-with-metadata.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE chapter_versions (content TEXT, metadata TEXT)")
    paragraph = "顾棠推开门，转身握住门闩，决定先检查账簿。"
    metadata = '{"chapter_mission":{"focus_characters":["顾棠"]}}'
    connection.execute(
        "INSERT INTO chapter_versions VALUES (?, ?)",
        (paragraph, metadata),
    )
    connection.commit()
    connection.close()

    module = _load_module()
    payload = module.run(database)
    expected = module.PipelineOrchestrator._evaluate_content_balance(
        [paragraph],
        word_count=module.PipelineOrchestrator._count_words(paragraph),
        character_names=["顾棠"],
    )

    assert payload["E04_content_balance"]["action_ratio"]["p50"] == expected["action_ratio"]
    assert expected["action_ratio"] == 1.0


def test_quality_metric_corpus_calibration_tolerates_missing_column_and_bad_metadata(tmp_path):
    legacy_database = tmp_path / "legacy.db"
    connection = sqlite3.connect(legacy_database)
    connection.execute("CREATE TABLE chapter_versions (content TEXT)")
    connection.execute("INSERT INTO chapter_versions VALUES (?)", ("顾棠推开门。",))
    connection.commit()
    connection.close()

    bad_metadata_database = tmp_path / "bad-metadata.db"
    connection = sqlite3.connect(bad_metadata_database)
    connection.execute("CREATE TABLE chapter_versions (content TEXT, metadata TEXT)")
    connection.execute(
        "INSERT INTO chapter_versions VALUES (?, ?)",
        ("顾棠推开门。", "不是 JSON"),
    )
    connection.commit()
    connection.close()

    legacy_payload = _load_module().run(legacy_database)
    bad_metadata_payload = _load_module().run(bad_metadata_database)

    assert legacy_payload["record_count"] == 1
    assert bad_metadata_payload["record_count"] == 1
    assert bad_metadata_payload["redaction"]["content_emitted"] is False


from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.services.chapter_writing_contract_snapshot import (
    ContractSnapshotError,
    load_chapter_writing_contract,
)


def test_default_contract_is_a_versioned_read_only_snapshot():
    snapshot = load_chapter_writing_contract()

    assert snapshot.contract_id == "chapter_writing_contract"
    assert snapshot.version == "1.0.0"
    assert snapshot.source_path.name == "chapter_writing_contract.v1.md"
    assert snapshot.content
    assert snapshot.sha256 == "37aef0f2ec3d9c0f1c63da1a58a4d489f03db7c4cf124b39f262c0fb5860ab3c"
    assert snapshot.sha256 == hashlib.sha256(snapshot.content.encode("utf-8")).hexdigest()
    assert snapshot.metadata["kind"] == "code-layer-writing-contract"
    assert snapshot.metadata["database_write_policy"] == "read-only"


def test_snapshot_contains_the_code_layer_rules_that_are_under_version_control():
    content = load_chapter_writing_contract().content

    required_rules = (
        "CHAPTER_DRAFT_CONTRACT",
        "target_chars",
        "minimum_chars",
        "recommended_scene_count",
        "Every 900-1500 chars should contain a concrete state change",
        "场景衔接规则",
        "对话硬要求",
    )
    for rule in required_rules:
        assert rule in content


def test_explicit_snapshot_path_is_read_without_database_or_mutation(tmp_path: Path):
    contract_path = tmp_path / "contract.md"
    contract_path.write_text(
        "---\n"
        "contract_id: test_contract\n"
        "version: 9.2.1\n"
        "kind: code-layer-writing-contract\n"
        "---\n"
        "A read-only test contract.\n",
        encoding="utf-8",
    )
    before = contract_path.read_bytes()

    snapshot = load_chapter_writing_contract(contract_path)

    assert snapshot.contract_id == "test_contract"
    assert snapshot.version == "9.2.1"
    assert snapshot.content == "A read-only test contract.\n"
    assert contract_path.read_bytes() == before


def test_missing_or_malformed_contract_metadata_fails_closed(tmp_path: Path):
    missing = tmp_path / "missing.md"
    with pytest.raises(FileNotFoundError):
        load_chapter_writing_contract(missing)

    malformed = tmp_path / "malformed.md"
    malformed.write_text("# no version metadata\n", encoding="utf-8")
    with pytest.raises(ContractSnapshotError, match="front matter"):
        load_chapter_writing_contract(malformed)


def test_contract_version_must_be_semver_like(tmp_path: Path):
    contract_path = tmp_path / "bad-version.md"
    contract_path.write_text(
        "---\n"
        "contract_id: bad\n"
        "version: latest\n"
        "kind: code-layer-writing-contract\n"
        "---\n"
        "content\n",
        encoding="utf-8",
    )

    with pytest.raises(ContractSnapshotError, match="version"):
        load_chapter_writing_contract(contract_path)

def test_loader_rejects_a_database_prompt_as_a_contract(tmp_path: Path):
    contract_path = tmp_path / "database-prompt.md"
    contract_path.write_text(
        "---\n"
        "contract_id: writing_v2\n"
        "version: 1.0.0\n"
        "kind: database-prompt\n"
        "---\n"
        "content\n",
        encoding="utf-8",
    )

    with pytest.raises(ContractSnapshotError, match="kind"):
        load_chapter_writing_contract(contract_path)


def test_nested_snapshot_is_not_a_root_level_database_prompt_seed():
    snapshot = load_chapter_writing_contract()
    prompts_root = snapshot.source_path.parents[1]

    assert snapshot.source_path.parent.name == "contracts"
    assert snapshot.source_path not in set(prompts_root.glob("*.md"))


def test_pipeline_exposes_contract_snapshot_metadata_without_db_write():
    from app.services.pipeline_orchestrator import PipelineOrchestrator
    metadata = PipelineOrchestrator._writing_contract_runtime_metadata()
    assert metadata["contract_id"] == "chapter_writing_contract"
    assert metadata["version"] == "1.0.0"
    assert len(metadata["sha256"]) == 64

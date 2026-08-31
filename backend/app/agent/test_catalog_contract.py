from __future__ import annotations

import json
from pathlib import Path

from app.agent.catalog_contract import CATALOG_CONTRACT_ID, CATALOG_CONTRACT_SCHEMA_VERSION, build_catalog_contract
from app.agent.registry import DEFAULT_TOOL_PROVIDER_HEALTH, DEFAULT_TOOL_REGISTRY


_CONTRACT_PATH = Path(__file__).with_name("catalog_contract_v1.json")


def _frozen_contract() -> dict:
    return json.loads(_CONTRACT_PATH.read_text(encoding="utf-8"))


def test_default_registry_matches_reviewed_catalog_contract_baseline():
    actual = build_catalog_contract(DEFAULT_TOOL_REGISTRY, DEFAULT_TOOL_PROVIDER_HEALTH)
    assert actual == _frozen_contract()


def test_catalog_contract_is_complete_and_does_not_store_provider_paths():
    contract = _frozen_contract()
    assert contract["schema_version"] == CATALOG_CONTRACT_SCHEMA_VERSION
    assert contract["catalog_id"] == CATALOG_CONTRACT_ID
    assert contract["tool_count"] == 19
    assert len(contract["tools"]) == 19
    assert [item["name"] for item in contract["tools"]] == sorted(item["name"] for item in contract["tools"])
    assert all("path" not in item for item in contract["tools"])
    by_name = {item["name"]: item for item in contract["tools"]}
    assert by_name["project.context"]["provider_id"] == "project-read"
    assert by_name["knowledge.inspect"]["provider_id"] == "memory-read"
    assert by_name["foreshadowing.inspect"]["provider_id"] == "foreshadowing-read"
    assert by_name["chapter.inspect"]["provider_id"] == "structure-read"
    assert by_name["chapter.version.diff"]["provider_id"] == "structure-read"
    assert by_name["quality.finding.inspect"] == {
        **by_name["quality.finding.inspect"],
        "risk_level": "read",
        "requires_confirmation": False,
        "project_scoped": True,
        "source": "legacy",
        "provider_id": None,
        "input_schema": {
            "type": "object",
            "required": ["quality_finding_refs"],
            "properties": {"quality_finding_refs": {"type": "array"}},
            "additionalProperties": False,
        },
        "context_bindings": [
            {
                "source": "selected_quality_finding_refs",
                "argument_name": "quality_finding_refs",
                "required": True,
            }
        ],
    }
    assert by_name["entity.inspect"] == {
        **by_name["entity.inspect"],
        "risk_level": "read",
        "requires_confirmation": False,
        "project_scoped": True,
        "provider_id": "project-read",
        "provider_version": "1.0.0",
        "source": "builtin",
        "input_schema": {
            "type": "object",
            "required": ["entity_refs"],
            "properties": {"entity_refs": {"type": "array"}},
            "additionalProperties": False,
        },
        "context_bindings": [
            {
                "source": "selected_entity_refs",
                "argument_name": "entity_refs",
                "required": True,
            }
        ],
    }
    assert by_name["chapter.generate"] == {
        **by_name["chapter.generate"],
        "risk_level": "write",
        "requires_confirmation": True,
        "supports_stream": True,
        "timeout_seconds": 300,
        "source": "legacy",
        "provider_id": None,
    }

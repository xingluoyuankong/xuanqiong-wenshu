from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest


_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "real_asgi_three_candidate_smoke.py"


def _summarizer():
    tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"), filename=str(_SCRIPT))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in {"_metrics", "summarize_candidates"}]
    constants = [node for node in tree.body if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "METRIC_KEYS" for target in node.targets)]
    imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom)) and any(alias.name in {"hashlib", "json"} for alias in node.names)]
    namespace: dict[str, object] = {"Any": object}
    exec(compile(ast.Module(body=[*imports, *constants, *selected], type_ignores=[]), str(_SCRIPT), "exec"), namespace)
    return namespace["summarize_candidates"]


def test_e06_summary_requires_three_candidates_two_metric_dimensions_and_score_margin():
    summarize = _summarizer()
    versions = [
        {"id": 1, "version_label": "v1", "content": "a", "metadata": {"quality_metrics": {"score": 100, "word_count": 1000, "dialogue_ratio": 0.2}, "ai_review": {"heuristic_score": 100, "heuristic_rank": 3}}},
        {"id": 2, "version_label": "v2", "content": "b", "metadata": {"quality_metrics": {"score": 500, "word_count": 1200, "dialogue_ratio": 0.4}, "ai_review": {"is_best": True, "heuristic_best": True, "heuristic_score": 500, "heuristic_rank": 1}}},
        {"id": 3, "version_label": "v3", "content": "c", "metadata": {"quality_metrics": {"score": 150, "word_count": 1100, "dialogue_ratio": 0.3}, "ai_review": {"heuristic_score": 150, "heuristic_rank": 2}}},
    ]
    result = summarize(versions=versions, selected_version_id=2)
    assert result["e06_candidate_count_passed"] is True
    assert result["e06_two_dimension_diversity_passed"] is True
    assert result["selected_score_margin_over_best_unselected"] == 350
    assert result["e06_score_margin_passed"] is True
    assert result["records"][1]["ai_selected"] is True
    assert result["records"][1]["heuristic_best"] is True
    assert result["records"][1]["heuristic_rank"] == 1


def test_e06_summary_rejects_identical_candidates_or_small_selected_margin():
    summarize = _summarizer()
    same = [{"id": index, "content": "same", "metadata": {"quality_metrics": {"score": 500, "word_count": 1200}}} for index in range(1, 4)]
    result = summarize(versions=same, selected_version_id=1)
    assert result["e06_two_dimension_diversity_passed"] is False
    assert result["e06_score_margin_passed"] is False

def test_e06_metrics_merge_preserves_full_guard_score():
    tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"), filename=str(_SCRIPT))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_metrics"]
    namespace: dict[str, object] = {"Any": object}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(_SCRIPT), "exec"), namespace)
    assert namespace["_metrics"]({
        "story_progression_guard": {"score": 1022, "reversal_signal_count": 1},
        "quality_metrics": {"word_count": 1200},
    })["score"] == 1022



def test_e06_metrics_prefers_full_guard_score_over_stale_compact_score():
    tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"), filename=str(_SCRIPT))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_metrics"]
    namespace: dict[str, object] = {"Any": object}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(_SCRIPT), "exec"), namespace)
    metrics = namespace["_metrics"]({
        "story_progression_guard": {"score": 1022, "reversal_signal_count": 1},
        "quality_metrics": {"score": 77, "word_count": 1200, "reversal_signal_count": 9},
    })
    assert metrics["score"] == 1022
    assert metrics["word_count"] == 1200
    assert metrics["reversal_signal_count"] == 9


def test_e06_metrics_reverse_contract_detects_compact_score_override():
    source = _SCRIPT.read_text(encoding="utf-8")
    assert 'if key == "score" or key not in merged:' in source
    sabotaged = source.replace('if key == "score" or key not in merged:', 'if key not in merged:', 1)
    with pytest.raises(AssertionError):
        assert 'if key == "score" or key not in merged:' in sabotaged

def _output_path_resolver():
    tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"), filename=str(_SCRIPT))
    selected = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "resolve_e06_output_path"]
    assert len(selected) == 1
    namespace: dict[str, object] = {
        "ROOT": Path("/e06-project"),
        "Path": Path,
        "os": SimpleNamespace(getenv=lambda _name: None),
        "time": SimpleNamespace(time_ns=lambda: 123456789),
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(_SCRIPT), "exec"), namespace)
    return namespace["resolve_e06_output_path"]


def test_e06_output_path_is_unique_contained_and_never_overwrites(monkeypatch, tmp_path):
    resolver = _output_path_resolver()
    monkeypatch.setitem(resolver.__globals__, "ROOT", tmp_path)
    path = resolver()
    assert path == (tmp_path / "output" / "e06-three-candidate-asgi-123456789.json").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("old evidence", encoding="utf-8")
    with pytest.raises(FileExistsError):
        resolver(str(path))
    with pytest.raises(ValueError):
        resolver("../outside.json")


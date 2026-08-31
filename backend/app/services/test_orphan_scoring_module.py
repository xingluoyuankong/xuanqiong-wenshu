import importlib


def test_orphan_scoring_module_is_removed():
    try:
        importlib.import_module("app.services.story_quality_scoring")
    except ImportError:
        return
    raise AssertionError("orphan scoring module must not remain importable")

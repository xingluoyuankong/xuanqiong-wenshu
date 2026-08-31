from __future__ import annotations
import importlib.util
from pathlib import Path

def load_t15_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "t15_cross_genre_marker_audit.py"
    spec = importlib.util.spec_from_file_location("t15_cross_genre_marker_audit", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module
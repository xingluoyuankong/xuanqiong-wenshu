import json
import subprocess
import sys
from pathlib import Path


def test_mysql_fk_plan_is_read_only_and_reports_cycles():
    root = Path(__file__).resolve().parents[3]
    script = root / "scripts/plan_mysql_fk_order.py"
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    assert payload["execute"] is False
    assert payload["connected"] is False
    assert payload["writes_performed"] is False
    assert payload["table_count"] == 57
    assert payload["edge_count"] == 76
    assert payload["status"] == "BLOCKED_BY_FK_CYCLES"
    cycles = {frozenset(item) for item in payload["blocked_cycles"]}
    assert frozenset({"chapters", "chapter_versions"}) in cycles
    assert frozenset({"timeline_events"}) in cycles
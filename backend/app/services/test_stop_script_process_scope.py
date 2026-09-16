"""Regression tests for stop.ps1 process ownership without touching real services."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "stop.ps1"


def _run_probe(tmp_path: Path, source: str, processes: dict[int, dict]) -> dict[str, bool]:
    fixture = tmp_path / "processes.json"
    fixture.write_text(json.dumps({str(k): v for k, v in processes.items()}, ensure_ascii=False), encoding="utf-8")
    start = source.index('function Test-RepoOwnedProcess {')
    end = source.index('function Get-RepoRuntimeProcesses {', start)
    prefix = source[start:end]
    harness = r'''
$processMap = Get-Content -LiteralPath $FixturePath -Raw | ConvertFrom-Json
function Get-CimInstance {
    param($ClassName, $Filter, $ErrorAction)
    if ($ClassName -ne 'Win32_Process' -or $Filter -notmatch '^ProcessId = (\d+)$') { throw "unexpected query" }
    $id = $Matches[1]
    $entry = $processMap.PSObject.Properties | Where-Object Name -eq $id | Select-Object -First 1
    if (-not $entry) { throw "missing process $id" }
    $row = $entry.Value
    [pscustomobject]@{ ProcessId=[int]$id; ParentProcessId=[int]$row.parent; ExecutablePath=[string]$row.path; CommandLine=[string]$row.command }
}
$result = [ordered]@{
  repo_child = Test-RepoOwnedProcess -ProcessId 100 -RepoPath 'D:\小说写作\xuanqiong-wenshu'
  foreign_child = Test-RepoOwnedProcess -ProcessId 200 -RepoPath 'D:\小说写作\xuanqiong-wenshu'
  cycle = Test-RepoOwnedProcess -ProcessId 300 -RepoPath 'D:\小说写作\xuanqiong-wenshu'
}
Write-Output ("OWNERSHIP_JSON=" + ($result | ConvertTo-Json -Compress))
'''
    probe = tmp_path / "probe.ps1"
    probe.write_text(
        "param([string]$FixturePath)\n"
        "$repoServicePattern = 'xuanqiong-wenshu[\\/](backend|frontend)'\n"
        + prefix + harness,
        encoding="utf-8",
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(probe), "-FixturePath", str(fixture)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    marker = next(line for line in result.stdout.splitlines() if line.startswith("OWNERSHIP_JSON="))
    return json.loads(marker.split("=", 1)[1])


def _fixtures() -> dict[int, dict]:
    return {
        100: {"parent": 101, "path": r"G:\python\3.11\python.exe", "command": "python -m uvicorn app.main:app"},
        101: {"parent": 1, "path": r"D:\小说写作\xuanqiong-wenshu\backend\.venv\Scripts\python.exe", "command": "python -m uvicorn app.main:app"},
        200: {"parent": 201, "path": r"G:\python\3.11\python.exe", "command": "python -m uvicorn other.app"},
        201: {"parent": 1, "path": r"C:\Python\python.exe", "command": "python worker.py"},
        300: {"parent": 301, "path": r"G:\python\3.11\python.exe", "command": "python app.py"},
        301: {"parent": 300, "path": r"C:\Python\python.exe", "command": "python app.py"},
    }


def test_stop_script_recognizes_bounded_repo_parent_chain(tmp_path):
    assert _run_probe(tmp_path, SCRIPT.read_text(encoding="utf-8"), _fixtures()) == {
        "repo_child": True, "foreign_child": False, "cycle": False,
    }


def test_stop_script_detects_removed_parent_walk(tmp_path):
    original = SCRIPT.read_text(encoding="utf-8")
    mutated = original.replace("$currentId = $parentId", "return $false", 1)
    assert mutated != original
    with pytest.raises(AssertionError):
        assert _run_probe(tmp_path, mutated, _fixtures()) == {
            "repo_child": True, "foreign_child": False, "cycle": False,
        }

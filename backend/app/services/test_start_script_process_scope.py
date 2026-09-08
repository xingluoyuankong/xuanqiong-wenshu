"""Execute start.ps1 with process/network stubs; never start/stop real services.

Mutation checks run only temporary script copies through the same stubs. Each
assertion below inspects executed effects, not the presence of source strings.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "start.ps1"

HARNESS = r'''
param([string]$Target, [string]$Trace, [string]$Scenario)
$ErrorActionPreference = 'Stop'
$global:scenario = $Scenario
$global:tracePath = $Trace
$global:started = @{}
$global:inspections = 0
$global:cleanupPhase = $false
$global:descendants = @{}
$global:treeMode = $Scenario.StartsWith('tree_')
$global:LASTEXITCODE = 0
function Record([string]$Kind, $Data) {
    @{kind=$Kind; data=$Data} | ConvertTo-Json -Compress -Depth 8 |
        Add-Content -LiteralPath $global:tracePath -Encoding utf8
}
function Get-NetTCPConnection {
    param($State, $LocalPort, $ErrorAction)
    $global:inspections++
    Record 'inspect' @{state=$State; port=$LocalPort}
    if ($global:scenario -in @('netstat_conflict','inspection_failure')) { throw 'CIM unavailable' }
    $back = $global:scenario -in @('healthy','healthy_mysql','tree_frontend','backend_only','backend_only_timeout','backend_conflict','backend_503','backend_wrong_app','backend_malformed','backend_unhealthy','frontend_conflict','proxy_conflict','custom_app')
    $front = $global:scenario -in @('healthy','healthy_mysql','frontend_only','frontend_conflict','proxy_conflict','custom_app')
    if ($global:scenario -eq 'port_race' -and $global:inspections -ge 3) { $back = $true }
    if ($back) { [pscustomobject]@{State='Listen'; LocalPort=8013; OwningProcess=41001} }
    if ($front) { [pscustomobject]@{State='Listen'; LocalPort=5174; OwningProcess=41002} }
}
function netstat {
    Record 'netstat' @{}
    if ($global:scenario -eq 'inspection_failure') { $global:LASTEXITCODE=1; return }
    $global:LASTEXITCODE=0
    '  TCP    [::]:8013    [::]:0    LISTENING    41001'
}
function Get-CimInstance {
    param($ClassName, $Filter, $Property, $OperationTimeoutSec, $ErrorAction)
    if ($ClassName -eq 'Win32_Process' -and $Filter -match '^ParentProcessId = (\d+)$') {
        $parentId = [int]$Matches[1]
        Record 'child_query' @{parent=$parentId; timeout=$OperationTimeoutSec; property=@($Property)}
        if (-not $global:treeMode) { return }
        if ($global:scenario -in @('tree_parent_exited','tree_parent_reused','tree_exit_time_unavailable') -and
            -not $global:cleanupPhase) { return }
        foreach ($item in $global:descendants.Values) {
            if ($item.ParentProcessId -ne $parentId) { continue }
            if ($global:scenario -eq 'tree_late_grandchild' -and $item.Id -eq 42102 -and -not $global:cleanupPhase) { continue }
            [pscustomobject]@{ProcessId=$item.Id; ParentProcessId=$item.ParentProcessId; CreationDate=$item.CimBirth}
        }
        if ($global:scenario -eq 'tree_external_lookalike' -and $parentId -eq 42001) {
            # Even a malformed query result naming a different parent is not proof.
            [pscustomobject]@{ProcessId=41999; ParentProcessId=49999; CreationDate=[datetime]'2026-09-06T01:00:01Z'; Name='python.exe'; CommandLine='xuanqiong-wenshu/backend python -m pytest'}
        }
        return
    }
    Record 'forbidden_scan' @{class=$ClassName; filter=$Filter}
    # Deliberately looks repo-owned; the original mutation must still fail.
    [pscustomobject]@{ProcessId=41999; Name='python.exe'; ExecutablePath=(Join-Path (Split-Path $Target) 'backend\.venv\Scripts\python.exe'); CommandLine='xuanqiong-wenshu/backend python -m pytest'}
}
function New-StubProcess {
    param([int]$ProcessId, [datetime]$Birth, [int]$ParentId = 0)
    $proc = [pscustomobject]@{
        Id=$ProcessId; StartTime=$Birth; HasExited=($global:scenario -eq 'early_exit')
        Handle=[IntPtr]$ProcessId; ExitTime=$Birth.AddSeconds(5); ParentProcessId=$ParentId; CimBirth=$Birth
    }
    $proc | Add-Member -MemberType ScriptMethod -Name Refresh -Value {
        if ($global:cleanupPhase -and $this.Id -eq 42001 -and
            $global:scenario -in @('tree_parent_exited','tree_parent_reused','tree_exit_time_unavailable')) {
            $this.HasExited = $true
        }
        if ($global:cleanupPhase -and $this.Id -eq 42101 -and $global:scenario -eq 'tree_child_recycled_cleanup') {
            $this.HasExited = $true
        }
    }
    return $proc
}
function Get-Command {
    param($Name, $ErrorAction)
    Record 'command' @{name=$Name}
    [pscustomobject]@{Source='stub-npm.cmd'}
}
function powershell { Record 'mysql' @{}; throw 'unexpected MySQL helper invocation' }
function Start-Process {
    param($FilePath, $ArgumentList, $WorkingDirectory, $RedirectStandardOutput,
          $RedirectStandardError, $WindowStyle, [switch]$PassThru)
    $role = if ($FilePath -like '*python.exe') { 'backend' } else { 'frontend' }
    Record 'start' @{role=$role; hidden=$WindowStyle; args=@($ArgumentList); passthru=[bool]$PassThru}
    if ($role -eq 'frontend' -and ($global:scenario -eq 'frontend_launch_failure' -or
        ($global:treeMode -and $global:scenario -ne 'tree_frontend'))) {
        $global:cleanupPhase = $true
        throw 'fixture launch failure'
    }
    $idValue = if ($role -eq 'backend') { 42001 } else { 42002 }
    $proc = New-StubProcess -ProcessId $idValue -Birth ([datetime]'2026-09-06T01:00:00Z')
    if ($global:scenario -eq 'tree_root_unpinned') {
        $proc.PSObject.Properties.Remove('Handle')
        $proc | Add-Member -MemberType ScriptProperty -Name Handle -Value { throw 'root handle unavailable' }
    }
    if ($global:scenario -eq 'tree_exit_time_unavailable') {
        $proc.PSObject.Properties.Remove('ExitTime')
        $proc | Add-Member -MemberType ScriptProperty -Name ExitTime -Value { throw 'exit time unavailable' }
    }
    if ($global:treeMode) {
        $global:descendants[42101] = New-StubProcess -ProcessId 42101 -ParentId $idValue -Birth $proc.StartTime.AddSeconds(1)
        $global:descendants[42102] = New-StubProcess -ProcessId 42102 -ParentId 42101 -Birth $proc.StartTime.AddSeconds(2)
        if ($global:scenario -eq 'tree_external_lookalike') {
            # Stale ParentProcessId from a PREVIOUS generation of the wrapper PID.
            $global:descendants[41888] = New-StubProcess -ProcessId 41888 -ParentId $idValue -Birth $proc.StartTime.AddSeconds(-10)
            $global:descendants[41889] = New-StubProcess -ProcessId 41889 -ParentId $idValue -Birth $proc.StartTime.AddSeconds(1)
            $global:descendants[41889].CimBirth = $null
        }
        if ($global:scenario -eq 'tree_parent_reused') {
            # Spawned by the replacement parent, after the pinned parent's exit.
            $global:descendants[41998] = New-StubProcess -ProcessId 41998 -ParentId $idValue -Birth $proc.StartTime.AddSeconds(61)
        }
    }
    $global:started[$role] = $proc
    return $proc
}
function Get-Process {
    param($Id, $ErrorAction)
    Record 'get_process' @{id=$Id}
    if ($global:cleanupPhase -and $Id -eq 42001 -and
        $global:scenario -in @('tree_parent_exited','tree_exit_time_unavailable')) { throw 'original parent exited' }
    foreach ($proc in @($global:started.Values) + @($global:descendants.Values)) {
        if ($proc.Id -ne $Id) { continue }
        if ($global:scenario -eq 'pid_recycled' -or
            ($global:scenario -eq 'tree_child_recycled_discovery' -and $Id -eq 42101) -or
            ($global:cleanupPhase -and $global:scenario -eq 'tree_child_recycled_cleanup' -and $Id -eq 42101) -or
            ($global:cleanupPhase -and $global:scenario -eq 'tree_parent_reused' -and $Id -eq 42001)) {
            return New-StubProcess -ProcessId $Id -Birth $proc.StartTime.AddMinutes(1)
        }
        return $proc
    }
    throw 'unowned lookup'
}
function Stop-Process {
    param($Id, $InputObject, [switch]$Force, $ErrorAction)
    Record 'stop' @{id=$(if ($InputObject) { $InputObject.Id } else { $Id }); input_object=[bool]$InputObject}
}
function Start-Sleep { param($Milliseconds, $Seconds); Record 'sleep' @{ms=$Milliseconds; seconds=$Seconds} }
function Invoke-WebRequest {
    param([switch]$UseBasicParsing, [Parameter(Position=0)]$Uri, $TimeoutSec)
    Record 'http' @{uri=$Uri; timeout=$TimeoutSec}
    $back = "$Uri" -like '*:8013/*'
    $proxy = "$Uri" -like '*:5174/api/health'
    if (($global:scenario -eq 'tree_frontend' -and -not $back) -or $global:scenario -in @('timeout','pid_recycled') -or
        ($global:scenario -eq 'backend_only_timeout' -and -not $back)) { throw 'not ready' }
    if ($back -and $global:scenario -in @('backend_conflict','netstat_conflict')) { throw 'occupied by pytest fixture' }
    if ($back -and $global:scenario -eq 'backend_503') { return [pscustomobject]@{StatusCode=503; Content='{}'} }
    if ($back -and $global:scenario -eq 'backend_malformed') { return [pscustomobject]@{StatusCode=200; Content='not json'} }
    if ($proxy -and $global:scenario -eq 'proxy_conflict') { throw 'proxy unavailable' }
    $appName = if ($global:scenario -eq 'custom_app') { 'Fixture API' } else { '玄穹文枢 API' }
    if ($back -and $global:scenario -eq 'backend_wrong_app') { $appName = 'Other API' }
    $health = if ($global:scenario -eq 'backend_unhealthy') { 'unhealthy' } else { 'healthy' }
    $body = if ($back -or $proxy) {
        @{status=$health; app=$appName; version='1.0.0'} | ConvertTo-Json -Compress
    } elseif ($global:scenario -eq 'frontend_conflict') { '<title>Other application</title>' }
    else { '<!DOCTYPE html><title>玄穹文枢</title><div id="app"></div>' }
    [pscustomobject]@{StatusCode=200; Content=$body}
}
try {
    & $Target
    $code = $LASTEXITCODE
} catch {
    Record 'error' @{message=$_.Exception.Message}
    $code = 1
}
Record 'exit' @{code=$code}
exit $code
'''


def _run(tmp_path, scenario, source=None):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    assert shell, "PowerShell is required for the executable startup contract"
    root = tmp_path / "space 中文 xuanqiong-wenshu"
    root.mkdir()
    (root / "backend").mkdir()
    (root / "frontend").mkdir()
    (root / "backend" / ".env").write_text(
        "DB_PROVIDER=sqlite\n" + ('APP_NAME="Fixture API"\n' if scenario == "custom_app" else ""),
        encoding="utf-8-sig",
    )
    target = root / "start.ps1"
    target.write_text(source if source is not None else SCRIPT.read_text(encoding="utf-8-sig"), encoding="utf-8-sig")
    harness = tmp_path / "stub.ps1"
    harness.write_text(HARNESS, encoding="utf-8-sig")
    trace = tmp_path / "effects.jsonl"
    env = {k: v for k, v in os.environ.items() if not k.startswith("XUANQIONG_WENSHU_") and k not in {"APP_NAME", "DB_PROVIDER"}}
    env["DB_PROVIDER"] = "mysql" if scenario == "healthy_mysql" else "sqlite"
    completed = subprocess.run(
        [shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(harness),
         "-Target", str(target), "-Trace", str(trace), "-Scenario", scenario],
        cwd=tmp_path, env=env, capture_output=True, encoding="utf-8", errors="replace", timeout=20,
    )
    assert trace.exists(), completed.stdout + completed.stderr
    effects = [json.loads(line) for line in trace.read_text(encoding="utf-8-sig").splitlines()]
    return completed, effects


def _events(effects, kind):
    return [e["data"] for e in effects if e["kind"] == kind]


def _assert_scope(effects, stopped=(), owned_ids=(42001, 42002)):
    assert not _events(effects, "forbidden_scan"), "repository-wide process scan executed"
    assert not _events(effects, "mysql"), "unexpected MySQL mutation"
    stops = _events(effects, "stop")
    assert {e["id"] for e in stops} == set(stopped), "unowned process termination or missing owned cleanup"
    assert all(e["input_object"] for e in stops), "cleanup must use a verified process object"
    assert all(e["id"] in set(owned_ids) for e in _events(effects, "get_process"))
    assert all(e["parent"] in set(owned_ids) and e["timeout"] == 2 for e in _events(effects, "child_query"))
    assert all(e["hidden"] == "Hidden" and e["passthru"] for e in _events(effects, "start"))
    assert all(e["timeout"] == 2 for e in _events(effects, "http"))
    assert all(e["ms"] == 500 for e in _events(effects, "sleep"))


@pytest.mark.parametrize("scenario,roles", [
    ("healthy", []), ("healthy_mysql", []), ("custom_app", []), ("backend_only", ["frontend"]),
    ("frontend_only", ["backend"]), ("vacant", ["backend", "frontend"]),
])
def test_start_reuses_only_healthy_services_and_leaves_other_tasks_alone(tmp_path, scenario, roles):
    result, effects = _run(tmp_path, scenario)
    assert result.returncode == 0, result.stdout + result.stderr
    _assert_scope(effects)
    assert [e["role"] for e in _events(effects, "start")] == roles
    for event in _events(effects, "start"):
        if event["role"] == "frontend":
            assert "--strictPort" in event["args"]
    assert "BACKEND_READY=True" in result.stdout
    assert "FRONTEND_PROXY_READY=True" in result.stdout


@pytest.mark.parametrize("scenario", [
    "backend_conflict", "frontend_conflict", "proxy_conflict", "backend_503",
    "backend_wrong_app", "backend_malformed", "backend_unhealthy", "netstat_conflict",
    "inspection_failure", "port_race",
])
def test_start_fails_closed_for_external_occupancy_without_killing(tmp_path, scenario):
    result, effects = _run(tmp_path, scenario)
    assert result.returncode != 0, result.stdout + result.stderr
    _assert_scope(effects)
    assert not _events(effects, "start")
    if scenario == "netstat_conflict":
        assert _events(effects, "netstat")
        assert "41001" in result.stderr or "41001" in result.stdout or any(
            "41001" in e["message"] for e in _events(effects, "error")
        )


@pytest.mark.parametrize("scenario,stopped,sleeps", [
    ("timeout", [42001, 42002], 60), ("pid_recycled", [], 60),
    ("backend_only_timeout", [42002], 60), ("frontend_launch_failure", [42001], 0),
    ("early_exit", [42001, 42002], 0),
])
def test_start_failure_cleanup_is_limited_to_this_invocation(tmp_path, scenario, stopped, sleeps):
    result, effects = _run(tmp_path, scenario)
    assert result.returncode != 0, result.stdout + result.stderr
    _assert_scope(effects, stopped=stopped)
    assert len(_events(effects, "sleep")) == sleeps


@pytest.mark.parametrize("mutation", ["kill_external", "sweep_repo", "visible_window", "pid_reuse", "trust_http_200", "shortened_wait"])
def test_start_contract_rejects_deliberately_broken_temporary_copies(tmp_path, mutation):
    source = SCRIPT.read_text(encoding="utf-8-sig")
    scenario = "healthy"
    check = _assert_scope
    if mutation == "kill_external":
        source = "Stop-Process -Id 41001 -Force\n" + source
    elif mutation == "sweep_repo":
        source = "Get-CimInstance Win32_Process | Out-Null\n" + source
    elif mutation == "visible_window":
        source = source.replace("-WindowStyle Hidden", "-WindowStyle Normal")
        scenario = "vacant"
    elif mutation == "pid_reuse":
        source = source.replace("if ($current.StartTime -eq $entry.StartTime)", "if ($true)")
        scenario = "pid_recycled"
    elif mutation == "shortened_wait":
        source = source.replace("$maxWait = 60", "$maxWait = 1")
        scenario = "timeout"
    else:
        source = source.replace("($health.status -eq 'healthy' -and $health.app -eq $expectedBackendApp)", "$true")
        scenario = "backend_wrong_app"
    assert source != SCRIPT.read_text(encoding="utf-8-sig"), "mutation failed to apply"
    result, effects = _run(tmp_path, scenario, source)
    if mutation == "shortened_wait":
        with pytest.raises(AssertionError):
            assert len(_events(effects, "sleep")) == 60, "startup retry budget shortened"
    elif mutation == "trust_http_200":
        with pytest.raises(AssertionError):
            assert result.returncode != 0, "foreign HTTP 200 was reused"
    else:
        with pytest.raises(AssertionError):
            check(effects)


TREE_CASES = [
    ("tree_chain", [42102, 42101, 42001]),
    ("tree_frontend", [42102, 42101, 42002]),
    ("tree_external_lookalike", [42102, 42101, 42001]),
    ("tree_child_recycled_discovery", [42001]),
    ("tree_child_recycled_cleanup", [42102, 42001]),
    ("tree_parent_exited", [42102, 42101]),
    ("tree_parent_reused", [42102, 42101]),
    ("tree_exit_time_unavailable", []),
    ("tree_root_unpinned", []),
    ("tree_late_grandchild", [42102, 42101, 42001]),
]


def _assert_tree_cleanup(result, effects, expected):
    assert result.returncode != 0, result.stdout + result.stderr
    _assert_scope(effects, stopped=expected, owned_ids=(42001, 42002, 42101, 42102))
    # Order, not just membership: grandchildren must stop before children/roots.
    assert [event["id"] for event in _events(effects, "stop")] == expected
    assert not any(e["id"] in {41888, 41889, 41998, 41999} for e in _events(effects, "get_process"))
    for query in _events(effects, "child_query"):
        assert set(query["property"]) == {"ProcessId", "ParentProcessId", "CreationDate"}


@pytest.mark.parametrize("scenario,expected", TREE_CASES)
def test_start_cleans_only_proven_descendants_child_first(tmp_path, scenario, expected):
    result, effects = _run(tmp_path, scenario)
    _assert_tree_cleanup(result, effects, expected)
    if scenario == "tree_frontend":
        assert len(_events(effects, "sleep")) == 60
        assert [event["role"] for event in _events(effects, "start")] == ["frontend"]
    else:
        assert not _events(effects, "sleep")
    if scenario == "tree_child_recycled_discovery":
        assert not any(e["parent"] == 42101 for e in _events(effects, "child_query"))
    if scenario in {"tree_exit_time_unavailable", "tree_root_unpinned"}:
        assert "unavailable" in result.stdout + result.stderr


@pytest.mark.parametrize("mutation,scenario,expected", [
    ("parent_first", "tree_chain", [42102, 42101, 42001]),
    ("child_pid_reuse", "tree_child_recycled_cleanup", [42102, 42001]),
    ("ignore_parent_exit", "tree_parent_reused", [42102, 42101]),
    ("unfiltered_query", "tree_chain", [42102, 42101, 42001]),
    ("omit_descendants", "tree_chain", [42102, 42101, 42001]),
])
def test_start_descendant_contract_rejects_broken_temporary_copies(tmp_path, mutation, scenario, expected):
    original = SCRIPT.read_text(encoding="utf-8-sig")
    replacements = {
        "parent_first": ("Sort-Object -Property Depth -Descending", "Sort-Object -Property Depth"),
        "child_pid_reuse": ("if ($current.StartTime -eq $entry.StartTime)", "if ($true)"),
        "ignore_parent_exit": ("$upperBound = $parent.Process.ExitTime.ToUniversalTime()", "$upperBound = [datetime]::MaxValue"),
        "unfiltered_query": ('-Filter "ParentProcessId = $($parent.Process.Id)"', '-Filter "Name = \'python.exe\'"'),
        "omit_descendants": ("    Update-OwnedDescendants", "    # Update-OwnedDescendants"),
    }
    before, after = replacements[mutation]
    source = original.replace(before, after)
    assert source != original, "mutation failed to apply"
    result, effects = _run(tmp_path, scenario, source)
    with pytest.raises(AssertionError):
        _assert_tree_cleanup(result, effects, expected)

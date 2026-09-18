$ErrorActionPreference = 'Continue'

[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

# === Timeout Configuration (US-002: bounded startup timeout) ===
$TIMEOUT_SECONDS = 30      # Max wait per service before declaring timeout
$CHECK_INTERVAL_MS = 500   # Health-check polling interval
$CLEANUP_TIMEOUT_MS = 3000 # Max wait for process termination during cleanup
$MAX_WAIT_SECONDS = 60     # Final readiness wait budget

Write-Host "⏱ Startup timeout configured: ${TIMEOUT_SECONDS}s per service" -ForegroundColor DarkGray
Write-Host "⚙️ Cleanup timeout configured: ${CLEANUP_TIMEOUT_MS}ms" -ForegroundColor DarkGray

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = $scriptPath
$logsRoot = Join-Path $repo 'logs'

# === Global job handles for cleanup ===
$global:backendJob = $null
$global:frontendJob = $null

function Get-EnvValue {
    param(
        [string[]]$Names,
        [string]$Default = ''
    )

    foreach ($name in $Names) {
        $value = [Environment]::GetEnvironmentVariable($name)
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value
        }
    }

    return $Default
}

$backendHost = Get-EnvValue -Names @('XUANQIONG_WENSHU_BACKEND_HOST') -Default '127.0.0.1'
$backendPortValue = Get-EnvValue -Names @('XUANQIONG_WENSHU_BACKEND_PORT') -Default '8013'
$frontendHost = Get-EnvValue -Names @('XUANQIONG_WENSHU_FRONTEND_HOST') -Default '127.0.0.1'
$frontendPortValue = Get-EnvValue -Names @('XUANQIONG_WENSHU_FRONTEND_PORT') -Default '5174'
$dbProvider = Get-EnvValue -Names @('DB_PROVIDER') -Default 'mysql'

$env:XUANQIONG_WENSHU_BACKEND_HOST = $backendHost
$env:XUANQIONG_WENSHU_BACKEND_PORT = $backendPortValue
$env:XUANQIONG_WENSHU_FRONTEND_HOST = $frontendHost
$env:XUANQIONG_WENSHU_FRONTEND_PORT = $frontendPortValue

if (-not $env:VITE_API_PROXY_TARGET) { $env:VITE_API_PROXY_TARGET = "http://${backendHost}:${backendPortValue}" }
if ($null -eq $env:VITE_API_BASE_URL) { $env:VITE_API_BASE_URL = '' }
if (-not $env:BROWSER) { $env:BROWSER = 'none' }

[int]$backendPort = $backendPortValue
[int]$frontendPort = $frontendPortValue
$backendBaseUrl = "http://${backendHost}:${backendPort}"
$frontendBaseUrl = "http://${frontendHost}:${frontendPort}"
$frontendProxyHealthUrl = "$frontendBaseUrl/api/health"

$runId = Get-Date -Format 'yyyyMMdd-HHmmss'
$runDir = Join-Path $logsRoot ("run-$runId")
New-Item -ItemType Directory -Path $runDir -Force | Out-Null
Set-Content -Path (Join-Path $logsRoot 'latest-run.txt') -Value $runDir -Encoding UTF8

Write-Host "=== 玄穹文枢启动 ===" -ForegroundColor Cyan
Write-Host "repo: $repo" -ForegroundColor Gray
Write-Host "logs: $runDir" -ForegroundColor Gray
Write-Host "formal backend: $backendBaseUrl" -ForegroundColor Gray
Write-Host "formal frontend: $frontendBaseUrl" -ForegroundColor Gray

$repoServicePattern = 'xuanqiong-wenshu[\\/](backend|frontend)'

# ---------------------------------------------------------------------------
# Helper: repo ownership / port / process helpers
# ---------------------------------------------------------------------------

function Test-RepoOwnedProcess {
    param(
        [int]$ProcessId,
        [string]$RepoPath
    )

    if ($ProcessId -le 0) {
        return $false
    }

    try {
        $procInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction Stop
    } catch {
        return $false
    }

    if ($procInfo.ExecutablePath -and $procInfo.ExecutablePath.StartsWith($RepoPath, [System.StringComparison]::OrdinalIgnoreCase)) {
        return $true
    }

    $commandLine = [string]$procInfo.CommandLine
    if ([string]::IsNullOrWhiteSpace($commandLine)) {
        return $false
    }

    return $commandLine -match $repoServicePattern
}

function Get-RepoRuntimeProcesses {
    param([string]$RepoPath)

    return @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
            $_.ProcessId -gt 0 -and
            $_.Name -match '^(python|node)\.exe$' -and
            (
                ($_.ExecutablePath -and $_.ExecutablePath.StartsWith($RepoPath, [System.StringComparison]::OrdinalIgnoreCase)) -or
                ($_.CommandLine -and $_.CommandLine -match $repoServicePattern)
            )
        } | Select-Object ProcessId, Name, ExecutablePath, CommandLine
    )
}

function Stop-PortProcess {
    param(
        [int]$Port,
        [string]$RepoPath
    )

    $pids = @()
    try {
        $connections = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
        foreach ($conn in $connections) {
            if ($conn.State -eq 'Listen' -and $conn.OwningProcess -gt 0) {
                $pids += $conn.OwningProcess
            }
        }
    } catch {}

    if ($pids.Count -eq 0) {
        try {
            $result = netstat -ano | Select-String ":$Port\s+.*LISTENING"
            foreach ($match in $result) {
                $parts = $match -split '\s+'
                $lastPart = $parts[-1]
                if ($lastPart -match '^\d+$' -and [int]$lastPart -gt 0) {
                    $pids += [int]$lastPart
                }
            }
        } catch {}
    }

    $pids = $pids | Where-Object { $_ -gt 0 } | Select-Object -Unique
    $stoppedCount = 0

    foreach ($procId in $pids) {
        try {
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $procId" -ErrorAction Stop
            if (-not (Test-RepoOwnedProcess -ProcessId $procId -RepoPath $RepoPath)) {
                Write-Host "  skip PID=$procId ($($proc.Name)) on port $Port because it is not repo-owned" -ForegroundColor DarkYellow
                continue
            }
            Write-Host "  stop PID=$procId ($($proc.Name))" -ForegroundColor Yellow
            Stop-Process -Id $procId -Force -ErrorAction Stop
            $stoppedCount += 1
        } catch {
            Write-Host "  failed to stop PID=${procId}: $($_.Exception.Message)" -ForegroundColor DarkGray
        }
    }

    return $stoppedCount
}

# ---------------------------------------------------------------------------
# US-002: wait for a TCP port to enter LISTEN (bounded)
# Returns $true when listening, $false when timeout reached.
# Distinguishes "slow" (port never opened) from "failed" (process died).
# ---------------------------------------------------------------------------
function Wait-ForPortListen {
    param(
        [string]$ServiceName,
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutSec,
        [int]$CheckIntervalMs,
        [object]$Process = $null
    )

    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $lastLog = -1

    while ($sw.Elapsed.TotalSeconds -lt $TimeoutSec) {
        # Fail fast: if we own a process handle and it already exited, stop waiting.
        if ($null -ne $Process -and $Process.Id -gt 0) {
            try {
                $proc = Get-Process -Id $Process.Id -ErrorAction Stop
                if ($proc.HasExited) {
                    Write-Host "`n❌ STARTUP FAILED: ${ServiceName} process exited prematurely (PID=$($Process.Id)) after $([math]::Floor($sw.Elapsed.TotalSeconds))s" -ForegroundColor Red
                    Write-Host "   Service: ${ServiceName} on port ${Port}" -ForegroundColor Yellow
                    return $false
                }
            } catch {
                Write-Host "`n❌ STARTUP FAILED: ${ServiceName} process (PID=$($Process.Id)) no longer exists after $([math]::Floor($sw.Elapsed.TotalSeconds))s" -ForegroundColor Red
                return $false
            }
        }

        $client = $null
        $listening = $false
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $iar = $client.BeginConnect($HostName, $Port, $null, $null)
            $wait = $iar.AsyncWaitHandle.WaitOne([Math]::Min($CheckIntervalMs, 1500), $false)
            if ($wait -and $client.Connected) {
                $listening = $true
            }
            try { $client.EndConnect($iar) } catch {}
        } catch {
            $listening = $false
        } finally {
            if ($null -ne $client) { try { $client.Close(); $client.Dispose() } catch {} }
        }

        if ($listening) {
            Write-Host "  ✓ ${ServiceName} listening on ${HostName}:${Port} after $([math]::Floor($sw.Elapsed.TotalSeconds))s" -ForegroundColor Green
            return $true
        }

        $elapsedInt = [math]::Floor($sw.Elapsed.TotalSeconds)
        if ($elapsedInt % 5 -eq 0 -and $elapsedInt -gt 0 -and $elapsedInt -ne $lastLog) {
            $remaining = [math]::Floor($TimeoutSec - $elapsedInt)
            Write-Host "  ⏱ ${ServiceName} still starting... (${elapsedInt}s elapsed, ${remaining}s remaining)" -ForegroundColor DarkGray
            $lastLog = $elapsedInt
        }

        Start-Sleep -Milliseconds $CheckIntervalMs
    }

    Write-Host "`n❌ STARTUP FAILED: ${ServiceName} timed out after $([math]::Floor($sw.Elapsed.TotalSeconds))s/${TimeoutSec}s — port ${Port} never entered LISTEN" -ForegroundColor Red
    Write-Host "   Service: ${ServiceName} on port ${Port}" -ForegroundColor Yellow
    return $false
}

function Get-ErrorTail {
    param([string]$Path, [int]$Lines = 20)

    if (-not (Test-Path $Path)) { return }
    try {
        $content = Get-Content $Path -Tail $Lines -ErrorAction SilentlyContinue
        if ($content) {
            Write-Host "   stderr tail (last $Lines lines of $(Split-Path $Path -Leaf)):" -ForegroundColor DarkYellow
            foreach ($line in $content) {
                Write-Host "     $line" -ForegroundColor DarkGray
            }
        }
    } catch {}
}

# ---------------------------------------------------------------------------
# Cleanup: terminate child processes and remove stale sockets (no orphans)
# ---------------------------------------------------------------------------
function CleanupOrphanedProcesses {
    param(
        [int]$BackendPid = 0,
        [int]$FrontendPid = 0
    )

    Write-Host "`n🔧 Initiating cleanup (no orphan processes)..." -ForegroundColor Yellow

    # Preferred path: cross-platform Python cleanup module (backend/app/cleanup.py)
    $pythonCleanupPath = Join-Path $repo 'backend\app\cleanup.py'
    $backendPy = Join-Path $repo 'backend\.venv\python.exe'
    if (-not (Test-Path $backendPy)) { $backendPy = 'python' }

    if (Test-Path $pythonCleanupPath) {
        try {
            $pyCode = @"
import sys
sys.path.insert(0, r'$repo\backend')
from app.cleanup import perform_graceful_cleanup
result = perform_graceful_cleanup(
    backend_pid=$BackendPid,
    frontend_pid=$FrontendPid,
    repo_path=r'$repo',
    run_dir=r'$runDir',
    ports=[8013, 5174]
)
print('sockets=%d remaining_orphans=%d' % (len(result['sockets_cleaned']), len(result['remaining_orphans'])))
"@
            $pyResult = & $backendPy -c $pyCode 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  ✓ Python cleanup executed: $pyResult" -ForegroundColor Green
            } else {
                Write-Host "  ⚠ Python cleanup exit=$LASTEXITCODE : $pyResult" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "  ⚠ Python cleanup unavailable: $($_.Exception.Message)" -ForegroundColor DarkGray
        }
    }

    # Fallback: native PowerShell termination
    foreach ($spec in @(@{P=$BackendPid; N='backend'}, @{P=$FrontendPid; N='frontend'})) {
        if ($spec.P -gt 0) {
            try {
                Write-Host "  terminating $($spec.N) PID=$($spec.P)..." -ForegroundColor Yellow
                Stop-Process -Id $spec.P -Force -ErrorAction Stop
            } catch {
                Write-Host "  $($spec.N) PID=$($spec.P) already gone" -ForegroundColor DarkGray
            }
        }
    }

    if ($global:backendJob -and $global:backendJob.Id -gt 0) {
        try { Stop-Process -Id $global:backendJob.Id -Force -ErrorAction SilentlyContinue } catch {}
    }
    if ($global:frontendJob -and $global:frontendJob.Id -gt 0) {
        try { Stop-Process -Id $global:frontendJob.Id -Force -ErrorAction SilentlyContinue } catch {}
    }

    Stop-PortProcess -Port $backendPort -RepoPath $repo > $null
    Stop-PortProcess -Port $frontendPort -RepoPath $repo > $null

    Remove-AllSocketFilesIfPresent
    Write-Host "✅ Cleanup complete" -ForegroundColor Green
}

function Remove-AllSocketFilesIfPresent {
    $patterns = @('uvicorn.sock', 'fastapi.sock', '*.sock', '*.socket')
    foreach ($p in $patterns) {
        $target = Join-Path $runDir $p
        if (Test-Path $target) {
            try { Remove-Item $target -Force -ErrorAction SilentlyContinue } catch {}
        }
    }
}

function ExitWithCode {
    param([int]$Code)
    Write-Host "`n=== start.ps1 exiting with code $Code ===" -ForegroundColor $(if ($Code -eq 0) { 'Green' } else { 'Red' })
    exit $Code
}

# ---------------------------------------------------------------------------
# Main startup sequence (single, non-duplicated control flow)
# ---------------------------------------------------------------------------
function Execute-Startup {
    try {
        # [1/5] stop old processes
        Write-Host "`n[1/5] stop old processes..." -ForegroundColor Cyan
        $stoppedBackend = Stop-PortProcess -Port $backendPort -RepoPath $repo
        $stoppedFrontend = Stop-PortProcess -Port $frontendPort -RepoPath $repo

        if ($stoppedBackend -gt 0 -or $stoppedFrontend -gt 0) {
            Write-Host "  wait for ports to be released..." -ForegroundColor Gray
            Start-Sleep -Seconds 2
        }

        Write-Host "  check leftover Python/Node processes..." -ForegroundColor Gray
        foreach ($proc in (Get-RepoRuntimeProcesses -RepoPath $repo)) {
            try {
                Write-Host "  stop $($proc.Name) PID=$($proc.ProcessId)" -ForegroundColor Yellow
                Stop-Process -Id $proc.ProcessId -Force
            } catch {}
        }

        # [2/5] MySQL (skipped unless DB_PROVIDER=mysql)
        if ($dbProvider -eq 'mysql') {
            Write-Host "`n[2/5] start local MySQL..." -ForegroundColor Cyan
            & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repo 'tools\start_local_mysql.ps1')
            if ($LASTEXITCODE -ne 0) { throw 'Local MySQL startup failed' }
        } else {
            Write-Host "`n[2/5] skip local MySQL (DB_PROVIDER=$dbProvider)" -ForegroundColor DarkGray
        }

        # [3/5] backend with bounded timeout
        Write-Host "`n[3/5] start backend (timeout: ${TIMEOUT_SECONDS}s)..." -ForegroundColor Cyan
        $backendWd = Join-Path $repo 'backend'
        $backendPy = Join-Path $backendWd '.venv\python.exe'
        if (-not (Test-Path $backendPy)) { $backendPy = 'python' }
        $backendOut = Join-Path $runDir 'backend.log'
        $backendErr = Join-Path $runDir 'backend-error.log'

        $env:XUANQIONG_WENSHU_LOG_DIR = $runDir
        $env:LOGGING_LEVEL = 'INFO'
        $env:CONSOLE_LOGGING_LEVEL = 'INFO'
        $env:XUANQIONG_WENSHU_UVICORN_LOG_LEVEL = 'info'
        $env:XUANQIONG_WENSHU_UVICORN_ACCESS_LOG = '0'
        $env:PYTHONUNBUFFERED = '1'
        $env:PYTHONUTF8 = '1'
        $env:PYTHONIOENCODING = 'utf-8'

        $global:backendJob = Start-Process -FilePath $backendPy `
            -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', $backendHost, '--port', "$backendPort", '--log-level', 'info', '--no-access-log') `
            -WorkingDirectory $backendWd `
            -RedirectStandardOutput $backendOut `
            -RedirectStandardError $backendErr `
            -PassThru
        Write-Host "  backend PID: $($global:backendJob.Id)" -ForegroundColor Gray

        $backendOk = Wait-ForPortListen -ServiceName 'backend (uvicorn 8013)' -HostName $backendHost -Port $backendPort `
            -TimeoutSec $TIMEOUT_SECONDS -CheckIntervalMs $CHECK_INTERVAL_MS -Process $global:backendJob

        if (-not $backendOk) {
            Get-ErrorTail -Path $backendErr
            Write-Host "`n💡 TIPS (backend):" -ForegroundColor Cyan
            Write-Host "  1. Logs: $runDir" -ForegroundColor White
            Write-Host "  2. Manual: cd backend && .venv\python.exe -m uvicorn app.main:app --host $backendHost --port $backendPort" -ForegroundColor White
            CleanupOrphanedProcesses -BackendPid $global:backendJob.Id -FrontendPid 0
            return 1
        }

        # [4/5] frontend with bounded timeout
        Write-Host "`n[4/5] start frontend (timeout: ${TIMEOUT_SECONDS}s)..." -ForegroundColor Cyan
        $frontendWd = Join-Path $repo 'frontend'
        $npmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
        if (-not $npmCmd) { $npmCmd = Get-Command npm -ErrorAction SilentlyContinue }
        if (-not $npmCmd) {
            Write-Host "❌ ERROR: npm not found" -ForegroundColor Red
            CleanupOrphanedProcesses -BackendPid $global:backendJob.Id -FrontendPid 0
            return 1
        }
        $frontendOut = Join-Path $runDir 'frontend.log'
        $frontendErr = Join-Path $runDir 'frontend-error.log'

        $global:frontendJob = Start-Process -FilePath $npmCmd.Source `
            -ArgumentList @('run', 'dev', '--', '--host', $frontendHost, '--port', "$frontendPort") `
            -WorkingDirectory $frontendWd `
            -RedirectStandardOutput $frontendOut `
            -RedirectStandardError $frontendErr `
            -PassThru
        Write-Host "  frontend PID: $($global:frontendJob.Id)" -ForegroundColor Gray

        $frontendOk = Wait-ForPortListen -ServiceName 'frontend (vite 5174)' -HostName $frontendHost -Port $frontendPort `
            -TimeoutSec $TIMEOUT_SECONDS -CheckIntervalMs $CHECK_INTERVAL_MS -Process $global:frontendJob

        if (-not $frontendOk) {
            Get-ErrorTail -Path $frontendErr
            Write-Host "`n💡 TIPS (frontend):" -ForegroundColor Cyan
            Write-Host "  1. Logs: $runDir" -ForegroundColor White
            Write-Host "  2. Manual: cd frontend && npm run dev -- --host $frontendHost --port $frontendPort" -ForegroundColor White
            CleanupOrphanedProcesses -BackendPid $global:backendJob.Id -FrontendPid $global:frontendJob.Id
            return 1
        }

        # [5/5] final readiness (backend /api/health, frontend /, frontend proxy)
        Write-Host "`n[5/5] wait for services readiness..." -ForegroundColor Cyan
        $backendReady = $false
        $frontendReady = $false
        $frontendProxyReady = $false

        for ($i = 1; $i -le $MAX_WAIT_SECONDS; $i++) {
            if (-not $backendReady) {
                try {
                    $r = Invoke-WebRequest -UseBasicParsing "$backendBaseUrl/api/health" -TimeoutSec 2
                    if ($r.StatusCode -eq 200) { $backendReady = $true; Write-Host '  [OK] backend ready' -ForegroundColor Green }
                } catch {}
            }
            if (-not $frontendReady) {
                try {
                    $r = Invoke-WebRequest -UseBasicParsing "$frontendBaseUrl/" -TimeoutSec 2
                    if ($r.StatusCode -eq 200) { $frontendReady = $true; Write-Host '  [OK] frontend ready' -ForegroundColor Green }
                } catch {}
            }
            if ($frontendReady -and -not $frontendProxyReady) {
                try {
                    $r = Invoke-WebRequest -UseBasicParsing $frontendProxyHealthUrl -TimeoutSec 2
                    if ($r.StatusCode -eq 200) { $frontendProxyReady = $true; Write-Host '  [OK] frontend proxy ready' -ForegroundColor Green }
                } catch {}
            }
            if ($backendReady -and $frontendReady -and $frontendProxyReady) { break }
            Write-Host '.' -NoNewline -ForegroundColor DarkGray
            Start-Sleep -Milliseconds $CHECK_INTERVAL_MS
        }
        Write-Host ''

        if ($backendReady -and $frontendReady -and $frontendProxyReady) {
            Write-Host "`n========================================" -ForegroundColor Cyan
            Write-Host "RUN_DIR=$runDir" -ForegroundColor White
            Write-Host "BACKEND_READY=$backendReady" -ForegroundColor Green
            Write-Host "FRONTEND_READY=$frontendReady" -ForegroundColor Green
            Write-Host "FRONTEND_PROXY_READY=$frontendProxyReady" -ForegroundColor Green
            Write-Host "TIMEOUT_LIMIT=${TIMEOUT_SECONDS}s" -ForegroundColor Gray
            Write-Host '========================================' -ForegroundColor Cyan
            Write-Host "`nURLs:" -ForegroundColor Green
            Write-Host "  frontend: $frontendBaseUrl" -ForegroundColor White
            Write-Host "  backend:  $backendBaseUrl" -ForegroundColor White
            Write-Host "  proxy:    $frontendProxyHealthUrl" -ForegroundColor White
            return 0
        }

        Write-Host "`n❌ STARTUP FAILED - final readiness not achieved within ${MAX_WAIT_SECONDS}s" -ForegroundColor Red
        if (-not $backendReady) { Write-Host "  backend /api/health failing" -ForegroundColor Yellow }
        if (-not $frontendReady -or -not $frontendProxyReady) { Write-Host "  frontend/proxy health failing" -ForegroundColor Yellow }
        CleanupOrphanedProcesses -BackendPid $global:backendJob.Id -FrontendPid $global:frontendJob.Id
        return 1
    }
    catch {
        Write-Host "`n⚠ EXCEPTION: $_" -ForegroundColor Red
        $bp = if ($global:backendJob -and $global:backendJob.Id) { $global:backendJob.Id } else { 0 }
        $fp = if ($global:frontendJob -and $global:frontendJob.Id) { $global:frontendJob.Id } else { 0 }
        CleanupOrphanedProcesses -BackendPid $bp -FrontendPid $fp
        return 1
    }
}

# ---------------------------------------------------------------------------
# Entry point (runs once)
# ---------------------------------------------------------------------------
try {
    $exitCode = Execute-Startup
    if ($exitCode -ne 0) {
        ExitWithCode $exitCode
    }
} catch {
    Write-Host "`n⚠ FATAL: $_" -ForegroundColor Red
    $bp = if ($global:backendJob -and $global:backendJob.Id) { $global:backendJob.Id } else { 0 }
    $fp = if ($global:frontendJob -and $global:frontendJob.Id) { $global:frontendJob.Id } else { 0 }
    CleanupOrphanedProcesses -BackendPid $bp -FrontendPid $fp
    ExitWithCode 1
} finally {
    Remove-AllSocketFilesIfPresent
}

Write-Host "`n=== startup OK ===" -ForegroundColor Green
exit 0

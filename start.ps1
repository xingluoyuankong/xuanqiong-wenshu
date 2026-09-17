$ErrorActionPreference = 'Continue'

[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

# === Timeout Configuration ===
$TIMEOUT_SECONDS = 30  # Maximum wait time for each service (configurable)
$CHECK_INTERVAL_MS = 500  # Health check interval in milliseconds
Write-Host "⏱ Startup timeout configured: ${TIMEOUT_SECONDS}s" -ForegroundColor DarkGray

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = $scriptPath
$logsRoot = Join-Path $repo 'logs'

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

function CleanupOrphanedProcesses {
    Write-Host "`n🛑 Starting process cleanup due to startup failure..." -ForegroundColor Red
    
    # Terminate backend job if still running
    if ($backendJob -and $backendJob.Id) {
        try {
            Write-Host "  terminating backend PID=$($backendJob.Id)..." -ForegroundColor Yellow
            Stop-Process -Id $backendJob.Id -Force -ErrorAction Stop
            $null = $backendJob | Wait-Job -ErrorAction SilentlyContinue 2>$null
        } catch {
            Write-Host "  backend process already terminated" -ForegroundColor DarkGray
        }
    }
    
    # Terminate frontend job if still running
    if ($frontendJob -and $frontendJob.Id) {
        try {
            Write-Host "  terminating frontend PID=$($frontendJob.Id)..." -ForegroundColor Yellow
            Stop-Process -Id $frontendJob.Id -Force -ErrorAction Stop
            $null = $frontendJob | Wait-Job -ErrorAction SilentlyContinue 2>$null
        } catch {
            Write-Host "  frontend process already terminated" -ForegroundColor DarkGray
        }
    }
    
    # Clean up any leftover Python/Node processes on our ports
    Write-Host "  cleaning leftover processes on ports ${backendPort},${frontendPort}..." -ForegroundColor Gray
    Stop-PortProcess -Port $backendPort -RepoPath $repo > $null
    Stop-PortProcess -Port $frontendPort -RepoPath $repo > $null
    
    # Clean socket files if present
    $socketFiles = @(
        Join-Path $runDir 'uvicorn.sock',
        Join-Path $runDir 'fastapi.sock'
    )
    foreach ($sock in $socketFiles) {
        if (Test-Path $sock) {
            try { Remove-Item $sock -Force } catch {}
        }
    }
    
    Write-Host "✅ Process cleanup complete" -ForegroundColor Green
}

Write-Host "`n[1/5] stop old processes..." -ForegroundColor Cyan
$stoppedBackend = Stop-PortProcess -Port $backendPort -RepoPath $repo
$stoppedFrontend = Stop-PortProcess -Port $frontendPort -RepoPath $repo

if ($stoppedBackend -gt 0 -or $stoppedFrontend -gt 0) {
    Write-Host "  wait for ports to be released..." -ForegroundColor Gray
    Start-Sleep -Seconds 2
}

Write-Host "  check leftover Python/Node processes..." -ForegroundColor Gray
$repoProcesses = Get-RepoRuntimeProcesses -RepoPath $repo

foreach ($proc in $repoProcesses) {
    try {
        Write-Host "  stop $($proc.Name) PID=$($proc.ProcessId)" -ForegroundColor Yellow
        Stop-Process -Id $proc.ProcessId -Force
    } catch {}
}

if ($dbProvider -eq 'mysql') {
    Write-Host "`n[2/5] start local MySQL..." -ForegroundColor Cyan
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repo 'tools\start_local_mysql.ps1')
    if ($LASTEXITCODE -ne 0) {
        throw 'Local MySQL startup failed'
    }
} else {
    Write-Host "`n[2/5] skip local MySQL (DB_PROVIDER=$dbProvider)" -ForegroundColor DarkGray
}

Write-Host "`n[3/5] start backend..." -ForegroundColor Cyan
$backendWd = Join-Path $repo 'backend'
$backendPy = Join-Path $backendWd '.venv\python.exe'
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

$startTimeBackend = Get-Date
$backendJob = Start-Process -FilePath $backendPy `
    -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', $backendHost, '--port', "$backendPort", '--log-level', 'info', '--no-access-log') `
    -WorkingDirectory $backendWd `
    -RedirectStandardOutput $backendOut `
    -RedirectStandardError $backendErr `
    -PassThru

Write-Host "  backend PID: $($backendJob.Id)" -ForegroundColor Gray

# Check if backend started within timeout
while ((Get-Date).Subtract($startTimeBackend).TotalSeconds -lt $TIMEOUT_SECONDS) {
    try {
        $resp = Invoke-WebRequest -UseBasicParsing "$backendBaseUrl/api/health" -TimeoutSec 2
        if ($resp.StatusCode -eq 200) {
            Write-Host '  [OK] backend ready' -ForegroundColor Green
            break
        }
    } catch {}
    
    # Still starting, wait a bit
    Start-Sleep -Milliseconds $CHECK_INTERVAL_MS
}

# Timeout check for backend
if (-not (Test-Path $backendOut)) {
    # Try reading what we have
    try {
        $lastLines = Get-Content $backendErr -Tail 10 2>$null
        if ($lastLines) {
            Write-Host "  backend stderr tail:" -ForegroundColor DarkYellow
            foreach ($line in $lastLines) {
                Write-Host "    $line" -ForegroundColor DarkGray
            }
        }
    } catch {}
    
    Write-Host "❌ TIMEOUT: Backend failed to respond within ${TIMEOUT_SECONDS}s" -ForegroundColor Red
    CleanupOrphanedProcesses
    exit 1
}

Write-Host "`n[4/5] start frontend..." -ForegroundColor Cyan
$frontendWd = Join-Path $repo 'frontend'
$npmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCmd) {
    $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
}
if (-not $npmCmd) {
    Write-Host "❌ ERROR: npm not found" -ForegroundColor Red
    CleanupOrphanedProcesses
    exit 1
}
$frontendOut = Join-Path $runDir 'frontend.log'
$frontendErr = Join-Path $runDir 'frontend-error.log'

$startTimeFrontend = Get-Date
$frontendJob = Start-Process -FilePath $npmCmd.Source `
    -ArgumentList @('run', 'dev', '--', '--host', $frontendHost, '--port', "$frontendPort") `
    -WorkingDirectory $frontendWd `
    -RedirectStandardOutput $frontendOut `
    -RedirectStandardError $frontendErr `
    -PassThru

Write-Host "  frontend PID: $($frontendJob.Id)" -ForegroundColor Gray

# Check if frontend started within timeout
while ((Get-Date).Subtract($startTimeFrontend).TotalSeconds -lt $TIMEOUT_SECONDS) {
    try {
        $resp = Invoke-WebRequest -UseBasicParsing "$frontendBaseUrl/" -TimeoutSec 2
        if ($resp.StatusCode -eq 200) {
            Write-Host '  [OK] frontend ready' -ForegroundColor Green
            break
        }
    } catch {}
    
    # Still starting, wait a bit
    Start-Sleep -Milliseconds $CHECK_INTERVAL_MS
}

# Timeout check for frontend
if (-not (Test-Path $frontendOut)) {
    try {
        $lastLines = Get-Content $frontendErr -Tail 10 2>$null
        if ($lastLines) {
            Write-Host "  frontend stderr tail:" -ForegroundColor DarkYellow
            foreach ($line in $lastLines) {
                Write-Host "    $line" -ForegroundColor DarkGray
            }
        }
    } catch {}
    
    Write-Host "❌ TIMEOUT: Frontend failed to respond within ${TIMEOUT_SECONDS}s" -ForegroundColor Red
    CleanupOrphanedProcesses
    exit 1
}

Write-Host "`n[5/5] wait for services..." -ForegroundColor Cyan
$backendReady = $false
$frontendReady = $false
$frontendProxyReady = $false
$maxWait = 60

for ($i = 1; $i -le $maxWait; $i++) {
    if (-not $backendReady) {
        try {
            $resp = Invoke-WebRequest -UseBasicParsing "$backendBaseUrl/api/health" -TimeoutSec 2
            if ($resp.StatusCode -eq 200) {
                $backendReady = $true
                Write-Host '  [OK] backend ready' -ForegroundColor Green
            }
        } catch {}
    }

    if (-not $frontendReady) {
        try {
            $resp = Invoke-WebRequest -UseBasicParsing "$frontendBaseUrl/" -TimeoutSec 2
            if ($resp.StatusCode -eq 200) {
                $frontendReady = $true
                Write-Host '  [OK] frontend ready' -ForegroundColor Green
            }
        } catch {}
    }

    if ($frontendReady -and -not $frontendProxyReady) {
        try {
            $resp = Invoke-WebRequest -UseBasicParsing $frontendProxyHealthUrl -TimeoutSec 2
            if ($resp.StatusCode -eq 200) {
                $frontendProxyReady = $true
                Write-Host '  [OK] frontend proxy ready' -ForegroundColor Green
            }
        } catch {}
    }

    if ($backendReady -and $frontendReady -and $frontendProxyReady) { break }

    Write-Host '.' -NoNewline -ForegroundColor DarkGray
    Start-Sleep -Milliseconds $CHECK_INTERVAL_MS
}

Write-Host ''
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "RUN_DIR=$runDir" -ForegroundColor White
Write-Host "BACKEND_READY=$backendReady" -ForegroundColor $(if ($backendReady) { 'Green' } else { 'Red' })
Write-Host "FRONTEND_READY=$frontendReady" -ForegroundColor $(if ($frontendReady) { 'Green' } else { 'Red' })
Write-Host "FRONTEND_PROXY_READY=$frontendProxyReady" -ForegroundColor $(if ($frontendProxyReady) { 'Green' } else { 'Red' })
Write-Host "TIMEOUT_LIMIT=${TIMEOUT_SECONDS}s" -ForegroundColor Gray
Write-Host '========================================' -ForegroundColor Cyan

if ($backendReady) {
    Write-Host "`nURLs:" -ForegroundColor Green
    Write-Host "  frontend: $frontendBaseUrl" -ForegroundColor White
    Write-Host "  backend:  $backendBaseUrl" -ForegroundColor White
    Write-Host "  proxy:    $frontendProxyHealthUrl" -ForegroundColor White
}

if (-not $backendReady -or -not $frontendReady -or -not $frontendProxyReady) {
    Write-Host "`n❌ STARTUP FAILED - inspect logs:" -ForegroundColor Red
    CleanupOrphanedProcesses
    
    if (-not $backendReady) {
        Write-Host "  backend stderr: $backendErr" -ForegroundColor Yellow
        if (Test-Path $backendErr) {
            Write-Host '  backend stderr tail:' -ForegroundColor DarkYellow
            Get-Content $backendErr -Tail 20
        }
    }
    if (-not $frontendReady -or -not $frontendProxyReady) {
        Write-Host "  frontend stderr: $frontendErr" -ForegroundColor Yellow
        if (Test-Path $frontendErr) {
            Write-Host '  frontend stderr tail:' -ForegroundColor DarkYellow
            Get-Content $frontendErr -Tail 20
        }
        Write-Host "  frontend proxy check failed: $frontendProxyHealthUrl" -ForegroundColor Yellow
    }
    
    Write-Host "`n💡 TIPS:" -ForegroundColor Cyan
    Write-Host "  1. Check logs in: $runDir" -ForegroundColor White
    Write-Host "  2. Ensure ports ${backendPort},${frontendPort} are free" -ForegroundColor White
    Write-Host "  3. Verify Python/npm are installed correctly" -ForegroundColor White
    Write-Host "  4. Try running manually: cd backend && .venv\python.exe -m uvicorn app.main:app --host localhost --port $backendPort" -ForegroundColor White
    
    exit 1
}

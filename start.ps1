$ErrorActionPreference = 'Continue'

[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

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

function Test-RepoOwnedProcess {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$RepoPath
    )

    if (-not $Process) {
        return $false
    }

    try {
        if ($Process.Path -and $Process.Path.StartsWith($RepoPath, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $true
        }
    } catch {}

    return $false
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
            $proc = Get-Process -Id $procId -ErrorAction Stop
            if (-not (Test-RepoOwnedProcess -Process $proc -RepoPath $RepoPath)) {
                Write-Host "  skip PID=$procId ($($proc.ProcessName)) on port $Port because it is not repo-owned" -ForegroundColor DarkYellow
                continue
            }
            Write-Host "  stop PID=$procId ($($proc.ProcessName))" -ForegroundColor Yellow
            Stop-Process -Id $procId -Force -ErrorAction Stop
            $stoppedCount += 1
        } catch {
            Write-Host "  failed to stop PID=${procId}: $($_.Exception.Message)" -ForegroundColor DarkGray
        }
    }

    return $stoppedCount
}

Write-Host "`n[1/5] stop old processes..." -ForegroundColor Cyan
$stoppedBackend = Stop-PortProcess -Port $backendPort -RepoPath $repo
$stoppedFrontend = Stop-PortProcess -Port $frontendPort -RepoPath $repo

if ($stoppedBackend -gt 0 -or $stoppedFrontend -gt 0) {
    Write-Host "  wait for ports to be released..." -ForegroundColor Gray
    Start-Sleep -Seconds 2
}

Write-Host "  check leftover Python/Node processes..." -ForegroundColor Gray
$pythonProcesses = Get-Process -Name "python*" -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -and $_.Path.StartsWith($repo, [System.StringComparison]::OrdinalIgnoreCase)
}
$nodeProcesses = Get-Process -Name "node" -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -and $_.Path.StartsWith($repo, [System.StringComparison]::OrdinalIgnoreCase)
}

foreach ($proc in $pythonProcesses) {
    try {
        Write-Host "  stop Python PID=$($proc.Id)" -ForegroundColor Yellow
        Stop-Process -Id $proc.Id -Force
    } catch {}
}

foreach ($proc in $nodeProcesses) {
    try {
        Write-Host "  stop Node PID=$($proc.Id)" -ForegroundColor Yellow
        Stop-Process -Id $proc.Id -Force
    } catch {}
}

Write-Host "`n[2/5] start local MySQL..." -ForegroundColor Cyan
& powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repo 'tools\start_local_mysql.ps1')
if ($LASTEXITCODE -ne 0) {
    throw 'Local MySQL startup failed'
}

Write-Host "`n[3/5] start backend..." -ForegroundColor Cyan
$backendWd = Join-Path $repo 'backend'
$backendPy = Join-Path $backendWd '.venv\Scripts\python.exe'
$backendOut = Join-Path $runDir 'backend.log'
$backendErr = Join-Path $runDir 'backend-error.log'

$env:XUANQIONG_WENSHU_LOG_DIR = $runDir
$env:LOGGING_LEVEL = 'INFO'
$env:CONSOLE_LOGGING_LEVEL = 'WARNING'
$env:XUANQIONG_WENSHU_UVICORN_LOG_LEVEL = 'warning'
$env:XUANQIONG_WENSHU_UVICORN_ACCESS_LOG = '0'
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

$backendJob = Start-Process -FilePath $backendPy `
    -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', $backendHost, '--port', "$backendPort", '--log-level', 'warning', '--no-access-log') `
    -WorkingDirectory $backendWd `
    -RedirectStandardOutput $backendOut `
    -RedirectStandardError $backendErr `
    -PassThru

Write-Host "  backend PID: $($backendJob.Id)" -ForegroundColor Gray

Write-Host "`n[4/5] start frontend..." -ForegroundColor Cyan
$frontendWd = Join-Path $repo 'frontend'
$npmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCmd) {
    $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
}
if (-not $npmCmd) {
    throw 'npm not found'
}
$frontendOut = Join-Path $runDir 'frontend.log'
$frontendErr = Join-Path $runDir 'frontend-error.log'

$frontendJob = Start-Process -FilePath $npmCmd.Source `
    -ArgumentList @('run', 'dev', '--', '--host', $frontendHost, '--port', "$frontendPort") `
    -WorkingDirectory $frontendWd `
    -RedirectStandardOutput $frontendOut `
    -RedirectStandardError $frontendErr `
    -PassThru

Write-Host "  frontend PID: $($frontendJob.Id)" -ForegroundColor Gray

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
    Start-Sleep -Milliseconds 500
}

Write-Host ''
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "RUN_DIR=$runDir" -ForegroundColor White
Write-Host "BACKEND_READY=$backendReady" -ForegroundColor $(if ($backendReady) { 'Green' } else { 'Red' })
Write-Host "FRONTEND_READY=$frontendReady" -ForegroundColor $(if ($frontendReady) { 'Green' } else { 'Red' })
Write-Host "FRONTEND_PROXY_READY=$frontendProxyReady" -ForegroundColor $(if ($frontendProxyReady) { 'Green' } else { 'Red' })
Write-Host '========================================' -ForegroundColor Cyan

if ($backendReady) {
    Write-Host "`nURLs:" -ForegroundColor Green
    Write-Host "  frontend: $frontendBaseUrl" -ForegroundColor White
    Write-Host "  backend:  $backendBaseUrl" -ForegroundColor White
    Write-Host "  proxy:    $frontendProxyHealthUrl" -ForegroundColor White
}

if (-not $backendReady -or -not $frontendReady -or -not $frontendProxyReady) {
    Write-Host "`nstartup failed, inspect logs:" -ForegroundColor Red
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
    exit 1
}

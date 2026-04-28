# 玄穹文枢 stop script
# Stop local formal stack processes

[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding

Write-Host "=== 停止玄穹文枢服务 ===" -ForegroundColor Cyan

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = $scriptPath

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

$backendPortValue = Get-EnvValue -Names @('XUANQIONG_WENSHU_BACKEND_PORT') -Default '8013'
$frontendPortValue = Get-EnvValue -Names @('XUANQIONG_WENSHU_FRONTEND_PORT') -Default '5174'

[int]$backendPort = $backendPortValue
[int]$frontendPort = $frontendPortValue

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
        } catch {}
    }

    return $stoppedCount
}

Write-Host "Check backend port $backendPort..." -ForegroundColor Gray
$stoppedBackend = Stop-PortProcess -Port $backendPort -RepoPath $repo

Write-Host "Check frontend port $frontendPort..." -ForegroundColor Gray
$stoppedFrontend = Stop-PortProcess -Port $frontendPort -RepoPath $repo

Write-Host "Check repo Python processes..." -ForegroundColor Gray
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

Write-Host "Stop local MySQL if running..." -ForegroundColor Gray
try {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repo 'tools\stop_local_mysql.ps1') | Out-Null
} catch {}

$repoPythonStopped = @($pythonProcesses).Count
$repoNodeStopped = @($nodeProcesses).Count
Write-Host "`nStop summary:" -ForegroundColor Green
Write-Host "  port listeners stopped: backend=$stoppedBackend, frontend=$stoppedFrontend" -ForegroundColor White
Write-Host "  repo-local processes stopped: python=$repoPythonStopped, node=$repoNodeStopped" -ForegroundColor White
Write-Host "  note: extra cleanup only targets Python/Node executables under the repo path." -ForegroundColor DarkGray

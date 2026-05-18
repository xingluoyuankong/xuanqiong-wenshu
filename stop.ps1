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
            $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $procId" -ErrorAction Stop
            if (-not (Test-RepoOwnedProcess -ProcessId $procId -RepoPath $RepoPath)) {
                Write-Host "  skip PID=$procId ($($proc.Name)) on port $Port because it is not repo-owned" -ForegroundColor DarkYellow
                continue
            }
            Write-Host "  stop PID=$procId ($($proc.Name))" -ForegroundColor Yellow
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

Write-Host "Check repo Python/Node processes..." -ForegroundColor Gray
$repoProcesses = Get-RepoRuntimeProcesses -RepoPath $repo

foreach ($proc in $repoProcesses) {
    try {
        Write-Host "  stop $($proc.Name) PID=$($proc.ProcessId)" -ForegroundColor Yellow
        Stop-Process -Id $proc.ProcessId -Force
    } catch {}
}

Write-Host "Stop local MySQL if running..." -ForegroundColor Gray
try {
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repo 'tools\stop_local_mysql.ps1') | Out-Null
} catch {}

$repoPythonStopped = @($repoProcesses | Where-Object { $_.Name -eq 'python.exe' }).Count
$repoNodeStopped = @($repoProcesses | Where-Object { $_.Name -eq 'node.exe' }).Count
Write-Host "`nStop summary:" -ForegroundColor Green
Write-Host "  port listeners stopped: backend=$stoppedBackend, frontend=$stoppedFrontend" -ForegroundColor White
Write-Host "  repo service processes stopped: python=$repoPythonStopped, node=$repoNodeStopped" -ForegroundColor White
Write-Host "  note: extra cleanup targets commands whose executable path or command line points to xuanqiong-wenshu/backend|frontend." -ForegroundColor DarkGray

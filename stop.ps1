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
Write-Host "`n停止摘要:" -ForegroundColor Green
Write-Host "  端口监听器已停止：backend=$stoppedBackend, frontend=$stoppedFrontend" -ForegroundColor White
Write-Host "  仓库服务进程已停止：python=$repoPythonStopped, node=$repoNodeStopped" -ForegroundColor White
Write-Host "  注：额外清理目标命令的可执行路径或命令行指向 xuanqiong-wenshu/backend|frontend。" -ForegroundColor DarkGray

# === Zombie Process Verification (US-004) ===
Write-Host "`n=== 僵尸进程验证 ===" -ForegroundColor DarkGray

# Define logsRoot for socket cleanup (was previously undefined - US-004 fix)
$logsRoot = Join-Path $repo 'logs'

$verificationResult = @{
    orphans_found = @()
    ports_still_in_use = @{}
    sockets_remaining = @()
    verified_clean = $false
}

try {
    # Check for Python zombie processes
    $pythonZombies = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -eq 'python.exe' -and 
        $_.ExecutablePath -notlike '*node_modules*' -and
        ($_.CommandLine -match 'xuanqiong-wenshu|uvicorn' -or $_.ExecutablePath -like '*\.venv*\python.exe')
    }
    
    if ($pythonZombies.Count -gt 0) {
        Write-Host "  ⚠ Found orphaned Python processes:" -ForegroundColor Yellow
        foreach ($proc in $pythonZombies) {
            Write-Host "    PID=$($proc.ProcessId) CommandLine=$($proc.CommandLine)" -ForegroundColor Gray
            $verificationResult.orphans_found += [PSCustomObject]@{
                Type = 'Python'
                Pid = $proc.ProcessId
                CmdLine = $proc.CommandLine
            }
        }
    } else {
        Write-Host "  ✓ No orphaned Python processes detected" -ForegroundColor Green
    }
    
    # Check Node zombie processes
    $nodeZombies = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -eq 'node.exe' -and 
        ($_.CommandLine -match 'xuanqiong-wenshu|npm|vite' -or $_.ExecutablePath -like '*nodejs*')
    }
    
    if ($nodeZombies.Count -gt 0) {
        Write-Host "  ⚠ Found orphaned Node processes:" -ForegroundColor Yellow
        foreach ($proc in $nodeZombies) {
            Write-Host "    PID=$($proc.ProcessId) CommandLine=$($proc.CommandLine)" -ForegroundColor Gray
            $verificationResult.orphans_found += [PSCustomObject]@{
                Type = 'Node'
                Pid = $proc.ProcessId
                CmdLine = $proc.CommandLine
            }
        }
    } else {
        Write-Host "  ✓ No orphaned Node processes detected" -ForegroundColor Green
    }
    
    # Check ports still in use
    foreach ($port in @($backendPort, $frontendPort)) {
        try {
            $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
            if ($connections) {
                $verificationResult.ports_still_in_use[$port] = $true
                Write-Host "  ⚠ Port $port still has listeners" -ForegroundColor Yellow
            } else {
                Write-Host "  ✓ Port $port is free" -ForegroundColor Green
            }
        } catch {
            Write-Host "  ⚠ Could not verify port $port" -ForegroundColor DarkGray
        }
    }
    
    # Check socket files remaining
    $socketPatterns = @(
        Join-Path $repo 'logs\uvicorn.sock',
        Join-Path $repo 'logs\fastapi.sock',
        Join-Path $env:TEMP '*.sock'
    )
    
    foreach ($pattern in $socketPatterns) {
        try {
            $sockets = Get-ChildItem -Path $pattern -ErrorAction SilentlyContinue -ErrorVariable sockErr
            if ($sockets -and $sockets.Count -gt 0) {
                Write-Host "  ⚠ Stale socket files found:" -ForegroundColor Yellow
                foreach ($sock in $sockets) {
                    Write-Host "    $($sock.FullName)" -ForegroundColor Gray
                    $verificationResult.sockets_remaining += $sock.FullName
                }
            } else {
                Write-Host "  ✓ No stale socket files" -ForegroundColor Green
            }
        } catch {}
    }
    
    # Final verification
    $verificationResult.verified_clean = (
        $verificationResult.orphans_found.Count -eq 0 -and
        $verificationResult.ports_still_in_use.Count -eq 0 -and
        $verificationResult.sockets_remaining.Count -eq 0
    )
    
    if ($verificationResult.verified_clean) {
        Write-Host "`n✅ 所有检查通过：无僵尸进程、端口已释放" -ForegroundColor Green
    } else {
        Write-Host "`n⚠ 发现残留资源：" -ForegroundColor Yellow
        Write-Host "  - 僵尸进程数：$($verificationResult.orphans_found.Count)" -ForegroundColor Gray
        Write-Host "  - 仍在使用中的端口：$($verificationResult.ports_still_in_use.Keys.Count)" -ForegroundColor Gray
        Write-Host "  - 剩余 socket 文件：$($verificationResult.sockets_remaining.Count)" -ForegroundColor Gray
    }
} catch {
    Write-Host "  ⚠ Warning: Unable to complete verification - $_" -ForegroundColor DarkYellow
}

# Clean up socket files
Write-Host "`n=== Socket 文件清理 ===" -ForegroundColor DarkGray
$socketsToClean = @(
    "$logsRoot\uvicorn.sock",
    "$logsRoot\fastapi.sock",
    "$env:TEMP\uvicorn*.sock",
    "$env:TMP\uvicorn*.sock"
)

foreach ($sockPattern in $socketsToClean) {
    try {
        $sockets = Get-ChildItem -Path $sockPattern -ErrorAction SilentlyContinue
        if ($sockets) {
            foreach ($sock in $sockets) {
                Write-Host "  Removing stale socket: $($sock.FullName)" -ForegroundColor DarkGray
                Remove-Item -Force $sock.FullName -ErrorAction SilentlyContinue
            }
            Write-Host "  ✓ Stale sockets cleaned" -ForegroundColor Green
        }
    } catch {}
}

Write-Host "`n=== 停止完成 ===" -ForegroundColor Cyan
# zombieCount was previously undefined - US-004 fix: derive from verification result
$zombieCount = $verificationResult.orphans_found.Count
Write-Host "僵尸进程数：$zombieCount" -ForegroundColor DarkGray

# === US-004: Explicit PASS/FAIL checklist summary ===
# Evaluated AFTER socket cleanup so sockets_remaining reflects current state,
# not the pre-cleanup snapshot (fixes false [FAIL] on "no stale sockets").
Write-Host "`n=== 清理验证清单 ===" -ForegroundColor Cyan

# Re-check socket state now that cleanup has run.
$socketsNow = @()
foreach ($sockPattern in @("$logsRoot\uvicorn.sock", "$logsRoot\fastapi.sock", "$env:TEMP\uvicorn*.sock", "$env:TMP\uvicorn*.sock")) {
    try {
        $socks = Get-ChildItem -Path $sockPattern -ErrorAction SilentlyContinue
        if ($socks) { foreach ($s in $socks) { $socketsNow += $s.FullName } }
    } catch {}
}
$verificationResult.sockets_remaining = $socketsNow

$checklist = @(
    @{ Item = '无孤儿 Python 进程'; Ok = (@($verificationResult.orphans_found | Where-Object { $_.Type -eq 'Python' }).Count -eq 0) },
    @{ Item = '无孤儿 Node 进程';   Ok = (@($verificationResult.orphans_found | Where-Object { $_.Type -eq 'Node' }).Count -eq 0) },
    @{ Item = '端口全部释放';       Ok = ($verificationResult.ports_still_in_use.Count -eq 0) },
    @{ Item = '无残留 socket 文件'; Ok = ($verificationResult.sockets_remaining.Count -eq 0) }
)
foreach ($c in $checklist) {
    if ($c.Ok) {
        Write-Host "  [PASS] $($c.Item)" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] $($c.Item)" -ForegroundColor Red
    }
}
    if ($c.Ok) {
        Write-Host ("  [PASS] " + $c.Item) -ForegroundColor Green
    } else {
        Write-Host ("  [FAIL] " + $c.Item) -ForegroundColor Red
    }
}
$allPass = @($checklist | Where-Object { -not $_.Ok }).Count -eq 0
if ($allPass) {
    Write-Host "✅ 全部清理检查通过（无孤儿进程、端口已释放、无残留 socket）" -ForegroundColor Green
} else {
    Write-Host "⚠ 存在残留资源，请检查上方 [FAIL] 项" -ForegroundColor Yellow
}

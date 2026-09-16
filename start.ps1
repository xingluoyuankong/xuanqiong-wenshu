$ErrorActionPreference = 'Stop'

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
$dbProvider = Get-EnvValue -Names @('DB_PROVIDER') -Default ''
if ([string]::IsNullOrWhiteSpace($dbProvider)) {
    $backendEnvPathForProvider = Join-Path $repo 'backend\.env'
    if (Test-Path -LiteralPath $backendEnvPathForProvider) {
        $providerLine = Get-Content -LiteralPath $backendEnvPathForProvider |
            Where-Object { $_ -match '^\s*DB_PROVIDER\s*=' } |
            Select-Object -First 1
        if ($providerLine) {
            $dbProvider = (($providerLine -split '=', 2)[1]).Trim().Trim('"').Trim("'")
        }
    }
}
if ([string]::IsNullOrWhiteSpace($dbProvider)) { $dbProvider = 'mysql' }
$dbProvider = $dbProvider.ToLowerInvariant()

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

$runId = (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [guid]::NewGuid().ToString('N').Substring(0, 8)
$runDir = Join-Path $logsRoot ("run-$runId")
New-Item -ItemType Directory -Path $runDir -Force | Out-Null
Set-Content -Path (Join-Path $logsRoot 'latest-run.txt') -Value $runDir -Encoding UTF8

Write-Host "=== 玄穹文枢启动 ===" -ForegroundColor Cyan
Write-Host "repo: $repo" -ForegroundColor Gray
Write-Host "logs: $runDir" -ForegroundColor Gray
Write-Host "formal backend: $backendBaseUrl" -ForegroundColor Gray
Write-Host "formal frontend: $frontendBaseUrl" -ForegroundColor Gray

# Port occupancy and repository location never establish process ownership.
# Roots come only from this invocation's Start-Process. Descendants require a
# parent identity plus a birth time inside that parent's lifetime, never a name,
# executable path or port match. Retained handles preserve exited-parent evidence.
$ownedProcesses = [System.Collections.Generic.List[object]]::new()
$ownedProcessKeys = [System.Collections.Generic.HashSet[string]]::new()
$ownershipWarnings = [System.Collections.Generic.HashSet[string]]::new()

function Get-ListenerIds {
    param([int]$Port)
    try {
        $connections = @(Get-NetTCPConnection -State Listen -ErrorAction Stop)
        return @($connections | Where-Object { $_.LocalPort -eq $Port } |
            Select-Object -ExpandProperty OwningProcess -Unique)
    } catch {
        $rows = @(netstat -ano -p tcp)
        if ($LASTEXITCODE -ne 0) { throw "Port inspection failed for ${Port}" }
        return @($rows | ForEach-Object {
            if ($_ -match '^\s*TCP\s+\S+:(\d+)\s+\S+\s+LISTENING\s+(\d+)\s*$' -and
                [int]$Matches[1] -eq $Port) { [int]$Matches[2] }
        } | Select-Object -Unique)
    }
}

function Test-ServiceHealth {
    param([string]$Url, [switch]$Frontend)
    try {
        $response = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 2
        if ($response.StatusCode -ne 200) { return $false }
        if ($Frontend) {
            return [bool]($response.Content -match '<div\s+id="app"\s*>')
        }
        $health = $response.Content | ConvertFrom-Json -ErrorAction Stop
        return ($health.status -eq 'healthy' -and $health.app -eq $expectedBackendApp)
    } catch { return $false }
}

function Get-CreationMicroticks {
    param([datetime]$Time)
    # CIM timestamps have microsecond precision; retain integer tick arithmetic.
    $ticks = $Time.ToUniversalTime().Ticks
    return ($ticks - ($ticks % 10))
}

function Write-OwnershipWarning {
    param($Entry, [string]$Reason)
    if ($ownershipWarnings.Add("$($Entry.Key):$Reason")) {
        Write-Warning "Process ownership evidence incomplete for PID=$($Entry.Process.Id): $Reason; unproven processes are preserved."
    }
}

function Add-OwnedProcessEntry {
    param($Process, [datetime]$StartTime, $Parent = $null)
    $key = "$($Process.Id):$($StartTime.ToUniversalTime().Ticks)"
    if ($ownedProcessKeys.Add($key)) {
        $ownedProcesses.Add([pscustomobject]@{
            Key = $key
            Process = $Process
            StartTime = $StartTime
            ParentId = $(if ($null -ne $Parent) { $Parent.Process.Id } else { $null })
            ParentStartTime = $(if ($null -ne $Parent) { $Parent.StartTime } else { $null })
            Depth = $(if ($null -ne $Parent) { $Parent.Depth + 1 } else { 0 })
        })
    }
}

function Update-OwnedDescendants {
    # Breadth-first, strictly parent-filtered queries. No repository/global sweep.
    # Limits bound discovery even if a launched service is producing many children.
    for ($index = 0; $index -lt $ownedProcesses.Count -and $index -lt 256; $index++) {
        $parent = $ownedProcesses[$index]
        if ($parent.Depth -ge 16) {
            Write-OwnershipWarning -Entry $parent -Reason 'descendant depth limit reached'
            continue
        }
        try {
            $children = @(Get-CimInstance -ClassName Win32_Process `
                -Filter "ParentProcessId = $($parent.Process.Id)" `
                -Property ProcessId, ParentProcessId, CreationDate -OperationTimeoutSec 2 -ErrorAction Stop)
            # Inspect the RETAINED parent object, not a new lookup of its PID.
            # Refresh after the query catches a wrapper exiting during enumeration.
            $parent.Process.Refresh()
            $upperBound = [datetime]::UtcNow
            if ($parent.Process.HasExited) {
                $upperBound = $parent.Process.ExitTime.ToUniversalTime()
            }
            $lowerBound = $parent.StartTime.ToUniversalTime()
        } catch {
            Write-OwnershipWarning -Entry $parent -Reason 'parent lifetime or child query unavailable'
            continue
        }
        foreach ($child in $children) {
            if ($ownedProcesses.Count -ge 256) {
                Write-OwnershipWarning -Entry $parent -Reason 'descendant count limit reached'
                break
            }
            if ($child.ParentProcessId -ne $parent.Process.Id -or $child.ProcessId -le 0 -or
                $child.ProcessId -eq $parent.Process.Id -or $null -eq $child.CreationDate) {
                Write-OwnershipWarning -Entry $parent -Reason 'invalid child identity or missing creation time'
                continue
            }
            try {
                $birth = ([datetime]$child.CreationDate).ToUniversalTime()
                if ((Get-CreationMicroticks $birth) -lt (Get-CreationMicroticks $lowerBound) -or
                    (Get-CreationMicroticks $birth) -gt (Get-CreationMicroticks $upperBound)) {
                    Write-OwnershipWarning -Entry $parent -Reason 'child creation outside parent lifetime'
                    continue
                }
                $childKey = "$($child.ProcessId):$(Get-CreationMicroticks $birth)"
                # Avoid opening additional handles for an already verified identity.
                $known = @($ownedProcesses | Where-Object {
                    "$($_.Process.Id):$(Get-CreationMicroticks $_.StartTime)" -eq $childKey
                })
                if ($known.Count -gt 0) { continue }
                $currentChild = Get-Process -Id $child.ProcessId -ErrorAction Stop
                $childHandle = $currentChild.Handle  # Pin identity before reading StartTime.
                if ($null -eq $childHandle -or $childHandle -eq [IntPtr]::Zero) {
                    throw 'child process handle unavailable'
                }
                $childStart = $currentChild.StartTime
                if ((Get-CreationMicroticks $childStart) -ne (Get-CreationMicroticks $birth) -or
                    $childStart.ToUniversalTime() -lt $lowerBound -or
                    $childStart.ToUniversalTime() -gt $upperBound) {
                    Write-OwnershipWarning -Entry $parent -Reason 'child PID changed during discovery'
                    continue
                }
                Add-OwnedProcessEntry -Process $currentChild -StartTime $childStart -Parent $parent
            } catch {
                Write-OwnershipWarning -Entry $parent -Reason 'child identity unavailable during discovery'
            }
        }
    }
}

function Stop-OwnedServices {
    # Capture late wrapper children, including those whose pinned parent exited.
    Update-OwnedDescendants
    foreach ($entry in @($ownedProcesses | Sort-Object -Property Depth -Descending)) {
        try {
            $current = Get-Process -Id $entry.Process.Id -ErrorAction Stop
            $cleanupHandle = $current.Handle
            if ($null -eq $cleanupHandle -or $cleanupHandle -eq [IntPtr]::Zero) {
                throw 'cleanup process handle unavailable'
            }
            # A recycled root OR descendant PID is never a cleanup target.
            if ($current.StartTime -eq $entry.StartTime) {
                Stop-Process -InputObject $current -Force -ErrorAction Stop
            } else {
                Write-OwnershipWarning -Entry $entry -Reason 'PID reused before cleanup'
            }
        } catch {
            Write-Warning "Owned process $($entry.Process.Id) already exited or cleanup failed: $($_.Exception.Message)"
        }
    }
    # Bounded snapshots are not OS job containment: a never-observed process,
    # or a wrapper lost before handle acquisition, is not inferred from a PID.
    # Deliberately no taskkill /T: descendants without lifetime evidence stay intact.
}

function Register-OwnedService {
    param($Process)
    try {
        # Acquire the handle immediately. Without a root identity, fail rather than
        # infer ownership from a dead wrapper PID, its path, or a listener later.
        $rootHandle = $Process.Handle
        if ($null -eq $rootHandle -or $rootHandle -eq [IntPtr]::Zero) {
            throw 'root process handle unavailable'
        }
        Add-OwnedProcessEntry -Process $Process -StartTime $Process.StartTime
    } catch {
        Write-Warning "Launch identity unavailable for PID=$($Process.Id); no descendant ownership inferred."
        throw
    }
    Update-OwnedDescendants
}

$expectedBackendApp = Get-EnvValue -Names @('APP_NAME') -Default ''
if (-not $expectedBackendApp) {
    $envPath = Join-Path $repo 'backend\.env'
    if (Test-Path -LiteralPath $envPath) {
        $appLine = Get-Content -LiteralPath $envPath |
            Where-Object { $_ -match '^\s*APP_NAME\s*=' } | Select-Object -First 1
        if ($appLine) { $expectedBackendApp = (($appLine -split '=', 2)[1]).Trim().Trim('"').Trim("'") }
    }
}
if (-not $expectedBackendApp) { $expectedBackendApp = '玄穹文枢 API' }

Write-Host "`n[1/5] inspect existing services (no process sweep)..." -ForegroundColor Cyan
$backendListeners = @(Get-ListenerIds -Port $backendPort)
$frontendListeners = @(Get-ListenerIds -Port $frontendPort)
$reuseBackend = $backendListeners.Count -gt 0 -and (Test-ServiceHealth -Url "$backendBaseUrl/api/health")
$reuseFrontend = $frontendListeners.Count -gt 0 -and
    (Test-ServiceHealth -Url "$frontendBaseUrl/" -Frontend) -and
    (Test-ServiceHealth -Url $frontendProxyHealthUrl)
# Check both ports before starting anything, including MySQL.
if ($backendListeners.Count -gt 0 -and -not $reuseBackend) {
    throw "Backend port $backendPort occupied by PID(s) $($backendListeners -join ','); service identity/health failed. No process was stopped."
}
if ($frontendListeners.Count -gt 0 -and -not $reuseFrontend) {
    throw "Frontend port $frontendPort occupied by PID(s) $($frontendListeners -join ','); service identity/proxy health failed. No process was stopped."
}

try {
    if (-not $reuseBackend -and $dbProvider -eq 'mysql') {
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
    $backendPy = Join-Path $backendWd '.venv\Scripts\python.exe'
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

    $backendJob = $null
    if ($reuseBackend) {
        Write-Host '  reuse healthy backend (not owned by this invocation)' -ForegroundColor Green
    } else {
        if (@(Get-ListenerIds -Port $backendPort).Count -gt 0) { throw 'Backend port became occupied before launch' }
        $backendJob = Start-Process -FilePath $backendPy `
            -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', $backendHost, '--port', "$backendPort", '--log-level', 'info', '--no-access-log') `
            -WorkingDirectory $backendWd `
            -RedirectStandardOutput $backendOut `
            -RedirectStandardError $backendErr `
            -WindowStyle Hidden `
            -PassThru

        Register-OwnedService -Process $backendJob
        Write-Host "  backend PID: $($backendJob.Id)" -ForegroundColor Gray
    }

    Write-Host "`n[4/5] start frontend..." -ForegroundColor Cyan
    $frontendWd = Join-Path $repo 'frontend'
    $frontendJob = $null
    $frontendOut = Join-Path $runDir 'frontend.log'
    $frontendErr = Join-Path $runDir 'frontend-error.log'
    if ($reuseFrontend) {
        Write-Host '  reuse healthy frontend (not owned by this invocation)' -ForegroundColor Green
    } else {
        $npmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
        if (-not $npmCmd) {
            $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
        }
        if (-not $npmCmd) {
            throw 'npm not found'
        }

        if (@(Get-ListenerIds -Port $frontendPort).Count -gt 0) { throw 'Frontend port became occupied before launch' }
        $frontendJob = Start-Process -FilePath $npmCmd.Source `
            -ArgumentList @('run', 'dev', '--', '--host', $frontendHost, '--port', "$frontendPort", '--strictPort') `
            -WorkingDirectory $frontendWd `
            -RedirectStandardOutput $frontendOut `
            -RedirectStandardError $frontendErr `
            -WindowStyle Hidden `
            -PassThru

        Register-OwnedService -Process $frontendJob
        Write-Host "  frontend PID: $($frontendJob.Id)" -ForegroundColor Gray
    }

    Write-Host "`n[5/5] wait for services..." -ForegroundColor Cyan
    $backendReady = $false
    $frontendReady = $false
    $frontendProxyReady = $false
    $maxWait = 60

    for ($i = 1; $i -le $maxWait; $i++) {
        Update-OwnedDescendants
        foreach ($entry in @($ownedProcesses | Where-Object { $_.Depth -eq 0 })) {
            if ($entry.Process.HasExited) { throw "Started service exited: PID=$($entry.Process.Id)" }
        }
        $backendReady = Test-ServiceHealth -Url "$backendBaseUrl/api/health"
        $frontendReady = Test-ServiceHealth -Url "$frontendBaseUrl/" -Frontend
        $frontendProxyReady = $frontendReady -and (Test-ServiceHealth -Url $frontendProxyHealthUrl)

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
        throw 'Service startup health checks failed'
    }


} catch {
    Stop-OwnedServices
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}

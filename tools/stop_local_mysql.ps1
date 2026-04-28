$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false

$repo = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path 'X:\')) {
    cmd /c ("subst X: `"" + $repo + "`"") | Out-Null
}
$mysqlRoot = 'X:\.mysql'
$defaultsExtra = Join-Path $mysqlRoot 'client.cnf'
Write-Host "Checking local MySQL under $mysqlRoot" -ForegroundColor Gray
$mysqladmin = 'D:/download/MySQL/bin/mysqladmin.exe'
$mysqlPidFile = Join-Path $mysqlRoot 'run/mysqld.pid'
$port = 3309

if (Test-Path $defaultsExtra) {
    $command = '"{0}" --defaults-extra-file="{1}" --protocol=tcp shutdown >nul 2>nul' -f $mysqladmin, $defaultsExtra
    cmd /c $command | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "MySQL stopped on 127.0.0.1:$port" -ForegroundColor Green
        exit 0
    }
}

if (Test-Path $mysqlPidFile) {
    $mysqlPid = (Get-Content $mysqlPidFile -Raw).Trim()
    if ($mysqlPid -match '^\d+$') {
        try {
            Stop-Process -Id ([int]$mysqlPid) -Force -ErrorAction Stop
            Write-Host "MySQL process stopped by pid $mysqlPid" -ForegroundColor Yellow
            exit 0
        } catch {}
    }
}

$listener = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    $owningPid = $listener[0].OwningProcess
    try {
        $process = Get-Process -Id $owningPid -ErrorAction Stop
        if ($process.ProcessName -like 'mysqld*') {
            Stop-Process -Id $owningPid -Force -ErrorAction Stop
            Write-Host "MySQL process stopped by port owner PID=$owningPid" -ForegroundColor Yellow
            exit 0
        }
        Write-Host "Port $port is occupied by non-MySQL process PID=$owningPid ($($process.ProcessName)); skip killing." -ForegroundColor Yellow
        exit 1
    } catch {
        Write-Host "Unable to inspect port owner PID=$owningPid; skip killing." -ForegroundColor Yellow
        exit 1
    }
}

Write-Host 'MySQL is not running.' -ForegroundColor Gray

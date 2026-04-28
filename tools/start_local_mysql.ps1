$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false

$repo = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path 'X:\')) {
    cmd /c ("subst X: `"" + $repo + "`"") | Out-Null
}
if (-not (Test-Path 'X:\')) {
    throw 'Failed to map project root to X:'
}
$mysqlRoot = 'X:\.mysql'
$dataDir = Join-Path $mysqlRoot 'data'
Write-Host "MySQL project root mapped to X: -> $repo" -ForegroundColor Gray
Write-Host "MySQL data dir: $dataDir" -ForegroundColor Gray
$logsDir = Join-Path $mysqlRoot 'logs'
$runDir = Join-Path $mysqlRoot 'run'
$tmpDir = Join-Path $mysqlRoot 'tmp'
$config = Join-Path $mysqlRoot 'my.ini'
$mysqld = if ($env:XUANQIONG_WENSHU_MYSQLD_PATH) { $env:XUANQIONG_WENSHU_MYSQLD_PATH } else { 'D:/download/MySQL/bin/mysqld.exe' }
$mysqladmin = if ($env:XUANQIONG_WENSHU_MYSQLADMIN_PATH) { $env:XUANQIONG_WENSHU_MYSQLADMIN_PATH } else { 'D:/download/MySQL/bin/mysqladmin.exe' }
$defaultsExtra = Join-Path $mysqlRoot 'client.cnf'
$port = 3309
$appClientDefaults = @"
[client]
host=127.0.0.1
port=$port
user=xuanqiong_wenshu
password=k6y4OZKO8F9H3vqPXZl38Sy8dKMW3fkX
protocol=tcp
default-character-set=utf8mb4
"@

if (-not (Test-Path $mysqld)) {
    throw "Missing mysqld.exe: $mysqld。可通过环境变量 XUANQIONG_WENSHU_MYSQLD_PATH 覆盖路径。"
}
if (-not (Test-Path $mysqladmin)) {
    throw "Missing mysqladmin.exe: $mysqladmin。可通过环境变量 XUANQIONG_WENSHU_MYSQLADMIN_PATH 覆盖路径。"
}
if (-not (Test-Path $config)) {
    throw "Missing MySQL config: $config"
}

New-Item -ItemType Directory -Force -Path $dataDir, $logsDir, $runDir, $tmpDir | Out-Null

if ((Test-Path (Join-Path $dataDir 'mysql')) -and -not (Test-Path $defaultsExtra)) {
    Set-Content -Path $defaultsExtra -Value $appClientDefaults -Encoding ASCII
}

function Test-MySqlReady {
    if (-not (Test-Path $defaultsExtra)) { return $false }
    $command = '"{0}" --defaults-extra-file="{1}" --protocol=tcp ping >nul 2>nul' -f $mysqladmin, $defaultsExtra
    cmd /c $command | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Wait-MySqlReady {
    param([int]$TimeoutSeconds = 45)

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-MySqlReady) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

if (Test-Path (Join-Path $dataDir 'mysql')) {
    if (Test-MySqlReady) {
        Write-Host "MySQL already running on 127.0.0.1:$port" -ForegroundColor Green
        exit 0
    }

    $existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($existing) {
        throw "Port $port is already occupied by another process."
    }

    $process = Start-Process -FilePath $mysqld `
        -ArgumentList @("--defaults-file=$config", '--console') `
        -WorkingDirectory $mysqlRoot `
        -RedirectStandardOutput (Join-Path $logsDir 'stdout.log') `
        -RedirectStandardError (Join-Path $logsDir 'stderr.log') `
        -PassThru

    if (-not (Wait-MySqlReady)) {
        throw "MySQL start timeout. Check .mysql/logs/error.log"
    }

    Write-Host "MySQL started, PID=$($process.Id), port=$port" -ForegroundColor Green
    exit 0
}

$bootstrap = Join-Path $mysqlRoot 'bootstrap.sql'
if (-not (Test-Path $bootstrap)) {
    throw 'Missing .mysql/bootstrap.sql'
}

& $mysqld --defaults-file="$config" --initialize-insecure --console
if ($LASTEXITCODE -ne 0) {
    throw 'mysqld --initialize-insecure failed'
}

Set-Content -Path $defaultsExtra -Value $appClientDefaults -Encoding ASCII

$process = Start-Process -FilePath $mysqld `
    -ArgumentList @("--defaults-file=$config", "--init-file=$bootstrap", '--console') `
    -WorkingDirectory $mysqlRoot `
    -RedirectStandardOutput (Join-Path $logsDir 'stdout.log') `
    -RedirectStandardError (Join-Path $logsDir 'stderr.log') `
    -PassThru

if (-not (Wait-MySqlReady)) {
    throw "Initialized MySQL but startup timed out. Check .mysql/logs/error.log"
}

Write-Host "MySQL initialized and started, PID=$($process.Id), port=$port" -ForegroundColor Green

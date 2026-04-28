param(
    [ValidateSet('quick', 'smoke', 'full')]
    [string]$Suite = 'quick'
)

$ErrorActionPreference = 'Stop'

[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = $scriptPath
$pwshCmd = Get-Command pwsh -ErrorAction SilentlyContinue
$powershellRunner = if ($pwshCmd) { $pwshCmd.Source } else { 'powershell.exe' }

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

function Get-DotEnvValue {
    param(
        [string]$Path,
        [string]$Name,
        [string]$Default = ''
    )

    if (-not (Test-Path $Path)) {
        return $Default
    }

    foreach ($rawLine in Get-Content $Path) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith('#')) {
            continue
        }
        $parts = $line.Split('=', 2)
        if ($parts.Count -ne 2) {
            continue
        }
        if ($parts[0].Trim() -eq $Name) {
            return $parts[1].Trim().Trim('"').Trim("'")
        }
    }

    return $Default
}

function Import-DotEnvVariables {
    param(
        [string]$Path
    )

    if (-not (Test-Path $Path)) {
        return
    }

    foreach ($rawLine in Get-Content $Path) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith('#')) {
            continue
        }
        $parts = $line.Split('=', 2)
        if ($parts.Count -ne 2) {
            continue
        }

        $name = $parts[0].Trim()
        if (-not $name) {
            continue
        }

        $value = $parts[1].Trim().Trim('"').Trim("'")
        if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name))) {
            [Environment]::SetEnvironmentVariable($name, $value)
        }
    }
}

$backendHost = Get-EnvValue -Names @('XUANQIONG_WENSHU_BACKEND_HOST') -Default '127.0.0.1'
$backendPortValue = Get-EnvValue -Names @('XUANQIONG_WENSHU_BACKEND_PORT') -Default '8013'
$frontendHost = Get-EnvValue -Names @('XUANQIONG_WENSHU_FRONTEND_HOST') -Default '127.0.0.1'
$frontendPortValue = Get-EnvValue -Names @('XUANQIONG_WENSHU_FRONTEND_PORT') -Default '5174'

$env:XUANQIONG_WENSHU_BACKEND_HOST = $backendHost
$env:XUANQIONG_WENSHU_BACKEND_PORT = $backendPortValue
$env:XUANQIONG_WENSHU_FRONTEND_HOST = $frontendHost
$env:XUANQIONG_WENSHU_FRONTEND_PORT = $frontendPortValue

$backendBaseUrlValue = Get-EnvValue -Names @('XUANQIONG_WENSHU_BACKEND_BASE_URL')
$frontendBaseUrlValue = Get-EnvValue -Names @('XUANQIONG_WENSHU_FRONTEND_BASE_URL')

$backendBaseUrl = if ($backendBaseUrlValue) {
    $backendBaseUrlValue.TrimEnd('/')
} else {
    "http://${backendHost}:${backendPortValue}"
}
$env:XUANQIONG_WENSHU_BACKEND_BASE_URL = $backendBaseUrl
$frontendBaseUrl = if ($frontendBaseUrlValue) {
    $frontendBaseUrlValue.TrimEnd('/')
} else {
    "http://${frontendHost}:${frontendPortValue}"
}
$frontendProxyHealthUrl = "$frontendBaseUrl/api/health"

$backendDir = Join-Path $repo 'backend'
$backendPython = Join-Path $backendDir '.venv\Scripts\python.exe'
$frontendDir = Join-Path $repo 'frontend'
$backendEnvPath = Join-Path $backendDir '.env'
$stepResults = New-Object System.Collections.Generic.List[object]
Import-DotEnvVariables -Path $backendEnvPath

$existingPythonPath = [Environment]::GetEnvironmentVariable('PYTHONPATH')
if ([string]::IsNullOrWhiteSpace($existingPythonPath)) {
    $env:PYTHONPATH = $backendDir
} elseif (-not ($existingPythonPath.Split([IO.Path]::PathSeparator) -contains $backendDir)) {
    $env:PYTHONPATH = "$backendDir$([IO.Path]::PathSeparator)$existingPythonPath"
}

function Test-PlaceholderValue {
    param(
        [string]$Value,
        [string[]]$PlaceholderTokens = @(),
        [int]$MinLength = 8
    )

    $normalized = ''
    if (-not [string]::IsNullOrWhiteSpace($Value)) {
        $normalized = $Value.Trim().ToLowerInvariant()
    }
    if (-not $normalized) {
        return $true
    }
    if ($normalized.Length -lt $MinLength) {
        return $true
    }
    if ($normalized -like '*请替换*' -or $normalized -like '*change-me*' -or $normalized -like '*changeme*' -or $normalized -like '*replace*') {
        return $true
    }
    foreach ($token in $PlaceholderTokens) {
        if ($normalized -eq $token.ToLowerInvariant()) {
            return $true
        }
    }
    return $false
}

$secretKey = Get-EnvValue -Names @('SECRET_KEY') -Default (Get-DotEnvValue -Path $backendEnvPath -Name 'SECRET_KEY')
if ([string]::IsNullOrWhiteSpace($secretKey)) {
    throw "缺少 SECRET_KEY：请先在 backend/.env 配置，再运行验证。"
}
if (Test-PlaceholderValue -Value $secretKey -MinLength 32 -PlaceholderTokens @('changeme', 'replace-me', 'replace_this_secret', 'your-secret-key', 'your_secret_key', 'your-secret-key-change-me-to-random-string', 'dev-secret-key-change-me')) {
    throw "SECRET_KEY 仍是占位值、包含明显占位语义或长度不足 32：请先在 backend/.env 配置真实密钥，再运行验证。"
}
$env:SECRET_KEY = $secretKey

if (-not (Test-Path $backendPython)) {
    throw "Missing backend virtualenv: $backendPython"
}

$npmCmd = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCmd) {
    $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
}
if (-not $npmCmd) {
    throw 'npm not found'
}

function Add-StepResult {
    param(
        [string]$Name,
        [string]$Status,
        [string]$Detail = ''
    )

    $stepResults.Add([pscustomobject]@{
        Name = $Name
        Status = $Status
        Detail = $Detail
    }) | Out-Null
}

function Show-StepSummary {
    Write-Host "`n验证步骤摘要:" -ForegroundColor Cyan
    foreach ($step in $stepResults) {
        $color = switch ($step.Status) {
            'PASS' { 'Green' }
            'FAIL' { 'Red' }
            default { 'Yellow' }
        }
        $line = "  [$($step.Status)] $($step.Name)"
        if ($step.Detail) {
            $line += " - $($step.Detail)"
        }
        Write-Host $line -ForegroundColor $color
    }
}

function Invoke-ExternalStep {
    param(
        [string]$Description,
        [scriptblock]$Command
    )

    Write-Host "`n[运行] $Description" -ForegroundColor Cyan
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Command
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($exitCode -ne 0) {
        Add-StepResult -Name $Description -Status 'FAIL' -Detail "exit=$exitCode"
        throw "$Description failed with exit code $exitCode"
    }
    Add-StepResult -Name $Description -Status 'PASS'
}

function Invoke-BufferedExternalStep {
    param(
        [string]$Description,
        [scriptblock]$Command,
        [int]$PreviewLines = 12
    )

    Write-Host "`n[运行] $Description" -ForegroundColor Cyan
    $logPath = Join-Path ([IO.Path]::GetTempPath()) ("verify-" + [guid]::NewGuid().ToString('N') + '.log')
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Command *> $logPath
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        if (Test-Path $logPath) {
            Write-Host "[失败输出] $Description（最后 $PreviewLines 行）" -ForegroundColor Yellow
            Get-Content $logPath -Tail $PreviewLines | ForEach-Object { Write-Host $_ }
        }
        Add-StepResult -Name $Description -Status 'FAIL' -Detail "exit=$exitCode; log=$logPath"
        throw "$Description failed with exit code $exitCode"
    }

    $interesting = @()
    if (Test-Path $logPath) {
        $interesting = Get-Content $logPath | Where-Object {
            $_ -match 'error|warning|failed|failed to|built in|type-check|typecheck|vite v|transforming|rendering|computing gzip size' -or
            $_ -match '构建|完成|耗时|通过'
        }
    }
    if ($interesting.Count -gt 0) {
        $interesting | Select-Object -Last $PreviewLines | ForEach-Object { Write-Host $_ -ForegroundColor DarkGray }
    } else {
        Write-Host "[摘要] $Description 已通过；详细输出已折叠。" -ForegroundColor DarkGray
    }

    if (Test-Path $logPath) {
        Remove-Item $logPath -Force -ErrorAction SilentlyContinue
    }
    Add-StepResult -Name $Description -Status 'PASS'
}

function Test-ServiceReachable {
    param(
        [string]$Url,
        [int]$TimeoutSec = 3
    )

    try {
        $resp = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec $TimeoutSec
        return ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 500)
    } catch {
        return $false
    }
}

function Assert-ServiceReachable {
    param(
        [string]$Name,
        [string]$Url
    )

    if (Test-ServiceReachable -Url $Url) {
        Write-Host "[正常] ${Name} 可访问：${Url}" -ForegroundColor Green
        Add-StepResult -Name $Name -Status 'PASS' -Detail $Url
        return
    }

    Add-StepResult -Name $Name -Status 'FAIL' -Detail $Url
    throw "${Name} 当前不可访问：${Url}。请先运行 ./start.ps1。"
}

Write-Host "=== 玄穹文枢验证 ===" -ForegroundColor Cyan
Write-Host "套件：$Suite" -ForegroundColor Gray
Write-Host "后端：$backendBaseUrl" -ForegroundColor Gray
Write-Host "前端：$frontendBaseUrl" -ForegroundColor Gray
Write-Host "后端 .env：$backendEnvPath" -ForegroundColor Gray

$dbProvider = Get-DotEnvValue -Path $backendEnvPath -Name 'DB_PROVIDER' -Default 'sqlite'
if ($dbProvider -eq 'mysql') {
    Invoke-ExternalStep '按需启动本地 MySQL' {
        & $powershellRunner -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repo 'tools\start_local_mysql.ps1')
    }
}

$requiresLiveStack = $Suite -in @('smoke', 'full')
if ($requiresLiveStack) {
    $backendHealthUrl = "$backendBaseUrl/api/health"
    $frontendHealthUrl = $frontendBaseUrl
    $backendReady = Test-ServiceReachable -Url $backendHealthUrl
    $frontendReady = Test-ServiceReachable -Url $frontendHealthUrl
    $frontendProxyReady = Test-ServiceReachable -Url $frontendProxyHealthUrl
    if (-not ($backendReady -and $frontendReady -and $frontendProxyReady)) {
        Invoke-ExternalStep '按需启动正式栈' {
            & $powershellRunner -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repo 'start.ps1')
        }
    }
}

if ($Suite -in @('quick', 'full')) {
    Invoke-BufferedExternalStep '前端类型检查' {
        & $powershellRunner -NoProfile -ExecutionPolicy Bypass -Command "& '$($npmCmd.Source)' --prefix '$frontendDir' run type-check"
    }
    Invoke-BufferedExternalStep '前端生产构建' {
        & $powershellRunner -NoProfile -ExecutionPolicy Bypass -Command "& '$($npmCmd.Source)' --prefix '$frontendDir' run build-only"
    }

    Push-Location $backendDir
    try {
        Invoke-ExternalStep '运行后端 phase4 pytest' { & .\.venv\Scripts\python.exe -m pytest app/services/test_phase4_integration.py }
    } finally {
        Pop-Location
    }
}

if ($Suite -in @('smoke', 'full')) {
    Assert-ServiceReachable -Name '后端健康检查' -Url "$backendBaseUrl/api/health"
    Assert-ServiceReachable -Name '前端首页' -Url $frontendBaseUrl
    Assert-ServiceReachable -Name '前端代理健康检查' -Url $frontendProxyHealthUrl

    Invoke-ExternalStep 'OpenAPI 路由冒烟检查' { & $backendPython (Join-Path $repo 'tools\smoke_api_routes.py') }
    Invoke-ExternalStep 'LLM 设置冒烟检查' { & $backendPython (Join-Path $repo 'tools\smoke_llm_settings_health.py') }
}

if ($Suite -eq 'full') {
    Push-Location $backendDir
    try {
        Invoke-ExternalStep '运行 token 与线索 E2E' { & .\.venv\Scripts\python.exe scripts/e2e_token_clue_validation.py }
        Invoke-ExternalStep '运行风格与记忆 E2E' { & .\.venv\Scripts\python.exe scripts/e2e_style_memory_validation.py }
        Invoke-ExternalStep '运行外部文风 E2E' { & .\.venv\Scripts\python.exe scripts/e2e_external_style_validation.py }
        Invoke-ExternalStep '运行大纲 E2E' { & .\.venv\Scripts\python.exe scripts/e2e_outline_validation.py }
        Invoke-ExternalStep '运行写作台生成/评审/确认/终止 E2E' { & .\.venv\Scripts\python.exe scripts/e2e_writingdesk_generation_evaluation_validation.py }
        Invoke-ExternalStep '运行伏笔图谱 E2E' { & .\.venv\Scripts\python.exe scripts/e2e_foreshadowing_graph_validation.py }
        Invoke-ExternalStep '运行并发链路冒烟验证' { & .\.venv\Scripts\python.exe scripts/concurrency_smoke_validation.py }
    } finally {
        Pop-Location
    }
}

Show-StepSummary
Write-Host "`n[通过] 验证套件 '$Suite' 已完成。" -ForegroundColor Green
exit 0

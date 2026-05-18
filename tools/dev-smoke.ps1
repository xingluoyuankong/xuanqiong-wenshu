param(
  [int]$BackendPort = 8013,
  [int]$FrontendPort = 5174,
  [string]$SqlitePath = "storage/xuanqiong_wenshu_smoke.db",
  [switch]$SkipScreenshot
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$ReportsDir = Join-Path $RepoRoot "docs\reports"
New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null

function Test-Port([int]$Port) {
  return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Wait-Http([string]$Url, [int]$Seconds = 30) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  do {
    try {
      return Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
    } catch {
      Start-Sleep -Seconds 1
    }
  } while ((Get-Date) -lt $deadline)
  throw "HTTP endpoint not ready: $Url"
}

if (-not (Test-Port $BackendPort)) {
  $backendCommand = "`$env:DB_PROVIDER='sqlite'; `$env:SQLITE_DB_PATH='$SqlitePath'; Set-Location -LiteralPath '$BackendDir'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort"
  Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand) -WindowStyle Hidden | Out-Null
}

if (-not (Test-Port $FrontendPort)) {
  Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev", "--", "--host", "127.0.0.1", "--port", "$FrontendPort") -WorkingDirectory $FrontendDir -WindowStyle Hidden | Out-Null
}

$health = Wait-Http "http://127.0.0.1:$BackendPort/api/health" 45
$frontendHome = Wait-Http "http://127.0.0.1:$FrontendPort/" 45

$smokeTitle = "SmokeProject-" + (Get-Date -Format "yyyyMMddHHmmss")
$body = @{ title = $smokeTitle; initial_prompt = "smoke prompt" } | ConvertTo-Json -Compress
$created = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/novels" -Method Post -ContentType "application/json; charset=utf-8" -Body $body -TimeoutSec 15
$status = Invoke-RestMethod -Uri "http://127.0.0.1:$BackendPort/api/novels/$($created.id)/blueprint/generate/status" -Method Get -TimeoutSec 15

$screenshotFileName = "frontend-home-smoke-$(Get-Date -Format yyyy-MM-dd-HHmmss).png"
$screenshotPath = Join-Path $ReportsDir $screenshotFileName
$screenshotPathForNode = "../docs/reports/$screenshotFileName"
$screenshot = $null
if (-not $SkipScreenshot) {
  $edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
  if (Test-Path $edge) {
    $nodeScript = @"
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: '$($edge.Replace('\', '/'))' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const errors = [];
  page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
  await page.goto('http://127.0.0.1:$FrontendPort/', { waitUntil: 'networkidle', timeout: 30000 });
  await page.screenshot({ path: '$screenshotPathForNode', fullPage: true });
  const text = await page.locator('body').innerText();
  await browser.close();
  console.log(JSON.stringify({ hasMojibake: text.includes('????'), consoleErrors: errors }));
})();
"@
    Push-Location $FrontendDir
    try { $browserResult = $nodeScript | node - } finally { Pop-Location }
    $screenshot = @{ path = $screenshotPath; browser = ($browserResult | ConvertFrom-Json) }
  }
}

$result = [ordered]@{
  backend_health = ($health.Content | ConvertFrom-Json)
  frontend_status = $frontendHome.StatusCode
  created_project_id = $created.id
  created_project_title = $created.title
  blueprint_status = $status.status
  screenshot = $screenshot
}
$result | ConvertTo-Json -Depth 8




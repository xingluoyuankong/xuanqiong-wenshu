param(
  [int]$BackendPort = 8013,
  [int]$FrontendPort = 5174,
  [string]$SqlitePath = "storage/xuanqiong_wenshu_e2e.db"
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

function Wait-Http([string]$Url, [int]$Seconds = 45) {
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

Wait-Http "http://127.0.0.1:$BackendPort/api/health" 60 | Out-Null
Wait-Http "http://127.0.0.1:$FrontendPort/" 60 | Out-Null

$stamp = Get-Date -Format "yyyy-MM-dd-HHmmss"
$screenshotFileName = "e2e-inspiration-to-export-$stamp.png"
$screenshotPathForNode = "../docs/reports/$screenshotFileName"
$jsonReportFileName = "e2e-inspiration-to-export-$stamp.json"
$jsonReportPathForNode = "../docs/reports/$jsonReportFileName"
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edge)) {
  throw "Microsoft Edge executable not found: $edge"
}

$nodeScript = @"
const fs = require('fs');
const { chromium, request } = require('playwright');

const backend = 'http://127.0.0.1:$BackendPort';
const frontend = 'http://127.0.0.1:$FrontendPort';
const title = 'E2E-Inspiration-To-Export-' + Date.now();
const projectHealthText = '\u9879\u76ee\u5065\u5eb7\u68c0\u67e5';
const contentHealthText = '\u6b63\u6587\u72b6\u6001';
const longContent = [
  'Rain falls on the old overpass like scattered silver needles. Lin Che stands beneath the advertising screen and hears the forgotten book turn a page inside his chest.',
  'He thinks inspiration is only another way to escape reality, until every shadow on the street starts leaning toward the same locked underground bookstore.',
  'The brass bell above the door rings three times without wind. No one is behind the counter. A blue-black notebook lies open under the lamp, carrying his name and a mistake he has not yet made.',
  'Lin Che does not touch it immediately. He records the door number, the smell of wet dust, the rhythm of rain, and the direction of cracks on the wall, because every detail may become evidence in the next chapter.',
].join('\\n\\n');

(async () => {
  const api = await request.newContext({ baseURL: backend });
  const created = await (await api.post('/api/novels', {
    data: { title, initial_prompt: 'Start from a rainy old bookstore and build an urban mystery fantasy novel.' }
  })).json();

  const blueprint = {
    title,
    genre: 'Urban mystery fantasy',
    style: 'Restrained, cinematic, and cold',
    tone: 'Mysterious and tense',
    target_audience: 'Readers who enjoy long-form urban mysteries',
    one_sentence_summary: 'A young restorer receives a book that writes the future and must investigate disappearing civic memory.',
    full_synopsis: 'After Lin Che finds the forgotten book, he discovers that someone is deleting public memory across the city and follows the predictions backward.',
    world_setting: { core_rules: 'Memory can be written, pawned, and deleted; deleted memory becomes an echo in the city shadow.' },
    characters: [
      { name: 'Lin Che', identity: 'Old book restorer', personality: 'Cautious, sharp, and curious', goals: 'Find the source of memory loss' },
      { name: 'Xu Deng', identity: 'Underground radio host', personality: 'Witty and skeptical', goals: 'Preserve erased city voices' }
    ],
    relationships: [
      { character_from: 'Lin Che', character_to: 'Xu Deng', description: 'A cautious and mutually testing alliance' }
    ],
    chapter_outline: [
      { chapter_number: 1, title: 'Rainy Old Bookstore', summary: 'Lin Che enters a closed bookstore and finds a notebook that writes his future.' }
    ]
  };

  await api.post('/api/novels/' + created.id + '/blueprint/save', { data: blueprint });
  await api.post('/api/writer/novels/' + created.id + '/chapters/edit-fast', {
    data: { chapter_number: 1, content: longContent }
  });

  const exportResp = await api.get('/api/novels/' + created.id + '/export/txt');
  const exported = await exportResp.text();
  const browser = await chromium.launch({ headless: true, executablePath: '$($edge.Replace('\', '/'))' });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1200 } });
  const consoleErrors = [];
  page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
  await page.goto(frontend + '/novel/' + created.id, { waitUntil: 'networkidle', timeout: 45000 });
  const firstChapterChip = page.locator('.wd-strip-chip').first();
  if (await firstChapterChip.count()) {
    await firstChapterChip.click();
    await page.waitForTimeout(600);
  }
  const bodyText = await page.locator('body').innerText();
  await page.screenshot({ path: '$screenshotPathForNode', fullPage: true });
  await browser.close();

  const result = {
    ok: exportResp.ok() && exported.includes('Rainy Old Bookstore') && bodyText.includes(projectHealthText) && bodyText.includes(contentHealthText),
    project_id: created.id,
    title,
    export_status: exportResp.status(),
    export_contains_title: exported.includes('Rainy Old Bookstore'),
    ui_contains_health_panel: bodyText.includes(projectHealthText),
    ui_contains_content_health: bodyText.includes(contentHealthText),
    has_mojibake: bodyText.includes('????') || exported.includes('????'),
    console_errors: consoleErrors,
    screenshot: '$screenshotPathForNode'
  };
  fs.writeFileSync('$jsonReportPathForNode', JSON.stringify(result, null, 2), 'utf8');
  console.log(JSON.stringify(result, null, 2));
  if (!result.ok || result.has_mojibake || consoleErrors.length) process.exit(1);
})();
"@

Push-Location $FrontendDir
try {
  $result = $nodeScript | node -
} finally {
  Pop-Location
}

$result

param(
  [int]$BackendPort = 8013,
  [int]$FrontendPort = 5174,
  [string]$SqlitePath = "storage/xuanqiong_wenshu_dialog_e2e.db"
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

function Wait-Http([string]$Url, [int]$Seconds = 60) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  do {
    try { return Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 } catch { Start-Sleep -Seconds 1 }
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
$jsonReportPathForNode = "../docs/reports/e2e-writing-desk-dialogs-$stamp.json"
$screenshotDirForNode = "../docs/reports/e2e-writing-desk-dialogs-$stamp"
$edge = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edge)) { throw "Microsoft Edge executable not found: $edge" }

$nodeScript = @"
const fs = require('fs');
const { chromium, request } = require('playwright');

const backend = 'http://127.0.0.1:$BackendPort';
const frontend = 'http://127.0.0.1:$FrontendPort';
const title = 'E2E-Dialog-Probe-' + Date.now();
const screenshotDir = '$screenshotDirForNode';
fs.mkdirSync(screenshotDir, { recursive: true });
const probes = [
  'version-detail',
  'evaluation-detail',
  'version-diff',
  'patch-diff',
  'skill-selector',
  'reader',
  'generate-chapter',
  'edit-chapter',
  'generate-outline'
];
const longContent = [
  'The rain writes silver code across the bookstore window while Lin Che waits for the bell to ring by itself.',
  'A notebook opens under a blue lamp. The first line names him, the second line predicts a choice, and the third line is still being written.',
  'He records the smell of wet dust, the broken spine of an atlas, and the fact that every clock in the shop is twelve minutes slow.',
  'When the door closes behind him, the city outside forgets the shop ever existed, but the ink on his sleeve keeps moving.'
].join('\\n\\n');

(async () => {
  const api = await request.newContext({ baseURL: backend });
  const created = await (await api.post('/api/novels', { data: { title, initial_prompt: 'Dialog probe novel.' } })).json();
  const blueprint = {
    title,
    genre: 'Urban mystery fantasy',
    style: 'Cinematic',
    tone: 'Tense',
    target_audience: 'Long-form fantasy readers',
    one_sentence_summary: 'A restorer follows a book that edits civic memory.',
    full_synopsis: 'Lin Che finds a notebook that predicts erased memories and starts tracing a hidden system beneath the city.',
    world_setting: { core_rules: 'Memory can be copied, pawned, erased, and restored through written artifacts.' },
    characters: [{ name: 'Lin Che', identity: 'Book restorer', personality: 'Careful and curious', goals: 'Find the hidden archive' }],
    relationships: [],
    chapter_outline: [{ chapter_number: 1, title: 'The Bell Without Wind', summary: 'Lin Che finds the notebook in a closed bookstore.' }]
  };
  await api.post('/api/novels/' + created.id + '/blueprint/save', { data: blueprint });
  await api.post('/api/writer/novels/' + created.id + '/chapters/edit-fast', { data: { chapter_number: 1, content: longContent } });

  const browser = await chromium.launch({ headless: true, executablePath: '$($edge.Replace('\', '/'))' });
  const results = [];
  for (const probe of probes) {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
    const consoleErrors = [];
    const pageErrors = [];
    page.on('console', msg => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });
    page.on('pageerror', err => pageErrors.push(String(err && err.stack || err)));
    const url = frontend + '/novel/' + created.id + '?dialog_probe=' + encodeURIComponent(probe);
    await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 });
    await page.waitForTimeout(1800);
    if (probe === 'reader') {
      const readerButton = page.getByText('\u5c55\u5f00\u5168\u6587').first();
      if (await readerButton.count()) {
        await readerButton.click();
        await page.waitForTimeout(900);
      }
    }
    if (probe === 'generate-chapter') {
      const generateButton = page.getByRole('button', { name: /\u751f\u6210\u7b2c\s*1\s*\u7ae0/ }).first();
      if (await generateButton.count()) {
        await generateButton.click();
        await page.waitForTimeout(900);
      }
    }
    const shell = page.locator('.xq-dialog-shell, .xq-reader-dialog, .xq-diff-dialog').first();
    let hasDialog = await shell.count().then(count => count > 0);
    const bodyText = await page.locator('body').innerText();
    if (probe === 'reader') hasDialog = hasDialog || bodyText.includes('\u5168\u6587\u9605\u8bfb') || bodyText.includes('\u5b8c\u6574\u6b63\u6587');
    if (probe === 'generate-chapter') hasDialog = hasDialog || bodyText.includes('\u751f\u6210\u7ae0\u8282') || bodyText.includes('\u7ae0\u8282\u65b9\u5411');
    const screenshot = screenshotDir + '/' + probe + '.png';
    await page.screenshot({ path: screenshot, fullPage: true });
    if (hasDialog) {
      await page.keyboard.press('Escape');
      await page.waitForTimeout(250);
    }
    results.push({
      probe,
      has_dialog: hasDialog,
      has_mojibake: bodyText.includes('????') || bodyText.includes('\u951f') || bodyText.includes('\ufffd') || bodyText.includes('\u9435') || bodyText.includes('\u936a') || bodyText.includes('\u8133'),
      console_errors: consoleErrors,
      page_errors: pageErrors,
      screenshot
    });
    await page.close();
  }
  await browser.close();

  const failed = results.filter(item => !item.has_dialog || item.has_mojibake || item.console_errors.length || item.page_errors.length);
  const report = { ok: failed.length === 0, project_id: created.id, title, probes: results, failed };
  fs.writeFileSync('$jsonReportPathForNode', JSON.stringify(report, null, 2), 'utf8');
  console.log(JSON.stringify(report, null, 2));
  if (!report.ok) process.exit(1);
})().catch(err => { console.error(err); process.exit(1); });
"@

Push-Location $FrontendDir
try { $result = $nodeScript | node - } finally { Pop-Location }
$result

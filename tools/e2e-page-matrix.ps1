param(
  [int]$BackendPort = 8013,
  [int]$FrontendPort = 5178,
  [string]$SqlitePath = "storage/xuanqiong_wenshu_page_matrix.db"
)
$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BackendDir = Join-Path $RepoRoot "backend"
$FrontendDir = Join-Path $RepoRoot "frontend"
$ReportsDir = Join-Path $RepoRoot "docs\reports"
New-Item -ItemType Directory -Force -Path $ReportsDir | Out-Null
function Test-Port([int]$Port) { return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) }
function Wait-Http([string]$Url, [int]$Seconds = 60) { $deadline=(Get-Date).AddSeconds($Seconds); do { try { return Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 } catch { Start-Sleep -Seconds 1 } } while((Get-Date)-lt $deadline); throw "HTTP endpoint not ready: $Url" }
if (-not (Test-Port $BackendPort)) { $cmd="`$env:DB_PROVIDER='sqlite'; `$env:SQLITE_DB_PATH='$SqlitePath'; Set-Location -LiteralPath '$BackendDir'; .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort"; Start-Process powershell.exe -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-Command',$cmd) -WindowStyle Hidden | Out-Null }
if (-not (Test-Port $FrontendPort)) { Start-Process npm.cmd -ArgumentList @('run','dev','--','--host','127.0.0.1','--port',"$FrontendPort") -WorkingDirectory $FrontendDir -WindowStyle Hidden | Out-Null }
Wait-Http "http://127.0.0.1:$BackendPort/api/health" 60 | Out-Null
Wait-Http "http://127.0.0.1:$FrontendPort/" 60 | Out-Null
$stamp=Get-Date -Format "yyyy-MM-dd-HHmmss"
$json="../docs/reports/e2e-page-matrix-$stamp.json"
$dir="../docs/reports/e2e-page-matrix-$stamp"
$edge="C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $edge)) { throw "Microsoft Edge executable not found: $edge" }
$nodeScript=@"
const fs = require('fs');
const { chromium, request } = require('playwright');
const backend='http://127.0.0.1:$BackendPort';
const frontend='http://127.0.0.1:$FrontendPort';
const screenshotDir='$dir'; fs.mkdirSync(screenshotDir,{recursive:true});
const title='E2E-Page-Matrix-'+Date.now();
(async()=>{
 const api=await request.newContext({baseURL:backend});
 const created=await (await api.post('/api/novels',{data:{title,initial_prompt:'Page matrix project.'}})).json();
 const blueprint={title,genre:'Urban fantasy',style:'Cinematic',tone:'Tense',target_audience:'Long-form readers',one_sentence_summary:'A book edits memory.',full_synopsis:'A restorer follows erased memories.',world_setting:{core_rules:'Memory can be written.'},characters:[{name:'Lin Che',identity:'Restorer',personality:'Careful',goals:'Find archive'}],relationships:[],chapter_outline:[{chapter_number:1,title:'First Signal',summary:'The first erased memory appears.'}]};
 await api.post('/api/novels/'+created.id+'/blueprint/save',{data:blueprint});
 await api.post('/api/writer/novels/'+created.id+'/chapters/edit-fast',{data:{chapter_number:1,content:'A complete validation chapter.\\n\\nThe page matrix checks all high-value surfaces.'}});
 const pages=[
  {name:'workspace-entry',url:'/',expect:['\u7075\u611f\u6a21\u5f0f','\u9879\u76ee\u5de5\u4f5c\u53f0']},
  {name:'novel-workspace',url:'/workspace',expect:['\u5c0f\u8bf4','\u9879\u76ee']},
  {name:'inspiration-mode',url:'/inspiration',expect:['\u7075\u611f\u6a21\u5f0f','\u5bf9\u8bdd']},
  {name:'writing-desk',url:'/novel/'+created.id,expect:[title,'\u5199\u4f5c','\u7ae0']},
  {name:'admin-overview',url:'/admin?tab=statistics',expect:['\u7384\u7a79\u6587\u67a2\u7ba1\u7406\u53f0']},
  {name:'admin-novels',url:'/admin?tab=novels',expect:['\u5c0f\u8bf4\u7ba1\u7406']},
  {name:'system-settings',url:'/settings',expect:['\u7cfb\u7edf\u914d\u7f6e','\u5168\u7ad9\u7cfb\u7edf\u53c2\u6570']},
  {name:'llm-settings',url:'/llm-settings',expect:['LLM \u914d\u7f6e']},
  {name:'style-center',url:'/style-center',expect:['\u5916\u90e8\u53c2\u8003\u6587\u98ce\u5e93']},
  {name:'knowledge-graph',url:'/detail/'+created.id+'?section=knowledge_graph',expect:['\u77e5\u8bc6\u56fe\u8c31']},
  {name:'clue-tracker',url:'/detail/'+created.id+'?section=clue_tracker',expect:['\u7ebf\u7d22\u8ffd\u8e2a']}
 ];
 const browser=await chromium.launch({headless:true, executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const results=[];
 for (const vp of [{label:'desktop',width:1440,height:1100},{label:'mobile',width:390,height:844}]) {
  for (const item of pages) {
   const page=await browser.newPage({viewport:{width:vp.width,height:vp.height}});
   const consoleErrors=[]; const pageErrors=[];
   page.on('console', msg=>{ if(msg.type()==='error' && !msg.text().includes('Failed to load resource')) consoleErrors.push(msg.text()) });
   page.on('pageerror', err=>pageErrors.push(String(err&&err.stack||err)));
   await page.goto(frontend+item.url,{waitUntil:'networkidle',timeout:45000});
   await page.waitForTimeout(900);
   await page.waitForFunction((tokens)=>tokens.some(t=>document.body && document.body.innerText.includes(t)), item.expect, {timeout:8000}).catch(()=>{});
   const text=await page.locator('body').innerText();
   const path=screenshotDir+'/'+item.name+'-'+vp.label+'.png';
   await page.screenshot({path,fullPage:true});
   const visible=item.expect.some(token=>text.includes(token));
   const topbarCount=await page.locator('.xq-topbar, .xq-page-topbar').count();
   const hasUnifiedTopbar=topbarCount>0;
   const warmSurfaceAudit=await page.evaluate(()=>{
    const vw=window.innerWidth, vh=window.innerHeight;
    const points=[];
    for(let y=20;y<vh;y+=Math.max(80, Math.floor(vh/8))) for(let x=20;x<vw;x+=Math.max(90, Math.floor(vw/8))) points.push([x,y]);
    function parseRgb(value){ const m=String(value||'').match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/); return m?[Number(m[1]),Number(m[2]),Number(m[3])]:null; }
    let warm=0, sampled=0, examples=[];
    for(const [x,y] of points){
      const el=document.elementFromPoint(x,y); if(!el) continue;
      const cs=getComputedStyle(el); const rgb=parseRgb(cs.backgroundColor); if(!rgb) continue;
      const [r,g,b]=rgb;
      const isWarm = r>238 && g>210 && b<205 && (r-b)>38;
      sampled++;
      if(isWarm){ warm++; if(examples.length<5) examples.push({x,y,color:cs.backgroundColor,tag:el.tagName,cls:String(el.className||'').slice(0,120)}); }
    }
    return {sampled,warm,warm_ratio: sampled ? warm/sampled : 0, examples};
   });
   const warmSurfaceOk=warmSurfaceAudit.warm_ratio<=0.08;
   const mojibake=text.includes('????') || text.includes('\u951f') || text.includes('\ufffd') || text.includes('\u9435') || text.includes('\u936a') || text.includes('\u8133');
   results.push({page:item.name,viewport:vp.label,visible,has_unified_topbar:hasUnifiedTopbar,topbar_count:topbarCount,warm_surface_ok:warmSurfaceOk,warm_surface_audit:warmSurfaceAudit,has_mojibake:mojibake,console_errors:consoleErrors,page_errors:pageErrors,screenshot:path});
   await page.close();
  }
 }
 await browser.close();
 const failed=results.filter(r=>!r.visible||!r.has_unified_topbar||!r.warm_surface_ok||r.has_mojibake||r.console_errors.length||r.page_errors.length);
 const report={ok:failed.length===0,project_id:created.id,title,results,failed};
 fs.writeFileSync('$json',JSON.stringify(report,null,2),'utf8');
 console.log(JSON.stringify(report,null,2));
 if(!report.ok) process.exit(1);
})().catch(err=>{console.error(err);process.exit(1)});
"@
Push-Location $FrontendDir
try { $result=$nodeScript | node - } finally { Pop-Location }
$result

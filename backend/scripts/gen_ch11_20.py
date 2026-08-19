# -*- coding: utf-8 -*-
import os, sys, time, re, requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv("BIGMODEL_BASE_URL","").rstrip("/")
KEY = os.getenv("BIGMODEL_API_KEY","")
MODEL = "glm-4-flash"
OUT = Path(__file__).parent.parent / "output" / "novels"
OUT.mkdir(parents=True, exist_ok=True)

CHAPTERS = [
    (11, "清洗日", "冷冻档案揭示了几年前全市系统性记忆清洗行动"),
    (12, "线人", "研究院前雇员泄密透露更多内幕"),
    (13, "追捕", "武警追踪林七,城市街道追逐,陈蓉出手"),
    (14, "记忆投影", "林七用能力回溯过去看到黑潮真实场景"),
    (15, "码头仓库", "废弃码头的仓库里发现被遗弃的实验设备"),
    (16, "第一真相", "黑潮是人为制造——目的是控制记忆和政治"),
    (17, "南阳街", "地下记忆交易市场——买卖记忆碎片"),
    (18, "身份集市", "秘密集会:记忆身份互换,各种复制假记忆"),
    (19, "伪造记忆", "某公司批量生产假记忆并嵌入怀旧产品"),
    (20, "创始家族", "黑潮背后几大创始家族——崔氏首次登场"),
]

def call_llm(messages, temperature=0.85, max_tok=2560):
    payload = {"model":MODEL,"messages":messages,"temperature":temperature,"max_tokens":max_tok}
    for attempt in range(3):
        try:
            resp = requests.post(
                f"{BASE}/chat/completions",
                headers={"Authorization":"Bearer "+KEY,"Content-Type":"application/json"},
                json=payload, timeout=180
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            else:
                print(f"  [ERR {resp.status_code}] {resp.text[:100]}")
                time.sleep(3)
        except Exception as e:
            print(f"  [EXC] {e}")
            time.sleep(5)
    return None

SYS = "你是出版过的悬疑小说家。雾港:中国海湾城,被迷雾笼罩。核心:黑潮抹去公共记忆。主角:林七,旧档案修复师,记忆抗性。陈蓉:记忆猎人,同伴。风格:阴暗紧凑,都市异能,悬疑。每章2500-3500字。只输出正文。不要标题,不要署名。"

print("="*60)
print("  Generate Ch11-20")
print("="*60)

full_text = "# WugangEcho\n\n"
completed = 0
t_start = time.time()

for (cn, ct, cd) in CHAPTERS:
    print(f"[Ch{cn}] {ct} ...", end=" ", flush=True)
    prompt = f"写《雾港回声》第{cn}章《{ct}》。内容:{cd}。2500-3500字连贯小说。对话丰富,悬念,章末钩子/反转。只输出正文:"
    text = call_llm([{"role":"system","content":SYS},{"role":"user","content":prompt}], 0.88, 2560)
    if text:
        clean = text.strip()
        cc = len(re.sub(r"\s+","",clean))
        full_text += "\n\n## Chapter " + str(cn) + ": " + ct + "\n\n" + clean
        completed += 1
        print(f"OK [{cc}] ({completed}/{len(CHAPTERS)})")
    else:
        print("FAILED")
    time.sleep(1.5)
    if completed % 5 == 0:
        (OUT / "auto_save.md").write_text(full_text, encoding="utf-8")

file_path = OUT / f"WugangEcho_ch11-20_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
file_path.write_text(full_text, encoding="utf-8")
tc = len(re.sub(r"\s+","",full_text))
elapsed = time.time()-t_start
print(f"\nDone! {completed}/{len(CHAPTERS)} chapters, {tc} chars, {elapsed/60:.1f}min")
print(f"File: {file_path}")
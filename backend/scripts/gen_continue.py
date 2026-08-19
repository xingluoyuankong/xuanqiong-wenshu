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
    (6, "记忆猎人", "林七遇到自称为记忆猎人的陈蓉"),
    (7, "第一次黑潮", "黑潮席卷城市,林七觉醒记忆抗性"),
    (8, "对峙", "林七保护古老记忆与市政府官员正面冲突"),
    (9, "废弃冷库", "林七陈蓉潜入黑潮研究院废弃冷库"),
    (10, "冷冻档案", "发现冷冻保存的实验档案,揭示了几年前的清洗"),
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

SYS = "你是出版过的悬疑小说.雾港是被迷雾覆盖的中国海湾城。核心:黑潮抹去公共记忆。主角:林七,档案修复师,记忆抗性.风格:紧凑阴暗都市异能悬疑。只输出章节正文(1500-3500字)。不要标题,不要作者。"

print("="*60)
print("  Continue Ch6-10")
print("="*60)

# load previous progress
auto_save = OUT / "auto_save.md"
if auto_save.exists():
    full_text = auto_save.read_text(encoding="utf-8")
else:
    full_text = "# WugangEcho\n\n"

completed = 0
t_start = time.time()

for (cn, ct, cd) in CHAPTERS:
    print(f"[Ch{cn}] {ct} ...", end=" ", flush=True)
    # Get context from previous chapter (last 200 chars)
    prev_context = ""
    parts = full_text.split("## Chapter ")
    if len(parts) > 1:
        prev = parts[-1]
        prev_context = prev[-200:]

    prompt = f"写《雾港回声》第{cn}章《{ct}》。前期剧情:{prev_context}。本章要点:{cd}。连贯故事,对话,悬念,章末钩子或反转。只输出正文:"

    text = call_llm([{"role":"system","content":SYS},{"role":"user","content":prompt}], 0.88, 2560)
    if text:
        clean = text.strip()
        cc = len(re.sub(r"\s+","",clean))
        full_text += "\n\n## Chapter " + str(cn) + ": " + ct + "\n\n" + clean
        completed += 1
        print(f"OK [{cc}] ({completed}/{len(CHAPTERS)})")
    else:
        print("FAILED")
        # simpler prompt retry
        prompt2 = f"写《雾港回声》第{cn}章。很简短,300字。只输出正文。"
        text = call_llm([{"role":"system","content":SYS},{"role":"user","content":prompt2}], 0.85, 800)
        if text:
            clean = text.strip()
            full_text += "\n\n## Chapter " + str(cn) + ": " + ct + "\n\n" + clean
            completed += 1
            print("  OK(short)")
        else:
            print("  FINAL FAILED")
    time.sleep(1.5)
    auto_save.write_text(full_text, encoding="utf-8")

file_path = OUT / f"WugangEcho_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
file_path.write_text(full_text, encoding="utf-8")
tc = len(re.sub(r"\s+","",full_text))
elapsed = time.time()-t_start
print(f"\nDone! {completed}/{len(CHAPTERS)} chapters, {tc} chars, {elapsed/60:.1f}min")
print(f"File: {file_path}")
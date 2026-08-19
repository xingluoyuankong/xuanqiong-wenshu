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
    (21, "三方对弈", "记忆猎人、市政府、研究院形成三方对立"),
    (22, "记忆芯片", "核心技术:记忆编码芯片实验室被发现"),
    (23, "幕后者", "幕后主使:记忆管理局长周白首次现身"),
    (24, "红月", "黑潮失控,记忆回流,全城陷入混乱"),
    (25, "沉入记忆海", "林七进入全记忆汇聚空间"),
    (26, "黑潮源码", "意识共鸣装置:黑潮技术核心曝露"),
    (27, "镜面", "周白的真相被记忆空间折射"),
    (28, "被遗忘的代价", "林七发现自己也曾是黑潮实验体"),
    (29, "双生", "记忆海中另有一个自己的存在"),
    (30, "决裂", "林七在两个核心立场中做出根本选择"),
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

SYS = "你是出版过的悬疑小说家。雾港:中国海湾城,被迷雾笼罩。核心:黑潮抹去公共记忆。主角:林七,旧档案修复师,记忆抗性。陈蓉:记忆猎人。周白:记忆管理局局长。风格:阴暗紧凑,都市异能悬疑。每章2500-3500字。只输出正文。"

print("="*60)
print("  Generate Ch21-30")
print("="*60)

full_text = "# WugangEcho Ch21-30\n\n"
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

file_path = OUT / f"WugangEcho_ch21-30_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
file_path.write_text(full_text, encoding="utf-8")
tc = len(re.sub(r"\s+","",full_text))
elapsed = time.time()-t_start
print(f"\nDone! {completed}/{len(CHAPTERS)} chapters, {tc} chars, {elapsed/60:.1f}min")
print(f"File: {file_path}")
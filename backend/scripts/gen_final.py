# -*- coding: utf-8 -*-
import os, sys, json, time, re, requests
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
    (1, "档案室的回声", "林七在档案馆发现被黑潮抹去的记录碎片,开始追查来源"),
    (2, "记忆裂痕", "全城居民丢失对同一事件的记忆,林七发现规律"),
    (3, "隐藏的地图", "旧市政地图上有被涂改的街道名"),
    (4, "午夜来客", "有人半夜闯入档案室翻阅秘密卷宗,监控被黑潮扭曲"),
    (5, "双重档案", "档案馆存在两套完全不同的记录"),
    (6, "记忆猎人", "林七遇到自称为记忆猎人的陈蓉"),
    (7, "第一次黑潮", "黑潮席卷城市,林七觉醒记忆抗性"),
    (8, "对峙", "林七保护古老记忆与市政府官员正面冲突"),
    (9, "废弃冷库", "林七陈蓉潜入黑潮研究院废弃冷库"),
    (10, "冷冻档案", "发现冷冻保存的实验档案,揭示了几年前的清洗"),
]

def call_llm(messages, temperature=0.85, max_tok=4096):
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

SYS = "你是出版过的悬疑小说作家。雾港是被迷雾覆盖的中国海湾城。核心现象:黑潮能抹去公共记忆。主角:林七,档案修复师,拥有记忆抗性。风格:紧凑、阴暗、都异能、悬疑。只输出章节正文。字数:1500-3500字。"

print("="*60)
print("  WugangEcho Generator")
print("="*60)

full_text = "# WugangEcho\n\n"
completed = 0
t_start = time.time()

for (cn, ct, cd) in CHAPTERS:
    print(f"[Ch{cn}] {ct} ...", end=" ", flush=True)
    prompt = f"写《雾港回声》第{cn}章《{ct}》章偷开:{cd}。连贯故事，对话，悬念，章末有钩子或反转。只输出正文。动笔:"
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

file_path = OUT / f"WugangEcho_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
file_path.write_text(full_text, encoding="utf-8")
tc = len(re.sub(r"\s+","",full_text))
elapsed = time.time()-t_start
print(f"\nDone! {completed}/{len(CHAPTERS)} chapters, {tc} chars, {elapsed/60:.1f}min")
print(f"File: {file_path}")
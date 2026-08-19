"""
独立小说生成脚本 — 目标 20 万字
使用智谱 BigModel glm-4-flash (免费)
"""
import os, sys, json, time, re, requests
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()
BASE_URL = os.getenv("BIGMODEL_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").rstrip('/')
API_KEY = os.getenv("BIGMODEL_API_KEY", "")
MODEL = "glm-4-flash"
OUTPUT_DIR = Path(__file__).parent.parent / "output" / "novels"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

NOVEL_TITLE = "雾港回声"
NOVEL_THEME = """写一部都市异能悬疑长篇《雾港回声》。
主角林七原本只是旧档案修复师，在一场突发黑潮后发现整座雾港会吞掉人的公共记忆。
世界观：雾港被迷雾笼罩的海湾城市，存在"黑潮"现象，能选择性抹去记忆。少数人有"记忆抗性"。核心悬念：黑潮究竟因为何而起？
风格：气氛阴暗，节奏紧凑，对话博弈，章末钩子，冲突推进。"""

MAX_TOKENS = 4096

def call_llm(messages, temperature=0.85, max_tokens=MAX_TOKENS):
    payload = {"model": MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens, "top_p": 0.95}
    for attempt in range(3):
        try:
            r = requests.post(f"{BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json=payload, timeout=180)
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            else:
                print(f"  [API Error {r.status_code}] {r.text[:150]}")
                time.sleep(3 if "429" in str(r.status_code) else 5)
        except Exception as e:
            print(f"  [Exception] {e}")
            time.sleep(5)
    return None

def save_md(filename, content):
    (OUTPUT_DIR / filename).write_text(content, encoding="utf-8")

def count_chars(text):
    return len(re.sub(r"\s+", "", text))

# === Step 1: Outline ===
print("=" * 60)
print("Step 1: 生成多卷长篇大纲...")
print("=" * 60)

prompt = f"""你是一位资深小说家，为《{NOVEL_TITLE}》设计完整的多卷长篇大纲。

主题：{NOVEL_THEME}

要求：5卷，每卷12-15章，总70-80章。每章有 章标题(chapter_title)、摘要(summary)、关键冲突(key_conflict)、章末钩子(hook)。

输出JSON：
{{"title": "{NOVEL_TITLE}", "overall_summary": "...", "volumes": [{{"volume_number":1, "volume_title":"...", "volume_summary":"...", "chapters":[{{"chapter_number":1, "chapter_title":"...", "summary":"...", "key_conflict":"...", "hook":"...", "word_count_target":2500}}]}}]}}
只输出JSON，不要其他。"""

outline_json = call_llm([{"role":"system","content":"你是专业小说创作助手。只输出JSON数据，不要任何额外文字或解释。"},
                         {"role":"user","content":prompt}], temperature=0.9, max_tokens=8192)

if not outline_json:
    print("FAILED: outline generation")
    sys.exit(1)

outline_json = re.sub(r"```(?:json)?\s*", "", outline_json).strip()
outline = json.loads(outline_json)
total_chapters = sum(len(v["chapters"]) for v in outline["volumes"])
print(f"大纲完成: {len(outline['volumes'])} 卷, {total_chapters} 章")
save_md("00_outline.json", json.dumps(outline, ensure_ascii=False, indent=2))

# === Step 2: Generate chapters ===
full_novel = f"# {NOVEL_TITLE}\n\n> {outline.get('overall_summary','')}\n\n"
chapter_count = 0
prev_summary = ""

for vol in outline["volumes"]:
    vt = vol["volume_title"]
    print(f"\n=== 卷{vol['volume_number']}: {vt} ===")
    full_novel += f"\n\n# 第{vol['volume_number']}卷 {vt}\n\n"

    for ch in vol["chapters"]:
        cn = chapter_count + 1
        ct = ch["chapter_title"]
        full_novel += f"\n## 第{cn}章 {ct}\n\n"

        ctx = f"上一章剧情：{prev_summary}" if prev_summary else "这是开篇。"
        ch_prompt = f"""你正在写作《{NOVEL_TITLE}》。写出第{cn}章《{ct}》。
卷名：{vt}
本章概要：{ch.get("summary","")}
核心冲突：{ch.get("key_conflict","")}
章末钩子：{ch.get("hook","")}
{ctx}

写作要求：
- 正文字数2800-3500字
- 节奏紧凑，每段推动剧情
- 对话博弈真实
- 章末有悬念/反转
- 聚焦人物心理和动作
- 只输出正文，不要标题、署名、分隔线。"""

        content = call_llm([{"role":"system","content":"你是专业小说写手。输出正文，没有标题，没有元信息。"},
                            {"role":"user","content":ch_prompt}], temperature=0.88, max_tokens=4096)

        if content:
            c_str = content.strip()
            cc = count_chars(c_str)
            full_novel += c_str + "\n"
            prev_summary = c_str[-200:]
            chapter_count += 1
            print(f"  Ch{cn} [{cc}字] OK")
        else:
            print(f"  Ch{cn} FAILED")

        time.sleep(1)
        if chapter_count % 15 == 0:
            save_md(f"progress_ch{chapter_count}.md", full_novel)

# === Final save ===
final_path = OUTPUT_DIR / f"雾港回声_完整版_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
final_path.write_text(full_novel, encoding="utf-8")
total_chars = count_chars(full_novel)

print(f"\n{'='*60}")
print(f"  完成! {chapter_count}章, {total_chars}字")
print(f"  文件: {final_path}")
print(f"{'='*60}")

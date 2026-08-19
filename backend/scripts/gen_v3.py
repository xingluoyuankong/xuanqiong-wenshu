# -*- coding: utf-8 -*-
"""雾港回声 - 20万字小说生成器 v3
使用智谱GLM-4-Flash免费API逐章生成
"""
import os, sys, json, time, re, requests
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()
BASE = os.getenv("BIGMODEL_BASE_URL","https://open.bigmodel.cn/api/paas/v4").rstrip("/")
KEY = os.getenv("BIGMODEL_API_KEY","")
MODEL = "glm-4-flash"
OUT = Path(__file__).parent.parent / "output" / "novels"
OUT.mkdir(parents=True, exist_ok=True)

VOLUMES = [
    ("卷一:黑潮之始", [
        (1,"档案室的回声","林七修复档案时发现被黑潮抹去的记录碎片，追查其源头。"),
        (2,"记忆裂痕","全市部分居民开始丢失对同一件事的记忆。"),
        (3,"隐藏的地图","旧地图上有被涂改的街道名，提示秘密地点。"),
        (4,"午夜来客","有人闯入档案室翻阅特定卷宗，监控录像被黑潮扭曲。"),
        (5,"双重档案","档案馆存在两套完全不同的记录——官方和真相。"),
        (6,"记忆猎人","林七遇到自称记忆猎人的女子陈蓉。"),
        (7,"第一次黑潮","黑潮席卷，林七首次体验记忆抗性。"),
        (8,"对峙","林七保护一份古老记忆，与市政府官员正面冲突。"),
    ]),
    ("卷二:忘记的战争", [
        (9,"废弃冷库","林七和陈蓉潜入黑潮研究院的一个废弃设施。"),
        (10,"冷冻档案","发现一批被冷冻的实验档案——揭示过去的清洗。"),
        (11,"前朝遗事","阅读冷冻档案揭示了几年前一次系统性记忆清除。"),
        (12,"钟楼对质","林七秘密约见的一位研究院前雇员透露内幕。"),
        (13,"追捕","警卫追踪林七，城市街道追逐，陈蓉出手。"),
        (14,"记忆投影","林七用能力回看过去——黑潮的真实场景。"),
        (15,"废弃码头","在码头仓库里发现老实验设备和记录。"),
        (16,"第一真相","黑潮是人为制造——人为了控制记忆和政治。"),
    ]),
    ("卷三:记忆市场", [
        (17,"南阳街","发现地下记忆交易场——人们把记忆卖给他权。"),
        (18,"谎言市场","一个秘密集市，身份和made-up记忆互换。"),
        (19,"伪造的记忆","某公司大量制作假记忆链接到怀旧产品。"),
        (20,"崔氏家族","黑潮背后几大创始家族之一初次登场。"),
        (21,"三层对立","记忆猎人、市政府、研究院形成三方对立。"),
        (22,"记忆芯片","核心技术——记忆编码芯片的实验室被发现。"),
        (23,"掌门人","幕后主使出现——记忆管理局局长周白。"),
        (24,"血月夜","黑潮失控，记忆开始回流，全城陷入混乱。"),
    ]),
    ("卷四:记忆之海", [
        (25,"记忆海","林七进入记忆集合空间——所有人的记忆流。"),
        (26,"源头","披露了黑潮起源——意识共鸣装置。"),
        (27,"镜面","周白的真实身份被折射在林七的原有记忆之上。"),
        (28,"回忆制成的墙","林七记起曾被抹去的身份——他自己也是实验体。"),
        (29,"镜像林七","记忆海中另一个自己的存在——揭示了分裂的记忆。"),
        (30,"决裂","林七不得不在两种立场中做出根本选择。"),
        (31,"浪潮的中央","林七在意识神经中心对峙黑潮源头。"),
        (32,"重生之门","记忆和遗忘的边界被打通——林七做决断。"),
    ]),
    ("卷五:雾港的天空", [
        (33,"审判","林七作为关键证人面对公众，记忆回流造成的社会冲突进入公开审判。"),
        (34,"公投","全城投票——接受记忆还是继续遗忘。"),
        (35,"代价","记忆恢复后，一些人崩溃并丧失现实感，林七必须承担选择的后果。"),
        (36,"和解","林七和陈蓉建立新的信任关系，城市开始寻找共存方案。"),
        (37,"黑潮残响","黑潮残余冲击再次威胁城市，林七清查最后的记忆碎片。"),
        (38,"真相回归","多年隐藏的真相被公开，公众开始艰难地接受完整历史。"),
        (39,"新秩序","记忆与遗忘的边界被重新定义，新的社会秩序逐步建立。"),
        (40,"雾港的日出","林七在晨光中眺望未来的城市，并发现黑潮仍留下一缕回声。"),

    ]),
]

def call(messages, temp=0.85, mtok=4096):
    p = {"model":MODEL,"messages":messages,"temperature":temp,"max_tokens":mtok,"top_p":0.95}
    if not KEY:
        raise RuntimeError("未配置 BIGMODEL_API_KEY，拒绝无提示地启动生成")
    for attempt in range(3):
        try:
            r = requests.post(f"{BASE}/chat/completions",
                headers={"Authorization":"Bearer "+KEY,"Content-Type":"application/json"},
                json=p, timeout=180)
            if r.status_code==200:
                return r.json()["choices"][0]["message"]["content"]
            else:
                print(f"  [Err {r.status_code}] {r.text[:100]}")
                time.sleep(3 if r.status_code == 429 else 5)
        except Exception as e:
            print(f"  [Exc] {e}")
            time.sleep(5)
    return None

all_chs = []
for vn, chs in VOLUMES:
    for (cn, ct, *_) in chs:
        all_chs.append((vn, cn, ct))

print("="*60)
print(f"  雾港回声生成器 v3")
print(f"  共 {len(all_chs)} 章")
print("="*60)

full = "# 雾港回声\n\n"
done = 0
previous_summary = "这是故事开篇。"
t0 = time.time()

for (vn, cn, ct) in all_chs:
    print(f"[Ch{cn}] {ct} ...", end=" ", flush=True)
    chapter_summary = next(
        (str(item[2]) for volume_name, chapters in VOLUMES if volume_name == vn
         for item in chapters if int(item[0]) == int(cn)),
        "推动主线冲突并留下新的悬念。",
    )
    content = call([
        {"role":"system","content":"你是出版过悬疑小说的专业作家。擅长氛围、悬念和节奏。只输出正文，无标题、无作者名。城市背景：雾港是一座被迷雾覆盖的现代中国海湾城。主角：林七。核心设定：黑潮——能抹去公共记忆现象。记忆抗性——少数人能保留记忆碎片。记忆市场——被遗忘记忆的交易。风格：紧凑、紧张、都市、异能、悬疑。字数：1800-3500字。"},
        {"role":"user","content":"写《雾港回声》第"+str(cn)+"章《"+ct+"》。卷信息：卷名《"+vn+"》。本章概要："+chapter_summary+"。上一章摘要："+previous_summary+"。正文要求：一体连贯的故事，对话吸引，动作清晰，章末有钩子或反转。只输出正文。"}
    ], temp=0.88, max_tok=4096)
    if content:
        cstr = content.strip()
        cc = len(re.sub(r"\s+","",cstr))
        full += "\n\n## 第"+str(cn)+"章 "+ct+"\n\n"+cstr
        done += 1
        previous_summary = cstr[-500:]
        print("OK ["+str(cc)+"字] {}/{})".format(done,len(all_chs)))
    else:
        print("FAILED")
        time.sleep(5)
        content = call([
            {"role":"system","content":"你是出版过悬疑小说的专业作家，只输出正文。"},
            {"role":"user","content":f"请重试第{cn}章《{ct}》，保持卷线和上一章结尾连续，输出完整正文。"},
        ], temp=0.88, max_tok=4096)
        if content:
            full += "\n\n## 第"+str(cn)+"章 "+ct+"\n\n"+content.strip()
            done += 1
            print("  OK retry")
    time.sleep(1.5)
    if done % 10 == 0:
        (OUT / f"progress_{datetime.now().strftime('%Y%m%d_%H%M')}.md").write_text(full, encoding="utf-8")

elapsed = time.time()-t0
fp = OUT / f"雾港回声_完整_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
fp.write_text(full, encoding="utf-8")
tc = len(re.sub(r"\s+","",full))
print("\n"+"="*60)
print(f"  完成! {done}/{len(all_chs)}章")
print(f"  总字数: {tc}")
print(f"  耗时: {elapsed/60:.1f}分钟")
print(f"  文件: {fp}")
print("="*60)

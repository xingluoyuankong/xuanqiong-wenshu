#!/usr/bin/env python3
from __future__ import annotations
import argparse, datetime as dt, json, re, sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
MOJIBAKE_PATTERNS=["????","\ufffd","\u951f","\u9435","\u936a","\u8133"]
PLACEHOLDER_PATTERNS=["TODO","\u5360\u4f4d","\u5f85\u8865\u5145","\u8f93\u5165\u4fe1\u606f\u4e0d\u5b8c\u6574","\u6682\u65e0\u6b63\u6587","\u793a\u4f8b\u6587\u672c"]
ACTION_WORDS=list("\u8d70\u8dd1\u51b2\u6293\u63a8\u62c9\u770b\u671b\u95ee\u7b54\u8bf4\u558a\u7b11\u54ed\u6740\u6253\u8eb2\u9003\u8ffd\u8f6c\u9192\u62ff\u653e\u5f00\u5173\u542c\u5199\u8bfb\u60f3")
DIALOGUE_MARKERS=["\u201c","\u201d","\uff1a",":"]
HOOK_WORDS=["\u7a81\u7136","\u5374","\u7136\u800c","\u4e0b\u4e00\u79d2","\u5c31\u5728\u8fd9\u65f6","\u95e8\u5916","\u8eab\u540e","\u79d8\u5bc6","\u771f\u76f8","\u9192\u6765","\u6d88\u5931","\u51fa\u73b0","\u8bb0\u5fc6"]
COMMON_IMAGERY=["\u8840","\u96e8","\u5899","\u706f","\u5f71","\u9634\u5f71","\u8bb0\u5fc6","\u65f6\u95f4","\u94c1\u9508","\u8150","\u96fe","\u5c4f\u5e55","\u88c2","\u9ed1\u6697","\u75bc","\u51b7"]
ENGLISH_RE=re.compile(r"[A-Za-z]{3,}"); CHINESE_TOKEN_RE=re.compile(r"[\u4e00-\u9fff]{2,}"); CHINESE_CHAR_RE=re.compile(r"[\u4e00-\u9fff]")
T={"mojibake":"\u7591\u4f3c\u4e71\u7801","placeholder":"\u5360\u4f4d/\u9519\u8bef\u63d0\u793a\u6df7\u5165\u6b63\u6587","short":"\u6b63\u6587\u8fc7\u77ed","long_para":"\u8d85\u957f\u6bb5\u843d\u5f71\u54cd\u9605\u8bfb","repetition":"\u91cd\u590d\u610f\u8c61\u504f\u591a","english":"\u82f1\u6587\u5939\u6742\u504f\u591a","momentum":"\u60c5\u8282\u63a8\u8fdb\u5bc6\u5ea6\u504f\u5f31","outline":"\u5927\u7eb2\u5173\u952e\u8bcd\u8986\u76d6\u504f\u4f4e"}
def connect_ro(path:Path):
    con=sqlite3.connect(f"file:{path.as_posix()}?mode=ro",uri=True); con.row_factory=sqlite3.Row; return con
def paras(t): return [p.strip() for p in re.split(r"\n\s*\n+",t or "") if p.strip()]
def sents(t): return [p.strip() for p in re.split(r"(?<=[\u3002\uff01\uff1f!?])\s*",t or "") if p.strip()]
def score(content, outline_title="", outline_summary=""):
    text=content or ""; ps=paras(text); ss=sents(text); n=len(text)
    dialogue_ratio=min(1.0,sum(text.count(m) for m in DIALOGUE_MARKERS)/max(1,len(ss)*2)); action_density=sum(text.count(w) for w in ACTION_WORDS)/max(1,len(ss)); hook_hits=sum(text.count(w) for w in HOOK_WORDS)
    imagery=Counter({w:text.count(w) for w in COMMON_IMAGERY if text.count(w)}); english=Counter(m.group(0) for m in ENGLISH_RE.finditer(text)); moj=sum(text.count(p) for p in MOJIBAKE_PATTERNS); ph=sum(text.count(p) for p in PLACEHOLDER_PATTERNS)
    avg=n/max(1,len(ps)); longp=sum(1 for p in ps if len(p)>900); toks=[x for x in CHINESE_TOKEN_RE.findall((outline_title or "")+" "+(outline_summary or "")) if len(x)>=2][:30]; cov=(sum(1 for x in toks if x in text)/max(1,len(toks))) if toks else None
    cleanliness=max(0,100-min(55,moj*12)-min(35,ph*15)-(10 if n<800 else 0)-(8 if len(english)>8 else 0)); readability=max(0,min(100,72+(10 if 180<=avg<=650 else 0)-(16 if avg>900 else 0)-min(20,longp*5)+(8 if len(ps)>=6 else 0)-(35 if moj or ph else 0)))
    momentum=max(0,min(100,48+min(28,action_density*7)+min(14,hook_hits*1.4)+(6 if dialogue_ratio>.08 else 0)-(12 if n<1000 else 0)))
    rep=0
    if imagery:
        _,cnt=imagery.most_common(1)[0]; rep=min(35,max(0,cnt-max(8,n//900))*2)
    style=max(0,min(100,78-rep+(6 if dialogue_ratio>.05 else 0))); complete=62+(16 if n>=2500 else 0)+(8 if len(ps)>=8 else 0)+(6 if hook_hits>=3 else 0)+(int(cov*10) if cov is not None else 0)-(25 if n<800 else 0)-(30 if moj or ph else 0); complete=max(0,min(100,complete))
    overall=round(cleanliness*.25+readability*.20+momentum*.22+style*.16+complete*.17,1); flags=[]
    if moj: flags.append(T["mojibake"])
    if ph: flags.append(T["placeholder"])
    if n<800: flags.append(T["short"])
    if longp: flags.append(T["long_para"])
    if rep>=18: flags.append(T["repetition"])
    if len(english)>8: flags.append(T["english"])
    if momentum<55 and n>=1200: flags.append(T["momentum"])
    if cov is not None and cov<.18: flags.append(T["outline"])
    return {"char_count":n,"chinese_count":len(CHINESE_CHAR_RE.findall(text)),"paragraph_count":len(ps),"sentence_count":len(ss),"avg_paragraph_length":round(avg,1),"long_paragraph_count":longp,"dialogue_ratio":round(dialogue_ratio,3),"action_density":round(action_density,3),"hook_hits":hook_hits,"outline_coverage":None if cov is None else round(cov,3),"mojibake_hits":moj,"placeholder_hits":ph,"english_top":english.most_common(10),"imagery_top":imagery.most_common(10),"scores":{"cleanliness":round(cleanliness,1),"readability":round(readability,1),"plot_momentum":round(momentum,1),"style_balance":round(style,1),"chapter_completeness":round(complete,1),"overall":overall},"flags":flags}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--db",default="backend/storage/arboris.db"); ap.add_argument("--out-dir",default="docs/reports"); ap.add_argument("--stamp",default=dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")); a=ap.parse_args(); db=Path(a.db); out=Path(a.out_dir); out.mkdir(parents=True,exist_ok=True)
    if not db.exists(): raise SystemExit(f"database not found: {db}")
    rows=connect_ro(db).execute("""SELECT p.id project_id,p.title project_title,c.id chapter_id,c.chapter_number,c.status,c.selected_version_id,v.id version_id,v.version_label,v.provider,v.content,o.title outline_title,o.summary outline_summary FROM novel_projects p JOIN chapters c ON c.project_id=p.id LEFT JOIN chapter_versions v ON v.id=c.selected_version_id LEFT JOIN chapter_outlines o ON o.project_id=p.id AND o.chapter_number=c.chapter_number ORDER BY p.updated_at DESC,c.chapter_number ASC""").fetchall()
    chapters=[]; pscores=defaultdict(list); pflags=defaultdict(Counter); gflags=Counter(); no_sel=0
    for r in rows:
        m=score(r["content"] or "",r["outline_title"] or "",r["outline_summary"] or ""); no_sel+=0 if r["version_id"] else 1; item={"project_id":r["project_id"],"project_title":r["project_title"],"chapter_id":r["chapter_id"],"chapter_number":r["chapter_number"],"status":r["status"],"selected_version_id":r["selected_version_id"],"version_id":r["version_id"],"version_label":r["version_label"],"provider":r["provider"],"outline_title":r["outline_title"],"metrics":m}; chapters.append(item); pscores[r["project_id"]].append(m["scores"]["overall"])
        for f in m["flags"]: pflags[r["project_id"]][f]+=1; gflags[f]+=1
    projects=[]
    for pid,sc in pscores.items():
        title=next(c["project_title"] for c in chapters if c["project_id"]==pid); projects.append({"project_id":pid,"project_title":title,"chapter_count":len(sc),"avg_score":round(sum(sc)/len(sc),1),"min_score":round(min(sc),1),"flags":pflags[pid].most_common()})
    projects.sort(key=lambda x:(x["avg_score"],-x["chapter_count"])); allsc=[c["metrics"]["scores"]["overall"] for c in chapters]
    summary={"database":str(db),"generated_at":a.stamp,"project_count_with_chapters":len(pscores),"chapter_count":len(chapters),"no_selected_version_chapters":no_sel,"avg_overall_score":round(sum(allsc)/max(1,len(allsc)),1),"min_overall_score":round(min(allsc),1) if allsc else 0,"max_overall_score":round(max(allsc),1) if allsc else 0,"flag_counts":gflags.most_common()}
    report={"summary":summary,"projects":projects,"chapters":chapters}; jp=out/f"generated-novel-literary-audit-{a.stamp}.json"; mp=out/f"generated-novel-literary-audit-{a.stamp}.md"; jp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    weak=sorted(chapters,key=lambda c:c["metrics"]["scores"]["overall"])[:12]; strong=sorted(chapters,key=lambda c:c["metrics"]["scores"]["overall"],reverse=True)[:8]; lines=[]
    lines.append(f"# \u5df2\u751f\u6210\u5c0f\u8bf4\u6587\u5b66\u8d28\u91cf\u53ea\u8bfb\u5ba1\u8ba1\n\n\u751f\u6210\u65f6\u95f4\uff1a{a.stamp}\n\n\u6570\u636e\u5e93\uff1a`{db}`\n\n> \u672c\u62a5\u544a\u53ea\u8bfb\u5206\u6790\uff0c\u4e0d\u4fee\u6539\u4efb\u4f55\u5df2\u751f\u6210\u5c0f\u8bf4\u5185\u5bb9\u3002\n")
    lines.append("## \u603b\u89c8\n"); lines.append(f"- \u6709\u7ae0\u8282\u9879\u76ee\u6570\uff1a{summary['project_count_with_chapters']}\n- \u7ae0\u8282\u6570\uff1a{summary['chapter_count']}\n- \u65e0\u9009\u4e2d\u7248\u672c\u7ae0\u8282\uff1a{summary['no_selected_version_chapters']}\n- \u5e73\u5747\u7efc\u5408\u5206\uff1a{summary['avg_overall_score']}\n- \u6700\u4f4e/\u6700\u9ad8\u7efc\u5408\u5206\uff1a{summary['min_overall_score']} / {summary['max_overall_score']}\n")
    lines.append("## \u98ce\u9669\u6807\u8bb0\u7edf\u8ba1\n"); [lines.append(f"- {k}: {v}\n") for k,v in summary["flag_counts"]] or lines.append("- \u672a\u547d\u4e2d\u660e\u663e\u6587\u5b66/\u6d01\u51c0\u5ea6\u98ce\u9669\u6807\u8bb0\u3002\n")
    lines.append("\n## \u9879\u76ee\u5747\u5206\u6700\u4f4e\u6837\u672c\n"); [lines.append(f"- {p['project_title']}\uff1aavg={p['avg_score']}\uff0c\u7ae0\u8282={p['chapter_count']}\uff0cflags={p['flags']}\n") for p in projects[:10]]
    lines.append("\n## \u7ae0\u8282\u4f4e\u5206\u6837\u672c\n"); [lines.append(f"- {c['project_title']} / \u7b2c{c['chapter_number']}\u7ae0\uff1aoverall={c['metrics']['scores']['overall']}\uff0c\u5b57\u6570={c['metrics']['char_count']}\uff0cflags={c['metrics']['flags']}\n") for c in weak]
    lines.append("\n## \u7ae0\u8282\u9ad8\u5206\u6837\u672c\n"); [lines.append(f"- {c['project_title']} / \u7b2c{c['chapter_number']}\u7ae0\uff1aoverall={c['metrics']['scores']['overall']}\uff0c\u5b57\u6570={c['metrics']['char_count']}\uff0c\u63a8\u8fdb={c['metrics']['scores']['plot_momentum']}\uff0c\u5b8c\u6574={c['metrics']['scores']['chapter_completeness']}\n") for c in strong]
    lines.append("\n## \u751f\u6210\u80fd\u529b\u7ed3\u8bba\n- \u7cfb\u7edf\u5df2\u5177\u5907\u957f\u7bc7\u89c4\u5212\u3001\u591a\u7248\u672c\u6b63\u6587\u3001\u7ae0\u8282\u8bc4\u4f30\u3001\u5065\u5eb7\u68c0\u67e5\u4e0e\u5bfc\u51fa\u4fdd\u62a4\u57fa\u7840\u3002\n- \u6587\u5b66\u80fd\u529b\u4e3b\u8981\u5f3a\u5728\u6c1b\u56f4\u3001\u7c7b\u578b\u611f\u548c\u8f83\u957f\u6b63\u6587\u751f\u6210\uff1b\u5f31\u5728\u60c5\u8282\u63a8\u8fdb\u5bc6\u5ea6\u3001\u91cd\u590d\u610f\u8c61\u63a7\u5236\u3001\u7ae0\u8282\u76ee\u6807\u5f3a\u7ea6\u675f\u3002\n- \u540e\u7eed\u5e94\u628a\u8be5\u5ba1\u8ba1\u63a5\u5165\u751f\u6210\u540e\u95e8\u7981\uff1a\u4f4e\u6d01\u51c0\u5ea6/\u5360\u4f4d/\u4e71\u7801/\u8fc7\u77ed\u6b63\u6587\u4e0d\u5f97\u81ea\u52a8\u6210\u4e3a\u6700\u7ec8\u7248\u672c\u3002\n")
    mp.write_text("".join(lines),encoding="utf-8"); print(json.dumps({"ok":True,"json":str(jp),"md":str(mp),"summary":summary},ensure_ascii=False,indent=2)); return 0
if __name__=="__main__": raise SystemExit(main())

from __future__ import annotations
import argparse, hashlib, importlib.util, json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def load_json(path):
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise ValueError(f"expected object: {path}")
    return value

def find_summary(run_dir):
    paths=sorted(run_dir.rglob("rescore-summary.json"))
    if len(paths)!=1: raise ValueError(f"expected one summary below {run_dir}, found {len(paths)}")
    return paths[0]

def load_run(run_dir):
    summary_path=find_summary(run_dir); summary=load_json(summary_path); records={}
    for path in sorted(summary_path.parent.glob("*.json")):
        if path.name in {"rescore-summary.json","live-status.json"}: continue
        payload=load_json(path); mid=str(payload.get("mission_id") or "").strip(); cf=str(payload.get("content_file") or "").strip()
        if not mid or not cf: raise ValueError(f"missing mission_id/content_file: {path}")
        content_path=summary_path.parent/cf
        if not content_path.is_file(): raise ValueError(f"missing content file: {content_path}")
        payload["_content"]=content_path.read_text(encoding="utf-8"); records[mid]=payload
    if set(records)!={str(x.get("mission_id")) for x in summary.get("records",[]) if isinstance(x,dict)}: raise ValueError("summary/live ids differ")
    return summary,records

def historical_module(root):
    path=root/"scripts"/"audit_historical_scorer_delta.py"; spec=importlib.util.spec_from_file_location("selector_historical",path)
    if not spec or not spec.loader: raise RuntimeError("cannot load historical scorer tool")
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

def score(scorer,payload,root):
    h=historical_module(root); metadata={"chapter_mission":payload.get("chapter_mission") or {},"quality_metrics":{"target_word_count":payload.get("target_word_count") or 0,"min_word_count":payload.get("min_word_count") or 0}}
    return h._call(scorer,content=str(payload.get("_content") or ""),metadata=metadata)

def simulate(baseline_dir,candidate_dir,*,old_scorer,current_scorer):
    root=Path(__file__).resolve().parents[1]; bs,br=load_run(baseline_dir); cs,cr=load_run(candidate_dir)
    bfp=bs.get("comparison_fingerprint") or {}; cfp=cs.get("comparison_fingerprint") or {}; bp=bs.get("provider") or {}; cp=cs.get("provider") or {}
    mids=sorted(br)
    if mids!=sorted(cr): raise ValueError("baseline/candidate mission sets differ")
    checks={"same_mission_ids":True,"same_provider_host":bp.get("provider_host")==cp.get("provider_host"),"same_model":bp.get("model")==cp.get("model"),"same_scorer":bfp.get("scorer_sha256")==cfp.get("scorer_sha256"),"different_prompt_request_contract":bfp.get("generation_request_contract_sha256")!=cfp.get("generation_request_contract_sha256"),"different_comparison_contract":bfp.get("comparison_contract_sha256")!=cfp.get("comparison_contract_sha256")}
    if not checks["same_provider_host"] or not checks["same_model"] or not checks["same_scorer"]: raise ValueError("requires same provider host/model/scorer")
    if not checks["different_prompt_request_contract"] or not checks["different_comparison_contract"]: raise ValueError("requires distinct request and comparison contracts")
    rows=[]
    for mid in mids:
        opts=[]
        for variant,payload in (("baseline",br[mid]),("candidate",cr[mid])):
            old=score(old_scorer,payload,root); cur=score(current_scorer,payload,root)
            opts.append({"variant":variant,"content_sha256":hashlib.sha256(str(payload.get("_content") or "").encode()).hexdigest(),"old_score":old.get("score"),"current_score":cur.get("score"),"old_issue_codes":sorted(old.get("quality_issue_codes") or []),"current_issue_codes":sorted(cur.get("quality_issue_codes") or [])})
        ob=max(opts,key=lambda x:(float(x.get("old_score") or -10**9),x["variant"])); cb=max(opts,key=lambda x:(float(x.get("current_score") or -10**9),x["variant"]))
        rows.append({"mission_id":mid,"options":opts,"old_selector":ob["variant"],"current_selector":cb["variant"],"selector_changed":ob["variant"]!=cb["variant"]})
    return {"kind":"redacted_frozen_scorer_selector_simulation","generated_at":datetime.now(timezone.utc).isoformat(),"status":"same_candidate_pool_selector_behavior_not_generation_gain","checks":checks,"input":{"baseline_dir":str(baseline_dir.resolve()),"candidate_dir":str(candidate_dir.resolve()),"mission_count":len(rows)},"selector_simulation":{"old_scorer_selection_counts":{"baseline":sum(x["old_selector"]=="baseline" for x in rows),"candidate":sum(x["old_selector"]=="candidate" for x in rows)},"current_scorer_selection_counts":{"baseline":sum(x["current_selector"]=="baseline" for x in rows),"candidate":sum(x["current_selector"]=="candidate" for x in rows)},"selector_changed_count":sum(x["selector_changed"] for x in rows),"rows":rows},"limitations":["同一候选池的 scorer selector 行为研究，不是生成 before/after 质量收益。","prompt contract 不同，不能作为 strict T-16 comparable pair。","没有人工标签，不能证明用户偏好、误杀率或生产收益。"]}

def main():
    p=argparse.ArgumentParser(); p.add_argument("--baseline-dir",type=Path,required=True); p.add_argument("--candidate-dir",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    from app.services.pipeline_orchestrator import PipelineOrchestrator
    h=historical_module(Path(__file__).resolve().parents[1]); out=simulate(a.baseline_dir,a.candidate_dir,old_scorer=h._load_old_class(),current_scorer=PipelineOrchestrator); a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps({"status":out["status"],"checks":out["checks"],"selector_simulation":out["selector_simulation"]},ensure_ascii=False))

if __name__=="__main__": main()

from __future__ import annotations
import argparse,json
from datetime import datetime,timezone
from pathlib import Path

def load(path):
 v=json.loads(path.read_text(encoding="utf-8")); assert isinstance(v,dict); return v
def summary(run):
 xs=sorted(run.rglob("rescore-summary.json"))
 if len(xs)!=1: raise ValueError(f"expected one summary, found {len(xs)}")
 return xs[0],load(xs[0])
def summary_or_none(run):
 xs=sorted(run.rglob("rescore-summary.json"))
 if len(xs)>1: raise ValueError(f"expected one summary, found {len(xs)}")
 if not xs: return None,None
 return xs[0],load(xs[0])
def contract(path):
 for f in sorted(path.parent.glob("*.json")):
  if f.name not in {"rescore-summary.json","live-status.json"}: return load(f).get("request_contract") or {}
 raise ValueError("no redacted live record")
def blocked_report(bp,b,cp,c):
 states=[]
 for side,path,run in (("baseline",bp,b),("candidate",cp,c)):
  records=run.get("records") if isinstance(run,dict) else []
  records=[x for x in records if isinstance(x,dict)] if isinstance(records,list) else []
  status=run.get("status") if isinstance(run,dict) else None
  declared=run.get("record_count") if isinstance(run,dict) else None
  reasons=[]
  if run is None: reasons.append("summary_missing")
  if status!="passed": reasons.append("status_not_passed")
  if not records or not isinstance(declared,int) or declared<=0: reasons.append("no_records")
  states.append({"side":side,"summary":str(path.resolve()) if path else None,"status":status,"record_count":declared,"observed_record_count":len(records),"failure_reasons":reasons})
 failure_counts={
  "baseline":len(states[0]["failure_reasons"]),
  "candidate":len(states[1]["failure_reasons"]),
  "total":sum(len(x["failure_reasons"]) for x in states),
  "non_passed_runs":sum(x["status"]!="passed" for x in states),
  "no_record_runs":sum("no_records" in x["failure_reasons"] for x in states),
 }
 checks={
  "baseline_summary_found":b is not None,
  "candidate_summary_found":c is not None,
  "baseline_status_passed":states[0]["status"]=="passed",
  "candidate_status_passed":states[1]["status"]=="passed",
  "baseline_has_records":"no_records" not in states[0]["failure_reasons"],
  "candidate_has_records":"no_records" not in states[1]["failure_reasons"],
  "provider_blocked_or_no_records":True,
  "ab_success":False,
 }
 return {"kind":"redacted_prompt_ab_audit","generated_at":datetime.now(timezone.utc).isoformat(),"status":"provider_blocked_or_no_records","checks":checks,"failure_counts":failure_counts,"failure_summary":states,"baseline":states[0],"candidate":states[1],"aggregate_delta":None,"rows":[],"limitations":["Provider/transport failure or empty run; no A/B success is claimed.","No prompt, response body, or live-record payload is included."]}
def audit(bdir,cdir):
 bp,b=summary_or_none(bdir); cp,c=summary_or_none(cdir)
 if b is None or c is None or b.get("status")!="passed" or c.get("status")!="passed" or not isinstance(b.get("records"),list) or not b.get("records") or not isinstance(c.get("records"),list) or not c.get("records") or not isinstance(b.get("record_count"),int) or b.get("record_count")<=0 or not isinstance(c.get("record_count"),int) or c.get("record_count")<=0:
  return blocked_report(bp,b,cp,c)
 bf=b.get("comparison_fingerprint") or {}; cf=c.get("comparison_fingerprint") or {}; bv=b.get("provider") or {}; cv=c.get("provider") or {}; bc=contract(bp); cc=contract(cp)
 br={str(x.get("mission_id")):x for x in b.get("records",[]) if isinstance(x,dict)}; cr={str(x.get("mission_id")):x for x in c.get("records",[]) if isinstance(x,dict)}
 checks={"same_mission_ids":set(br)==set(cr),"same_provider_host":bv.get("provider_host")==cv.get("provider_host"),"same_model":bv.get("model")==cv.get("model"),"same_scorer":bf.get("scorer_sha256")==cf.get("scorer_sha256"),"different_request_contract":bf.get("generation_request_contract_sha256")!=cf.get("generation_request_contract_sha256"),"different_comparison_contract":bf.get("comparison_contract_sha256")!=cf.get("comparison_contract_sha256"),"baseline_variant":bc.get("prompt_variant"),"candidate_variant":cc.get("prompt_variant")}
 if not all(checks[x] for x in ("same_mission_ids","same_provider_host","same_model","same_scorer")): raise ValueError("A/B requires same missions/provider/model/scorer")
 if checks["baseline_variant"]!="baseline" or checks["candidate_variant"]!="candidate": raise ValueError("prompt variants must be baseline/candidate")
 if not checks["different_request_contract"] or not checks["different_comparison_contract"]: raise ValueError("A/B requires distinct request/comparison contracts")
 rows=[]
 for mid in sorted(br):
  x,y=br[mid],cr[mid]; rows.append({"mission_id":mid,"baseline_score":x.get("score"),"candidate_score":y.get("score"),"score_delta":round(float(y.get("score") or 0)-float(x.get("score") or 0),2),"baseline_word_count":x.get("word_count"),"candidate_word_count":y.get("word_count"),"word_count_delta":int(y.get("word_count") or 0)-int(x.get("word_count") or 0),"baseline_issue_codes":list(x.get("quality_issue_codes") or []),"candidate_issue_codes":list(y.get("quality_issue_codes") or [])})
 ba=b.get("aggregate") or {}; ca=c.get("aggregate") or {}
 return {"kind":"redacted_prompt_ab_audit","generated_at":datetime.now(timezone.utc).isoformat(),"status":"controlled_prompt_ab_not_strict_t16_comparable","checks":checks,"baseline":{"summary":str(bp.resolve()),"status":b.get("status"),"record_count":b.get("record_count"),"aggregate":{k:ba.get(k) for k in ("average_score","average_word_count","quality_issue_record_count","blocker_counts")}},"candidate":{"summary":str(cp.resolve()),"status":c.get("status"),"record_count":c.get("record_count"),"aggregate":{k:ca.get(k) for k in ("average_score","average_word_count","quality_issue_record_count","blocker_counts")}},"aggregate_delta":{"average_score_delta":round(float(ca.get("average_score") or 0)-float(ba.get("average_score") or 0),2),"average_word_count_delta":round(float(ca.get("average_word_count") or 0)-float(ba.get("average_word_count") or 0),2)},"rows":rows,"limitations":["prompt intervention intentionally changes request/comparison contracts; not strict T-16 comparable=true.","No human labels; does not prove production gain, recall, false-kill rate, or user preference."]}
def main():
 p=argparse.ArgumentParser(); p.add_argument("--baseline-dir",type=Path,required=True); p.add_argument("--candidate-dir",type=Path,required=True); p.add_argument("--output",type=Path,required=True); a=p.parse_args(); out=a.output; out.parent.mkdir(parents=True,exist_ok=True); result=audit(a.baseline_dir,a.candidate_dir); out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8"); print(json.dumps({"status":result["status"],"checks":result["checks"],"aggregate_delta":result["aggregate_delta"]},ensure_ascii=False))
if __name__=="__main__": main()

from __future__ import annotations
import importlib.util,json
from pathlib import Path
import pytest
def mod():
 p=Path(__file__).resolve().parents[2]/"scripts/audit_quality_bench_prompt_ab.py"; s=importlib.util.spec_from_file_location("prompt_ab_test",p); assert s and s.loader; m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m
def run(root,variant,req,cmp,score):
 d=root/"provider-live"; d.mkdir(parents=True); (d/"m.json").write_text(json.dumps({"mission_id":"m","request_contract":{"prompt_variant":variant}})); (d/"rescore-summary.json").write_text(json.dumps({"status":"passed","record_count":1,"provider":{"provider_host":"p","model":"m"},"comparison_fingerprint":{"mission_ids":["m"],"scorer_sha256":"s","generation_request_contract_sha256":req,"comparison_contract_sha256":cmp},"aggregate":{"average_score":score,"average_word_count":100},"records":[{"mission_id":"m","score":score,"word_count":100,"quality_issue_codes":[]}]}))
def run_blocked(root,status="failed"):
 d=root/"provider-live"; d.mkdir(parents=True,exist_ok=True); (d/"rescore-summary.json").write_text(json.dumps({"status":status,"record_count":0,"records":[]}))
def test_ab_checks_contracts_and_delta(tmp_path):
 run(tmp_path/"b","baseline","r1","c1",100); run(tmp_path/"c","candidate","r2","c2",80); r=mod().audit(tmp_path/"b",tmp_path/"c"); assert r["checks"]["same_scorer"] is True; assert r["checks"]["different_request_contract"] is True; assert r["aggregate_delta"]["average_score_delta"]==-20
def test_ab_rejects_same_contract(tmp_path):
 run(tmp_path/"b","baseline","same","same",100); run(tmp_path/"c","candidate","same","same",80);
 with pytest.raises(ValueError,match="distinct request") : mod().audit(tmp_path/"b",tmp_path/"c")

@pytest.mark.parametrize("blocked_side",["baseline","candidate"])
def test_provider_blocked_or_no_records_is_redacted_and_not_success(tmp_path,blocked_side):
 run(tmp_path/"b","baseline","r1","c1",100); run(tmp_path/"c","candidate","r2","c2",80)
 run_blocked(tmp_path/("b" if blocked_side=="baseline" else "c"))
 result=mod().audit(tmp_path/"b",tmp_path/"c")
 assert result["status"]=="provider_blocked_or_no_records"
 assert result["aggregate_delta"] is None
 assert result["rows"]==[]
 assert result["checks"]["provider_blocked_or_no_records"] is True
 assert result["checks"]["ab_success"] is False
 assert result["failure_counts"][blocked_side]>=1
 assert "status_not_passed" in result[blocked_side]["failure_reasons"]
 assert "no_records" in result[blocked_side]["failure_reasons"]
 assert result[blocked_side]["observed_record_count"]==0

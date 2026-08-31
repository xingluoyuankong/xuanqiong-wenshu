from __future__ import annotations
import importlib.util, json
from pathlib import Path
import pytest
def load():
 path=Path(__file__).resolve().parents[2]/"scripts"/"audit_frozen_selector_simulation.py"
 spec=importlib.util.spec_from_file_location("frozen_selector_test",path); assert spec and spec.loader
 mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
class Old:
 @classmethod
 def _score_story_quality_candidate(cls,**kwargs): return {"score":10 if "PRIVATE_PROSE_A" in kwargs["content"] else 5,"quality_issue_codes":[]}
class Current:
 @classmethod
 def _score_story_quality_candidate(cls,**kwargs): return {"score":5 if "PRIVATE_PROSE_A" in kwargs["content"] else 10,"quality_issue_codes":[]}
def run(root,request,compare,content):
 live=root/"provider-live"; live.mkdir(parents=True); (live/"m.txt").write_text(content,encoding="utf-8")
 (live/"m.json").write_text(json.dumps({"mission_id":"m","content_file":"m.txt","chapter_mission":{},"target_word_count":1200,"min_word_count":900}),encoding="utf-8")
 (live/"rescore-summary.json").write_text(json.dumps({"status":"passed","record_count":1,"provider":{"provider_host":"p","model":"m"},"comparison_fingerprint":{"mission_ids":["m"],"scorer_sha256":"same","generation_request_contract_sha256":request,"comparison_contract_sha256":compare},"records":[{"mission_id":"m"}]}),encoding="utf-8")
def test_simulation_redacts_prose_and_detects_selector_change(tmp_path):
 run(tmp_path/"b","ra","ca","PRIVATE_PROSE_A"); run(tmp_path/"c","rb","cb","PRIVATE_PROSE_B")
 result=load().simulate(tmp_path/"b",tmp_path/"c",old_scorer=Old,current_scorer=Current)
 assert result["checks"]["same_scorer"] is True
 assert result["selector_simulation"]["selector_changed_count"]==1
 assert "PRIVATE_PROSE_A" not in json.dumps(result,ensure_ascii=False)
 assert "PRIVATE_PROSE_B" not in json.dumps(result,ensure_ascii=False)
def test_simulation_rejects_same_contract(tmp_path):
 run(tmp_path/"b","same","same","PRIVATE_PROSE_A"); run(tmp_path/"c","same","same","PRIVATE_PROSE_B")
 with pytest.raises(ValueError,match="distinct request and comparison"):
  load().simulate(tmp_path/"b",tmp_path/"c",old_scorer=Old,current_scorer=Current)

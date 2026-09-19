#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,sys
from pathlib import Path

def main():
 root=Path(__file__).resolve().parents[1]
 manifest=json.loads((root/"backend/db/migration_manifest.json").read_text())
 failures=[]
 for item in manifest.get("migrations",[]):
  p=root/item["path"]
  if not p.is_file(): failures.append({"path":item["path"],"error":"missing"}); continue
  digest=hashlib.sha256(p.read_bytes()).hexdigest()
  if digest != item["sha256"] or p.stat().st_size != item["size"]:
   failures.append({"path":item["path"],"expected_sha256":item["sha256"],"actual_sha256":digest,"expected_size":item["size"],"actual_size":p.stat().st_size})
 result={"status":"pass" if not failures else "fail","manifest_commit":manifest.get("git_commit"),"migration_count":len(manifest.get("migrations",[])),"failures":failures,"baseline_schema_sha256":manifest.get("baseline_schema_sha256")}
 print(json.dumps(result,ensure_ascii=False,indent=2))
 return 0 if not failures else 10
if __name__=="__main__": raise SystemExit(main())

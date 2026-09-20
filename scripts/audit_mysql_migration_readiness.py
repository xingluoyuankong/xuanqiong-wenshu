#!/usr/bin/env python3
"""Read-only MySQL migration readiness audit; never connects or writes."""
from __future__ import annotations
import hashlib,json,re
from pathlib import Path
from importlib.util import find_spec

MYSQL_ONLY={
 "AUTO_INCREMENT": re.compile(r"\bAUTO_INCREMENT\b",re.I),
 "ENGINE=": re.compile(r"\bENGINE\s*=",re.I),
 "COLLATE": re.compile(r"\bCOLLATE\b",re.I),
 "MODIFY COLUMN": re.compile(r"\bMODIFY\s+COLUMN\b",re.I),
 "ADD COLUMN IF NOT EXISTS": re.compile(r"\bADD\s+COLUMN\s+IF\s+NOT\s+EXISTS\b",re.I),
}
DANGEROUS={
 "DROP TABLE": re.compile(r"\bDROP\s+TABLE\b",re.I),
 "DROP DATABASE": re.compile(r"\bDROP\s+DATABASE\b",re.I),
 "TRUNCATE": re.compile(r"\bTRUNCATE\b",re.I),
}

def main():
 root=Path(__file__).resolve().parents[1]
 from app.core.config import settings
 manifest_path=root/'backend/db/migration_manifest.json'
 manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
 fragments=[]; failures=[]
 for item in manifest.get('migrations',[]):
  path=root/item['path']; exists=path.is_file(); actual=hashlib.sha256(path.read_bytes()).hexdigest() if exists else None
  if not exists or actual != item['sha256'] or path.stat().st_size != item['size']:
   failures.append(item['path'])
  sql=path.read_text(encoding='utf-8',errors='replace') if exists else ''
  fragments.append({
   'path':item['path'],
   'mysql_only_tokens':[name for name,pat in MYSQL_ONLY.items() if pat.search(sql)],
   'dangerous_tokens':[name for name,pat in DANGEROUS.items() if pat.search(sql)],
   'sha256':actual,
  })
 mysql_config={
  'db_provider':settings.db_provider,
  'mysql_host_set':bool(settings.mysql_host),
  'mysql_port':settings.mysql_port,
  'mysql_database_set':bool(settings.mysql_database),
  'mysql_user_set':bool(settings.mysql_user),
  'mysql_password_set':bool(settings.mysql_password),
 }
 result={
  'audit_type':'readonly_mysql_migration_readiness',
  'execute':False,
  'connected':False,
  'writes_performed':False,
  'mysql_config':mysql_config,
  'asyncmy_installed':find_spec('asyncmy') is not None,
  'migration_manifest':str(manifest_path),
  'provenance_failures':failures,
  'fragments':fragments,
  'status':'READY_FOR_REVIEW' if not failures and mysql_config['mysql_password_set'] and find_spec('asyncmy') is not None else 'BLOCKED',
 }
 print(json.dumps(result,ensure_ascii=False,indent=2))
 return 0

if __name__=='__main__':
 raise SystemExit(main())
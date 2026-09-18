#!/bin/bash
# 数据库备份脚本（用 Python sqlite3 标准库替代不存在的 sqlite3 CLI）
set -eu
BASE=/run/csi/mount-root/nas/4079184d856ecc166ed19d4887083405/qwenpaw-data/xuanqiong-wenshu
BACKUP_DIR=$BASE/backups
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
mkdir -p "$BACKUP_DIR"

python3 - "$BASE" "$BACKUP_DIR" "$TIMESTAMP" <<'PY'
import sqlite3, sys, gzip, tarfile, os
from pathlib import Path
base, backup_dir, ts = sys.argv[1], sys.argv[2], sys.argv[3]
dbs = [("xuanqiong_wenshu", Path(base)/"storage/xuanqiong_wenshu.db"),
       ("rag_vectors", Path(base)/"storage/rag_vectors.db")]
for name, src in dbs:
    if not src.is_file():
        print(f"跳过 {name}: {src} 不存在")
        continue
    dst = Path(backup_dir)/f"{name}_{ts}.db"
    con = sqlite3.connect(src)
    bak = sqlite3.connect(dst)
    con.backup(bak)          # 在线一致性备份，不锁业务库
    bak.close(); con.close()
    with open(dst, "rb") as f_in, gzip.open(f"{dst}.gz", "wb") as f_out:
        f_out.writelines(f_in)
    dst.unlink()
    print(f"数据库备份完成: {name}_{ts}.db.gz")
tar_path = Path(backup_dir)/f"config_{ts}.tar.gz"
with tarfile.open(tar_path, "w:gz") as t:
    env = Path(base)/"backend/.env"
    if env.is_file():
        t.add(env, arcname="backend/.env")
print(f"配置备份完成: config_{ts}.tar.gz")
PY

# 清理旧备份（保留 7 天）
find "$BACKUP_DIR" -type f -mtime +7 -delete
echo "旧备份已清理"
echo "备份完成: $TIMESTAMP"

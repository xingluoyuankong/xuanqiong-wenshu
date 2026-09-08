"""Restart the isolated MySQL instance for Stage 14 testing."""
import json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(r'D:\小说写作\xuanqiong-wenshu')
manifest_path = ROOT / 'logs' / 'mysql-isolated-active.json'
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))

mysqld = manifest['mysqld']
datadir = manifest['datadir']
port = manifest['port']
pid_file = manifest['server_command'][-1].replace('--pid-file=', '')
credential_file = manifest['credential_file']
init_file = [arg for arg in manifest['server_command'] if arg.startswith('--init-file=')][0]

print(f"Starting MySQL: {mysqld}")
print(f"  datadir: {datadir}")
print(f"  port: {port}")

cmd = [
    mysqld,
    '--no-defaults',
    '--no-monitor',
    '--console',
    f'--basedir={Path(mysqld).parent.parent}',
    f'--datadir={datadir}',
    f'--port={port}',
    '--bind-address=127.0.0.1',
    '--mysqlx=OFF',
    '--skip-name-resolve',
    '--default-time-zone=+00:00',
    '--transaction-isolation=REPEATABLE-READ',
    '--character-set-server=utf8mb4',
    '--collation-server=utf8mb4_unicode_ci',
    '--max-connections=60',
    '--innodb-buffer-pool-size=128M',
    '--skip-log-bin',
    f'--pid-file={pid_file}',
    init_file,
]

# Start MySQL in background
proc = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
)

print(f"  MySQL PID: {proc.pid}")

# Wait for MySQL to be ready
import asyncio
async def wait_for_mysql():
    import asyncmy
    creds = json.loads(Path(credential_file).read_text(encoding='utf-8'))
    for i in range(30):
        try:
            conn = await asyncmy.connect(
                host='127.0.0.1', port=port,
                user=creds['user'], password=creds['password'],
                database='mysql', connect_timeout=2
            )
            conn.close()
            return True
        except Exception:
            await asyncio.sleep(1)
    return False

ready = asyncio.run(wait_for_mysql())
if ready:
    print(f"  MySQL READY on port {port}")
    # Update manifest with new PID
    manifest['server_pid'] = proc.pid
    manifest['server_running'] = True
    manifest['controlled_pids'] = [proc.pid]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print("  Manifest updated")
else:
    print("  MySQL FAILED to start within 30s")
    proc.terminate()

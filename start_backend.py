import subprocess, os
os.chdir(r"D:\小说写作\xuanqiong-wenshu\backend")
p = subprocess.Popen(
    ["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8013", "--timeout-keep-alive", "600"],
    env={**os.environ, "PYTHONPATH": r"D:\小说写作\xuanqiong-wenshu\backend"},
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    creationflags=subprocess.DETACHED_PROCESS | 0x00000008
)
print(f"Backend started PID={p.pid}")

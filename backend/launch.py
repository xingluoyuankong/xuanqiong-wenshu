import subprocess, os, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("PYTHONPATH", os.getcwd())
port = sys.argv[1] if len(sys.argv) > 1 else "8013"
print(f"Backend @ http://127.0.0.1:{port} (no-reload, stable mode)")
subprocess.run(["python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", port, "--timeout-keep-alive", "600", "--log-level", "warning"])

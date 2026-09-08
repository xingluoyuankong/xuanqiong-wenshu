"""Compatibility launcher: mutations are now Vite in-memory transforms; no source writes."""
from pathlib import Path
import subprocess
root = Path(__file__).resolve().parents[2]
raise SystemExit(subprocess.call(['node', str(Path(__file__).with_name('run-mutations.mjs'))], cwd=root))

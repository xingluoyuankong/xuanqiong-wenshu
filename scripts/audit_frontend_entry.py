#!/usr/bin/env python3
"""Audit the production frontend entry HTML and preload byte budget."""
from __future__ import annotations
import argparse
import json
from html.parser import HTMLParser
from pathlib import Path

class EntryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.assets: list[dict[str, str]] = []
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script" and values.get("src"):
            self.assets.append({"kind": "script", "rel": values.get("rel", ""), "path": values["src"] or ""})
        elif tag == "link" and values.get("href") and values.get("rel") in {"modulepreload", "stylesheet"}:
            self.assets.append({"kind": "link", "rel": values.get("rel", ""), "path": values["href"] or ""})

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", default="frontend/dist")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    dist = (root / args.dist).resolve()
    index = dist / "index.html"
    parsed = EntryParser()
    parsed.feed(index.read_text(encoding="utf-8"))
    records = []
    failures = []
    for asset in parsed.assets:
        relative = asset["path"].lstrip("/")
        path = dist / relative
        exists = path.is_file()
        size = path.stat().st_size if exists else None
        if not exists:
            failures.append(f"missing:{relative}")
        records.append({**asset, "bytes": size})
    modulepreload = [item for item in records if item["rel"] == "modulepreload"]
    admin_preload = [item for item in modulepreload if "admin-vendor" in item["path"]]
    result = {
        "audit_type": "frontend_entry_budget",
        "dist": str(dist),
        "index_bytes": index.stat().st_size,
        "assets": records,
        "modulepreload_count": len(modulepreload),
        "modulepreload_bytes": sum(item["bytes"] or 0 for item in modulepreload),
        "entry_script_bytes": sum(item["bytes"] or 0 for item in records if item["kind"] == "script"),
        "stylesheet_bytes": sum(item["bytes"] or 0 for item in records if item["rel"] == "stylesheet"),
        "admin_vendor_preloads": admin_preload,
        "failures": failures,
        "status": "PASS" if not failures and not admin_preload else "FAIL",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 10

if __name__ == "__main__":
    raise SystemExit(main())
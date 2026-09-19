#!/usr/bin/env python3
"""Verify server dependency versions, source roots, and imports."""
from __future__ import annotations
import importlib
import importlib.metadata as metadata
import json
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / "deploy/runtime_dependencies.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    observed: dict[str, object] = {}
    for group_name in ("runtime", "test"):
        packages = manifest.get(group_name, {})
        for distribution_name, expected in packages.items():
            record: dict[str, object] = {"group": group_name, "expected": expected}
            try:
                distribution = metadata.distribution(distribution_name)
                actual_version = distribution.version
                actual_root = Path(str(distribution.locate_file(""))).resolve()
                aliases = expected.get("source_aliases") or [expected.get("source_root")]
                expected_roots = []
                for alias in aliases:
                    if not alias:
                        continue
                    alias_path = Path(alias)
                    if not alias_path.is_absolute():
                        alias_path = root / alias_path
                    expected_roots.append(alias_path.resolve())
                record.update({
                    "version": actual_version,
                    "source_root": str(actual_root),
                    "source_aliases": [str(item) for item in expected_roots],
                    "import": expected["import"],
                })
                if actual_version != expected["version"]:
                    failures.append(f"{distribution_name}:version:{actual_version}!={expected['version']}")
                if actual_root not in expected_roots:
                    failures.append(f"{distribution_name}:source:{actual_root} not in {expected_roots}")
                importlib.import_module(expected["import"])
                record["import_status"] = "ok"
            except Exception as exc:  # noqa: BLE001
                record["error"] = f"{type(exc).__name__}: {exc}"
                failures.append(f"{distribution_name}:error")
            observed[distribution_name] = record
    result = {
        "manifest": str(manifest_path),
        "python": sys.executable,
        "observed": observed,
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 10


if __name__ == "__main__":
    raise SystemExit(main())
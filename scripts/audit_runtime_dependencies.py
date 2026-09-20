#!/usr/bin/env python3
"""Verify server dependency versions, source roots, and imports."""
from __future__ import annotations
import importlib
import importlib.metadata as metadata
import json
import re
import sys
from pathlib import Path



def _canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def _read_freeze_snapshot(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        if "==" not in line:
            continue
        name, version = line.split("==", 1)
        result[_canonical_name(name)] = version.strip()
    return result


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / "deploy/runtime_dependencies.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    snapshot_failures: list[str] = []
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

    snapshots = {
        "runtime": root / "deploy/runtime_requirements.txt",
        "test": root / "deploy/test_requirements.txt",
    }
    excluded_runtime = {
        _canonical_name(item)
        for item in manifest.get("runtime_excluded_test_distributions", [])
    }
    snapshot_counts: dict[str, int] = {}
    snapshot_values: dict[str, dict[str, str]] = {}
    for group_name, snapshot_path in snapshots.items():
        if not snapshot_path.is_file():
            snapshot_failures.append(f"{group_name}:snapshot_missing:{snapshot_path}")
            continue
        expected_snapshot = _read_freeze_snapshot(snapshot_path)
        snapshot_values[group_name] = expected_snapshot
        snapshot_counts[group_name] = len(expected_snapshot)
        if group_name == "runtime":
            for excluded in sorted(excluded_runtime & set(expected_snapshot)):
                snapshot_failures.append(f"runtime:excluded_test_distribution_present:{excluded}")
        for distribution_name, expected_version in expected_snapshot.items():
            try:
                actual_version = metadata.version(distribution_name)
            except metadata.PackageNotFoundError:
                snapshot_failures.append(f"{group_name}:{distribution_name}:missing")
                continue
            if actual_version != expected_version:
                snapshot_failures.append(
                    f"{group_name}:{distribution_name}:version:{actual_version}!={expected_version}"
                )

    overlap = sorted(set(snapshot_values.get("runtime", {})) & set(snapshot_values.get("test", {})))
    unexpected_overlap = [item for item in overlap if item not in excluded_runtime]
    snapshot_failures.extend(f"runtime_test_overlap:{item}" for item in unexpected_overlap)
    result = {
        "manifest": str(manifest_path),
        "python": sys.executable,
        "observed": observed,
        "runtime_excluded_test_distributions": sorted(excluded_runtime),
        "runtime_test_overlap": overlap,
        "snapshot_counts": snapshot_counts,
        "snapshot_failures": snapshot_failures,
        "failures": failures,
        "status": "PASS" if not failures and not snapshot_failures else "FAIL",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 10


if __name__ == "__main__":
    raise SystemExit(main())
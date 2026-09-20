import importlib
import importlib.metadata as metadata
import json
import sys
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "deploy/runtime_dependencies.json"
SNAPSHOT = ROOT / "deploy/runtime_requirements.txt"


def canonical(name: str) -> str:
    return name.lower().replace("-", "_")


def snapshot_versions() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in SNAPSHOT.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, version = line.split("==", 1)
        values[canonical(name)] = version.strip()
    return values


def inside(path: Path, roots: list[Path]) -> bool:
    return any(path == root or root in path.parents for root in roots)


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = snapshot_versions()
    purelib = Path(sysconfig.get_paths()["purelib"]).resolve()
    platlib = Path(sysconfig.get_paths().get("platlib", str(purelib))).resolve()
    package_roots = [purelib, platlib]
    failures: list[str] = []
    observed: dict[str, object] = {}

    for normalized_name, expected_version in sorted(expected.items()):
        try:
            dist = metadata.distribution(normalized_name)
            version = dist.version
            root = Path(str(dist.locate_file(""))).resolve()
            if version != expected_version:
                failures.append(f"{normalized_name}:version:{version}!={expected_version}")
            if not inside(root, package_roots):
                failures.append(f"{normalized_name}:source:{root} outside {package_roots}")
            observed[normalized_name] = {
                "version": version,
                "source_root": str(root),
                "source_in_rebuild_venv": inside(root, package_roots),
            }
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{normalized_name}:metadata:{type(exc).__name__}:{exc}")

    for distribution_name, config in manifest.get("runtime", {}).items():
        module_name = config["import"]
        try:
            module = importlib.import_module(module_name)
            module_file = Path(str(getattr(module, "__file__", ""))).resolve()
            if not module_file or not inside(module_file, package_roots):
                failures.append(f"{distribution_name}:import_source:{module_file} outside {package_roots}")
            observed_key = canonical(distribution_name)
            observed.setdefault(observed_key, {})
            observed[observed_key]["import"] = module_name
            observed[observed_key]["import_file"] = str(module_file)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{distribution_name}:import:{type(exc).__name__}:{exc}")

    result = {
        "audit_type": "isolated_runtime_dependency_rebuild",
        "python": sys.executable,
        "sys_prefix": sys.prefix,
        "package_roots": [str(item) for item in package_roots],
        "snapshot_count": len(expected),
        "observed_count": len(observed),
        "failures": failures,
        "status": "PASS" if not failures else "FAIL",
        "observed_sample": {key: observed[key] for key in list(sorted(observed))[:12]},
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not failures else 10


if __name__ == "__main__":
    raise SystemExit(main())
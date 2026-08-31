"""Export a reviewed Agent catalog contract for explicit migration review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent.catalog_contract import build_catalog_contract
from app.agent.registry import DEFAULT_TOOL_PROVIDER_HEALTH, DEFAULT_TOOL_REGISTRY


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出当前 Agent 工具目录的审核契约基线")
    parser.add_argument("--output", required=True, type=Path, help="要写入的 JSON 文件")
    parser.add_argument("--overwrite", action="store_true", help="明确允许覆盖已有基线")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output.resolve()
    if output.exists() and not args.overwrite:
        raise SystemExit(f"输出已存在，使用 --overwrite 明确覆盖：{output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    contract = build_catalog_contract(DEFAULT_TOOL_REGISTRY, DEFAULT_TOOL_PROVIDER_HEALTH)
    output.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"catalog_id={contract['catalog_id']}")
    print(f"tool_count={contract['tool_count']}")
    print(f"output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json


# Keep generated paths repo-relative so local directory rename won't churn docs.
ROOT = Path(__file__).parent.parent
ROOT_DISPLAY = "<repo-root>"
OUTPUT_DIR = ROOT / "docs" / "code-index"
OUTPUT_MD = OUTPUT_DIR / "auto-file-index.md"
OUTPUT_JSON = OUTPUT_DIR / "auto-file-index.json"

EXCLUDED_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "output",
    "storage",
    ".pytest_cache",
    ".benchmarks",
    "__pycache__",
}

INCLUDED_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".vue",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".sql",
    ".sh",
    ".cmd",
    ".ps1",
    ".md",
}

INCLUDED_FILE_NAMES = {
    "Dockerfile",
}


@dataclass(frozen=True)
class Zone:
    zone_id: str
    title: str
    description: str
    prefixes: tuple[str, ...]


ZONES: list[Zone] = [
    Zone(
        "backend-api",
        "Backend API Layer",
        "FastAPI 路由层，承接请求并调用服务层。",
        ("backend/app/api/routers/",),
    ),
    Zone(
        "backend-core",
        "Backend Core & Infra",
        "配置、依赖、数据库会话和初始化。",
        (
            "backend/app/core/",
            "backend/app/config/",
            "backend/app/db/",
        ),
    ),
    Zone(
        "backend-domain",
        "Backend Domain Models",
        "ORM 模型、Schema、Repository。",
        (
            "backend/app/models/",
            "backend/app/schemas/",
            "backend/app/repositories/",
        ),
    ),
    Zone(
        "backend-service",
        "Backend Service Pipeline",
        "写作流水线、LLM 调度、业务服务与异步任务。",
        (
            "backend/app/services/",
            "backend/app/tasks/",
        ),
    ),
    Zone(
        "backend-utils",
        "Backend Utilities",
        "工具函数、第三方适配与辅助脚本。",
        (
            "backend/app/utils/",
            "backend/scripts/",
        ),
    ),
    Zone(
        "frontend-shell",
        "Frontend App Shell",
        "前端入口、路由、状态管理。",
        (
            "frontend/src/main.ts",
            "frontend/src/App.vue",
            "frontend/src/router/",
            "frontend/src/stores/",
        ),
    ),
    Zone(
        "frontend-ui",
        "Frontend UI Layer",
        "页面与组件层。",
        (
            "frontend/src/views/",
            "frontend/src/components/",
            "frontend/src/assets/",
        ),
    ),
    Zone(
        "frontend-data",
        "Frontend Data & Client Logic",
        "API 客户端、组合式逻辑和前端工具。",
        (
            "frontend/src/api/",
            "frontend/src/composables/",
            "frontend/src/utils/",
        ),
    ),
    Zone(
        "ops-deploy",
        "Deploy & Runtime",
        "部署配置、容器、启动器和迁移脚本。",
        (
            "deploy/",
            "start_xuanqiong_wenshu.cmd",
            "backend/db/",
        ),
    ),
    Zone(
        "docs-and-guides",
        "Documentation",
        "说明文档、审计报告、优化报告。",
        (
            "docs/",
            "README.md",
            "README-en.md",
            "CODE_AUDIT_REPORT.md",
            "DEEP_OPTIMIZATION_REPORT.md",
            "INTEGRATION_REPORT.md",
            "NOVEL_KIT_FUSION_REPORT.md",
        ),
    ),
]

FALLBACK_ZONE_ID = "other"


def should_include(path: Path) -> bool:
    rel_parts = path.relative_to(ROOT).parts
    if any(part in EXCLUDED_DIR_NAMES for part in rel_parts):
        return False
    if path.name in INCLUDED_FILE_NAMES:
        return True
    return path.suffix.lower() in INCLUDED_SUFFIXES


def detect_zone(relative_path: str) -> Zone | None:
    for zone in ZONES:
        for prefix in zone.prefixes:
            if relative_path == prefix or relative_path.startswith(prefix):
                return zone
    return None


def build_index() -> dict:
    buckets: dict[str, list[str]] = {zone.zone_id: [] for zone in ZONES}
    buckets[FALLBACK_ZONE_ID] = []

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if not should_include(path):
            continue
        rel = path.relative_to(ROOT).as_posix()
        zone = detect_zone(rel)
        if zone:
            buckets[zone.zone_id].append(rel)
        else:
            buckets[FALLBACK_ZONE_ID].append(rel)

    for bucket in buckets.values():
        bucket.sort()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": ROOT_DISPLAY,
        "zones": [
            {
                "id": zone.zone_id,
                "title": zone.title,
                "description": zone.description,
                "file_count": len(buckets[zone.zone_id]),
                "files": buckets[zone.zone_id],
            }
            for zone in ZONES
        ],
        "fallback": {
            "id": FALLBACK_ZONE_ID,
            "title": "Other",
            "file_count": len(buckets[FALLBACK_ZONE_ID]),
            "files": buckets[FALLBACK_ZONE_ID],
        },
    }


def render_markdown(index: dict) -> str:
    lines: list[str] = []
    lines.append("# Auto File Index")
    lines.append("")
    lines.append(f"- Generated at (UTC): `{index['generated_at']}`")
    lines.append(f"- Project root: `{index['root']}`")
    lines.append("")
    lines.append("## Zone Summary")
    lines.append("")
    lines.append("| Zone | Files | Description |")
    lines.append("| --- | ---: | --- |")
    for zone in index["zones"]:
        lines.append(f"| `{zone['id']}` | {zone['file_count']} | {zone['description']} |")
    lines.append(
        f"| `{index['fallback']['id']}` | {index['fallback']['file_count']} | "
        "未命中分区规则的文件 |"
    )
    lines.append("")

    lines.append("## Zone Details")
    lines.append("")
    for zone in index["zones"]:
        lines.append(f"### {zone['title']} (`{zone['id']}`)")
        lines.append("")
        if not zone["files"]:
            lines.append("_暂无文件。_")
            lines.append("")
            continue
        for rel in zone["files"]:
            lines.append(f"- `{rel}`")
        lines.append("")

    fallback = index["fallback"]
    lines.append(f"### {fallback['title']} (`{fallback['id']}`)")
    lines.append("")
    if fallback["files"]:
        for rel in fallback["files"]:
            lines.append(f"- `{rel}`")
    else:
        lines.append("_暂无文件。_")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    index = build_index()
    OUTPUT_JSON.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    OUTPUT_MD.write_text(render_markdown(index), encoding="utf-8")
    print(f"索引已写入：{OUTPUT_JSON.relative_to(ROOT)}")
    print(f"索引已写入：{OUTPUT_MD.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

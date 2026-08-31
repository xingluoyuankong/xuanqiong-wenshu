from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import selectinload

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a read-only compatible plan hierarchy candidate.")
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--output-dir",
        default=str(ROOT.parent / "audit" / "production-readiness" / "evidence"),
    )
    parser.add_argument("--target-text-units", type=int, default=100_000)
    return parser.parse_args()


def _markdown(payload: dict) -> str:
    book = payload["book"]
    lines = [
        "# 十万字计划层结构诊断与候选",
        "",
        f"- 方案：`{book['plan_id']}`",
        f"- 项目：`{book['project_id']}`",
        f"- 书名：{book['title']}",
        f"- 目标正文单位：`{book['target_text_units']}`",
        f"- 计划 digest：`{payload['content_digest']}`",
        "",
        "## 诊断",
        "",
    ]
    if payload["diagnostics"]:
        lines.extend(f"- `{item.get('code')}`：{json.dumps(item, ensure_ascii=False)}" for item in payload["diagnostics"])
    else:
        lines.append("- 未发现计划结构诊断项")
    lines += ["", "## 卷候选", "", "| 卷 | 标题 | 章节范围 | 章节数 | 估算正文单位 | 来源 |", "|---:|---|---:|---:|---:|---|"]
    for volume in payload["volumes"]:
        scope = f"{volume['start_chapter'] or '?'}-{volume['end_chapter'] or '?'}"
        lines.append(f"| {volume['volume_number']} | {volume['title']} | {scope} | {len(volume['chapter_numbers'])} | {volume['target_text_units'] or '-'} | {volume['source']} |")
    lines += ["", "## 章节计划候选", "", "| 章 | 标题 | 卷 | 目标正文单位 | 场景数 | 事件数 | 来源 |", "|---:|---|---:|---:|---:|---:|---|"]
    for chapter in payload["chapters"]:
        lines.append(f"| {chapter['chapter_number']} | {chapter['title']} | {chapter['volume_number'] or '-'} | {chapter['target_text_units'] or '-'} | {len(chapter['scene_plans'])} | {len(chapter['key_events'])} | {chapter['source']} |")
    return "\n".join(lines) + "\n"


async def main() -> int:
    args = _args()
    from app.db.session import AsyncSessionLocal
    from app.models.novel import NovelProject
    from app.services.novel_plan_hierarchy import build_plan_hierarchy

    async with AsyncSessionLocal() as session:
        statement = (
            select(NovelProject)
            .where(NovelProject.id == args.project)
            .options(selectinload(NovelProject.blueprint), selectinload(NovelProject.outlines))
        )
        project = (await session.execute(statement)).scalar_one_or_none()
        if project is None:
            raise SystemExit(f"novel project not found: {args.project}")
        hierarchy = build_plan_hierarchy(project, target_text_units=args.target_text_units)

    payload = hierarchy.as_dict()
    payload["content_digest"] = hierarchy.content_digest
    payload["candidate_status"] = "read_only_candidate"
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"novel-100k-plan-candidate-20260831-{args.project}"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(markdown_path), "content_digest": hierarchy.content_digest, "volume_count": len(hierarchy.volumes), "chapter_count": len(hierarchy.chapters), "diagnostic_count": len(hierarchy.diagnostics)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

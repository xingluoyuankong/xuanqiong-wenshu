from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a read-only formal-text baseline for one novel project.")
    parser.add_argument("--project", required=True, help="Novel project id")
    parser.add_argument(
        "--output-dir",
        default=str(ROOT.parent / "audit" / "production-readiness" / "evidence"),
        help="Directory used for JSON and Markdown evidence",
    )
    parser.add_argument("--counting-policy", default="zh-visible-v1")
    return parser.parse_args()


def _markdown(payload: dict) -> str:
    volumes = payload.get("volume_distribution") or []
    chapters = payload.get("chapter_distribution") or []
    lines = [
        "# 十万字小说正文基线",
        "",
        f"- 项目：`{payload['project_id']}`",
        f"- 标题：{payload['project_title']}",
        f"- 生成时间：{payload['generated_at']}",
        f"- 统计策略：`{payload['counting_policy']['version']}`",
        f"- 正式正文 text_units：`{payload['text_units']}`",
        f"- 章节：`{payload['selected_chapter_count']}/{payload['chapter_count']}`",
        f"- 覆盖率：`{payload['chapter_coverage_ratio']:.2%}`",
        f"- 缺少 selected version：`{payload['missing_selected_version_count']}`",
        f"- 空 selected version：`{payload['empty_selected_content_count']}`",
        f"- 内容 digest：`{payload['content_digest']}`",
        "",
        "## 卷分布",
        "",
    ]
    if volumes:
        lines += ["| 卷 | 范围 | 已选章节 | text_units |", "|---|---:|---:|---:|"]
        for volume in volumes:
            scope = f"{volume['start_chapter'] or '?'}-{volume['end_chapter'] or '?'}"
            lines.append(f"| {volume['title']} | {scope} | {volume['selected_chapter_count']}/{volume['chapter_count']} | {volume['text_units']} |")
    else:
        lines.append("未在当前蓝图中找到可解析的 `volume_plan`；正文基线仍按章节正式版本计算。")
    lines += ["", "## 章节分布", "", "| 章 | selected version | 状态 | text_units |", "|---:|---:|---|---:|"]
    for chapter in chapters:
        lines.append(f"| {chapter['chapter_number']} | {chapter['selected_version_id'] or '-'} | {chapter['status']} | {chapter['text_units']} |")
    lines.append("")
    return "\n".join(lines)


async def _main() -> int:
    args = _arguments()
    from app.db.session import AsyncSessionLocal
    from app.services.novel_benchmark_service import CountingPolicy, NovelBenchmarkService

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    async with AsyncSessionLocal() as session:
        baseline = await NovelBenchmarkService(session).build_baseline(
            args.project,
            policy=CountingPolicy(version=args.counting_policy),
        )
    payload = baseline.as_dict()
    stem = f"novel-100k-baseline-20260831-{args.project}"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(markdown_path), "text_units": payload["text_units"], "content_digest": payload["content_digest"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))

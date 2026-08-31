from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.orm import selectinload

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a bounded context snapshot evidence file for a novel chapter scope.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--chapter", type=int, required=True)
    parser.add_argument("--output-dir", default=str(ROOT.parent / "audit" / "production-readiness" / "evidence"))
    parser.add_argument("--max-text-units", type=int, default=20_000)
    return parser.parse_args()


def _json(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value[:24]]
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in list(value.items())[:32]}
    return str(value)


def _record(ref_type, ref_key, project_id, *, chapter_number=None, reason_code="related_context", text_units=0, **payload):
    return {"project_id": project_id, "ref_type": ref_type, "ref_key": ref_key, "chapter_number": chapter_number, "reason_code": reason_code, "text_units": max(0, int(text_units or 0)), **{k: _json(v) for k, v in payload.items()}}


def _markdown(payload: dict) -> str:
    lines = [
        "# 十万字项目上下文快照证据",
        "",
        f"- 快照：`{payload['snapshot_id']}`",
        f"- 项目：`{payload['project_id']}`",
        f"- 目标章节：`{payload['target_chapter']}`",
        f"- 策略：`{payload['selection_policy_version']}`",
        f"- 预算：`{payload['budget_text_units']}`",
        f"- 已选估算单位：`{payload['estimated_text_units']}`",
        f"- selected：`{len(payload['selected'])}`",
        f"- excluded：`{len(payload['excluded'])}`",
        f"- compressed：`{len(payload['compressed'])}`",
        f"- stale：`{len(payload['stale'])}`",
        f"- conflicts：`{len(payload['conflicts'])}`",
        f"- digest：`{payload['digest']}`",
        "",
        "## 已选上下文",
        "",
        "| 类型 | 引用 | 章节 | 单位 | 原因 |",
        "|---|---|---:|---:|---|",
    ]
    for item in payload["selected"]:
        lines.append(f"| {item['ref_type']} | {item['ref_key']} | {item['chapter_number'] or '-'} | {item['text_units']} | {item['reason_code']} |")
    lines += ["", "## 选择说明", "", "快照只包含目标项目、目标章节之前的结构化记录和选定章节版本摘要；未来章节和其他项目记录在构建阶段被拒绝。正文大对象不写入该证据文件，只保存引用、摘要字段和单位估算。", ""]
    return "\n".join(lines)


async def main() -> int:
    options = args()
    from app.db.session import AsyncSessionLocal
    from app.models.agent_quality import QualityFinding
    from app.models.foreshadowing import Foreshadowing
    from app.models.memory_layer import CausalChain, CharacterState, TimelineEvent
    from app.models.novel import Chapter, ChapterOutline, NovelProject
    from app.services.novel_context_snapshot_service import ContextSelectionRequest, ContextSnapshotBuilder

    async with AsyncSessionLocal() as session:
        project = (await session.execute(
            select(NovelProject)
            .where(NovelProject.id == options.project)
            .options(
                selectinload(NovelProject.blueprint),
                selectinload(NovelProject.outlines),
                selectinload(NovelProject.chapters).selectinload(Chapter.selected_version),
            )
        )).scalar_one_or_none()
        if project is None:
            raise SystemExit(f"novel project not found: {options.project}")
        records = [_record("project", project.id, project.id, reason_code="current_scope", summary=project.title)]
        for outline in project.outlines:
            if outline.chapter_number <= options.chapter:
                records.append(_record("chapter_plan", f"chapter-plan:{outline.chapter_number}", project.id, chapter_number=outline.chapter_number, reason_code="current_scope" if outline.chapter_number == options.chapter else "recent_continuity", title=outline.title, summary=outline.summary))
        for chapter in project.chapters:
            if chapter.chapter_number > options.chapter or chapter.selected_version is None:
                continue
            version = chapter.selected_version
            reason = "current_scope" if chapter.chapter_number == options.chapter else "recent_continuity"
            records.append(_record("chapter_version", f"chapter-version:{version.id}", project.id, chapter_number=chapter.chapter_number, reason_code=reason, text_units=len([c for c in str(version.content or "") if not c.isspace()]), version_id=version.id, content_digest=version.content_hash))
        model_specs = [
            (CharacterState, "character_state", "character_state", "character_dependency"),
            (TimelineEvent, "timeline", "timeline", "causal_dependency"),
            (CausalChain, "causal_chain", "causal", "causal_dependency"),
            (Foreshadowing, "foreshadowing", "foreshadowing", "foreshadowing_dependency"),
            (QualityFinding, "quality_finding", "quality", "quality_blocker"),
        ]
        for model, ref_type, key_prefix, reason in model_specs:
            try:
                rows = (await session.execute(select(model).where(model.project_id == options.project_id))).scalars().all()
            except Exception:
                rows = []
            for row in rows:
                chapter_number = getattr(row, "chapter_number", None) or getattr(row, "resolved_chapter_number", None)
                if chapter_number is not None and int(chapter_number) > options.chapter:
                    continue
                key = getattr(row, "finding_id", None) or getattr(row, "name", None) or getattr(row, "event_title", None) or getattr(row, "id", None)
                records.append(_record(ref_type, f"{key_prefix}:{key}", project.id, chapter_number=chapter_number, reason_code=reason, status=getattr(row, "status", None), name=getattr(row, "name", None), title=getattr(row, "event_title", None), message=getattr(row, "message", None), severity=getattr(row, "severity", None), summary=getattr(row, "event_description", None) or getattr(row, "content", None)))
    snapshot_id = f"novel-100k-ch{options.chapter}-{uuid4()}"
    payload = ContextSnapshotBuilder(ContextSelectionRequest(project_id=options.project, target_chapter=options.chapter, max_text_units=options.max_text_units)).build(records, snapshot_id=snapshot_id).as_dict()
    output_dir = Path(options.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"novel-100k-context-snapshot-20260831-{options.project}-ch{options.chapter}"
    json_path = output_dir / f"{stem}.json"
    markdown_path = output_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(markdown_path), "snapshot_id": snapshot_id, "target_chapter": options.chapter, "selected": len(payload["selected"]), "estimated_text_units": payload["estimated_text_units"], "digest": payload["digest"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

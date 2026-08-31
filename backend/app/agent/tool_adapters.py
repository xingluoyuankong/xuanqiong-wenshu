"""项目内 Agent 只读工具适配器；不复制领域业务逻辑。"""
from __future__ import annotations

import asyncio
import difflib
from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import select

from ..schemas.novel import NovelSectionType
from ..models.agent import AgentArtifactRef, AgentRun
from ..models.agent_quality import QualityFinding, QualityResult
from ..models.novel import BlueprintCharacter, Chapter, ChapterOutline, ChapterVersion, NovelProject
from ..models.faction import Faction
from ..models.foreshadowing import Foreshadowing
from ..models.knowledge_graph import CharacterNode
from ..models.research import ResearchArtifact
from ..models.project_memory import ProjectMemory
from ..services.foreshadowing_service import ForeshadowingService
from ..services.knowledge_graph_service import KnowledgeGraphService
from ..services.novel_service import NovelService
from ..services.style_rag_service import StyleRAGService


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if hasattr(value, "model_dump"):
        return _plain(value.model_dump(mode="json"))
    if hasattr(value, "__table__"):
        return {column.name: _plain(getattr(value, column.name, None)) for column in value.__table__.columns}
    return str(value)


async def execute_project_list(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    novel = NovelService(session)
    return {"tool_name": "project.list", "projects": _plain(await novel.list_projects_for_user(user_id))}


async def execute_project_context(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if not project_id:
        raise ValueError("project-scoped tool requires project_id")
    return {"tool_name": "project.context", "project": _plain(await NovelService(session).get_project_schema(project_id, user_id))}


async def execute_entity_inspect(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read only the user-selected project entities; never bulk-dumps project prose."""
    if not project_id:
        raise ValueError("project-scoped tool requires project_id")
    rows = (arguments or {}).get("entity_refs")
    if not isinstance(rows, list) or not rows:
        raise ValueError("entity.inspect requires selected entity_refs")
    if len(rows) > 16:
        raise ValueError("entity.inspect accepts at most 16 entity_refs")
    model_by_kind = {
        "character": BlueprintCharacter,
        "faction": Faction,
        "foreshadowing": Foreshadowing,
        "knowledge_node": CharacterNode,
        "research_artifact": ResearchArtifact,
    }
    summaries: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("entity_refs items must be objects")
        kind = str(item.get("kind") or "")
        try:
            entity_id = int(item.get("entity_id"))
        except (TypeError, ValueError) as exc:
            raise ValueError("entity_refs entity_id must be an integer") from exc
        model = model_by_kind.get(kind)
        if model is None:
            raise ValueError(f"unsupported entity context kind: {kind}")
        filters = [model.id == entity_id, model.project_id == project_id]
        if model is ResearchArtifact:
            filters.append(ResearchArtifact.user_id == user_id)
        entity = await session.scalar(select(model).where(*filters))
        if entity is None:
            raise ValueError(f"{kind} entity is unavailable for this project")
        if kind == "character":
            payload = {"name": entity.name, "identity": entity.identity, "personality": (entity.personality or "")[:800], "goals": (entity.goals or "")[:800]}
        elif kind == "faction":
            payload = {"name": entity.name, "faction_type": entity.faction_type, "leader": entity.leader, "current_status": (entity.current_status or "")[:800], "description": (entity.description or "")[:800]}
        elif kind == "foreshadowing":
            payload = {"name": entity.name, "chapter_number": entity.chapter_number, "status": entity.status, "type": entity.type, "content": (entity.content or "")[:800], "target_reveal_chapter": entity.target_reveal_chapter}
        elif kind == "knowledge_node":
            payload = {"name": entity.name, "role_type": entity.role_type, "status": entity.status, "location": entity.location, "description": (entity.description or "")[:800], "traits": list(entity.traits or [])[:12]}
        else:
            payload = {"scope": entity.scope, "chapter_number": entity.chapter_number, "status": entity.status, "trigger": entity.trigger, "summary": (entity.summary or "")[:1000], "source_count": len(entity.sources or [])}
        summaries.append({"kind": kind, "entity_id": entity_id, "summary": payload})
    return {"tool_name": "entity.inspect", "entities": summaries}


async def execute_quality_finding_inspect(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read only selected relational quality findings; never expose evidence/prose payloads."""
    if not project_id:
        raise ValueError("project-scoped tool requires project_id")
    rows = (arguments or {}).get("quality_finding_refs")
    if not isinstance(rows, list) or not rows:
        raise ValueError("quality.finding.inspect requires selected quality_finding_refs")
    if len(rows) > 16:
        raise ValueError("quality.finding.inspect accepts at most 16 quality finding refs")
    findings: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("quality_finding_refs items must be objects")
        finding_id = str(item.get("finding_id") or "").strip()
        if not finding_id:
            raise ValueError("quality finding ref requires finding_id")
        finding = await session.scalar(
            select(QualityFinding)
            .join(QualityResult, QualityResult.id == QualityFinding.quality_result_id)
            .join(AgentArtifactRef, AgentArtifactRef.id == QualityResult.artifact_ref_id)
            .join(AgentRun, AgentRun.id == QualityResult.run_id)
            .where(
                QualityFinding.finding_id == finding_id,
                QualityResult.run_id == AgentArtifactRef.run_id,
                QualityResult.user_id == user_id,
                QualityResult.project_id == project_id,
                AgentArtifactRef.user_id == user_id,
                AgentArtifactRef.project_id == project_id,
                AgentRun.user_id == user_id,
                AgentRun.project_id == project_id,
            )
        )
        if finding is None:
            raise ValueError("quality finding is unavailable for this project")
        findings.append({
            "finding_id": finding.finding_id,
            "code": finding.code,
            "category": finding.category,
            "severity": finding.severity,
            "status": finding.status,
            "message": finding.message[:800],
        })
    return {"tool_name": "quality.finding.inspect", "findings": findings}


async def execute_chapter_inspect(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if not project_id:
        raise ValueError("project-scoped tool requires project_id")
    arguments = arguments or {}
    data = _plain(await NovelService(session).get_section_data(project_id, user_id, NovelSectionType.CHAPTERS))
    chapter_number = arguments.get("chapter_number")
    if chapter_number is not None and isinstance(data.get("data"), dict):
        chapters = data["data"].get("chapters")
        if isinstance(chapters, list):
            data["data"]["chapters"] = [item for item in chapters if item.get("chapter_number") == int(chapter_number)]
    return {"tool_name": "chapter.inspect", "result": data}


async def execute_chapter_version_list(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """List safe version metadata without exposing chapter正文 to the planner/UI."""
    if not project_id:
        raise ValueError("project-scoped tool requires project_id")
    arguments = arguments or {}
    try:
        limit = min(100, max(1, int(arguments.get("limit", 50))))
    except (TypeError, ValueError):
        limit = 50
    chapter_number = arguments.get("chapter_number")
    try:
        chapter_number = int(chapter_number) if chapter_number is not None else None
    except (TypeError, ValueError) as exc:
        raise ValueError("chapter_number must be an integer") from exc
    stmt = (
        select(Chapter, ChapterVersion)
        .join(ChapterVersion, ChapterVersion.chapter_id == Chapter.id)
        .join(NovelProject, NovelProject.id == Chapter.project_id)
        .where(Chapter.project_id == project_id, NovelProject.user_id == user_id)
    )
    if chapter_number is not None:
        stmt = stmt.where(Chapter.chapter_number == chapter_number)
    stmt = stmt.order_by(Chapter.chapter_number.asc(), ChapterVersion.created_at.desc(), ChapterVersion.id.desc()).limit(limit)
    rows = list((await session.execute(stmt)).all())
    versions = []
    for chapter, version in rows:
        created_at = version.created_at.isoformat() if isinstance(version.created_at, datetime) else str(version.created_at or "")
        versions.append({
            "version_id": int(version.id),
            "chapter_id": int(chapter.id),
            "chapter_number": int(chapter.chapter_number),
            "version_label": version.version_label,
            "provider": version.provider,
            "status": version.status,
            "content_hash": version.content_hash,
            "parent_version_id": version.parent_version_id,
            "selected": chapter.selected_version_id == version.id,
            "word_count": len(str(version.content or "")),
            "created_at": created_at,
        })
    return {"tool_name": "chapter.version.list", "count": len(versions), "versions": versions}


async def execute_chapter_version_diff(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compare two same-chapter versions with bounded, project-scoped diff output."""
    if not project_id:
        raise ValueError("project-scoped tool requires project_id")
    arguments = arguments or {}
    try:
        chapter_number = int(arguments.get("chapter_number"))
        from_version_id = int(arguments.get("from_version_id"))
        to_version_id = int(arguments.get("to_version_id"))
    except (TypeError, ValueError) as exc:
        raise ValueError("chapter_number/from_version_id/to_version_id must be integers") from exc
    try:
        max_lines = min(200, max(1, int(arguments.get("max_lines", 100))))
    except (TypeError, ValueError):
        max_lines = 100
    stmt = (
        select(Chapter, ChapterVersion)
        .join(ChapterVersion, ChapterVersion.chapter_id == Chapter.id)
        .join(NovelProject, NovelProject.id == Chapter.project_id)
        .where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number,
            NovelProject.user_id == user_id,
            ChapterVersion.id.in_([from_version_id, to_version_id]),
        )
    )
    rows = list((await session.execute(stmt)).all())
    by_id = {int(version.id): (chapter, version) for chapter, version in rows}
    if from_version_id == to_version_id or from_version_id not in by_id or to_version_id not in by_id:
        raise ValueError("version ids must belong to the same accessible chapter and be different")
    from_chapter, from_version = by_id[from_version_id]
    to_chapter, to_version = by_id[to_version_id]
    if from_chapter.id != to_chapter.id:
        raise ValueError("version ids must belong to the same chapter")
    original = str(from_version.content or "").splitlines()
    patched = str(to_version.content or "").splitlines()
    lines: list[dict[str, Any]] = []
    counts = {"added": 0, "deleted": 0, "modified": 0, "unchanged": 0}
    matcher = difflib.SequenceMatcher(a=original, b=patched, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            counts["unchanged"] += i2 - i1
            continue
        if tag == "replace":
            width = max(i2 - i1, j2 - j1)
            for offset in range(width):
                old_value = original[i1 + offset] if i1 + offset < i2 else None
                new_value = patched[j1 + offset] if j1 + offset < j2 else None
                change_type = "modified" if old_value is not None and new_value is not None else ("deleted" if old_value is not None else "added")
                counts[change_type] += 1
                if len(lines) < max_lines:
                    lines.append({"line_number": j1 + offset + 1, "original_line": old_value, "patched_line": new_value, "change_type": change_type})
        elif tag == "delete":
            counts["deleted"] += i2 - i1
            for value in original[i1:i2]:
                if len(lines) < max_lines:
                    lines.append({"line_number": j1 + 1, "original_line": value, "patched_line": None, "change_type": "deleted"})
        elif tag == "insert":
            counts["added"] += j2 - j1
            for offset, value in enumerate(patched[j1:j2]):
                if len(lines) < max_lines:
                    lines.append({"line_number": j1 + offset + 1, "original_line": None, "patched_line": value, "change_type": "added"})
    return {
        "tool_name": "chapter.version.diff",
        "chapter_number": chapter_number,
        "from_version_id": from_version_id,
        "to_version_id": to_version_id,
        "from_content_hash": from_version.content_hash,
        "to_content_hash": to_version.content_hash,
        "summary": counts,
        "diff_lines": lines[:max_lines],
    }


async def execute_outline_inspect(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if not project_id:
        raise ValueError("project-scoped tool requires project_id")
    return {"tool_name": "outline.inspect", "result": _plain(await NovelService(session).get_section_data(project_id, user_id, NovelSectionType.CHAPTER_OUTLINE))}


async def execute_quality_inspect(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if not project_id:
        raise ValueError("project-scoped tool requires project_id")
    section = _plain(await NovelService(session).get_section_data(project_id, user_id, NovelSectionType.CHAPTERS))
    chapters = section.get("data", {}).get("chapters", []) if isinstance(section, dict) else []
    observed = []
    for chapter in chapters if isinstance(chapters, list) else []:
        runtime = chapter.get("generation_runtime") or {}
        gate = runtime.get("quality_gate") if isinstance(runtime, dict) else None
        observed.append({"chapter_number": chapter.get("chapter_number"), "status": chapter.get("generation_status"), "quality_gate": gate})
    return {"tool_name": "quality.inspect", "result": {"chapter_count": len(observed), "chapters": observed, "source": "NovelService.get_section_data"}}


async def execute_quality_retest(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Re-run the structural quality gate for an owned ChapterVersion without writes."""
    if not project_id:
        raise ValueError("project-scoped tool requires project_id")
    arguments = arguments or {}
    try:
        chapter_number = int(arguments.get("chapter_number"))
        version_id = int(arguments.get("version_id"))
    except (TypeError, ValueError) as exc:
        raise ValueError("chapter_number and version_id must be integers") from exc
    stmt = (
        select(Chapter, ChapterVersion)
        .join(ChapterVersion, ChapterVersion.chapter_id == Chapter.id)
        .join(NovelProject, NovelProject.id == Chapter.project_id)
        .where(
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number,
            ChapterVersion.id == version_id,
            NovelProject.user_id == user_id,
        )
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        raise ValueError("version does not belong to the accessible project/chapter")
    chapter, version = row
    metadata = dict(version.metadata or {}) if isinstance(version.metadata, dict) else {}
    from .write_executor import _quality_observation
    _summaries, gate = _quality_observation(str(version.content or ""), metadata)
    raw_blockers = gate.get("blockers") if isinstance(gate.get("blockers"), list) else []
    blockers = []
    for raw in raw_blockers[:100]:
        item = raw if isinstance(raw, dict) else {"code": str(raw)}
        blockers.append({
            "code": str(item.get("code") or "quality_blocker")[:120],
            "severity": str(item.get("severity") or "blocker")[:32],
            "message": str(item.get("message") or item.get("hint") or "")[:500],
            "source": str(item.get("source") or "quality_gate")[:120],
            "snippet": str(item.get("snippet") or item.get("text") or "")[:240] or None,
        })
    return {
        "tool_name": "quality.retest",
        "project_id": project_id,
        "chapter_number": chapter_number,
        "version_id": version_id,
        "content_hash": version.content_hash,
        "word_count": len(str(version.content or "")),
        "quality_status": "passed" if bool(gate.get("passed", False)) else "blocked",
        "quality_gate": {
            "passed": bool(gate.get("passed", False)),
            "tone": str(gate.get("tone") or "")[:32],
            "quality_score": gate.get("quality_score"),
            "quality_issue_codes": [str(code)[:120] for code in list(gate.get("quality_issue_codes") or [])[:100]],
            "quality_issue_labels": [str(label)[:240] for label in list(gate.get("quality_issue_labels") or [])[:100]],
            "blocker_count": len(raw_blockers),
            "blockers": blockers,
        },
    }


async def execute_quality_rewrite_instructions(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return safe rewrite proposals for one owned candidate Artifact without exposing its prose."""
    if not project_id:
        raise ValueError("project-scoped tool requires project_id")
    artifact_id = str((arguments or {}).get("artifact_id") or "").strip()
    if not artifact_id:
        raise ValueError("artifact_id is required")
    artifact = (await session.execute(
        select(AgentArtifactRef)
        .join(NovelProject, NovelProject.id == AgentArtifactRef.project_id)
        .where(
            AgentArtifactRef.id == artifact_id,
            AgentArtifactRef.user_id == user_id,
            AgentArtifactRef.project_id == project_id,
            NovelProject.user_id == user_id,
        )
    )).scalar_one_or_none()
    if artifact is None:
        # Deliberately avoid revealing whether the artifact exists in another project/account.
        raise ValueError("artifact does not belong to the accessible project")

    from .write_executor import build_rewrite_instructions, list_artifact_rewrite_instructions

    raw_instructions = await list_artifact_rewrite_instructions(
        artifact_id=artifact.id, user_id=user_id, session=session
    )
    metadata = dict(artifact.metadata_json or {})
    chapter_number = metadata.get("chapter_number")
    try:
        chapter_number = int(chapter_number) if chapter_number is not None else None
    except (TypeError, ValueError):
        chapter_number = None
    source_version_id = metadata.get("source_version_id")
    try:
        source_version_id = int(source_version_id) if source_version_id is not None else None
    except (TypeError, ValueError):
        source_version_id = None

    # The existing Artifact endpoint is allowed to include a short anchor snippet for a user
    # who explicitly opens the Artifact.  The Planner-facing Tool must never receive prose,
    # including prose embedded in an instruction string, so rebuild each proposal from only
    # structural blocker fields and retain offsets as redacted anchors.
    safe_blockers: list[dict[str, Any]] = []
    for raw in raw_instructions[:100]:
        item = raw if isinstance(raw, dict) else {}
        safe_blockers.append({
            "code": str(item.get("code") or "quality_blocker")[:120],
            "severity": str(item.get("severity") or "blocker")[:32],
            "message": str(item.get("message") or item.get("code") or "质量阻断")[:1000],
            "source": str(item.get("source") or "quality_gate")[:120],
            "start_char": item.get("start_char"),
            "end_char": item.get("end_char"),
            "anchor_status": "redacted" if item.get("anchor_status") == "located" else "unavailable",
        })
    instructions = build_rewrite_instructions(
        safe_blockers,
        artifact_id=artifact.id,
        project_id=project_id,
        chapter_number=chapter_number,
        source_version_id=source_version_id,
    )
    for item in instructions:
        # Project/artifact identity is provided once at the envelope level.  Snippets and
        # deep links are intentionally omitted so this bounded Tool cannot leak candidate text.
        item.pop("artifact_id", None)
        item.pop("project_id", None)
        item.pop("snippet", None)
    return {
        "tool_name": "quality.rewrite_instructions",
        "artifact_id": artifact.id,
        "chapter_number": chapter_number,
        "instruction_count": len(instructions),
        "instructions": instructions,
    }


async def execute_statistics_project(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return compact project/quality counters without loading chapter prose or mutating runtime."""
    if not project_id:
        raise ValueError("project-scoped tool requires project_id")
    project = (await session.execute(
        select(NovelProject).where(NovelProject.id == project_id, NovelProject.user_id == user_id)
    )).scalar_one_or_none()
    if project is None:
        raise ValueError("project is not accessible")
    chapters = list((await session.execute(
        select(Chapter).where(Chapter.project_id == project_id).order_by(Chapter.chapter_number.asc())
    )).scalars().all())
    outlines = list((await session.execute(
        select(ChapterOutline).where(ChapterOutline.project_id == project_id)
    )).scalars().all())
    outline_count = len(outlines)
    selected_ids = [int(chapter.selected_version_id) for chapter in chapters if chapter.selected_version_id is not None]
    selected_versions = []
    if selected_ids:
        selected_versions = list((await session.execute(select(ChapterVersion).where(ChapterVersion.id.in_(selected_ids)))).scalars().all())
    version_by_id = {int(version.id): version for version in selected_versions}
    status_counts = Counter(str(chapter.status or "unknown")[:64] for chapter in chapters)
    quality_passed = quality_blocked = quality_unknown = 0
    blocker_counts: Counter[str] = Counter()
    for chapter in chapters:
        if chapter.selected_version_id is None:
            continue
        version = version_by_id.get(int(chapter.selected_version_id))
        metadata = dict(version.metadata or {}) if version is not None and isinstance(version.metadata, dict) else {}
        gate = metadata.get("quality_gate") if isinstance(metadata.get("quality_gate"), dict) else {}
        if not gate:
            quality_unknown += 1
            continue
        if bool(gate.get("passed", False)):
            quality_passed += 1
        else:
            quality_blocked += 1
        for blocker in list(gate.get("blockers") or [])[:100]:
            code = str(blocker.get("code") if isinstance(blocker, dict) else blocker)[:120]
            if code:
                blocker_counts[code] += 1
    total_word_count = sum(max(0, int(chapter.word_count or 0)) for chapter in chapters)
    return {
        "tool_name": "statistics.project",
        "project_id": project_id,
        "project": {
            "title": str(project.title)[:255],
            "status": str(project.status or "")[:64],
            "updated_at": project.updated_at.isoformat() if isinstance(project.updated_at, datetime) else str(project.updated_at or ""),
        },
        "chapters": {
            "chapter_count": len(chapters),
            "outline_count": outline_count,
            "selected_version_count": len(selected_ids),
            "total_word_count": total_word_count,
            "status_counts": dict(sorted(status_counts.items())),
            "latest_chapter_number": max((int(chapter.chapter_number) for chapter in chapters), default=None),
        },
        "quality": {
            "evaluated_version_count": quality_passed + quality_blocked,
            "passed_count": quality_passed,
            "blocked_count": quality_blocked,
            "unknown_count": quality_unknown,
            "top_blocker_counts": dict(blocker_counts.most_common(20)),
        },
    }


async def execute_knowledge_inspect(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if not project_id:
        raise ValueError("project-scoped tool requires project_id")
    await NovelService(session).ensure_project_owner(project_id, user_id)
    return {"tool_name": "knowledge.inspect", "result": _plain(await KnowledgeGraphService(session).get_project_graph(project_id))}


def _safe_style_value(value: Any, *, depth: int = 0) -> Any:
    """Keep style summaries useful while excluding raw source/prompt payloads."""
    if depth >= 3:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, list):
        return [_safe_style_value(item, depth=depth + 1) for item in value[:20]]
    if isinstance(value, dict):
        return {str(key)[:80]: _safe_style_value(item, depth=depth + 1) for key, item in list(value.items())[:30]}
    return str(value)[:500]


async def execute_style_inspect(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read style metadata without extraction, generation, source prose, or prompt context."""
    if not project_id:
        raise ValueError("project-scoped tool requires project_id")
    await NovelService(session).ensure_project_owner(project_id, user_id)
    style_service = StyleRAGService(session, llm_service=None)
    profiles = await style_service.list_style_profiles(user_id)
    memory_extra = (await session.execute(select(ProjectMemory.extra).where(ProjectMemory.project_id == project_id))).scalar_one_or_none()
    applied_profile_id = str((memory_extra or {}).get("applied_style_profile_id") or "") if isinstance(memory_extra, dict) else ""
    project_feature = await style_service.get_style_for_project(project_id)
    rows = []
    for profile in profiles[:50]:
        summary = _safe_style_value(profile.summary)
        feature = profile.style_feature if isinstance(profile.style_feature, dict) else {}
        rows.append({
            "profile_id": str(profile.id),
            "name": str(profile.name)[:255],
            "profile_type": str(profile.profile_type)[:64],
            "global_active": bool(profile.active),
            "applied_to_project": str(profile.id) == applied_profile_id,
            "source_count": len(profile.source_ids or []),
            "summary": summary,
            "feature_dimensions": [str(key)[:80] for key in list(feature.keys())[:20]],
            "quality_metric_keys": [str(key)[:80] for key in list((profile.quality_metrics or {}).keys())[:20]],
            "created_at": str(profile.created_at)[:64],
            "updated_at": str(profile.updated_at)[:64],
        })
    return {
        "tool_name": "style.inspect",
        "project_id": project_id,
        "profile_count": len(rows),
        "applied_profile_id": applied_profile_id or None,
        "project_chapter_style": _safe_style_value(project_feature.to_summary_dict()) if project_feature else None,
        "profiles": rows,
    }


async def execute_research_inspect(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Read safe persisted research summaries; never starts a network research job."""
    if not project_id:
        raise ValueError("project-scoped tool requires project_id")
    arguments = arguments or {}
    scope = arguments.get("scope")
    if scope is not None:
        scope = str(scope).strip()
        if scope not in {"global", "enhanced", "chapter"}:
            raise ValueError("scope must be global, enhanced, or chapter")
    chapter_number = arguments.get("chapter_number")
    try:
        chapter_number = int(chapter_number) if chapter_number is not None else None
    except (TypeError, ValueError) as exc:
        raise ValueError("chapter_number must be an integer") from exc
    try:
        limit = min(20, max(1, int(arguments.get("limit", 5))))
    except (TypeError, ValueError):
        limit = 5
    stmt = (
        select(ResearchArtifact)
        .join(NovelProject, NovelProject.id == ResearchArtifact.project_id)
        .where(
            ResearchArtifact.project_id == project_id,
            ResearchArtifact.user_id == user_id,
            NovelProject.user_id == user_id,
        )
    )
    if scope:
        stmt = stmt.where(ResearchArtifact.scope == scope)
    if chapter_number is not None:
        stmt = stmt.where(ResearchArtifact.chapter_number == chapter_number)
    stmt = stmt.order_by(ResearchArtifact.created_at.desc(), ResearchArtifact.id.desc()).limit(limit)
    artifacts = list((await session.execute(stmt)).scalars().all())
    rows = []
    for artifact in artifacts:
        payload = artifact.category_payload if isinstance(artifact.category_payload, dict) else {}
        categories = payload.get("categories") if isinstance(payload.get("categories"), dict) else {}
        error = artifact.error if isinstance(artifact.error, dict) else {}
        rows.append({
            "artifact_id": int(artifact.id),
            "run_id": str(artifact.run_id),
            "scope": str(artifact.scope),
            "chapter_number": artifact.chapter_number,
            "status": str(artifact.status),
            "trigger": str(artifact.trigger),
            "summary": str(artifact.summary or payload.get("summary") or "").strip()[:2000] or None,
            "query_count": len(artifact.query_plan or []),
            "source_count": len(artifact.sources or []),
            "category_keys": [str(key)[:80] for key in list(categories.keys())[:20]],
            "error_code": str(error.get("code") or "")[:120] or None,
            "retryable": bool(error.get("retryable")) if error else None,
            "created_at": artifact.created_at.isoformat() if isinstance(artifact.created_at, datetime) else str(artifact.created_at or ""),
            "finished_at": artifact.finished_at.isoformat() if isinstance(artifact.finished_at, datetime) else (str(artifact.finished_at) if artifact.finished_at else None),
        })
    return {"tool_name": "research.inspect", "count": len(rows), "artifacts": rows}


async def execute_foreshadowing_inspect(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if not project_id:
        raise ValueError("project-scoped tool requires project_id")
    await NovelService(session).ensure_project_owner(project_id, user_id)
    arguments = arguments or {}
    items, total = await ForeshadowingService(session).get_foreshadowings(project_id, limit=min(int(arguments.get("limit", 100)), 100))
    return {"tool_name": "foreshadowing.inspect", "result": {"total": total, "items": _plain(items)}}


async def execute_read_tool(*, tool_name: str, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None, cancel_event: asyncio.Event | None = None) -> dict[str, Any]:
    """Compatibility facade; actual dispatch is owned by the registry."""
    from .registry import DEFAULT_TOOL_REGISTRY
    return await DEFAULT_TOOL_REGISTRY.execute(tool_name, session=session, user_id=user_id, project_id=project_id, arguments=arguments, cancel_event=cancel_event)


async def execute_chapter_generate_candidate(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = dict(arguments or {})
    approval_id = str(arguments.pop('_approval_id', '')).strip()
    if not approval_id:
        raise ValueError('approved write handler requires _approval_id')
    if not project_id:
        raise ValueError('write handler requires project_id')
    from .write_executor import execute_approved_write
    artifact = await execute_approved_write(approval_id=approval_id, user_id=user_id, session=session)
    return {'artifact': artifact, 'tool_name': 'chapter.generate'}


async def execute_chapter_version_accept(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """Accept an approved candidate only through the registered, audited write path."""
    if not project_id:
        raise ValueError("write handler requires project_id")
    arguments = dict(arguments or {})
    approval_id = str(arguments.pop("_approval_id", "")).strip()
    artifact_id = str(arguments.get("artifact_id") or "").strip()
    if not approval_id or not artifact_id:
        raise ValueError("chapter.version.accept requires approval and artifact identity")
    from ..services.agent_runtime import AgentConflict, AgentRuntimeService, AgentScopeViolation
    from .write_executor import accept_candidate_artifact

    runtime = AgentRuntimeService(session)
    approval = await runtime.get_approval(approval_id=approval_id, user_id=user_id)
    requested = dict(approval.request_json or {})
    if approval.status != "approved":
        raise AgentConflict("approval must be approved before candidate acceptance")
    if approval.tool_name != "chapter.version.accept":
        raise AgentScopeViolation("approval is not for chapter.version.accept")
    if approval.project_id != project_id:
        raise AgentScopeViolation("approval project does not match requested project")
    if str(requested.get("artifact_id") or "") != artifact_id:
        raise AgentScopeViolation("approval artifact does not match requested artifact")
    artifact = (await session.execute(
        select(AgentArtifactRef).where(
            AgentArtifactRef.id == artifact_id,
            AgentArtifactRef.user_id == user_id,
            AgentArtifactRef.project_id == project_id,
            AgentArtifactRef.run_id == approval.run_id,
        )
    )).scalar_one_or_none()
    if artifact is None:
        raise AgentScopeViolation("candidate artifact does not belong to the approval run/project")

    approval = await runtime.claim_approval_execution(approval_id=approval.id, user_id=user_id)
    lease_owner = f"version-accept:{approval.id}"[:128]
    claimed_step = None
    capability_execution = None
    execution_facts = None
    try:
        if approval.step_id:
            claimed_step = await runtime.claim_step(
                step_id=approval.step_id, user_id=user_id, lease_owner=lease_owner, lease_seconds=120
            )
            if claimed_step.run_id != approval.run_id or claimed_step.tool_name != approval.tool_name:
                raise AgentScopeViolation("approval step does not match acceptance approval")
        from ..services.agent_execution_service import AgentExecutionService
        from .registry import DEFAULT_TOOL_REGISTRY

        execution_facts = AgentExecutionService(session)
        capability_execution = await execution_facts.begin_write_execution(
            run=await runtime.get_run(approval.run_id, user_id),
            approval=approval,
            step=claimed_step,
            arguments=arguments,
            lease_generation=int(claimed_step.lease_generation or 0) if claimed_step is not None else 0,
            actual_handler_identity=DEFAULT_TOOL_REGISTRY.get_handler_identity(approval.tool_name),
        )
        accepted = await accept_candidate_artifact(
            artifact_id=artifact.id,
            user_id=user_id,
            note=str(requested.get("note") or arguments.get("note") or "")[:2000] or None,
            session=session,
            acceptance_approval_id=approval.id,
        )
        if claimed_step is not None:
            await runtime.complete_step(
                step_id=claimed_step.id,
                lease_generation=int(claimed_step.lease_generation or 0), user_id=user_id, lease_owner=lease_owner,
                output={"artifact_id": accepted.id, "accepted_version_id": (accepted.metadata_json or {}).get("accepted_version_id")},
            )
        if capability_execution is not None and execution_facts is not None:
            await execution_facts.complete_write_execution(
                execution=capability_execution,
                lease_generation=int(claimed_step.lease_generation or 0) if claimed_step is not None else 0,
                output={
                    "artifact_id": accepted.id,
                    "kind": accepted.kind,
                    "accepted_version_id": (accepted.metadata_json or {}).get("accepted_version_id"),
                },
            )
        await runtime.mark_approval_executed(approval_id=approval.id, user_id=user_id, status="executed")
        return {"artifact": accepted, "tool_name": "chapter.version.accept"}
    except Exception as exc:
        if capability_execution is not None and execution_facts is not None:
            try:
                await execution_facts.fail_write_execution(
                    execution=capability_execution,
                    lease_generation=int(claimed_step.lease_generation or 0) if claimed_step is not None else 0,
                    error=exc,
                )
            except Exception:
                pass
        if claimed_step is not None:
            try:
                await runtime.fail_step(step_id=claimed_step.id, user_id=user_id, lease_owner=lease_owner, lease_generation=int(claimed_step.lease_generation or 0), error_type="ChapterVersionAcceptFailed")
            except Exception:
                pass
        try:
            current = await runtime.get_approval(approval_id=approval.id, user_id=user_id)
            if current.status == "executing":
                await runtime.mark_approval_executed(approval_id=approval.id, user_id=user_id, status="execution_failed")
        except Exception:
            pass
        raise


async def execute_chapter_rewrite_candidate(*, session, user_id: int, project_id: str | None, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    arguments = dict(arguments or {})
    approval_id = str(arguments.pop('_approval_id', '')).strip()
    if not approval_id:
        raise ValueError('approved write handler requires _approval_id')
    if not project_id:
        raise ValueError('write handler requires project_id')
    from .write_executor import execute_approved_write
    artifact = await execute_approved_write(approval_id=approval_id, user_id=user_id, session=session)
    return {'artifact': artifact, 'tool_name': 'chapter.rewrite'}

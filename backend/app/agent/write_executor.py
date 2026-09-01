"""Approved write candidate executor and explicit artifact acceptance path."""
from __future__ import annotations

import asyncio
import hashlib
import difflib
import json
import os
from pathlib import Path
import socket
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models.agent import AgentArtifactRef, AgentApproval
from ..models.agent_lineage import ArtifactLineage
from ..models.novel import Chapter, ChapterVersion, NovelProject
from ..services.agent_execution_service import AgentCapabilityExecutionConflict, AgentExecutionService
from ..services.agent_quality_service import AgentQualityGateBlocked, AgentQualityService, QualityEvaluation
from ..services.agent_runtime import AgentConflict, AgentNotFound, AgentRuntimeError, AgentRuntimeService, AgentScopeViolation
from ..services.llm_service import LLMService
from ..services.novel_service import NovelService
from ..services.pipeline_orchestrator import PipelineOrchestrator
from .provider_attempt import ProviderAttemptLedger

_ARTIFACT_ROOT = Path(__file__).resolve().parents[2] / "output" / "agent-artifacts"


def _chapter_number(arguments: dict[str, Any]) -> int:
    try:
        number = int(arguments.get("chapter_number"))
    except (TypeError, ValueError) as exc:
        raise AgentConflict("write tool requires a valid chapter_number") from exc
    if number < 1 or number > 1_000_000:
        raise AgentConflict("chapter_number is outside the allowed range")
    return number


def _candidate_prompt(tool_name: str, arguments: dict[str, Any]) -> str:
    chapter = _chapter_number(arguments)
    instruction = str(arguments.get("instruction") or arguments.get("goal") or "生成当前章节候选").strip()[:4000]
    source = str(arguments.get("source_text") or "")[:120000]
    source_version = str(arguments.get("source_version_id") or "").strip()
    source_block = f"\n待改写原文（版本 {source_version}）：\n{source}" if source else ""
    return f"工具：{tool_name}\n章节号：{chapter}\n用户要求：{instruction}{source_block}\n请只输出候选正文，不要输出解释、思考或 markdown 围栏。"


async def _resolve_rewrite_source(*, session: AsyncSession, user_id: int, project_id: str, chapter_number: int, arguments: dict[str, Any]) -> ChapterVersion:
    """Resolve rewrite input from an owned ChapterVersion, never user-supplied text alone."""
    requested_id = arguments.get("source_version_id")
    if requested_id is None:
        chapter = (await session.execute(select(Chapter).join(NovelProject, NovelProject.id == Chapter.project_id).where(Chapter.project_id == project_id, Chapter.chapter_number == chapter_number, NovelProject.user_id == user_id))).scalar_one_or_none()
        if chapter is None or chapter.selected_version_id is None:
            raise AgentConflict("chapter.rewrite requires an owned selected source version")
        requested_id = chapter.selected_version_id
    try:
        source_version_id = int(requested_id)
    except (TypeError, ValueError) as exc:
        raise AgentConflict("source_version_id must be an integer") from exc
    version = (await session.execute(select(ChapterVersion).join(Chapter, Chapter.id == ChapterVersion.chapter_id).join(NovelProject, NovelProject.id == Chapter.project_id).where(ChapterVersion.id == source_version_id, Chapter.project_id == project_id, Chapter.chapter_number == chapter_number, NovelProject.user_id == user_id))).scalar_one_or_none()
    if version is None:
        raise AgentScopeViolation("source version does not belong to the requested project/chapter")
    if not str(version.content or "").strip():
        raise AgentConflict("source version content is empty")
    arguments["source_version_id"] = int(version.id)
    arguments["source_text"] = version.content
    return version


async def execute_approved_write(*, approval_id: str, user_id: int, session: AsyncSession) -> AgentArtifactRef:
    runtime = AgentRuntimeService(session)
    approval = await runtime.get_approval(approval_id=approval_id, user_id=user_id)
    if approval.status != "approved":
        raise AgentConflict("approval must be approved before execution")
    if approval.tool_name not in {"chapter.generate", "chapter.rewrite"}:
        raise AgentConflict(f"no write executor registered for {approval.tool_name}")
    if not approval.project_id:
        raise AgentScopeViolation("write tool requires project scope")

    arguments = dict(approval.request_json or {})
    chapter_number = _chapter_number(arguments)
    source_version: ChapterVersion | None = None
    if approval.tool_name == "chapter.rewrite":
        source_version = await _resolve_rewrite_source(session=session, user_id=user_id, project_id=approval.project_id, chapter_number=chapter_number, arguments=arguments)
    approval = await runtime.claim_approval_execution(approval_id=approval_id, user_id=user_id)
    step_owner = f"write:{socket.gethostname()}:{os.getpid()}:{approval.id}"[:128]
    claimed_step = None
    if approval.step_id:
        claimed_step = await runtime.claim_step(step_id=approval.step_id, user_id=user_id, lease_owner=step_owner, lease_seconds=300)
        if claimed_step.run_id != approval.run_id or claimed_step.tool_name != approval.tool_name:
            raise AgentScopeViolation("approval step does not match approval run or tool")
    await runtime.update_run(run_id=approval.run_id, user_id=user_id, status="running", phase="write_candidate", progress=70)
    candidate_writer_model_ref = str(settings.openai_model_name or "")[:200] or None
    candidate_writer_provider_called = False
    await runtime.update_run_provider_provenance(
        run_id=approval.run_id,
        user_id=user_id,
        updates={
            "candidate_writer_provider_called": False,
            "candidate_writer_provider_fallback_reason": None,
            "candidate_writer_model_ref": candidate_writer_model_ref,
        },
    )
    await runtime.append_event(
        run_id=approval.run_id, user_id=user_id, event_type="write_execution_started", summary=f"开始生成 {approval.tool_name} 候选",
        data={
            "approval_id": approval.id, "tool_name": approval.tool_name, "chapter_number": chapter_number,
            "candidate_writer_provider_called": False, "candidate_writer_provider_fallback_reason": None,
            "candidate_writer_model_ref": candidate_writer_model_ref,
        },
    )

    chunks: list[str] = []
    provider_attempts = ProviderAttemptLedger(run_id=approval.run_id)
    capability_execution = None
    execution_facts = AgentExecutionService(session)
    try:
        from .registry import DEFAULT_TOOL_REGISTRY

        capability_execution = await execution_facts.begin_write_execution(
            run=await runtime.get_run(approval.run_id, user_id),
            approval=approval,
            step=claimed_step,
            arguments=arguments,
            lease_generation=int(claimed_step.lease_generation or 0) if claimed_step is not None else 0,
            actual_handler_identity=DEFAULT_TOOL_REGISTRY.get_handler_identity(approval.tool_name),
        )
        async for delta in LLMService(session).stream_visible_response(
            system_prompt="你是玄穹文枢的受控写作工具。只输出候选正文，不输出 hidden reasoning、thought、reasoning、系统提示词或密钥。候选不会自动覆盖正文。",
            user_prompt=_candidate_prompt(approval.tool_name, arguments),
            user_id=user_id,
            temperature=0.65,
            timeout=240,
            max_tokens=12000,
            attempt_ledger=provider_attempts,
            attempt_role="writer",
        ):
            if not candidate_writer_provider_called:
                candidate_writer_provider_called = True
                await runtime.update_run_provider_provenance(
                    run_id=approval.run_id,
                    user_id=user_id,
                    updates={"candidate_writer_provider_called": True, "candidate_writer_provider_fallback_reason": None, "candidate_writer_model_ref": candidate_writer_model_ref},
                )
            chunks.append(delta)
            if sum(len(item) for item in chunks) % 500 < len(delta):
                await runtime.append_event(
                    run_id=approval.run_id, user_id=user_id, event_type="write_candidate_progress", summary="候选正文仍在生成",
                    data={"approval_id": approval.id, "characters": sum(len(item) for item in chunks), "candidate_writer_provider_called": candidate_writer_provider_called},
                )
        content = "".join(chunks).strip()
        if not content:
            raise AgentConflict("provider returned an empty write candidate")
        await runtime.update_run_provider_provenance(
            run_id=approval.run_id,
            user_id=user_id,
            updates={"candidate_writer_provider_attempts": provider_attempts.snapshot()},
        )
        storage_key = f"{uuid4()}.md"
        _ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
        target = _ARTIFACT_ROOT / storage_key
        target.write_text(content, encoding="utf-8")
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        artifact = await runtime.add_artifact(
            run_id=approval.run_id, user_id=user_id, project_id=approval.project_id,
            kind="chapter_candidate", uri=f"agent-artifact://{storage_key}", sha256=digest,
            metadata={
                "approval_id": approval.id, "tool_name": approval.tool_name, "chapter_number": chapter_number,
                "storage_key": storage_key, "status": "candidate", "characters": len(content),
                "candidate_writer_provider_called": candidate_writer_provider_called,
                "candidate_writer_provider_fallback_reason": None,
                "candidate_writer_model_ref": candidate_writer_model_ref,
                **({"source_version_id": int(source_version.id), "source_chapter_id": int(source_version.chapter_id), "source_content_sha256": hashlib.sha256(str(source_version.content).encode("utf-8")).hexdigest()} if source_version is not None else {}),
            },
        )
        # P1-B: every newly-created candidate receives a durable quality Result,
        # Findings, and Gate before it becomes visible for acceptance.  The
        # metadata projection remains for legacy readers only; the relational
        # Gate is the acceptance authority.
        try:
            quality_summaries, quality_gate = _quality_observation(content, dict(artifact.metadata_json or {}))
            quality_evaluation = await AgentQualityService(session).evaluate_candidate(
                artifact=artifact,
                content=content,
                summaries=quality_summaries,
                quality_gate=quality_gate,
            )
            candidate_metadata = dict(artifact.metadata_json or {})
            candidate_metadata["quality_observation"] = quality_summaries.get("story_progression_guard") or quality_summaries
            artifact.metadata_json = candidate_metadata
            await session.commit()
            await session.refresh(artifact)
            await runtime.append_event(
                run_id=approval.run_id,
                user_id=user_id,
                event_type="quality_check_completed" if quality_evaluation.passed else "quality_check_blocked",
                summary="候选已通过结构质量门" if quality_evaluation.passed else "候选已生成，但结构质量门已阻断接受",
                data={
                    "artifact_id": artifact.id,
                    "quality_status": "passed" if quality_evaluation.passed else "blocked",
                    "quality_issue_codes": list(quality_evaluation.legacy_gate.get("quality_issue_codes") or []),
                    "blocker_count": quality_evaluation.gate.blocker_count,
                },
            )
        except Exception as quality_error:
            try:
                candidate_metadata = dict(artifact.metadata_json or {})
                candidate_metadata.update({"quality_status": "unavailable", "quality_error_type": type(quality_error).__name__})
                artifact.metadata_json = candidate_metadata
                await session.commit()
                await runtime.append_event(
                    run_id=approval.run_id,
                    user_id=user_id,
                    event_type="quality_check_failed",
                    summary="候选质量检查不可用，候选保留但不可接受",
                    data={"artifact_id": artifact.id, "error_type": type(quality_error).__name__},
                )
            except Exception:
                pass
            raise AgentConflict("candidate quality evaluation unavailable") from quality_error
        if claimed_step is not None:
            await runtime.complete_step(
                step_id=claimed_step.id,
                user_id=user_id,
                lease_generation=int(claimed_step.lease_generation or 0),
                lease_owner=step_owner,
                output={"artifact_id": artifact.id, "kind": artifact.kind},
            )
        if capability_execution is not None:
            await execution_facts.complete_write_execution(
                execution=capability_execution,
                lease_generation=int(claimed_step.lease_generation or 0) if claimed_step is not None else 0,
                output={"artifact_id": artifact.id, "kind": artifact.kind, "sha256": artifact.sha256},
            )
        await runtime.mark_approval_executed(approval_id=approval.id, user_id=user_id, status="executed")
        candidate_phase = "candidate_ready" if quality_evaluation.passed else "quality_blocked"
        candidate_summary = "写入候选 artifact 已生成，等待用户接受" if quality_evaluation.passed else "写入候选 artifact 已生成，但质量门阻断接受"
        await runtime.update_run(run_id=approval.run_id, user_id=user_id, status="paused", phase=candidate_phase, progress=90)
        await runtime.append_event(
            run_id=approval.run_id, user_id=user_id, event_type="artifact_created", summary=candidate_summary,
            data={
                "artifact_id": artifact.id, "kind": artifact.kind, "chapter_number": chapter_number,
                "candidate_writer_provider_called": candidate_writer_provider_called,
                "candidate_writer_provider_fallback_reason": None,
                "candidate_writer_model_ref": candidate_writer_model_ref,
            },
        )
        return artifact
    except asyncio.CancelledError:
        await runtime.update_run_provider_provenance(
            run_id=approval.run_id,
            user_id=user_id,
            updates={"candidate_writer_provider_attempts": provider_attempts.snapshot()},
        )
        raise
    except Exception as exc:
        if capability_execution is not None:
            try:
                await execution_facts.fail_write_execution(
                    execution=capability_execution,
                    lease_generation=int(claimed_step.lease_generation or 0) if claimed_step is not None else 0,
                    error=exc,
                )
            except AgentCapabilityExecutionConflict:
                pass
        if claimed_step is not None:
            try:
                await runtime.fail_step(step_id=claimed_step.id, user_id=user_id, lease_owner=step_owner, lease_generation=int(claimed_step.lease_generation or 0), error_type=type(exc).__name__)
            except AgentRuntimeError:
                pass
        fallback_reason = "empty_response" if isinstance(exc, AgentConflict) and "empty write candidate" in str(exc) else type(exc).__name__
        await runtime.update_run_provider_provenance(
            run_id=approval.run_id,
            user_id=user_id,
            updates={
                "candidate_writer_provider_called": candidate_writer_provider_called,
                "candidate_writer_provider_fallback_reason": fallback_reason,
                "candidate_writer_model_ref": candidate_writer_model_ref,
                "candidate_writer_provider_attempts": provider_attempts.snapshot(),
            },
        )
        await runtime.mark_approval_executed(approval_id=approval.id, user_id=user_id, status="execution_failed")
        await runtime.update_run(run_id=approval.run_id, user_id=user_id, status="failed", phase="write_candidate_error")
        await runtime.append_event(
            run_id=approval.run_id, user_id=user_id, event_type="write_execution_failed", summary="写入候选生成失败",
            data={
                "approval_id": approval.id, "error_type": type(exc).__name__,
                "candidate_writer_provider_called": candidate_writer_provider_called,
                "candidate_writer_provider_fallback_reason": fallback_reason,
            },
        )
        # The durable event and provenance retain the failure classification; the
        # HTTP layer receives a stable AgentRuntimeError instead of a raw Provider
        # transport exception or implementation traceback.
        failure_label = (
            "handler identity mismatch"
            if type(exc).__name__ == "AgentCapabilityHandlerIdentityMismatch"
            else type(exc).__name__
        )
        raise AgentConflict(f"candidate writer execution failed: {failure_label}") from exc


def _quality_observation(content: str, metadata: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    target = metadata.get("target_word_count")
    minimum = metadata.get("min_word_count")
    try:
        target_value = int(target) if target is not None else max(1, len(content))
    except (TypeError, ValueError):
        target_value = max(1, len(content))
    try:
        minimum_value = int(minimum) if minimum is not None else max(1, int(target_value * 0.9))
    except (TypeError, ValueError):
        minimum_value = max(1, int(target_value * 0.9))
    summaries, gate = PipelineOrchestrator._evaluate_structural_quality_gate_for_content(
        review_summaries={},
        content=content,
        violations=[],
        chapter_mission=metadata.get("chapter_mission") if isinstance(metadata.get("chapter_mission"), dict) else None,
        target_word_count=target_value,
        min_word_count=minimum_value,
    )
    return summaries, gate


async def _source_quality_retest(
    *,
    session: AsyncSession,
    user_id: int,
    project_id: str,
    chapter_number: int,
    source_version_id: int | None,
    candidate_content: str,
    metadata: dict[str, Any],
) -> dict[str, Any] | None:
    """Compare rewrite source and candidate with the same structural gate."""
    if source_version_id is None:
        return None
    source = (await session.execute(
        select(ChapterVersion)
        .join(Chapter, Chapter.id == ChapterVersion.chapter_id)
        .join(NovelProject, NovelProject.id == Chapter.project_id)
        .where(
            ChapterVersion.id == int(source_version_id),
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number,
            NovelProject.user_id == user_id,
        )
    )).scalar_one_or_none()
    if source is None or not str(source.content or '').strip():
        raise AgentScopeViolation('rewrite source version is unavailable for quality retest')
    source_summaries, source_gate = _quality_observation(str(source.content), metadata)
    candidate_summaries, candidate_gate = _quality_observation(candidate_content, metadata)
    before_codes = list(source_gate.get('quality_issue_codes') or [])
    after_codes = list(candidate_gate.get('quality_issue_codes') or [])
    before_score = source_gate.get('quality_score')
    after_score = candidate_gate.get('quality_score')
    return {
        'source_version_id': int(source.id),
        'source_content_sha256': hashlib.sha256(str(source.content).encode('utf-8')).hexdigest(),
        'before': {
            'passed': bool(source_gate.get('passed', False)),
            'quality_issue_codes': before_codes,
            'blocker_count': len(source_gate.get('blockers') or []),
            'quality_score': before_score,
            'summary': source_summaries,
        },
        'after': {
            'passed': bool(candidate_gate.get('passed', False)),
            'quality_issue_codes': after_codes,
            'blocker_count': len(candidate_gate.get('blockers') or []),
            'quality_score': after_score,
            'summary': candidate_summaries,
        },
        'delta': {
            'blocker_count': len(candidate_gate.get('blockers') or []) - len(source_gate.get('blockers') or []),
            'quality_issue_codes_added': sorted(set(after_codes) - set(before_codes)),
            'quality_issue_codes_removed': sorted(set(before_codes) - set(after_codes)),
            'quality_score': (float(after_score) - float(before_score)) if isinstance(before_score, (int, float)) and isinstance(after_score, (int, float)) else None,
        },
    }


async def accept_candidate_artifact(*, artifact_id: str, user_id: int, note: str | None, session: AsyncSession, acceptance_approval_id: str | None = None) -> AgentArtifactRef:
    """Accept a candidate only after the persisted P1-B Gate allows it.

    This function intentionally recomputes the old structural evaluator for
    compatibility, but the write decision comes from ``QualityGate.decision``.
    A stale or hand-edited metadata ``quality_gate`` can therefore never bypass
    acceptance.
    """
    runtime = AgentRuntimeService(session)
    artifact = (await session.execute(select(AgentArtifactRef).where(AgentArtifactRef.id == artifact_id, AgentArtifactRef.user_id == user_id))).scalar_one_or_none()
    if artifact is None:
        raise AgentNotFound("artifact not found")
    metadata = dict(artifact.metadata_json or {})
    if artifact.kind != "chapter_candidate":
        raise AgentConflict("artifact is not a chapter candidate")
    if metadata.get("status") == "accepted":
        return artifact
    if metadata.get("status") != "candidate":
        raise AgentConflict("artifact is not an unaccepted chapter candidate")
    if not artifact.project_id:
        raise AgentScopeViolation("candidate artifact has no project scope")
    try:
        chapter_number = _chapter_number(metadata)
    except AgentConflict:
        raise AgentConflict("candidate artifact has no valid chapter number")
    storage_key = str(metadata.get("storage_key") or "")
    target = (_ARTIFACT_ROOT / storage_key).resolve()
    if target.parent != _ARTIFACT_ROOT.resolve() or not target.is_file():
        raise AgentNotFound("candidate artifact content is unavailable")
    content = target.read_text(encoding="utf-8")
    if hashlib.sha256(content.encode("utf-8")).hexdigest() != artifact.sha256:
        raise AgentConflict("candidate artifact integrity check failed")
    quality_service = AgentQualityService(session)
    quality_evaluation = await quality_service.get_artifact_evaluation(
        artifact_id=artifact.id, user_id=user_id
    )
    quality_summaries: dict[str, Any] = {}
    if quality_evaluation is None:
        # Legacy candidates created before P1-B have no Gate. Evaluate once to
        # migrate their decision; later accept attempts always use this durable
        # result and never re-run evaluation to bypass a blocked fact.
        try:
            quality_summaries, quality_gate = _quality_observation(content, metadata)
            quality_evaluation = await quality_service.evaluate_candidate(
                artifact=artifact,
                content=content,
                summaries=quality_summaries,
                quality_gate=quality_gate,
            )
        except Exception as exc:
            metadata.update({"quality_status": "unavailable", "quality_error_type": type(exc).__name__})
            artifact.metadata_json = metadata
            await session.commit()
            await runtime.append_event(run_id=artifact.run_id, user_id=user_id, event_type="quality_check_failed", summary="候选质量检查不可用，未保存版本", data={"artifact_id": artifact.id, "error_type": type(exc).__name__})
            raise AgentConflict("candidate quality check unavailable") from exc
    assert quality_evaluation is not None

    metadata = dict(artifact.metadata_json or {})
    if quality_summaries:
        metadata["quality_observation"] = quality_summaries.get("story_progression_guard") or quality_summaries
    try:
        metadata["quality_retest"] = await _source_quality_retest(
            session=session,
            user_id=user_id,
            project_id=artifact.project_id,
            chapter_number=chapter_number,
            source_version_id=int(metadata["source_version_id"]) if metadata.get("source_version_id") is not None else None,
            candidate_content=content,
            metadata=metadata,
        )
    except AgentRuntimeError:
        raise
    except Exception as exc:
        metadata["quality_retest"] = {"status": "unavailable", "error_type": type(exc).__name__}
    artifact.metadata_json = metadata
    await session.commit()
    await session.refresh(artifact)

    try:
        await quality_service.assert_acceptance_allowed(
            artifact_id=artifact.id, user_id=user_id, require_evaluation=True
        )
    except AgentQualityGateBlocked as exc:
        await runtime.update_run(run_id=artifact.run_id, user_id=user_id, status="paused", phase="quality_blocked", progress=92)
        await runtime.append_event(
            run_id=artifact.run_id,
            user_id=user_id,
            event_type="quality_check_blocked",
            summary="候选未通过持久化质量门，未保存章节版本",
            data={
                "artifact_id": artifact.id,
                "quality_issue_codes": list(quality_evaluation.legacy_gate.get("quality_issue_codes") or []),
                "blocker_count": quality_evaluation.gate.blocker_count,
            },
        )
        raise AgentConflict("candidate did not pass persisted quality gate") from exc

    await runtime.append_event(run_id=artifact.run_id, user_id=user_id, event_type="quality_check_completed", summary="候选已通过持久化结构质量门", data={"artifact_id": artifact.id, "quality_status": "passed"})
    novel = NovelService(session)
    await novel.ensure_project_owner(artifact.project_id, user_id)
    chapter = await novel.get_or_create_chapter(artifact.project_id, chapter_number)
    versions = await novel.append_chapter_versions(chapter, [content], metadata=[{"source": "agent_approved_candidate", "artifact_id": artifact.id, "approval_id": metadata.get("approval_id"), "acceptance_approval_id": acceptance_approval_id, "source_version_id": metadata.get("source_version_id"), "quality_gate_id": quality_evaluation.gate.id, "quality_result_id": quality_evaluation.result.id, "note": (note or "")[:2000]}])
    accepted_version = max(versions, key=lambda item: int(item.id)) if versions else None
    if accepted_version is not None and metadata.get("source_version_id") is not None:
        accepted_version.parent_version_id = int(metadata["source_version_id"])
        await session.commit()

    accepted_artifact = None
    if accepted_version is not None:
        accepted_artifact = AgentArtifactRef(
            id=str(uuid4()),
            run_id=artifact.run_id,
            correlation_id=artifact.correlation_id,
            transaction_id=artifact.transaction_id,
            user_id=artifact.user_id,
            project_id=artifact.project_id,
            kind="chapter_version",
            uri=f"chapter-version://{accepted_version.id}",
            sha256=hashlib.sha256(str(accepted_version.content or "").encode("utf-8")).hexdigest(),
            metadata_json={
                "status": "accepted_version",
                "chapter_number": chapter_number,
                "chapter_id": int(chapter.id),
                "version_id": int(accepted_version.id),
                "source_artifact_id": artifact.id,
                "quality_gate_id": quality_evaluation.gate.id,
                "quality_result_id": quality_evaluation.result.id,
            },
        )
        session.add(accepted_artifact)
        await session.flush()
        session.add(ArtifactLineage(
            lineage_id=str(uuid4()),
            run_id=artifact.run_id,
            source_artifact_ref_id=artifact.id,
            derived_artifact_ref_id=accepted_artifact.id,
            correlation_id=artifact.correlation_id,
            transaction_id=artifact.transaction_id,
            relation_type="accepted_as_version",
            operation="chapter.version.accept",
            input_digest=artifact.sha256,
            output_digest=accepted_artifact.sha256,
            metadata_json={
                "chapter_number": chapter_number,
                "accepted_version_id": int(accepted_version.id),
                "quality_gate_id": quality_evaluation.gate.id,
                "quality_result_id": quality_evaluation.result.id,
                "acceptance_approval_id": acceptance_approval_id,
            },
        ))

    metadata.update({
        "status": "accepted",
        "accepted_version_id": accepted_version.id if accepted_version else None,
        "accepted_artifact_ref_id": accepted_artifact.id if accepted_artifact is not None else None,
        **({"acceptance_approval_id": acceptance_approval_id} if acceptance_approval_id else {}),
    })
    artifact.metadata_json = metadata
    await session.commit()
    await session.refresh(artifact)
    await runtime.append_event(run_id=artifact.run_id, user_id=user_id, event_type="artifact_accepted", summary="用户已接受候选并保存为新章节版本", data={"artifact_id": artifact.id, "chapter_number": chapter_number, "version_id": accepted_version.id if accepted_version else None, **({"acceptance_approval_id": acceptance_approval_id} if acceptance_approval_id else {})})
    await runtime.update_run(run_id=artifact.run_id, user_id=user_id, status="completed", phase="accepted", progress=100)
    await runtime.append_event(run_id=artifact.run_id, user_id=user_id, event_type="run_completed", summary="候选已接受，Agent 写入流程完成", data={"artifact_id": artifact.id, "version_id": accepted_version.id if accepted_version else None})
    return artifact


async def diff_artifacts(*, artifact_id: str, against_artifact_id: str, user_id: int, session: AsyncSession) -> dict[str, Any]:
    if artifact_id == against_artifact_id:
        raise AgentConflict('artifacts must be different for diff')
    left_artifact, left_content = await read_artifact_content(artifact_id=artifact_id, user_id=user_id, session=session)
    right_artifact, right_content = await read_artifact_content(artifact_id=against_artifact_id, user_id=user_id, session=session)
    if left_artifact.project_id != right_artifact.project_id:
        raise AgentScopeViolation('artifact projects do not match')
    original = left_content.splitlines()
    patched = right_content.splitlines()
    lines: list[dict[str, Any]] = []
    counts = {'added': 0, 'deleted': 0, 'modified': 0, 'unchanged': 0}
    matcher = difflib.SequenceMatcher(a=original, b=patched, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for offset, value in enumerate(original[i1:i2]):
                lines.append({'line_number': j1 + offset + 1, 'original_line': value, 'patched_line': patched[j1 + offset], 'change_type': 'unchanged'})
                counts['unchanged'] += 1
        elif tag == 'replace':
            width = max(i2 - i1, j2 - j1)
            for offset in range(width):
                old_value = original[i1 + offset] if i1 + offset < i2 else None
                new_value = patched[j1 + offset] if j1 + offset < j2 else None
                change_type = 'modified' if old_value is not None and new_value is not None else ('deleted' if old_value is not None else 'added')
                lines.append({'line_number': j1 + offset + 1, 'original_line': old_value, 'patched_line': new_value, 'change_type': change_type})
                counts[change_type] += 1
        elif tag == 'delete':
            for offset, value in enumerate(original[i1:i2]):
                lines.append({'line_number': j1 + offset + 1, 'original_line': value, 'patched_line': None, 'change_type': 'deleted'})
                counts['deleted'] += 1
        elif tag == 'insert':
            for offset, value in enumerate(patched[j1:j2]):
                lines.append({'line_number': j1 + offset + 1, 'original_line': None, 'patched_line': value, 'change_type': 'added'})
                counts['added'] += 1
    return {'artifact_id': left_artifact.id, 'against_artifact_id': right_artifact.id, 'diff_lines': lines, 'summary': {'total_lines': len(lines), **counts}}

async def diff_artifact_with_chapter_version(*, artifact_id: str, project_id: str, chapter_number: int, version_id: int, user_id: int, session: AsyncSession) -> dict[str, Any]:
    artifact, artifact_content = await read_artifact_content(artifact_id=artifact_id, user_id=user_id, session=session)
    if artifact.project_id != project_id:
        raise AgentScopeViolation('artifact project does not match requested project')
    version = (await session.execute(
        select(ChapterVersion)
        .join(Chapter, Chapter.id == ChapterVersion.chapter_id)
        .join(NovelProject, NovelProject.id == Chapter.project_id)
        .where(
            ChapterVersion.id == version_id,
            Chapter.project_id == project_id,
            Chapter.chapter_number == chapter_number,
            NovelProject.user_id == user_id,
        )
    )).scalar_one_or_none()
    if version is None:
        raise AgentNotFound('chapter version not found')
    original = artifact_content.splitlines()
    patched = str(version.content or '').splitlines()
    lines: list[dict[str, Any]] = []
    counts = {'added': 0, 'deleted': 0, 'modified': 0, 'unchanged': 0}
    matcher = difflib.SequenceMatcher(a=original, b=patched, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for offset, value in enumerate(original[i1:i2]):
                lines.append({'line_number': j1 + offset + 1, 'original_line': value, 'patched_line': patched[j1 + offset], 'change_type': 'unchanged'})
                counts['unchanged'] += 1
        elif tag == 'replace':
            width = max(i2 - i1, j2 - j1)
            for offset in range(width):
                old_value = original[i1 + offset] if i1 + offset < i2 else None
                new_value = patched[j1 + offset] if j1 + offset < j2 else None
                change_type = 'modified' if old_value is not None and new_value is not None else ('deleted' if old_value is not None else 'added')
                lines.append({'line_number': j1 + offset + 1, 'original_line': old_value, 'patched_line': new_value, 'change_type': change_type})
                counts[change_type] += 1
        elif tag == 'delete':
            for offset, value in enumerate(original[i1:i2]):
                lines.append({'line_number': j1 + offset + 1, 'original_line': value, 'patched_line': None, 'change_type': 'deleted'})
                counts['deleted'] += 1
        elif tag == 'insert':
            for offset, value in enumerate(patched[j1:j2]):
                lines.append({'line_number': j1 + offset + 1, 'original_line': None, 'patched_line': value, 'change_type': 'added'})
                counts['added'] += 1
    return {
        'artifact_id': artifact.id,
        'project_id': project_id,
        'chapter_number': chapter_number,
        'version_id': int(version.id),
        'diff_lines': lines,
        'summary': {'total_lines': len(lines), **counts},
        'deep_link': f'/novel/{project_id}?chapter={chapter_number}&version_id={int(version.id)}&focus=version',
    }

async def list_artifact_quality_blockers(*, artifact_id: str, user_id: int, session: AsyncSession) -> list[dict[str, Any]]:
    artifact, content = await read_artifact_content(artifact_id=artifact_id, user_id=user_id, session=session)
    metadata = dict(artifact.metadata_json or {})
    evaluation = await AgentQualityService(session).get_artifact_evaluation(
        artifact_id=artifact_id,
        user_id=user_id,
    )
    if evaluation is not None:
        raw_blockers: list[dict[str, Any]] = []
        for finding in evaluation.findings:
            if finding.severity != "blocker":
                continue
            location = dict(finding.location_json or {})
            evidence = dict(finding.evidence_json or {})
            remediation = dict(finding.remediation_json or {})
            raw_blockers.append({
                "code": finding.code,
                "category": finding.category,
                "severity": finding.severity,
                "message": finding.message,
                "source": "quality_finding",
                "snippet": evidence.get("excerpt") or evidence.get("snippet") or location.get("snippet"),
                "start_char": location.get("start_char", location.get("offset")),
                "end_char": location.get("end_char"),
                "hint": remediation.get("action") or remediation.get("instruction"),
            })
    else:
        gate = metadata.get('quality_gate') if isinstance(metadata.get('quality_gate'), dict) else {}
        raw_blockers = gate.get('blockers') if isinstance(gate.get('blockers'), list) else []
    chapter_number = None
    try:
        if metadata.get('chapter_number') is not None:
            chapter_number = int(metadata.get('chapter_number'))
    except (TypeError, ValueError):
        chapter_number = None
    version_id = None
    try:
        candidate_version_id = metadata.get('accepted_version_id') or metadata.get('version_id')
        if candidate_version_id is not None:
            version_id = int(candidate_version_id)
    except (TypeError, ValueError):
        version_id = None
    rows: list[dict[str, Any]] = []
    for raw in raw_blockers:
        item = raw if isinstance(raw, dict) else {'code': str(raw)}
        code = str(item.get('code') or 'quality_blocker')[:120]
        message = str(item.get('message') or item.get('hint') or code)[:1000]
        source = str(item.get('source') or 'quality_gate')[:120]
        severity = str(item.get('severity') or 'blocker')[:32]
        snippet = str(item.get('snippet') or item.get('text') or '').strip()[:240] or None
        start_char = item.get('start_char')
        end_char = item.get('end_char')
        try:
            start_char = int(start_char) if start_char is not None else None
            end_char = int(end_char) if end_char is not None else None
        except (TypeError, ValueError):
            start_char, end_char = None, None
        if snippet and start_char is None:
            found = content.find(snippet)
            if found >= 0:
                start_char, end_char = found, found + len(snippet)
        if start_char is not None and end_char is None:
            end_char = start_char + len(snippet or '')
        valid_anchor = start_char is not None and end_char is not None and 0 <= start_char <= end_char <= len(content)
        if not valid_anchor:
            start_char, end_char = None, None
        normalized_snippet = content[start_char:end_char] if valid_anchor else snippet
        text_hash = hashlib.sha256(normalized_snippet.encode('utf-8')).hexdigest() if normalized_snippet else None
        deep_link = None
        if artifact.project_id and chapter_number:
            deep_link = f'/novel/{artifact.project_id}?chapter={chapter_number}' + (f'&version_id={version_id}&focus=quality-blocker' if version_id else '&focus=quality-blocker')
        rows.append({
            'artifact_id': artifact.id,
            'project_id': artifact.project_id,
            'chapter_number': chapter_number,
            'version_id': version_id,
            'code': code,
            'severity': severity,
            'message': message,
            'source': source,
            'snippet': normalized_snippet,
            'start_char': start_char,
            'end_char': end_char,
            'text_hash': text_hash,
            'anchor_status': 'located' if valid_anchor else 'unavailable',
            'deep_link': deep_link,
        })
    return rows

def _rewrite_instruction_for_blocker(item: dict[str, Any], *, snippet: str | None, anchor_status: str) -> str:
    code = str(item.get("code") or "quality_blocker")
    message = str(item.get("message") or item.get("hint") or code).strip()
    hint = str(item.get("hint") or "").strip()
    target = f"定位片段：{snippet}" if snippet and anchor_status == "located" else "未能安全定位原文片段，只能按规则和章节上下文重写"
    return f"修复质量问题 {code}：{message}。{hint} {target}。保持章节核心事实和人物关系不变，完成后重新运行同一质量门。"[:2000]


def build_rewrite_instructions(blockers: list[dict[str, Any]], *, artifact_id: str, project_id: str | None, chapter_number: int | None, source_version_id: int | None) -> list[dict[str, Any]]:
    """Convert normalized blockers into safe, non-writing rewrite proposals."""
    instructions: list[dict[str, Any]] = []
    for raw in blockers:
        item = raw if isinstance(raw, dict) else {"code": str(raw)}
        anchor_status = str(item.get("anchor_status") or "unavailable")
        snippet = item.get("snippet") if isinstance(item.get("snippet"), str) else None
        instruction = _rewrite_instruction_for_blocker(item, snippet=snippet, anchor_status=anchor_status)
        arguments: dict[str, Any] = {
            "chapter_number": chapter_number,
            "instruction": instruction,
        }
        if source_version_id is not None:
            arguments["source_version_id"] = source_version_id
        instructions.append({
            "artifact_id": artifact_id,
            "project_id": project_id,
            "chapter_number": chapter_number,
            "source_version_id": source_version_id,
            "code": str(item.get("code") or "quality_blocker"),
            "severity": str(item.get("severity") or "blocker"),
            "message": str(item.get("message") or item.get("hint") or item.get("code") or "质量阻断")[:1000],
            "source": str(item.get("source") or "quality_gate")[:120],
            "snippet": snippet,
            "start_char": item.get("start_char"),
            "end_char": item.get("end_char"),
            "anchor_status": anchor_status,
            "instruction": instruction,
            "rewrite_arguments": arguments,
        })
    return instructions


async def list_artifact_rewrite_instructions(*, artifact_id: str, user_id: int, session: AsyncSession) -> list[dict[str, Any]]:
    blockers = await list_artifact_quality_blockers(artifact_id=artifact_id, user_id=user_id, session=session)
    artifact = (await session.execute(select(AgentArtifactRef).where(AgentArtifactRef.id == artifact_id, AgentArtifactRef.user_id == user_id))).scalar_one_or_none()
    if artifact is None:
        raise AgentNotFound("artifact not found")
    metadata = dict(artifact.metadata_json or {})
    chapter_number = None
    try:
        chapter_number = int(metadata.get("chapter_number")) if metadata.get("chapter_number") is not None else None
    except (TypeError, ValueError):
        chapter_number = None
    source_version_id = None
    try:
        source_version_id = int(metadata.get("source_version_id")) if metadata.get("source_version_id") is not None else None
    except (TypeError, ValueError):
        source_version_id = None
    return build_rewrite_instructions(blockers, artifact_id=artifact.id, project_id=artifact.project_id, chapter_number=chapter_number, source_version_id=source_version_id)


async def read_artifact_content(*, artifact_id: str, user_id: int, session: AsyncSession) -> tuple[AgentArtifactRef, str]:
    artifact = (await session.execute(select(AgentArtifactRef).where(AgentArtifactRef.id == artifact_id, AgentArtifactRef.user_id == user_id))).scalar_one_or_none()
    if artifact is None:
        raise AgentNotFound("artifact not found")
    metadata = dict(artifact.metadata_json or {})
    storage_key = str(metadata.get("storage_key") or "")
    target = (_ARTIFACT_ROOT / storage_key).resolve()
    if target.parent != _ARTIFACT_ROOT.resolve() or not target.is_file():
        raise AgentNotFound("artifact content is unavailable")
    content = target.read_text(encoding="utf-8")
    if artifact.sha256 and hashlib.sha256(content.encode("utf-8")).hexdigest() != artifact.sha256:
        raise AgentConflict("artifact integrity check failed")
    return artifact, content

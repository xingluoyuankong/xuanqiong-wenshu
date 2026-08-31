"""P1-B candidate quality evaluation and acceptance gate service.

The service is the durable boundary between the legacy metadata quality payload and
relational QualityResult/QualityFinding/QualityGate facts.  It deliberately does
not own the evaluator: callers provide the existing structural evaluator output,
so old quality services remain compatible while acceptance consumes the durable
Gate decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.agent import AgentArtifactRef, AgentRun
from ..models.agent_quality import QualityFinding, QualityGate, QualityResult


class AgentQualityServiceError(RuntimeError):
    """Base error for durable candidate quality operations."""


class AgentQualityGateBlocked(AgentQualityServiceError):
    """Raised when an artifact has an authoritative blocking Gate."""


@dataclass(frozen=True)
class QualityEvaluation:
    result: QualityResult
    gate: QualityGate
    legacy_gate: dict[str, Any]
    findings: tuple[QualityFinding, ...]

    @property
    def passed(self) -> bool:
        return self.gate.decision in {"passed", "waived"}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _digest(value: Any) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _bounded_text(value: Any, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _severity(value: Any, default: str) -> str:
    value = str(value or default).strip().lower()
    return value if value in {"info", "warning", "error", "blocker"} else default


def _score(summaries: dict[str, Any], gate: dict[str, Any]) -> float | None:
    candidates: list[Any] = [
        gate.get("quality_score"),
        gate.get("score"),
        summaries.get("quality_score"),
        (summaries.get("story_progression_guard") or {}).get("score")
        if isinstance(summaries.get("story_progression_guard"), dict)
        else None,
        ((summaries.get("story_progression_guard") or {}).get("quality_metric_snapshot") or {}).get("score")
        if isinstance(summaries.get("story_progression_guard"), dict)
        else None,
    ]
    for value in candidates:
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            return max(0.0, min(100.0, number))
    return None


def _items(gate: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, default_severity in (("blockers", "blocker"), ("warnings", "warning")):
        raw = gate.get(key)
        if not isinstance(raw, list):
            continue
        for item in raw:
            payload = item if isinstance(item, dict) else {"code": str(item)}
            code = _bounded_text(payload.get("code") or "quality_issue", 160)
            message = _bounded_text(payload.get("message") or payload.get("hint") or code, 4000)
            source = _bounded_text(payload.get("source") or "structural_quality_gate", 120)
            severity = _severity(payload.get("severity"), default_severity)
            location = payload.get("location") if isinstance(payload.get("location"), dict) else {}
            for key in ("start_char", "end_char", "chapter_number", "line", "column", "snippet"):
                if key in payload and key not in location:
                    location[key] = payload[key]
            evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}
            if payload.get("snippet") is not None and "snippet" not in evidence:
                evidence["snippet"] = _bounded_text(payload.get("snippet"), 500)
            remediation = payload.get("remediation") if isinstance(payload.get("remediation"), dict) else {}
            if payload.get("patch_suggestion") and "suggestion" not in remediation:
                remediation["suggestion"] = _bounded_text(payload.get("patch_suggestion"), 1000)
            rows.append({
                "code": code,
                "category": source,
                "severity": severity,
                "message": message,
                "location": location,
                "evidence": evidence,
                "remediation": remediation,
            })
    return rows


def _legacy_gate(raw_gate: dict[str, Any], findings: list[dict[str, Any]]) -> dict[str, Any]:
    blockers = [item for item in findings if item["severity"] == "blocker"]
    warnings = [item for item in findings if item["severity"] != "blocker"]
    normalized = dict(raw_gate)
    normalized["passed"] = not blockers
    normalized["decision"] = "blocked" if blockers else "passed"
    normalized["blockers"] = blockers
    normalized["warnings"] = warnings
    normalized["blocker_count"] = len(blockers)
    normalized["quality_issue_codes"] = [item["code"] for item in findings if item["severity"] in {"blocker", "error"}]
    normalized["quality_issue_labels"] = [item["message"] for item in findings if item["severity"] in {"blocker", "error"}]
    return normalized


class AgentQualityService:
    """Persist and enforce quality facts for candidate Artifacts."""

    GATE_NAME = "chapter_candidate_acceptance"
    GATE_VERSION = "p1-b-2026-08-28"

    def __init__(self, session: AsyncSession):
        self.session = session

    async def evaluate_candidate(
        self,
        *,
        artifact: AgentArtifactRef,
        content: str,
        summaries: dict[str, Any] | None,
        quality_gate: dict[str, Any] | None,
        assessor_id: str = "structural-quality-v1",
        gate_name: str = GATE_NAME,
    ) -> QualityEvaluation:
        run = await self.session.get(AgentRun, artifact.run_id)
        if run is None:
            raise AgentQualityServiceError("quality evaluation run not found")
        summary_payload = summaries if isinstance(summaries, dict) else {}
        raw_gate = quality_gate if isinstance(quality_gate, dict) else {}
        finding_payloads = _items(raw_gate)
        legacy_gate = _legacy_gate(raw_gate, finding_payloads)
        input_digest = sha256(str(content).encode("utf-8")).hexdigest()
        metrics = {
            "summaries": summary_payload,
            "legacy_gate": legacy_gate,
            "content_characters": len(content),
        }
        result_payload = {
            "input_digest": input_digest,
            "metrics": metrics,
            "findings": finding_payloads,
            "decision": "blocked" if finding_payloads and any(item["severity"] == "blocker" for item in finding_payloads) else "passed",
        }
        result_digest = _digest(result_payload)

        existing = (
            await self.session.execute(
                select(QualityResult)
                .where(
                    QualityResult.artifact_ref_id == artifact.id,
                    QualityResult.input_digest == input_digest,
                    QualityResult.result_digest == result_digest,
                )
                .options(selectinload(QualityResult.findings), selectinload(QualityResult.gates))
                .order_by(QualityResult.created_at.desc(), QualityResult.id.desc())
            )
        ).scalars().first()
        if existing is not None:
            gate_row = next((item for item in existing.gates if item.gate_name == gate_name), None)
            if gate_row is not None:
                self._project_metadata(artifact, legacy_gate, existing, gate_row)
                return QualityEvaluation(existing, gate_row, legacy_gate, tuple(existing.findings))

        result = QualityResult(
            result_id=str(uuid4()),
            run_id=run.id,
            artifact_ref_id=artifact.id,
            correlation_id=run.correlation_id,
            transaction_id=run.transaction_id,
            user_id=artifact.user_id,
            project_id=artifact.project_id,
            assessor_id=assessor_id,
            rubric_version=self.GATE_VERSION,
            status="completed",
            score=_score(summary_payload, raw_gate),
            summary="候选 Artifact 已完成结构质量评估。" if not finding_payloads else "候选 Artifact 存在需要处理的质量发现项。",
            metrics_json=metrics,
            input_digest=input_digest,
            result_digest=result_digest,
        )
        finding_rows: list[QualityFinding] = []
        for item in finding_payloads:
            fingerprint = _digest({"code": item["code"], "severity": item["severity"], "message": item["message"], "location": item["location"]})
            finding_rows.append(
                QualityFinding(
                    finding_id=str(uuid4()),
                    code=item["code"],
                    category=item["category"],
                    severity=item["severity"],
                    status="open",
                    message=item["message"],
                    fingerprint=fingerprint,
                    location_json=item["location"],
                    evidence_json=item["evidence"],
                    remediation_json=item["remediation"],
                )
            )
        for finding in finding_rows:
            result.findings.append(finding)
        blocker_count = sum(1 for item in finding_payloads if item["severity"] == "blocker")
        decision = "blocked" if blocker_count else "passed"
        gate_row = QualityGate(
            gate_id=str(uuid4()),
            run_id=run.id,
            artifact_ref_id=artifact.id,
            correlation_id=run.correlation_id,
            transaction_id=run.transaction_id,
            gate_name=gate_name,
            gate_version=self.GATE_VERSION,
            decision=decision,
            blocker_count=blocker_count,
            rationale="存在 blocker，禁止接受候选。" if blocker_count else "未发现 blocker，允许接受候选。",
            policy_json={"blocker_severity": ["blocker"], "source": "AgentQualityService"},
        )
        result.gates.append(gate_row)
        self.session.add(result)
        await self.session.flush()
        self._project_metadata(artifact, legacy_gate, result, gate_row)
        return QualityEvaluation(result, gate_row, legacy_gate, tuple(finding_rows))

    @staticmethod
    def _project_metadata(artifact: AgentArtifactRef, legacy_gate: dict[str, Any], result: QualityResult, gate: QualityGate) -> None:
        metadata = dict(artifact.metadata_json or {})
        metadata["quality_status"] = "passed" if gate.decision in {"passed", "waived"} else "blocked"
        metadata["quality_gate"] = legacy_gate
        metadata["quality_persistence"] = {
            "quality_result_id": result.id,
            "result_id": result.result_id,
            "gate_id": gate.id,
            "gate_identity": gate.gate_id,
            "gate_name": gate.gate_name,
            "decision": gate.decision,
            "blocker_count": gate.blocker_count,
            "result_digest": result.result_digest,
        }
        artifact.metadata_json = metadata

    async def get_artifact_evaluation(
        self, *, artifact_id: str, user_id: int, gate_name: str = GATE_NAME
    ) -> QualityEvaluation | None:
        row = (
            await self.session.execute(
                select(QualityResult)
                .join(QualityGate, QualityGate.quality_result_id == QualityResult.id)
                .join(AgentArtifactRef, AgentArtifactRef.id == QualityResult.artifact_ref_id)
                .where(
                    AgentArtifactRef.id == artifact_id,
                    AgentArtifactRef.user_id == user_id,
                    QualityGate.gate_name == gate_name,
                )
                .options(selectinload(QualityResult.findings), selectinload(QualityResult.gates))
                .order_by(QualityGate.created_at.desc(), QualityGate.id.desc())
            )
        ).scalars().first()
        if row is None:
            return None
        gate = next((item for item in row.gates if item.gate_name == gate_name), None)
        if gate is None:
            return None
        metrics = row.metrics_json if isinstance(row.metrics_json, dict) else {}
        legacy_gate = metrics.get("legacy_gate") if isinstance(metrics.get("legacy_gate"), dict) else {}
        return QualityEvaluation(row, gate, dict(legacy_gate), tuple(row.findings))

    async def get_artifact_gate(self, *, artifact_id: str, user_id: int, gate_name: str = GATE_NAME) -> QualityGate | None:
        evaluation = await self.get_artifact_evaluation(
            artifact_id=artifact_id, user_id=user_id, gate_name=gate_name
        )
        return evaluation.gate if evaluation is not None else None

    async def assert_acceptance_allowed(
        self, *, artifact_id: str, user_id: int, gate_name: str = GATE_NAME, require_evaluation: bool = False
    ) -> QualityGate | None:
        gate = await self.get_artifact_gate(artifact_id=artifact_id, user_id=user_id, gate_name=gate_name)
        if gate is None and require_evaluation:
            raise AgentQualityGateBlocked("artifact has no persisted quality gate")
        if gate is not None and gate.decision == "blocked":
            raise AgentQualityGateBlocked(
                f"artifact quality gate is blocked: {gate.blocker_count} blocker(s)"
            )
        return gate

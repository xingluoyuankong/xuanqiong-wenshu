from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping


class ContextSnapshotSelectionError(ValueError):
    """Raised when a context selection violates project or time boundaries."""


@dataclass(frozen=True)
class ContextSelectionRequest:
    project_id: str
    target_chapter: int | None = None
    target_volume: int | None = None
    max_text_units: int = 20_000
    max_refs: int = 128
    explicit_refs: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True)
class ContextSelectionItem:
    ref_type: str
    ref_key: str
    role: str
    chapter_number: int | None
    text_units: int
    payload: dict[str, Any]
    reason_code: str
    stale: bool = False
    conflict: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContextSnapshotPayload:
    snapshot_id: str
    project_id: str
    target_chapter: int | None
    target_volume: int | None
    selection_policy_version: str
    budget_text_units: int
    estimated_text_units: int
    selected: tuple[ContextSelectionItem, ...]
    excluded: tuple[dict[str, Any], ...]
    compressed: tuple[dict[str, Any], ...]
    stale: tuple[dict[str, Any], ...]
    conflicts: tuple[dict[str, Any], ...]
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "project_id": self.project_id,
            "target_chapter": self.target_chapter,
            "target_volume": self.target_volume,
            "selection_policy_version": self.selection_policy_version,
            "budget_text_units": self.budget_text_units,
            "estimated_text_units": self.estimated_text_units,
            "selected": [item.as_dict() for item in self.selected],
            "excluded": list(self.excluded),
            "compressed": list(self.compressed),
            "stale": list(self.stale),
            "conflicts": list(self.conflicts),
            "digest": self.digest,
        }


class ContextSnapshotBuilder:
    """Build a bounded, explainable context payload from project-owned records."""

    POLICY_VERSION = "novel-100k-context-v1"

    def __init__(self, request: ContextSelectionRequest):
        if not request.project_id.strip():
            raise ContextSnapshotSelectionError("project_id is required")
        if request.max_text_units < 1 or request.max_refs < 1:
            raise ContextSnapshotSelectionError("context budgets must be positive")
        self.request = request

    @staticmethod
    def _text_units(record: Mapping[str, Any]) -> int:
        for key in ("text_units", "word_count", "estimated_text_units"):
            try:
                return max(0, int(record.get(key) or 0))
            except (TypeError, ValueError):
                continue
        text = str(record.get("text") or record.get("content") or record.get("summary") or "")
        return sum(1 for char in text if not char.isspace())

    @staticmethod
    def _chapter(record: Mapping[str, Any]) -> int | None:
        value = record.get("chapter_number")
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _validate_record(self, record: Mapping[str, Any]) -> None:
        record_project = str(record.get("project_id") or self.request.project_id)
        if record_project != self.request.project_id:
            raise ContextSnapshotSelectionError("context record belongs to another project")
        chapter = self._chapter(record)
        if self.request.target_chapter is not None and chapter is not None and chapter > self.request.target_chapter:
            raise ContextSnapshotSelectionError("context record is from a future chapter")

    def build(self, records: Iterable[Mapping[str, Any]], *, snapshot_id: str) -> ContextSnapshotPayload:
        if not snapshot_id.strip():
            raise ContextSnapshotSelectionError("snapshot_id is required")
        normalized: list[dict[str, Any]] = []
        for raw in records:
            record = dict(raw)
            self._validate_record(record)
            normalized.append(record)
        # Explicit refs are validated even if their payload is not selected by budget.
        for ref in self.request.explicit_refs:
            self._validate_record(ref)

        def priority(record: Mapping[str, Any]) -> tuple[int, int, str]:
            reason = str(record.get("reason_code") or "related_context")
            reason_rank = {
                "explicit_user_ref": 0,
                "current_scope": 1,
                "causal_dependency": 2,
                "character_dependency": 3,
                "foreshadowing_dependency": 4,
                "recent_continuity": 5,
                "quality_blocker": 6,
                "style_preference": 7,
            }.get(reason, 8)
            chapter = self._chapter(record)
            distance = abs((self.request.target_chapter or chapter or 0) - (chapter or 0))
            return reason_rank, distance, str(record.get("ref_key") or record.get("id") or "")

        normalized.sort(key=priority)
        selected: list[ContextSelectionItem] = []
        excluded: list[dict[str, Any]] = []
        compressed: list[dict[str, Any]] = []
        stale: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        used = 0
        seen: set[tuple[str, str]] = set()
        for record in normalized:
            ref_type = str(record.get("ref_type") or record.get("kind") or "unknown")
            ref_key = str(record.get("ref_key") or record.get("id") or "")
            key = (ref_type, ref_key)
            if not ref_key or key in seen:
                excluded.append({"ref_type": ref_type, "ref_key": ref_key, "reason": "duplicate_or_missing_key"})
                continue
            seen.add(key)
            units = self._text_units(record)
            reason = str(record.get("reason_code") or "related_context")
            if len(selected) >= self.request.max_refs:
                excluded.append({"ref_type": ref_type, "ref_key": ref_key, "reason": "max_refs"})
                continue
            if used + units > self.request.max_text_units:
                if units > 0 and used < self.request.max_text_units:
                    compressed.append({"ref_type": ref_type, "ref_key": ref_key, "original_text_units": units, "reason": "text_budget"})
                else:
                    excluded.append({"ref_type": ref_type, "ref_key": ref_key, "reason": "text_budget"})
                continue
            item = ContextSelectionItem(
                ref_type=ref_type,
                ref_key=ref_key,
                role=str(record.get("role") or "selected"),
                chapter_number=self._chapter(record),
                text_units=units,
                payload={key: value for key, value in record.items() if key not in {"content", "text"}},
                reason_code=reason,
                stale=bool(record.get("stale", False)),
                conflict=bool(record.get("conflict", False)),
            )
            selected.append(item)
            used += units
            if item.stale:
                stale.append(item.as_dict())
            if item.conflict:
                conflicts.append(item.as_dict())

        material = {
            "snapshot_id": snapshot_id,
            "project_id": self.request.project_id,
            "target_chapter": self.request.target_chapter,
            "target_volume": self.request.target_volume,
            "selection_policy_version": self.POLICY_VERSION,
            "budget_text_units": self.request.max_text_units,
            "selected": [item.as_dict() for item in selected],
            "excluded": excluded,
            "compressed": compressed,
            "stale": stale,
            "conflicts": conflicts,
        }
        digest = hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()
        return ContextSnapshotPayload(
            snapshot_id=snapshot_id,
            project_id=self.request.project_id,
            target_chapter=self.request.target_chapter,
            target_volume=self.request.target_volume,
            selection_policy_version=self.POLICY_VERSION,
            budget_text_units=self.request.max_text_units,
            estimated_text_units=used,
            selected=tuple(selected),
            excluded=tuple(excluded),
            compressed=tuple(compressed),
            stale=tuple(stale),
            conflicts=tuple(conflicts),
            digest=digest,
        )


def snapshot_to_agent_context_inputs(payload: ContextSnapshotPayload) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Adapt the bounded novel selection into the existing immutable Agent snapshot contract."""
    context_json = {
        "selection_policy_version": payload.selection_policy_version,
        "target_chapter": payload.target_chapter,
        "target_volume": payload.target_volume,
        "budget_text_units": payload.budget_text_units,
        "estimated_text_units": payload.estimated_text_units,
        "selected_count": len(payload.selected),
        "excluded": list(payload.excluded),
        "compressed": list(payload.compressed),
        "stale_count": len(payload.stale),
        "conflict_count": len(payload.conflicts),
        "selection_digest": payload.digest,
    }
    refs = [
        {
            "ref_type": item.ref_type,
            "ref_key": item.ref_key,
            "ref_version": str(item.payload.get("version_id") or item.payload.get("version") or "") or None,
            "role": item.role,
            "payload_json": item.payload,
        }
        for item in payload.selected
    ]
    return context_json, refs

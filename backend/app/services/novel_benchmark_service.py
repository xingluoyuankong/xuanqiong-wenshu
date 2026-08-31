from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.novel import Chapter, NovelProject


class NovelBaselineError(ValueError):
    """Raised when a project baseline cannot be constructed from formal chapter versions."""


@dataclass(frozen=True)
class CountingPolicy:
    """Versioned visible-text counting policy for Chinese long-form novel baselines."""

    version: str = "zh-visible-v1"
    include_whitespace: bool = False
    include_markdown_markers: bool = False

    def normalize(self, text: str | None) -> str:
        value = unicodedata.normalize("NFC", str(text or ""))
        value = re.sub(r"[\u200b-\u200f\u2060\ufeff]", "", value)
        if not self.include_markdown_markers:
            value = re.sub(r"(?m)^\s{0,3}[>#]+\s?", "", value)
            value = value.replace("**", "").replace("__", "").replace("`", "")
        return value

    def count(self, text: str | None) -> int:
        value = self.normalize(text)
        if self.include_whitespace:
            return len(value)
        return sum(1 for char in value if not char.isspace())

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NovelChapterBaseline:
    chapter_id: int
    chapter_number: int
    selected_version_id: int | None
    selected_version_status: str | None
    text_units: int
    content_digest: str | None
    status: str
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NovelVolumeBaseline:
    volume_index: int
    title: str
    start_chapter: int | None
    end_chapter: int | None
    chapter_count: int
    selected_chapter_count: int
    text_units: int
    source: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class NovelBaseline:
    plan_id: str
    project_id: str
    project_title: str
    generated_at: str
    counting_policy: dict[str, Any]
    chapter_count: int
    selected_chapter_count: int
    missing_selected_version_count: int
    empty_selected_content_count: int
    text_units: int
    chapter_coverage_ratio: float
    content_digest: str
    chapter_distribution: tuple[NovelChapterBaseline, ...]
    volume_distribution: tuple[NovelVolumeBaseline, ...]
    volume_mapping_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "project_id": self.project_id,
            "project_title": self.project_title,
            "generated_at": self.generated_at,
            "counting_policy": self.counting_policy,
            "chapter_count": self.chapter_count,
            "selected_chapter_count": self.selected_chapter_count,
            "missing_selected_version_count": self.missing_selected_version_count,
            "empty_selected_content_count": self.empty_selected_content_count,
            "text_units": self.text_units,
            "chapter_coverage_ratio": self.chapter_coverage_ratio,
            "content_digest": self.content_digest,
            "chapter_distribution": [item.as_dict() for item in self.chapter_distribution],
            "volume_distribution": [item.as_dict() for item in self.volume_distribution],
            "volume_mapping_status": self.volume_mapping_status,
        }


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _parse_chapter_range(value: Any) -> tuple[int | None, int | None]:
    if isinstance(value, Mapping):
        start = value.get("start") or value.get("start_chapter")
        end = value.get("end") or value.get("end_chapter")
        try:
            return int(start), int(end)
        except (TypeError, ValueError):
            return None, None
    numbers = [int(item) for item in re.findall(r"\d+", str(value or ""))]
    if len(numbers) >= 2:
        return numbers[0], numbers[1]
    if len(numbers) == 1:
        return numbers[0], numbers[0]
    return None, None


def _volume_specs(world_setting: Mapping[str, Any] | None) -> list[tuple[int, str, int | None, int | None]]:
    payload = dict(world_setting or {})
    values = payload.get("volume_plan") or payload.get("volumes") or []
    if not isinstance(values, list):
        return []
    result: list[tuple[int, str, int | None, int | None]] = []
    for index, item in enumerate(values, start=1):
        if not isinstance(item, Mapping):
            continue
        start, end = _parse_chapter_range(item.get("chapter_range") or item)
        title = str(item.get("title") or item.get("name") or f"第{index}卷").strip()
        result.append((index, title or f"第{index}卷", start, end))
    return result


def _build_volumes(
    chapters: Iterable[NovelChapterBaseline],
    world_setting: Mapping[str, Any] | None,
) -> tuple[tuple[NovelVolumeBaseline, ...], str]:
    rows = tuple(chapters)
    specs = _volume_specs(world_setting)
    if not specs:
        return (), "unavailable"
    volumes: list[NovelVolumeBaseline] = []
    for index, title, start, end in specs:
        members = [
            row for row in rows
            if start is not None and end is not None and start <= row.chapter_number <= end
        ]
        volumes.append(
            NovelVolumeBaseline(
                volume_index=index,
                title=title,
                start_chapter=start,
                end_chapter=end,
                chapter_count=len(members),
                selected_chapter_count=sum(1 for row in members if row.selected_version_id is not None and row.text_units > 0),
                text_units=sum(row.text_units for row in members),
                source="blueprint.volume_plan",
            )
        )
    return tuple(volumes), "blueprint_volume_plan"


class NovelBenchmarkService:
    """Build a reproducible formal-text baseline without mutating novel content."""

    PLAN_ID = "NOVEL_100K_OPT_V1"

    def __init__(self, session: AsyncSession):
        self.session = session

    async def build_baseline(
        self,
        project_id: str,
        *,
        policy: CountingPolicy | None = None,
    ) -> NovelBaseline:
        selected_policy = policy or CountingPolicy()
        statement = (
            select(NovelProject)
            .where(NovelProject.id == project_id)
            .options(
                selectinload(NovelProject.chapters).selectinload(Chapter.selected_version),
                selectinload(NovelProject.blueprint),
            )
        )
        project = (await self.session.execute(statement)).scalar_one_or_none()
        if project is None:
            raise NovelBaselineError(f"novel project not found: {project_id}")

        rows: list[NovelChapterBaseline] = []
        for chapter in sorted(project.chapters, key=lambda item: (item.chapter_number, item.id)):
            version = chapter.selected_version
            if version is None:
                rows.append(
                    NovelChapterBaseline(
                        chapter_id=chapter.id,
                        chapter_number=chapter.chapter_number,
                        selected_version_id=None,
                        selected_version_status=None,
                        text_units=0,
                        content_digest=None,
                        status="missing_selected_version",
                        reason="chapter.selected_version_id is empty or unresolved",
                    )
                )
                continue
            text = str(version.content or "")
            units = selected_policy.count(text)
            digest = _sha256(selected_policy.normalize(text)) if text else None
            rows.append(
                NovelChapterBaseline(
                    chapter_id=chapter.id,
                    chapter_number=chapter.chapter_number,
                    selected_version_id=version.id,
                    selected_version_status=version.status,
                    text_units=units,
                    content_digest=digest,
                    status="selected" if units > 0 else "empty_selected_content",
                    reason=None if units > 0 else "selected chapter version has empty visible content",
                )
            )

        chapter_rows = tuple(rows)
        selected_rows = [row for row in chapter_rows if row.status == "selected"]
        empty_selected = [row for row in chapter_rows if row.status == "empty_selected_content"]
        missing_selected = [row for row in chapter_rows if row.status == "missing_selected_version"]
        digest_payload = [
            {
                "chapter_number": row.chapter_number,
                "chapter_id": row.chapter_id,
                "selected_version_id": row.selected_version_id,
                "content_digest": row.content_digest,
                "text_units": row.text_units,
                "status": row.status,
            }
            for row in chapter_rows
        ]
        volumes, volume_status = _build_volumes(
            chapter_rows,
            getattr(getattr(project, "blueprint", None), "world_setting", None),
        )
        chapter_count = len(chapter_rows)
        selected_count = len(selected_rows)
        return NovelBaseline(
            plan_id=self.PLAN_ID,
            project_id=project.id,
            project_title=project.title,
            generated_at=datetime.now(timezone.utc).isoformat(),
            counting_policy=selected_policy.as_dict(),
            chapter_count=chapter_count,
            selected_chapter_count=selected_count,
            missing_selected_version_count=len(missing_selected),
            empty_selected_content_count=len(empty_selected),
            text_units=sum(row.text_units for row in selected_rows),
            chapter_coverage_ratio=round(selected_count / chapter_count, 6) if chapter_count else 0.0,
            content_digest=_sha256(_canonical_json(digest_payload)),
            chapter_distribution=chapter_rows,
            volume_distribution=volumes,
            volume_mapping_status=volume_status,
        )

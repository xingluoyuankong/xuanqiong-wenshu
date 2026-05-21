from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services.export_service import ExportService


def chapter(number: int, *, status: str = "successful", content: str | None = "正文") -> SimpleNamespace:
    selected_version = None if content is None else SimpleNamespace(content=content)
    return SimpleNamespace(chapter_number=number, status=status, selected_version=selected_version)


def test_export_validation_accepts_successful_selected_non_empty_chapters() -> None:
    service = ExportService(session=None)  # type: ignore[arg-type]

    service._validate_exportable_chapters([chapter(1, content="有效正文")])


def test_export_validation_rejects_missing_selected_version() -> None:
    service = ExportService(session=None)  # type: ignore[arg-type]

    with pytest.raises(HTTPException) as exc:
        service._validate_exportable_chapters([chapter(1, content=None)])

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "novel_export_not_ready"
    assert "未选中正文版本" in exc.value.detail["issues"][0]


def test_export_validation_rejects_non_successful_chapter() -> None:
    service = ExportService(session=None)  # type: ignore[arg-type]

    with pytest.raises(HTTPException) as exc:
        service._validate_exportable_chapters([chapter(2, status="generating", content="临时正文")])

    assert exc.value.status_code == 409
    assert "状态为 generating" in exc.value.detail["issues"][0]


@pytest.mark.asyncio
async def test_export_preflight_reports_outline_only_chapters() -> None:
    service = ExportService(session=None)  # type: ignore[arg-type]

    async def fake_get_project(project_id: str) -> SimpleNamespace:
        return SimpleNamespace(id=project_id)

    async def fake_get_ordered_chapters(project_id: str) -> list[SimpleNamespace]:
        return [chapter(1, content="有效正文")]

    async def fake_get_outlines_map(project_id: str) -> dict[int, SimpleNamespace]:
        return {
            1: SimpleNamespace(chapter_number=1, title="第一章"),
            2: SimpleNamespace(chapter_number=2, title="第二章"),
        }

    service._get_project = fake_get_project  # type: ignore[method-assign]
    service._get_ordered_chapters = fake_get_ordered_chapters  # type: ignore[method-assign]
    service._get_outlines_map = fake_get_outlines_map  # type: ignore[method-assign]

    result = await service.preflight_export("project-1")

    assert result["ready"] is False
    assert result["exportable_chapters"] == 1
    assert result["missing_chapter_numbers"] == [2]
    assert "第2章只有大纲" in result["issues"][0]

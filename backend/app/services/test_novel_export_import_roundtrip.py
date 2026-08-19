"""导出再导入往返一致性回归。

验收标准要求「导出全文并重新导入后，章节、摘要、账本和版本数据一致」。
历史实现里导出用换行包裹标题并加 `---` 分隔线，而导入只认「第N章」开头，
导致 N 章导出后重新导入被切成 1 章（全部落进「序章」），
章节数、每章摘要、账本与版本全部错位。这里锁死双向契约。
"""
from types import SimpleNamespace

import pytest

from app.services.export_service import ExportService
from app.services.import_service import ImportService
from app.services.novel_text_format import (
    EXPORT_HEADER_MARKER,
    build_chapter_title,
    parse_export_metadata,
    split_into_chapters,
)


def _chapter(number: int, content: str) -> SimpleNamespace:
    return SimpleNamespace(
        chapter_number=number,
        status="successful",
        selected_version=SimpleNamespace(content=content),
    )


def _export_service(titles: list[str], bodies: list[str]) -> ExportService:
    service = ExportService(session=None)  # type: ignore[arg-type]
    chapters = [_chapter(i, body) for i, body in enumerate(bodies, 1)]
    outlines = {
        i: SimpleNamespace(chapter_number=i, title=title)
        for i, title in enumerate(titles, 1)
    }

    async def fake_project(project_id: str) -> SimpleNamespace:
        return SimpleNamespace(id=project_id, title="往返测试小说")

    async def fake_chapters(_project_id: str) -> list[SimpleNamespace]:
        return chapters

    async def fake_outlines(_project_id: str) -> dict[int, SimpleNamespace]:
        return outlines

    service._get_project = fake_project  # type: ignore[method-assign]
    service._get_ordered_chapters = fake_chapters  # type: ignore[method-assign]
    service._get_outlines_map = fake_outlines  # type: ignore[method-assign]
    return service


@pytest.mark.asyncio
async def test_exported_txt_reimports_with_identical_chapter_boundaries() -> None:
    titles = ["血契三日", "诏狱夺人", "第3章 夜雨归令", ""]
    bodies = [
        "正文一段。甲乙丙。",
        "正文二段。\n\n含空行的第二自然段。",
        "正文三段。丁戊己。",
        "正文四段。无标题章节。",
    ]
    service = _export_service(titles, bodies)

    exported = await service.export_novel_as_txt("project-roundtrip")
    reimported = ImportService(session=None)._split_into_chapters(exported)  # type: ignore[arg-type]

    # 章节数量必须完全一致，不得出现额外的「序章」。
    assert len(reimported) == len(bodies)
    assert [title for title, _ in reimported] == [
        "第1章 血契三日",
        "第2章 诏狱夺人",
        "第3章 夜雨归令",
        "第4章",
    ]
    # 每章正文逐字一致，含多自然段的章节也不能串段。
    assert [body for _, body in reimported] == bodies


@pytest.mark.asyncio
async def test_export_emits_machine_readable_header_and_strips_it_on_import() -> None:
    service = _export_service(["开篇"], ["正文。"])

    exported = await service.export_novel_as_txt("project-header")

    assert exported.startswith(EXPORT_HEADER_MARKER)
    assert "往返测试小说" in exported
    reimported = split_into_chapters(exported)
    # 书名与导出时间属于文件头，不得被当成正文导入。
    assert len(reimported) == 1
    assert reimported[0][1] == "正文。"
    assert "往返测试小说" not in reimported[0][1]


def test_legacy_manuscript_prologue_still_imported() -> None:
    """对齐导出格式不能牺牲真实旧稿：无导出头时前言仍作为序章保留。"""
    legacy = "这是旧稿前言，没有章号。\n\n第一章 起势\n旧稿正文。"

    chapters = split_into_chapters(legacy)

    assert [title for title, _ in chapters] == ["序章", "第一章 起势"]
    assert chapters[0][1] == "这是旧稿前言，没有章号。"
    assert chapters[1][1] == "旧稿正文。"


def test_build_chapter_title_does_not_duplicate_existing_prefix() -> None:
    assert build_chapter_title(7, "第7章 已有前缀") == "第7章 已有前缀"
    assert build_chapter_title(7, "无前缀标题") == "第7章 无前缀标题"
    assert build_chapter_title(7, None) == "第7章"
    assert build_chapter_title(7, "  ") == "第7章"


def test_export_metadata_roundtrip_contains_structure_contract():
    project = SimpleNamespace(
        id="project-meta", title="结构小说", initial_prompt="初始设定", status="blueprint_ready",
        blueprint=SimpleNamespace(
            title="结构小说", target_audience="成人", genre="玄幻", style="冷峻", tone="紧张",
            one_sentence_summary="一句话摘要", full_synopsis="全书摘要",
            world_setting={"core_rules": "灵气规则", "volume_plan": [{"volume": 1, "title": "起势"}]},
        ), characters=[SimpleNamespace(name="主角", identity="剑修", goals="复仇")],
        relationships_=[],
    )
    service = ExportService(session=None)  # type: ignore[arg-type]
    metadata = service._build_roundtrip_metadata(project, {
        1: SimpleNamespace(chapter_number=1, title="开局", summary="章节摘要", continuity_notes=["承接前章"]),
    })
    from app.services.novel_text_format import encode_export_metadata
    parsed = parse_export_metadata("# XUANQIONG-EXPORT v1\n" + encode_export_metadata(metadata))
    assert parsed["blueprint"]["full_synopsis"] == "全书摘要"
    assert parsed["blueprint"]["characters"][0]["name"] == "主角"
    assert parsed["chapter_outlines"][0]["summary"] == "章节摘要"

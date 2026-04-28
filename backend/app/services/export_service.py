# 导出服务 - 支持 TXT 和 DOCX 格式导出小说
from __future__ import annotations

import io
import logging
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import Chapter, ChapterOutline, NovelProject

logger = logging.getLogger(__name__)


class ExportService:
    """处理小说导出服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def export_novel_as_txt(self, project_id: str) -> str:
        """导出小说为 TXT 格式"""
        project = await self._get_project(project_id)
        chapters = await self._get_ordered_chapters(project_id)

        if not chapters:
            raise HTTPException(status_code=404, detail="没有章节可导出")

        outlines = await self._get_outlines_map(project_id)

        output = []
        output.append(project.title or "无标题小说")
        output.append(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        output.append("=" * 50)
        output.append("")

        for chapter in chapters:
            outline = outlines.get(chapter.chapter_number)
            chapter_title = outline.title if outline and outline.title else f"第{chapter.chapter_number}章"
            content = self._get_chapter_content(chapter)
            output.append(f"\n{chapter_title}\n")
            output.append("-" * 30)
            output.append(content)
            output.append("")

        return "\n".join(output)

    async def export_novel_as_docx(self, project_id: str) -> bytes:
        """导出小说为 DOCX 格式"""
        try:
            from docx import Document
            from docx.shared import Pt
        except ImportError:
            raise HTTPException(
                status_code=500,
                detail="DOCX 导出功能未安装，请运行: pip install python-docx"
            )

        project = await self._get_project(project_id)
        chapters = await self._get_ordered_chapters(project_id)

        if not chapters:
            raise HTTPException(status_code=404, detail="没有章节可导出")

        outlines = await self._get_outlines_map(project_id)

        doc = Document()
        doc.add_heading(project.title or "无标题小说", level=0)
        doc.add_paragraph(f"导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        doc.add_paragraph("")

        for chapter in chapters:
            outline = outlines.get(chapter.chapter_number)
            chapter_title = outline.title if outline and outline.title else f"第{chapter.chapter_number}章"
            doc.add_page_break()
            doc.add_heading(chapter_title, level=1)

            content = self._get_chapter_content(chapter)
            if content:
                for para in content.split("\n\n"):
                    if not para.strip():
                        continue
                    paragraph = doc.add_paragraph(para.strip())
                    for run in paragraph.runs:
                        run.font.size = Pt(12)

        bio = io.BytesIO()
        doc.save(bio)
        bio.seek(0)
        return bio.getvalue()

    async def _get_project(self, project_id: str) -> NovelProject:
        """获取项目信息"""
        result = await self.session.execute(
            select(NovelProject).where(NovelProject.id == project_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise HTTPException(status_code=404, detail="项目不存在")
        return project

    async def _get_ordered_chapters(self, project_id: str) -> list[Chapter]:
        """获取按顺序排列的章节列表"""
        result = await self.session.execute(
            select(Chapter)
            .where(Chapter.project_id == project_id)
            .options(
                selectinload(Chapter.selected_version),
                selectinload(Chapter.versions),
            )
            .order_by(Chapter.chapter_number)
        )
        return list(result.scalars().all())

    async def _get_outlines_map(self, project_id: str) -> dict[int, ChapterOutline]:
        result = await self.session.execute(
            select(ChapterOutline)
            .where(ChapterOutline.project_id == project_id)
            .order_by(ChapterOutline.chapter_number)
        )
        outlines = result.scalars().all()
        return {outline.chapter_number: outline for outline in outlines}

    def _get_chapter_content(self, chapter: Chapter) -> str:
        selected_version = chapter.selected_version
        if selected_version and selected_version.content:
            return selected_version.content

        if chapter.versions:
            latest_version = chapter.versions[-1]
            if latest_version.content:
                return latest_version.content

        return ""

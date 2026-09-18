# AIMETA P=PatchDiff服务_Patch和Diff业务逻辑|R=精细编辑_版本对比|NR=不含HTTP逻辑|E=PatchDiffService|X=internal|A=服务类|D=sqlalchemy|S=db
from __future__ import annotations

import logging
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models import Chapter, ChapterVersion, PatchEdit, DiffLine, ChapterVersionPatch
from ..models.novel import NovelProject

logger = logging.getLogger(__name__)


@dataclass
class DiffLineResult:
    """差异行结果"""
    line_number: int
    original_line: Optional[str]
    patched_line: Optional[str]
    change_type: str  # added, modified, deleted, unchanged


@dataclass
class PatchOperation:
    """Patch 操作"""
    op: str  # replace, delete, insert
    start: int
    end: int
    text: str = ""


class PatchDiffService:
    """Patch+Diff 服务类，负责精细编辑和版本对比"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_chapter_by_number(self, project_id: str, chapter_number: int) -> Chapter:
        """根据项目ID和章节号获取章节"""
        # 验证项目所有权
        project = await self.session.get(NovelProject, project_id)
        if not project:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="项目不存在")

        # 获取章节
        result = await self.session.execute(
            select(Chapter)
            .options(selectinload(Chapter.versions), selectinload(Chapter.selected_version))
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number == chapter_number
            )
        )
        chapter = result.scalar_one_or_none()
        if not chapter:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="章节不存在")
        return chapter

    async def get_version_by_id(self, version_id: int) -> ChapterVersion:
        """根据版本ID获取版本"""
        version = await self.session.get(ChapterVersion, version_id)
        if not version:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="版本不存在")
        return version

    async def create_patch(
        self,
        chapter_id: int,
        original_text: str,
        patched_text: str,
        from_version_id: Optional[int] = None,
        to_version_id: Optional[int] = None,
        description: Optional[str] = None,
    ) -> PatchEdit:
        """创建 Patch 记录"""
        patch_operations = self.generate_patch_operations(original_text, patched_text)

        patch_edit = PatchEdit(
            chapter_id=chapter_id,
            original_text=original_text,
            patched_text=patched_text,
            patch_operations=patch_operations,
            from_version_id=from_version_id,
            to_version_id=to_version_id,
            description=description,
        )
        self.session.add(patch_edit)
        await self.session.flush()

        diff_lines = self.generate_diff(original_text, patched_text)
        for diff in diff_lines:
            diff_line = DiffLine(
                patch_edit_id=patch_edit.id,
                line_number=diff.line_number,
                original_line=diff.original_line,
                patched_line=diff.patched_line,
                change_type=diff.change_type,
            )
            self.session.add(diff_line)

        await self.session.flush()
        logger.info("创建 Patch 记录: chapter_id=%d, patch_id=%d", chapter_id, patch_edit.id)
        return patch_edit

    def generate_diff(self, original: str, patched: str) -> List[DiffLineResult]:
        """生成差异（基于行的比较）"""
        original_lines = original.split('\n') if original else []
        patched_lines = patched.split('\n') if patched else []

        diff_result: List[DiffLineResult] = []

        # 使用 SequenceMatcher 进行行级比较
        matcher = SequenceMatcher(None, original_lines, patched_lines)
        op_codes = matcher.get_opcodes()

        patched_line_idx = 0
        original_line_idx = 0

        for tag, i1, i2, j1, j2 in op_codes:
            if tag == 'equal':
                # 未修改的行
                for idx in range(i2 - i1):
                    diff_result.append(DiffLineResult(
                        line_number=original_line_idx + idx + 1,
                        original_line=original_lines[original_line_idx + idx],
                        patched_line=patched_lines[patched_line_idx + idx],
                        change_type='unchanged',
                    ))
                original_line_idx += (i2 - i1)
                patched_line_idx += (j2 - j1)
            elif tag == 'replace':
                # 修改的行
                max_len = max(i2 - i1, j2 - j1)
                for idx in range(max_len):
                    orig_line = original_lines[original_line_idx + idx] if original_line_idx + idx < len(original_lines) else None
                    pat_line = patched_lines[patched_line_idx + idx] if patched_line_idx + idx < len(patched_lines) else None
                    diff_result.append(DiffLineResult(
                        line_number=original_line_idx + idx + 1,
                        original_line=orig_line,
                        patched_line=pat_line,
                        change_type='modified' if orig_line and pat_line else ('deleted' if orig_line else 'added'),
                    ))
                original_line_idx += (i2 - i1)
                patched_line_idx += (j2 - j1)
            elif tag == 'delete':
                # 删除的行
                for idx in range(i2 - i1):
                    diff_result.append(DiffLineResult(
                        line_number=original_line_idx + idx + 1,
                        original_line=original_lines[original_line_idx + idx],
                        patched_line=None,
                        change_type='deleted',
                    ))
                original_line_idx += (i2 - i1)
            elif tag == 'insert':
                # 新增的行
                for idx in range(j2 - j1):
                    diff_result.append(DiffLineResult(
                        line_number=original_line_idx + idx + 1 if original_line_idx > 0 else original_line_idx + idx + 1,
                        original_line=None,
                        patched_line=patched_lines[patched_line_idx + idx],
                        change_type='added',
                    ))
                patched_line_idx += (j2 - j1)

        return diff_result

    def generate_patch_operations(self, original: str, patched: str) -> List[Dict[str, Any]]:
        """生成 Patch 操作序列（简化版：基于行）"""
        original_lines = original.split('\n') if original else []
        patched_lines = patched.split('\n') if patched else []

        matcher = SequenceMatcher(None, original_lines, patched_lines)
        op_codes = matcher.get_opcodes()

        operations: List[Dict[str, Any]] = []

        for tag, i1, i2, j1, j2 in op_codes:
            if tag == 'equal':
                continue
            elif tag == 'replace':
                operations.append({
                    "op": "replace",
                    "start": i1,
                    "end": i2,
                    "original_lines": original_lines[i1:i2],
                    "new_lines": patched_lines[j1:j2],
                })
            elif tag == 'delete':
                operations.append({
                    "op": "delete",
                    "start": i1,
                    "end": i2,
                    "deleted_lines": original_lines[i1:i2],
                })
            elif tag == 'insert':
                operations.append({
                    "op": "insert",
                    "start": j1,
                    "lines": patched_lines[j1:j2],
                })

        return operations

    def apply_patch(self, content: str, operations: List[Dict[str, Any]]) -> str:
        """应用 Patch 到内容"""
        if not operations:
            return content

        lines = content.split('\n')
        # 从后向前应用操作，避免索引偏移问题
        for op in reversed(operations):
            op_type = op.get("op")
            start = op.get("start", 0)

            if op_type == "replace":
                end = op.get("end", start)
                new_lines = op.get("new_lines", [])
                lines = lines[:start] + new_lines + lines[end:]
            elif op_type == "delete":
                end = op.get("end", start)
                lines = lines[:start] + lines[end:]
            elif op_type == "insert":
                new_lines = op.get("lines", [])
                lines = lines[:start] + new_lines + lines[start:]

        return '\n'.join(lines)

    async def revert_patch(self, chapter_id: int, patch_id: int) -> str:
        """撤销 Patch，恢复到原始文本"""
        # 获取 Patch 记录
        patch_edit = await self.session.get(PatchEdit, patch_id)
        if not patch_edit:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Patch 记录不存在")

        if patch_edit.chapter_id != chapter_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="Patch 记录不属于该章节")

        # 返回原始文本
        return patch_edit.original_text

    async def get_version_diff(
        self,
        chapter_id: int,
        version1_id: int,
        version2_id: int,
    ) -> List[DiffLineResult]:
        """获取两个版本之间的差异"""
        # 获取两个版本
        v1 = await self.get_version_by_id(version1_id)
        v2 = await self.get_version_by_id(version2_id)

        # 确保两个版本都属于同一章节
        if v1.chapter_id != chapter_id or v2.chapter_id != chapter_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="版本不属于同一章节")

        # 生成差异
        return self.generate_diff(v1.content, v2.content)

    async def get_patch_history(self, chapter_id: int) -> List[PatchEdit]:
        """获取章节的 Patch 历史"""
        result = await self.session.execute(
            select(PatchEdit)
            .where(PatchEdit.chapter_id == chapter_id)
            .order_by(PatchEdit.created_at.desc())
        )
        return list(result.scalars().all())

    async def apply_patch_to_chapter(
        self,
        project_id: str,
        chapter_number: int,
        original_text: str,
        patched_text: str,
    ) -> Chapter:
        """应用 Patch 到章节内容"""
        # 获取章节
        chapter = await self.get_chapter_by_number(project_id, chapter_number)

        # 获取当前选中的版本
        if not chapter.selected_version_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=400, detail="章节没有选中版本，无法应用 Patch")

        selected_content = chapter.selected_version.content if chapter.selected_version else ""
        if (selected_content or "") != original_text:
            from fastapi import HTTPException
            raise HTTPException(status_code=409, detail="当前章节内容已变化，请先刷新后再进行精细编辑")

        patch_edit = await self.create_patch(
            chapter_id=chapter.id,
            original_text=original_text,
            patched_text=patched_text,
            from_version_id=chapter.selected_version_id,
            description=f"手动精细编辑 - 第 {chapter_number} 章",
        )

        next_version_number = len(chapter.versions) + 1
        new_version = ChapterVersion(
            chapter_id=chapter.id,
            version_label=f"v{next_version_number}",
            content=patched_text,
            metadata_={
                "patch_id": patch_edit.id,
                "patch_description": "精细编辑",
            },
        )
        self.session.add(new_version)
        await self.session.flush()

        patch_edit.to_version_id = new_version.id
        chapter.selected_version_id = new_version.id
        chapter.status = "successful"
        chapter.word_count = len(patched_text.replace('\n', ''))

        await self.session.commit()
        await self.session.refresh(chapter)

        logger.info("应用 Patch 到章节: project_id=%s, chapter=%d, patch_id=%d",
                    project_id, chapter_number, patch_edit.id)
        return chapter
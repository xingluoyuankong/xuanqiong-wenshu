# AIMETA P=PatchDiff API_Patch和Diff精细编辑接口|R=精细编辑_版本对比|NR=不含业务逻辑|E=api:/projects/{project_id}/chapters/{chapter_number}/patch/*|X=http|A=精细编辑API|D=fastapi|S=net
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...schemas.user import UserInDB
from ...services.patch_diff_service import PatchDiffService, DiffLineResult

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Patch-Diff"])


# ============ Schema 定义 ============

class ApplyPatchRequest(BaseModel):
    """应用 Patch 请求"""
    original_text: str
    patched_text: str


class GetDiffRequest(BaseModel):
    """获取文本差异请求"""
    original_text: str
    patched_text: str


class DiffLineSchema(BaseModel):
    """差异行 Schema"""
    line_number: int
    original_line: Optional[str] = None
    patched_line: Optional[str] = None
    change_type: str  # added, modified, deleted, unchanged


class PatchEditSchema(BaseModel):
    """Patch 编辑记录 Schema"""
    id: int
    chapter_id: int
    original_text: str
    patched_text: str
    patch_operations: Optional[dict] = None
    from_version_id: Optional[int] = None
    to_version_id: Optional[int] = None
    description: Optional[str] = None
    created_at: str


class ApplyPatchResponse(BaseModel):
    """应用 Patch 响应"""
    status: str
    message: str
    patch_id: int
    chapter_number: int


class GetDiffResponse(BaseModel):
    """获取差异响应"""
    chapter_number: int
    diff_lines: List[DiffLineSchema]
    summary: dict  # 统计信息


class GetVersionDiffResponse(BaseModel):
    """版本对比响应"""
    chapter_number: int
    version1_id: int
    version2_id: int
    diff_lines: List[DiffLineSchema]
    summary: dict


class PatchHistoryResponse(BaseModel):
    """Patch 历史响应"""
    chapter_number: int
    patches: List[PatchEditSchema]
    total: int


class RevertPatchRequest(BaseModel):
    """撤销 Patch 请求"""
    patch_id: int


class RevertPatchResponse(BaseModel):
    """撤销 Patch 响应"""
    status: str
    message: str
    original_text: str


# ============ 辅助函数 ============

def diff_result_to_schema(diff: DiffLineResult) -> DiffLineSchema:
    return DiffLineSchema(
        line_number=diff.line_number,
        original_line=diff.original_line,
        patched_line=diff.patched_line,
        change_type=diff.change_type,
    )


def calculate_diff_summary(diff_lines: List[DiffLineResult]) -> dict:
    """计算差异统计"""
    added = sum(1 for d in diff_lines if d.change_type == 'added')
    deleted = sum(1 for d in diff_lines if d.change_type == 'deleted')
    modified = sum(1 for d in diff_lines if d.change_type == 'modified')
    unchanged = sum(1 for d in diff_lines if d.change_type == 'unchanged')

    return {
        "total_lines": len(diff_lines),
        "added": added,
        "deleted": deleted,
        "modified": modified,
        "unchanged": unchanged,
    }


# ============ API 路由 ============

@router.post(
    "/projects/{project_id}/chapters/{chapter_number}/patch/apply",
    response_model=ApplyPatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def apply_patch(
    project_id: str,
    chapter_number: int,
    request: ApplyPatchRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ApplyPatchResponse:
    """应用 Patch 到章节内容"""
    service = PatchDiffService(session)

    try:
        # 验证项目所有权
        from ...services.novel_service import NovelService
        novel_service = NovelService(session)
        await novel_service.ensure_project_owner(project_id, current_user.id)

        # 应用 Patch
        chapter = await service.apply_patch_to_chapter(
            project_id=project_id,
            chapter_number=chapter_number,
            original_text=request.original_text,
            patched_text=request.patched_text,
        )

        # 获取最新的 Patch 记录
        patch_history = await service.get_patch_history(chapter.id)
        latest_patch = patch_history[0] if patch_history else None

        logger.info("用户 %s 应用 Patch 到项目 %s 第 %d 章", current_user.id, project_id, chapter_number)

        return ApplyPatchResponse(
            status="success",
            message="Patch 应用成功，已创建新版本",
            patch_id=latest_patch.id if latest_patch else 0,
            chapter_number=chapter_number,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("应用 Patch 失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"应用 Patch 失败: {str(exc)}")


@router.post(
    "/projects/{project_id}/chapters/{chapter_number}/diff",
    response_model=GetDiffResponse,
)
async def get_diff(
    project_id: str,
    chapter_number: int,
    request: GetDiffRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> GetDiffResponse:
    """获取两个文本之间的差异"""
    service = PatchDiffService(session)

    try:
        # 验证项目所有权
        from ...services.novel_service import NovelService
        novel_service = NovelService(session)
        await novel_service.ensure_project_owner(project_id, current_user.id)

        original_text = request.original_text
        patched_text = request.patched_text

        # 生成差异
        diff_lines = service.generate_diff(original_text, patched_text)
        diff_schemas = [diff_result_to_schema(d) for d in diff_lines]
        summary = calculate_diff_summary(diff_lines)

        logger.info("用户 %s 获取项目 %s 第 %d 章的差异", current_user.id, project_id, chapter_number)

        return GetDiffResponse(
            chapter_number=chapter_number,
            diff_lines=diff_schemas,
            summary=summary,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("生成差异失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"生成差异失败: {str(exc)}")


@router.get(
    "/projects/{project_id}/chapters/{chapter_number}/versions/{v1}/vs/{v2}",
    response_model=GetVersionDiffResponse,
)
async def get_version_diff(
    project_id: str,
    chapter_number: int,
    v1: int,
    v2: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> GetVersionDiffResponse:
    """获取两个版本之间的差异"""
    service = PatchDiffService(session)

    try:
        # 验证项目所有权
        from ...services.novel_service import NovelService
        novel_service = NovelService(session)
        project = await novel_service.ensure_project_owner(project_id, current_user.id)

        # 获取章节
        chapter = await service.get_chapter_by_number(project_id, chapter_number)

        # 获取版本差异
        diff_lines = await service.get_version_diff(chapter.id, v1, v2)
        diff_schemas = [diff_result_to_schema(d) for d in diff_lines]
        summary = calculate_diff_summary(diff_lines)

        logger.info("用户 %s 获取项目 %s 第 %d 章版本 %d vs %d 的差异",
                    current_user.id, project_id, chapter_number, v1, v2)

        return GetVersionDiffResponse(
            chapter_number=chapter_number,
            version1_id=v1,
            version2_id=v2,
            diff_lines=diff_schemas,
            summary=summary,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("获取版本差异失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"获取版本差异失败: {str(exc)}")


@router.get(
    "/projects/{project_id}/chapters/{chapter_number}/patch/history",
    response_model=PatchHistoryResponse,
)
async def get_patch_history(
    project_id: str,
    chapter_number: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> PatchHistoryResponse:
    """获取章节的 Patch 历史"""
    service = PatchDiffService(session)

    try:
        # 验证项目所有权
        from ...services.novel_service import NovelService
        novel_service = NovelService(session)
        await novel_service.ensure_project_owner(project_id, current_user.id)

        # 获取章节
        chapter = await service.get_chapter_by_number(project_id, chapter_number)

        # 获取 Patch 历史
        patches = await service.get_patch_history(chapter.id)
        patch_schemas = [
            PatchEditSchema(
                id=p.id,
                chapter_id=p.chapter_id,
                original_text=p.original_text[:500] + "..." if len(p.original_text) > 500 else p.original_text,
                patched_text=p.patched_text[:500] + "..." if len(p.patched_text) > 500 else p.patched_text,
                patch_operations=p.patch_operations,
                from_version_id=p.from_version_id,
                to_version_id=p.to_version_id,
                description=p.description,
                created_at=p.created_at.isoformat() if p.created_at else "",
            )
            for p in patches
        ]

        logger.info("用户 %s 获取项目 %s 第 %d 章的 Patch 历史，共 %d 条",
                    current_user.id, project_id, chapter_number, len(patches))

        return PatchHistoryResponse(
            chapter_number=chapter_number,
            patches=patch_schemas,
            total=len(patches),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("获取 Patch 历史失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"获取 Patch 历史失败: {str(exc)}")


@router.post(
    "/projects/{project_id}/chapters/{chapter_number}/patch/revert",
    response_model=RevertPatchResponse,
)
async def revert_patch(
    project_id: str,
    chapter_number: int,
    request: RevertPatchRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> RevertPatchResponse:
    """撤销指定 Patch"""
    service = PatchDiffService(session)

    try:
        # 验证项目所有权
        from ...services.novel_service import NovelService
        novel_service = NovelService(session)
        await novel_service.ensure_project_owner(project_id, current_user.id)

        # 获取章节
        chapter = await service.get_chapter_by_number(project_id, chapter_number)

        # 撤销 Patch
        original_text = await service.revert_patch(chapter.id, request.patch_id)

        logger.info("用户 %s 撤销项目 %s 第 %d 章的 Patch %d",
                    current_user.id, project_id, chapter_number, request.patch_id)

        return RevertPatchResponse(
            status="success",
            message=f"Patch {request.patch_id} 已撤销",
            original_text=original_text,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("撤销 Patch 失败: %s", exc)
        raise HTTPException(status_code=500, detail=f"撤销 Patch 失败: {str(exc)}")
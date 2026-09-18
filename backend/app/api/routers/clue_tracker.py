# 线索追踪 API
from __future__ import annotations

from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...schemas.user import UserInDB
from ...services.clue_tracker_service import ClueTrackerService
from ...services.novel_service import NovelService

router = APIRouter(prefix="/projects", tags=["clue-tracker"])


# ============ Schema 定义 ============

class CreateClueRequest(BaseModel):
    """创建线索请求"""
    name: str
    clue_type: str  # key_evidence/mysterious_event/character_secret/timeline/red_herring/plot_hook
    description: Optional[str] = None
    importance: int = 3
    planted_chapter: Optional[int] = None
    is_red_herring: bool = False
    red_herring_explanation: Optional[str] = None
    clue_content: Optional[str] = None
    hint_level: int = 2
    design_intent: Optional[str] = None


class UpdateClueRequest(BaseModel):
    """更新线索请求"""
    name: Optional[str] = None
    clue_type: Optional[str] = None
    description: Optional[str] = None
    importance: Optional[int] = None
    planted_chapter: Optional[int] = None
    resolution_chapter: Optional[int] = None
    status: Optional[str] = None
    is_red_herring: Optional[bool] = None
    red_herring_explanation: Optional[str] = None
    clue_content: Optional[str] = None
    hint_level: Optional[int] = None
    design_intent: Optional[str] = None


class LinkChapterRequest(BaseModel):
    """关联章节请求"""
    chapter_id: int
    chapter_number: int
    appearance_type: str  # mention/reveal/clue_hints/resolution
    content_excerpt: Optional[str] = None
    detail_level: int = 3
    chapter_role: Optional[str] = None


class ClueResponse(BaseModel):
    """线索响应"""
    id: int
    project_id: str
    name: str
    clue_type: str
    description: Optional[str]
    importance: int
    planted_chapter: Optional[int]
    resolution_chapter: Optional[int]
    status: str
    is_red_herring: bool
    red_herring_explanation: Optional[str]
    clue_content: Optional[str]
    hint_level: int
    design_intent: Optional[str]
    created_at: str
    updated_at: str


class ClueTimelineResponse(BaseModel):
    """线索时间线响应"""
    clue_id: int
    clue_name: str
    clue_type: str
    status: str
    planted_chapter: Optional[int]
    resolution_chapter: Optional[int]
    is_red_herring: bool
    appearances: List[dict]


class ClueThreadAnalysisResponse(BaseModel):
    """线索网络分析响应"""
    project_id: str
    total_clues: int
    type_counts: dict
    status_counts: dict
    red_herring_count: int
    unresolved_count: int
    threads: List[dict]


# ============ 路由端点 ============

@router.post("/{project_id}/clues", response_model=ClueResponse)
async def create_clue(
    project_id: str,
    request: CreateClueRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user)
) -> dict:
    """创建新线索"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    service = ClueTrackerService(session)
    clue = await service.create_clue(
        project_id=project_id,
        name=request.name,
        clue_type=request.clue_type,
        description=request.description,
        importance=request.importance,
        planted_chapter=request.planted_chapter,
        is_red_herring=request.is_red_herring,
        red_herring_explanation=request.red_herring_explanation,
        clue_content=request.clue_content,
        hint_level=request.hint_level,
        design_intent=request.design_intent
    )
    return {
        "id": clue.id,
        "project_id": clue.project_id,
        "name": clue.name,
        "clue_type": clue.clue_type,
        "description": clue.description,
        "importance": clue.importance,
        "planted_chapter": clue.planted_chapter,
        "resolution_chapter": clue.resolution_chapter,
        "status": clue.status,
        "is_red_herring": clue.is_red_herring,
        "red_herring_explanation": clue.red_herring_explanation,
        "clue_content": clue.clue_content,
        "hint_level": clue.hint_level,
        "design_intent": clue.design_intent,
        "created_at": clue.created_at.isoformat(),
        "updated_at": clue.updated_at.isoformat()
    }


@router.get("/{project_id}/clues", response_model=List[ClueResponse])
async def get_project_clues(
    project_id: str,
    status: Optional[str] = None,
    clue_type: Optional[str] = None,
    include_red_herring: bool = True,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user)
) -> List[dict]:
    """获取项目的所有线索"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    service = ClueTrackerService(session)
    await service.sync_from_foreshadowings(project_id)
    clues = await service.get_project_clues(
        project_id=project_id,
        status=status,
        clue_type=clue_type,
        include_red_herring=include_red_herring
    )
    return [
        {
            "id": clue.id,
            "project_id": clue.project_id,
            "name": clue.name,
            "clue_type": clue.clue_type,
            "description": clue.description,
            "importance": clue.importance,
            "planted_chapter": clue.planted_chapter,
            "resolution_chapter": clue.resolution_chapter,
            "status": clue.status,
            "is_red_herring": clue.is_red_herring,
            "red_herring_explanation": clue.red_herring_explanation,
            "clue_content": clue.clue_content,
            "hint_level": clue.hint_level,
            "design_intent": clue.design_intent,
            "created_at": clue.created_at.isoformat(),
            "updated_at": clue.updated_at.isoformat()
        }
        for clue in clues
    ]


@router.get("/{project_id}/clues/threads", response_model=ClueThreadAnalysisResponse)
async def analyze_clue_threads(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user)
) -> dict:
    """分析项目的线索网络"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    service = ClueTrackerService(session)
    await service.sync_from_foreshadowings(project_id)
    analysis = await service.analyze_clue_threads(project_id)
    return analysis


@router.get("/{project_id}/clues/red-herring", response_model=List[dict])
async def get_red_herrings(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user)
) -> List[dict]:
    """获取红鲱鱼线索列表"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    service = ClueTrackerService(session)
    herrings = await service.identify_red_herrings(project_id)
    return herrings


@router.get("/{project_id}/clues/unresolved", response_model=List[dict])
async def get_unresolved_clues(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user)
) -> List[dict]:
    """获取未回收的伏笔列表"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    service = ClueTrackerService(session)
    unresolved = await service.find_unresolved_clues(project_id)
    return unresolved


@router.get("/{project_id}/clues/{clue_id}", response_model=ClueResponse)
async def get_clue(
    project_id: str,
    clue_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user)
) -> dict:
    """获取单个线索详情"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    service = ClueTrackerService(session)
    clue = await service.get_clue_by_id(clue_id)

    if not clue or clue.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"线索 ID {clue_id} 不存在"
        )

    return {
        "id": clue.id,
        "project_id": clue.project_id,
        "name": clue.name,
        "clue_type": clue.clue_type,
        "description": clue.description,
        "importance": clue.importance,
        "planted_chapter": clue.planted_chapter,
        "resolution_chapter": clue.resolution_chapter,
        "status": clue.status,
        "is_red_herring": clue.is_red_herring,
        "red_herring_explanation": clue.red_herring_explanation,
        "clue_content": clue.clue_content,
        "hint_level": clue.hint_level,
        "design_intent": clue.design_intent,
        "created_at": clue.created_at.isoformat(),
        "updated_at": clue.updated_at.isoformat()
    }


@router.put("/{project_id}/clues/{clue_id}", response_model=ClueResponse)
async def update_clue(
    project_id: str,
    clue_id: int,
    request: UpdateClueRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user)
) -> dict:
    """更新线索"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    service = ClueTrackerService(session)
    clue = await service.update_clue(clue_id, **request.model_dump(exclude_none=True))

    if not clue or clue.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"线索 ID {clue_id} 不存在"
        )

    return {
        "id": clue.id,
        "project_id": clue.project_id,
        "name": clue.name,
        "clue_type": clue.clue_type,
        "description": clue.description,
        "importance": clue.importance,
        "planted_chapter": clue.planted_chapter,
        "resolution_chapter": clue.resolution_chapter,
        "status": clue.status,
        "is_red_herring": clue.is_red_herring,
        "red_herring_explanation": clue.red_herring_explanation,
        "clue_content": clue.clue_content,
        "hint_level": clue.hint_level,
        "design_intent": clue.design_intent,
        "created_at": clue.created_at.isoformat(),
        "updated_at": clue.updated_at.isoformat()
    }


@router.delete("/{project_id}/clues/{clue_id}")
async def delete_clue(
    project_id: str,
    clue_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user)
) -> dict:
    """删除线索"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    service = ClueTrackerService(session)
    success = await service.delete_clue(clue_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"线索 ID {clue_id} 不存在"
        )

    return {"status": "success", "message": f"线索 {clue_id} 已删除"}


@router.post("/{project_id}/clues/{clue_id}/link-chapter")
async def link_clue_to_chapter(
    project_id: str,
    clue_id: int,
    request: LinkChapterRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user)
) -> dict:
    """将线索关联到章节"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    service = ClueTrackerService(session)

    # 验证线索存在
    clue = await service.get_clue_by_id(clue_id)
    if not clue or clue.project_id != project_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"线索 ID {clue_id} 不存在"
        )

    link = await service.link_clue_to_chapter(
        clue_id=clue_id,
        chapter_id=request.chapter_id,
        chapter_number=request.chapter_number,
        appearance_type=request.appearance_type,
        content_excerpt=request.content_excerpt,
        detail_level=request.detail_level,
        chapter_role=request.chapter_role
    )

    return {
        "id": link.id,
        "clue_id": link.clue_id,
        "chapter_id": link.chapter_id,
        "chapter_number": link.chapter_number,
        "appearance_type": link.appearance_type,
        "created_at": link.created_at.isoformat()
    }


@router.get("/{project_id}/clues/{clue_id}/timeline", response_model=ClueTimelineResponse)
async def get_clue_timeline(
    project_id: str,
    clue_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user)
) -> dict:
    """获取线索的时间线"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    service = ClueTrackerService(session)
    timeline = await service.get_clue_timeline(clue_id)

    if not timeline:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"线索 ID {clue_id} 不存在"
        )

    return timeline

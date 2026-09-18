# AIMETA P=大纲演进路由_剧情推演API|R=演进生成_选项选择_替代方案查询|NR=不含业务逻辑|E=outline|X=internal|A=路由端点|D=none|S=none|RD=./README.ai
"""
大纲演进路由 (Outline Evolution Router)

提供剧情推演相关的 API：
- POST /api/projects/{id}/outline/evolve - 基于当前大纲生成演进选项
- POST /api/projects/{id}/outline/next - 选择某个演进选项，更新大纲
- GET /api/projects/{id}/outline/alternatives - 获取当前章节的所有可能走向
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...schemas.user import UserInDB
from ...services.llm_service import LLMService
from ...services.outline_evolution_service import OutlineEvolutionService
from ...services.novel_service import NovelService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/outline", tags=["outline-evolution"])


class EvolveRequest(BaseModel):
    chapter_number: int = Field(default=1, ge=0, description="章节号，0表示整本书大纲")
    num_options: int = Field(default=3, ge=2, le=5, description="生成的选项数量")


class EvolveResponse(BaseModel):
    alternatives: List[dict]
    batch_id: str
    chapter_number: int


class SelectAlternativeRequest(BaseModel):
    option_id: int = Field(..., description="选择的选项ID")
    chapter_number: int = Field(default=1, ge=0, description="章节号")


class SelectAlternativeResponse(BaseModel):
    success: bool
    message: str
    updated_outline: Optional[dict] = None


class AlternativesResponse(BaseModel):
    alternatives: List[dict]
    chapter_number: int
    total: int


@router.post("/evolve", response_model=EvolveResponse)
async def evolve_outline(
    project_id: str,
    request: EvolveRequest = Body(default=EvolveRequest()),
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """基于当前大纲，生成 N 个剧情演进选项（抽卡式互动）"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    llm_service = LLMService(session)
    evolution_service = OutlineEvolutionService(session, llm_service)

    try:
        await evolution_service.clear_expired_alternatives(
            project_id,
            request.chapter_number,
            hours=24
        )

        alternatives = await evolution_service.evolve_outline(
            project_id=project_id,
            chapter_number=request.chapter_number,
            user_id=current_user.id,
            num_options=request.num_options
        )

        if not alternatives:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="生成剧情演进选项失败"
            )

        batch_id = alternatives[0].batch_id if alternatives else ""
        alt_list = [
            {
                "id": alt.id,
                "title": alt.title,
                "description": alt.description,
                "new_outline": alt.new_outline,
                "changes": alt.changes,
                "evolution_type": alt.evolution_type,
                "score": alt.score
            }
            for alt in alternatives
        ]

        return EvolveResponse(
            alternatives=alt_list,
            batch_id=batch_id,
            chapter_number=request.chapter_number
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"剧情演进失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/next", response_model=SelectAlternativeResponse)
async def select_alternative(
    project_id: str,
    request: SelectAlternativeRequest = Body(...),
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """选择某个演进选项，更新大纲"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    llm_service = LLMService(session)
    evolution_service = OutlineEvolutionService(session, llm_service)

    try:
        updated_outline = await evolution_service.select_alternative(
            project_id=project_id,
            selected_option_id=request.option_id,
            user_id=current_user.id
        )

        return SelectAlternativeResponse(
            success=True,
            message="大纲已更新",
            updated_outline={
                "chapter_number": request.chapter_number,
                "title": updated_outline.title if updated_outline else None,
                "summary": updated_outline.summary if updated_outline else None
            } if updated_outline else None
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"选择演进选项失败: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/alternatives", response_model=AlternativesResponse)
async def get_alternatives(
    project_id: str,
    chapter_number: int = Query(default=1, ge=0, description="章节号"),
    status_filter: Optional[str] = Query(default=None, description="状态过滤"),
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """获取当前章节的所有可能走向"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    llm_service = LLMService(session)
    evolution_service = OutlineEvolutionService(session, llm_service)

    if status_filter:
        alternatives = await evolution_service.get_alternatives(
            project_id=project_id,
            chapter_number=chapter_number,
            status=status_filter
        )
    else:
        alternatives = await evolution_service.get_latest_batch_alternatives(
            project_id=project_id,
            chapter_number=chapter_number
        )

    if not alternatives:
        alternatives = await evolution_service.get_pending_alternatives(
            project_id=project_id,
            chapter_number=chapter_number
        )

    alt_list = [
        {
            "id": alt.id,
            "title": alt.title,
            "description": alt.description,
            "new_outline": alt.new_outline,
            "changes": alt.changes,
            "evolution_type": alt.evolution_type,
            "score": alt.score,
            "status": alt.status,
            "created_at": alt.created_at.isoformat() if alt.created_at else None
        }
        for alt in alternatives
    ]

    return AlternativesResponse(alternatives=alt_list, chapter_number=chapter_number, total=len(alt_list))


@router.get("/history")
async def get_evolution_history(
    project_id: str,
    chapter_number: Optional[int] = Query(default=None, description="章节号"),
    limit: int = Query(default=20, ge=1, le=100),
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """获取演进历史记录"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    llm_service = LLMService(session)
    evolution_service = OutlineEvolutionService(session, llm_service)

    history = await evolution_service.get_evolution_history(
        project_id=project_id,
        chapter_number=chapter_number,
        limit=limit
    )

    return {
        "history": [
            {
                "id": h.id,
                "batch_id": h.batch_id,
                "chapter_number": h.chapter_number,
                "previous_title": h.previous_title,
                "new_title": h.new_title,
                "created_at": h.created_at.isoformat() if h.created_at else None
            }
            for h in history
        ],
        "total": len(history)
    }
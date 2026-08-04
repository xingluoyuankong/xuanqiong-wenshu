# AIMETA P=大纲演进路由_剧情推演API|R=演进生成_选项选择_替代方案查询|NR=不含业务逻辑|E=outline|X=internal|A=路由端点|D=none|S=none|RD=./README.ai
"""
大纲演进路由 (Outline Evolution Router)

提供剧情推演相关的 API：
- POST /api/projects/{id}/outline/evolve - 基于当前大纲生成演进选项
- POST /api/projects/{id}/outline/next - 选择某个演进选项，更新大纲
- GET /api/projects/{id}/outline/alternatives - 获取当前章节的所有可能走向
"""
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...schemas.user import UserInDB
from ...services.llm_service import LLMService
from ...services.outline_evolution_service import OutlineEvolutionService

from ...services.long_novel_outline_generator import LongNovelOutlineGenerator
from ...services.novel_service import NovelService

logger = logging.getLogger(__name__)


class LongNovelOutlineRequest(BaseModel):
    """长篇小说大纲生成请求"""
    target_word_count: int = Field(default=200000, ge=10000, le=2000000, description="目标总字数")
    volume_count: Optional[int] = Field(default=None, ge=1, le=50, description="指定卷数（可选，自动估算）")
    chapters_per_volume: Optional[int] = Field(default=None, ge=3, le=30, description="每卷章节数（可选，自动估算）")
    protagonist: str = Field(default="", description="主角设定")
    central_conflict: str = Field(default="", description="核心冲突")
    worldview: str = Field(default="", description="世界观")
    regenerate: bool = Field(default=False, description="是否覆盖已有大纲")


class VolumeOutline(BaseModel):
    """卷大纲"""
    volume_number: int
    volume_title: str
    volume_summary: str
    theme: str
    chapter_count: int


class ChapterOutlineItem(BaseModel):
    """章节大纲条目"""
    chapter_number: int
    volume_number: int
    volume_title: str = ""
    title: str
    summary: str
    key_events: List[str] = Field(default_factory=list)
    character_focus: List[str] = Field(default_factory=list)
    emotional_tone: str = ""
    word_count_estimate: int = 5000


class LongNovelOutlineResponse(BaseModel):
    """长篇小说大纲响应"""
    project_id: str
    novel_title: str
    target_word_count: int
    structure: Dict[str, Any]
    volumes: List[VolumeOutline]
    chapters: List[ChapterOutlineItem]
    total_chapters: int
    generated_at: str


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



@router.post("/generate-long", response_model=LongNovelOutlineResponse)
async def generate_long_novel_outline(
    project_id: str,
    request: LongNovelOutlineRequest = Body(...),
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """生成完整的长篇小说大纲（多卷多章节结构）"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    novel = await novel_service.get_project_schema(project_id, current_user.id)
    if not novel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="项目不存在"
        )

    # 获取项目角色信息
    characters = await novel_service.get_characters(project_id) if hasattr(novel_service, 'get_characters') else []
    character_dicts = [
        {"name": getattr(c, "name", ""), "identity": getattr(c, "identity", ""), "description": getattr(c, "description", "")}
        for c in characters
    ] if characters else []

    generator = LongNovelOutlineGenerator()
    prompt = generator.build_prompt(
        title=novel.title,
        genre=getattr(novel, "genre", ""),
        style=getattr(novel, "style", ""),
        target_word_count=request.target_word_count,
        protagonist=request.protagonist,
        central_conflict=request.central_conflict,
        worldview=request.worldview,
        characters=character_dicts,
        volume_count=request.volume_count,
        chapters_per_volume=request.chapters_per_volume,
    )

    # 调用 LLM 生成
    llm_service = LLMService(session)
    try:
        response = await llm_service.generate(
            prompt=prompt,
            user_id=current_user.id,
            temperature=0.8,
            max_tokens=40000,
        )
        outline_data = generator.parse_outline_response(response)
    except Exception as e:
        logger.warning("LLM 大纲生成失败，使用兜底结构: %s", e)
        outline_data = None

    if not outline_data:
        outline_data = generator.generate_fallback_outline(
            title=novel.title,
            genre=getattr(novel, "genre", ""),
            target_word_count=request.target_word_count,
            protagonist=request.protagonist or "主角",
        )

    # 验证结构
    issues = generator.validate_outline_structure(outline_data)
    if issues:
        logger.warning("大纲结构验证问题: %s", "; ".join(issues))

    # 展平章节列表
    chapters = generator.flatten_outline(outline_data)

    # 构建响应
    volumes = []
    for vol in outline_data.get("volumes", []):
        volumes.append(VolumeOutline(
            volume_number=vol.get("volume_number", 0),
            volume_title=vol.get("volume_title", ""),
            volume_summary=vol.get("volume_summary", ""),
            theme=vol.get("theme", ""),
            chapter_count=len(vol.get("chapters", [])),
        ))

    structure = generator.estimate_structure(request.target_word_count, getattr(novel, "genre", ""))

    # 持久化大纲到数据库
    try:
        from ...models.novel import ChapterOutline
        from sqlalchemy import select
        for ch in chapters:
            cn = ch.get("chapter_number", 0)
            stmt = select(ChapterOutline).where(
                ChapterOutline.project_id == project_id,
                ChapterOutline.chapter_number == cn
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            extra = {
                "key_events": ch.get("key_events", []),
                "character_focus": ch.get("character_focus", []),
                "emotional_tone": ch.get("emotional_tone", ""),
                "word_count_estimate": ch.get("word_count_estimate", 0),
                "volume_number": ch.get("volume_number", 1),
                "volume_title": ch.get("volume_title", ""),
            }
            if existing:
                existing.title = ch.get("title", "")
                existing.summary = ch.get("summary", "")
                existing.metadata_ = extra
            else:
                session.add(ChapterOutline(
                    project_id=project_id,
                    chapter_number=cn,
                    title=ch.get("title", ""),
                    summary=ch.get("summary", ""),
                    metadata_=extra,
                ))
        await session.commit()
    except Exception as e:
        logger.warning("大纲持久化失败: %s", e)
        await session.rollback()

    from datetime import datetime
    return LongNovelOutlineResponse(
        project_id=project_id,
        novel_title=outline_data.get("novel_title", novel.title),
        target_word_count=request.target_word_count,
        structure=structure,
        volumes=volumes,
        chapters=[ChapterOutlineItem(**ch) for ch in chapters],
        total_chapters=len(chapters),
        generated_at=datetime.utcnow().isoformat(),
    )


@router.get("/structure")
async def get_outline_structure(
    project_id: str,
    current_user: UserInDB = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """获取当前小说的卷-章结构统计"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    # 获取所有章节大纲
    from ...models.novel import ChapterOutline
    from sqlalchemy import select
    stmt = select(ChapterOutline).where(
        ChapterOutline.project_id == project_id
    ).order_by(ChapterOutline.chapter_number)
    result = await session.execute(stmt)
    outlines = list(result.scalars().all())

    if not outlines:
        return {
            "project_id": project_id,
            "total_chapters": 0,
            "volumes": [],
            "chapters": [],
        }

    chapters = []
    for o in outlines:
        chapters.append({
            "chapter_number": o.chapter_number,
            "title": o.title,
            "summary": o.summary,
            "word_count": len(o.summary) if o.summary else 0,
        })

    return {
        "project_id": project_id,
        "total_chapters": len(chapters),
        "estimated_word_count": sum(c.get("word_count", 0) for c in chapters),
        "chapters": chapters,
    }



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

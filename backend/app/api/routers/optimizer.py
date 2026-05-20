# AIMETA P=优化器API_内容优化建议|R=内容优化_建议生成|NR=不含内容修改|E=route:POST_/api/optimizer/*|X=http|A=优化建议|D=fastapi|S=net|RD=./README.ai
"""
章节内容分层优化API
支持对话、环境描写、心理活动、节奏韵律四个维度的深度优化
"""
import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...models.novel import ChapterVersion
from ...schemas.novel import Chapter as ChapterSchema
from ...schemas.user import UserInDB
from ...services.llm_service import LLMService
from ...services.generation_call_service import GenerationCallPolicy, GenerationJSONDecodeError, call_generation_json
from ...services.longform_context_service import LongformContextService
from ...services.novel_service import NovelService
from ...services.prompt_service import PromptService

router = APIRouter(prefix="/api/optimizer", tags=["Optimizer"])
logger = logging.getLogger(__name__)


class OptimizeRequest(BaseModel):
    """优化请求"""
    project_id: str = Field(..., description="项目ID")
    chapter_number: int = Field(..., description="章节编号")
    dimension: str = Field(..., description="优化维度: dialogue/environment/psychology/rhythm")
    additional_notes: Optional[str] = Field(default=None, description="额外优化指令")
    version_index: Optional[int] = Field(default=None, description="要优化的版本索引（0-based），不传则使用已选版本")
    version_id: Optional[int] = Field(default=None, description="Stable version id; preferred over version_index")


class OptimizeResponse(BaseModel):
    """优化响应"""
    optimized_content: str = Field(..., description="优化后的内容")
    optimization_notes: str = Field(..., description="优化说明")
    dimension: str = Field(..., description="优化维度")


# 优化维度到提示词的映射
class ApplyOptimizationRequest(BaseModel):
    project_id: str = Field(..., description="Project ID")
    chapter_number: int = Field(..., description="Chapter number")
    optimized_content: str = Field(..., description="Optimized chapter content")


class ApplyOptimizationResponse(BaseModel):
    status: str = Field(..., description="Operation status")
    message: str = Field(..., description="Operation message")
    chapter: ChapterSchema = Field(..., description="Updated chapter")

DIMENSION_PROMPT_MAP = {
    "dialogue": "optimize_dialogue",
    "environment": "optimize_environment", 
    "psychology": "optimize_psychology",
    "rhythm": "optimize_rhythm"
}

# 默认的节奏优化提示词（如果数据库中没有）
DEFAULT_RHYTHM_PROMPT = """# 节奏韵律优化专家

你是一位专注于小说节奏和韵律的编辑大师。你的任务是优化文章的节奏感，让阅读体验更加流畅和沉浸。

## 优化原则

### 1. 句子长度变化
- 长短句交替，像呼吸一样自然
- 紧张时用短句，舒缓时用长句
- 避免连续多个相同长度的句子

### 2. 段落节奏
- 重要情节放慢，细致描写
- 过渡情节加快，简洁带过
- 高潮部分可以用单句成段

### 3. 标点符号
- 善用省略号表示思绪飘散
- 用破折号表示突然转念
- 感叹号要克制使用

### 4. 韵律感
- 注意句尾的音节变化
- 避免重复的句式结构
- 适当使用排比增强气势

## 输入格式
```json
{
  "original_content": "需要优化的章节内容",
  "additional_notes": "额外优化指令"
}
```

## 输出格式
```json
{
  "optimized_content": "优化后的完整章节内容",
  "optimization_notes": "优化说明"
}
```
"""


def _compact_len(text: str) -> int:
    return len("".join((text or "").split()))


def _optimizer_response_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "required": ["optimized_content", "optimization_notes"],
        "properties": {
            "optimized_content": {"type": "string"},
            "optimization_notes": {"type": "string"},
        },
    }


def _anchor_overlap_count(original_sample: str, optimized_content: str, *, chunk_size: int = 16) -> int:
    sample = "".join((original_sample or "").split())
    optimized = "".join((optimized_content or "").split())
    if not sample or not optimized:
        return 0
    if len(sample) <= chunk_size:
        return 1 if sample in optimized else 0
    hits = 0
    seen: set[str] = set()
    step = max(8, chunk_size)
    for start in range(0, max(1, len(sample) - chunk_size + 1), step):
        chunk = sample[start:start + chunk_size]
        if len(chunk) < chunk_size or chunk in seen:
            continue
        seen.add(chunk)
        if chunk in optimized:
            hits += 1
    return hits


CONTINUITY_MOTIF_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("old_south_canal", ("\u65e7\u5357\u6e20", "\u5357\u6e20")),
    ("medicine_trace", ("\u836f\u6e23", "\u836f\u5473", "\u836f\u8017", "\u836f\u65b9", "\u836f\u884c")),
    ("death_risk", ("\u6b7b\u4eba", "\u4eba\u547d", "\u4f1a\u6b7b", "\u771f\u4f1a\u6b7b")),
    ("jingzhe_gap", ("\u60ca\u86f0",)),
    ("ledger_evidence", ("\u8d26\u518c", "\u8d26\u672c", "\u8d26\u9875", "\u7a7a\u8d26")),
)


def _extract_required_motif_groups(text: str) -> list[Dict[str, Any]]:
    source = str(text or "")
    required: list[Dict[str, Any]] = []
    for label, markers in CONTINUITY_MOTIF_GROUPS:
        present_markers = [marker for marker in markers if marker in source]
        if present_markers:
            required.append({"label": label, "markers": list(markers), "present_markers": present_markers})
    return required


def _build_nearby_outline_context(project: Any, chapter_number: int, *, radius: int = 2) -> list[Dict[str, Any]]:
    outlines = sorted(getattr(project, "outlines", []) or [], key=lambda item: item.chapter_number)
    payload: list[Dict[str, Any]] = []
    for outline in outlines:
        distance = outline.chapter_number - chapter_number
        if abs(distance) > radius:
            continue
        payload.append(
            {
                "chapter_number": outline.chapter_number,
                "relative_position": "current" if distance == 0 else ("previous" if distance < 0 else "next"),
                "title": outline.title,
                "summary": (outline.summary or "")[:700],
            }
        )
    return payload


def _build_nearby_chapter_state(project: Any, chapter_number: int, *, radius: int = 1) -> list[Dict[str, Any]]:
    chapters = sorted(getattr(project, "chapters", []) or [], key=lambda item: item.chapter_number)
    payload: list[Dict[str, Any]] = []
    for chapter in chapters:
        distance = chapter.chapter_number - chapter_number
        if abs(distance) > radius or distance == 0:
            continue
        selected = getattr(chapter, "selected_version", None)
        payload.append(
            {
                "chapter_number": chapter.chapter_number,
                "relative_position": "previous" if distance < 0 else "next",
                "real_summary": (getattr(chapter, "real_summary", None) or "")[:600],
                "ending_sample": ((getattr(selected, "content", None) or "")[-450:] if selected else ""),
            }
        )
    return payload


def _build_continuity_contract(project: Any, request: OptimizeRequest, original_content: str) -> Dict[str, Any]:
    return {
        "mode": "local_window_with_anchors_return_full_chapter",
        "chapter_number": request.chapter_number,
        "dimension": request.dimension,
        "nearby_outlines": _build_nearby_outline_context(project, request.chapter_number),
        "nearby_chapter_state": _build_nearby_chapter_state(project, request.chapter_number),
        "original_opening_sample": original_content[:700],
        "original_ending_sample": original_content[-700:],
        "required_motif_groups": _extract_required_motif_groups(original_content),
        "hard_rules": [
            "优先只修改问题片段，用前后锚点把局部改动缝回原文；最后必须返回完整章节正文，便于系统保存。",
            "保留原章节的事件顺序、因果链、角色目标、章尾钩子和上下章承接点。",
            "只在当前优化维度上改写表达，不新增无法在相邻章节承接的新支线。",
            "可以润色句段和补强细节，但不能把连续场景切碎成互不相连的短块。",
            "除非原文存在严重结构断裂，不要重写整章；扩展修补范围必须让连续性更清楚。",
        ],
    }


def _continuity_guard_failure(original_content: str, optimized_content: str) -> Optional[str]:
    original_len = _compact_len(original_content)
    optimized_len = _compact_len(optimized_content)
    if optimized_len < 80:
        return "optimized content is too short"
    if original_len >= 1200 and optimized_len < int(original_len * 0.72):
        return f"optimized content shrank from {original_len} to {optimized_len} non-space chars"
    if original_len >= 400 and optimized_len < int(original_len * 0.58):
        return f"optimized content lost too much content ({optimized_len}/{original_len})"
    stripped = (optimized_content or "").strip()
    if stripped.startswith("{") and "optimized_content" in stripped[:300]:
        return "optimized content still looks like raw JSON"
    if original_len >= 500:
        opening_hits = _anchor_overlap_count(original_content[:360], optimized_content)
        ending_hits = _anchor_overlap_count(original_content[-360:], optimized_content)
        if opening_hits == 0 and ending_hits == 0:
            return "optimized content lost both opening and ending continuity anchors"
    missing_motif_groups = []
    for group in _extract_required_motif_groups(original_content):
        markers = group.get("markers") or []
        if not any(str(marker) in optimized_content for marker in markers):
            missing_motif_groups.append(str(group.get("label") or "unknown"))
    if missing_motif_groups:
        return "optimized content lost critical continuity motifs: " + ", ".join(missing_motif_groups[:6])
    return None


@router.post("/optimize", response_model=OptimizeResponse)
async def optimize_chapter(
    request: OptimizeRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> OptimizeResponse:
    """
    对章节内容进行分层优化
    支持指定版本索引优化候选版本
    """
    novel_service = NovelService(session)
    prompt_service = PromptService(session)
    llm_service = LLMService(session)

    # 验证项目所有权
    project = await novel_service.ensure_project_owner(request.project_id, current_user.id)

    # 获取章节内容
    chapter = next(
        (ch for ch in project.chapters if ch.chapter_number == request.chapter_number),
        None
    )
    if not chapter:
        raise HTTPException(status_code=404, detail="章节不存在")

    # 确定要优化的内容来源
    original_content = None

    # 路径 A：使用指定版本 ID 或版本序号
    if request.version_id is not None or request.version_index is not None:
        versions = sorted(list(chapter.versions or []), key=lambda v: (v.created_at, v.id))
        if not versions:
            raise HTTPException(status_code=400, detail="该章节没有可优化的候选版本")
        selected_version = None
        if request.version_id is not None:
            selected_version = next((version for version in versions if version.id == request.version_id), None)
            if selected_version is None:
                raise HTTPException(status_code=400, detail="未找到指定的章节版本，无法优化")
        else:
            if request.version_index is None or request.version_index < 0 or request.version_index >= len(versions):
                raise HTTPException(status_code=400, detail=f"版本序号 {request.version_index} 无效")
            selected_version = versions[request.version_index]
        if not selected_version.content:
            raise HTTPException(status_code=400, detail="所选版本内容为空，无法优化")
        original_content = selected_version.content

    # 路径 B：使用已选定稿版本
    if not original_content and chapter.selected_version and chapter.selected_version.content:
        original_content = chapter.selected_version.content

    # 路径 C：没有可用内容
    if not original_content:
        raise HTTPException(status_code=400, detail="章节尚未生成内容，无法进行优化")
    
    # 验证优化维度
    if request.dimension not in DIMENSION_PROMPT_MAP:
        raise HTTPException(
            status_code=400, 
            detail=f"不支持的优化维度: {request.dimension}，支持的维度: {list(DIMENSION_PROMPT_MAP.keys())}"
        )
    
    # 获取对应的优化提示词
    prompt_name = DIMENSION_PROMPT_MAP[request.dimension]
    optimizer_prompt = await prompt_service.get_prompt(prompt_name)
    
    # 如果没有找到提示词，使用默认提示词（仅对rhythm维度）
    if not optimizer_prompt:
        if request.dimension == "rhythm":
            optimizer_prompt = DEFAULT_RHYTHM_PROMPT
        else:
            raise HTTPException(
                status_code=500, 
                detail=f"缺少{request.dimension}优化提示词，请联系管理员配置 '{prompt_name}' 提示词"
            )
    
    # 获取角色DNA信息（用于心理活动优化）
    character_dna = {}
    if request.dimension == "psychology":
        project_schema = await novel_service._serialize_project(project)
        for char in project_schema.blueprint.characters:
            if "extra" in char and "dna_profile" in char.get("extra", {}):
                character_dna[char.get("name", "")] = char["extra"]["dna_profile"]
    
    # 构建优化请求
    optimize_input = {
        "original_content": original_content,
        "additional_notes": request.additional_notes or "无额外指令",
        "continuity_contract": _build_continuity_contract(project, request, original_content),
    }
    try:
        outline = next((item for item in getattr(project, "outlines", []) or [] if item.chapter_number == request.chapter_number), None)
        longform_package = await LongformContextService(session).build_context_package(
            project=project,
            outline=outline,
            chapter_number=request.chapter_number,
            writing_notes=request.additional_notes,
            chapter_mission=None,
            allowed_new_characters=[],
        )
        optimize_input["longform_continuity_package"] = longform_package.to_optimizer_payload()
    except Exception as exc:  # noqa: BLE001 - optimization should keep working with nearby anchors.
        logger.warning(
            "章节优化长篇上下文包装配失败，继续使用相邻章节锚点: project=%s chapter=%s error=%s",
            request.project_id,
            request.chapter_number,
            exc,
        )
        optimize_input["longform_continuity_package_error"] = str(exc)[:200]
    
    # 如果是心理活动优化，添加角色DNA信息
    if character_dna:
        optimize_input["character_dna"] = character_dna
    
    logger.info(
        "用户 %s 开始优化项目 %s 第 %s 章，维度: %s",
        current_user.id,
        request.project_id,
        request.chapter_number,
        request.dimension
    )
    
    # 调用LLM进行优化
    try:
        with LLMService.daily_limit_scope(f"optimizer:{request.project_id}:{request.chapter_number}:{request.dimension}:{current_user.id}"):
            json_result = await call_generation_json(
                llm_service=llm_service,
                system_prompt=optimizer_prompt,
                conversation_history=[{
                    "role": "user",
                    "content": json.dumps(optimize_input, ensure_ascii=False)
                }],
                temperature=0.7,
                user_id=current_user.id,
                timeout=600.0,
                policy=GenerationCallPolicy(
                    stage_label="章节优化",
                    retry_attempts=3,
                    response_format="json_object",
                    json_schema=_optimizer_response_schema(),
                    json_schema_name="chapter_optimization",
                    json_schema_strict=False,
                    allow_truncated_response=True,
                    json_repair_attempts=2,
                ),
            )
        result = json_result.data
        optimized_content = str(result.get("optimized_content") or "").strip()
        optimization_notes = str(result.get("optimization_notes") or "优化完成").strip()
        guard_failure = _continuity_guard_failure(original_content, optimized_content)
        if guard_failure:
            logger.warning(
                "章节优化结果未通过连续性保护，返回原文: project=%s chapter=%s dimension=%s reason=%s",
                request.project_id,
                request.chapter_number,
                request.dimension,
                guard_failure,
            )
            optimized_content = original_content
            optimization_notes = f"优化结果未通过连续性保护，已保留原文。原因: {guard_failure}"
        
        logger.info(
            "项目 %s 第 %s 章 %s 优化完成",
            request.project_id,
            request.chapter_number,
            request.dimension
        )
        
        return OptimizeResponse(
            optimized_content=optimized_content,
            optimization_notes=optimization_notes,
            dimension=request.dimension
        )
        
    except GenerationJSONDecodeError as exc:
        logger.warning(
            "章节优化返回 JSON 不可解析，返回原文: project=%s chapter=%s dimension=%s error=%s raw=%s",
            request.project_id,
            request.chapter_number,
            request.dimension,
            exc,
            exc.raw_text[:500],
        )
        return OptimizeResponse(
            optimized_content=original_content,
            optimization_notes="优化结果格式异常，已保留原文以避免破坏章节连续性。",
            dimension=request.dimension,
        )
    except Exception as exc:
        logger.exception(
            "项目 %s 第 %s 章优化失败: %s",
            request.project_id,
            request.chapter_number,
            exc
        )
        raise HTTPException(
            status_code=500,
            detail=f"优化过程中发生错误: {str(exc)[:200]}"
        )


@router.post("/apply-optimization", response_model=ApplyOptimizationResponse)
async def apply_optimization(
    request: Optional[ApplyOptimizationRequest] = None,
    project_id: Optional[str] = Query(default=None),
    chapter_number: Optional[int] = Query(default=None),
    optimized_content: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
):
    """Apply optimized content to the selected chapter."""
    novel_service = NovelService(session)

    resolved_project_id = request.project_id if request else project_id
    resolved_chapter_number = request.chapter_number if request else chapter_number
    resolved_optimized_content = request.optimized_content if request else optimized_content

    if not resolved_project_id or resolved_chapter_number is None or resolved_optimized_content is None:
        raise HTTPException(
            status_code=422,
            detail="project_id, chapter_number, optimized_content are required",
        )

    project = await novel_service.ensure_project_owner(resolved_project_id, current_user.id)

    chapter = next(
        (ch for ch in project.chapters if ch.chapter_number == resolved_chapter_number),
        None,
    )
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")

    selected_version = chapter.selected_version
    if not selected_version:
        raise HTTPException(status_code=400, detail="Selected chapter version not found")

    existing_versions = sorted(list(chapter.versions or []), key=lambda v: (v.created_at, v.id))
    next_version_number = len(existing_versions) + 1
    optimized_version = type(selected_version)(
        chapter_id=chapter.id,
        version_label=f"v{next_version_number}",
        content=resolved_optimized_content,
        provider=selected_version.provider,
        metadata_={
            **(selected_version.metadata_ or {}),
            "optimized_from_version_id": selected_version.id,
            "optimization_applied": True,
        },
    )
    session.add(optimized_version)
    await session.flush()

    chapter.selected_version_id = optimized_version.id
    chapter.selected_version = optimized_version
    chapter.status = "successful"
    chapter.word_count = len(resolved_optimized_content or "")
    await novel_service._touch_project(resolved_project_id, auto_commit=False)
    await session.commit()

    updated_chapter = await novel_service.get_chapter_schema(
        resolved_project_id,
        current_user.id,
        resolved_chapter_number,
    )

    logger.info(
        "User %s applied optimization for project %s chapter %s",
        current_user.id,
        resolved_project_id,
        resolved_chapter_number,
    )

    return ApplyOptimizationResponse(
        status="success",
        message="Optimization applied successfully",
        chapter=updated_chapter,
    )

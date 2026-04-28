# AIMETA P=优化器API_内容优化建议|R=内容优化_建议生成|NR=不含内容修改|E=route:POST_/api/optimizer/*|X=http|A=优化建议|D=fastapi|S=net|RD=./README.ai
"""
章节内容分层优化API
支持对话、环境描写、心理活动、节奏韵律四个维度的深度优化
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...schemas.novel import Chapter as ChapterSchema
from ...schemas.user import UserInDB
from ...services.llm_service import LLMService
from ...services.novel_service import NovelService
from ...services.prompt_service import PromptService
from ...utils.json_utils import remove_think_tags, unwrap_markdown_json

router = APIRouter(prefix="/api/optimizer", tags=["Optimizer"])
logger = logging.getLogger(__name__)


class OptimizeRequest(BaseModel):
    """优化请求"""
    project_id: str = Field(..., description="项目ID")
    chapter_number: int = Field(..., description="章节编号")
    dimension: str = Field(..., description="优化维度: dialogue/environment/psychology/rhythm")
    additional_notes: Optional[str] = Field(default=None, description="额外优化指令")
    version_index: Optional[int] = Field(default=None, description="要优化的版本索引（0-based），不传则使用已选版本")


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

    # 情况 A: 指定了版本索引
    if request.version_index is not None:
        versions = sorted(list(chapter.versions or []), key=lambda v: v.created_at)
        if not versions:
            raise HTTPException(status_code=400, detail="该章节还没有生成任何版本")
        if request.version_index < 0 or request.version_index >= len(versions):
            raise HTTPException(status_code=400, detail=f"版本索引 {request.version_index} 无效")
        if not versions[request.version_index].content:
            raise HTTPException(status_code=400, detail="指定版本的内容为空")
        original_content = versions[request.version_index].content

    # 情况 B: 使用已选版本
    if not original_content and chapter.selected_version and chapter.selected_version.content:
        original_content = chapter.selected_version.content

    # 情况 C: 使用最新版本
    if not original_content:
        versions = sorted(list(chapter.versions or []), key=lambda v: v.created_at)
        if versions and versions[-1].content:
            original_content = versions[-1].content

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
        "additional_notes": request.additional_notes or "无额外指令"
    }
    
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
        response = await llm_service.get_llm_response(
            system_prompt=optimizer_prompt,
            conversation_history=[{
                "role": "user",
                "content": json.dumps(optimize_input, ensure_ascii=False)
            }],
            temperature=0.7,
            user_id=current_user.id,
            timeout=600.0,
        )
        
        cleaned = remove_think_tags(response)
        normalized = unwrap_markdown_json(cleaned)
        
        try:
            result = json.loads(normalized)
            optimized_content = result.get("optimized_content", cleaned)
            optimization_notes = result.get("optimization_notes", "优化完成")
        except json.JSONDecodeError:
            # 如果无法解析JSON，将整个响应作为优化后的内容
            optimized_content = cleaned
            optimization_notes = "优化完成（响应格式非标准JSON）"
        
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

    existing_versions = sorted(list(chapter.versions or []), key=lambda v: v.created_at)
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
    chapter.status = "successful"
    chapter.word_count = len(resolved_optimized_content or "")
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

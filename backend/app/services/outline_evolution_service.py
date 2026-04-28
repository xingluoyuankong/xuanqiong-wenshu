# AIMETA P=剧情演进服务_大纲分支生成和选择|R=演进生成_选项选择_历史记录|NR=不含ORM操作|E=OutlineEvolutionService|X=internal|A=演进核心|D=llm_service|S=none|RD=./README.ai
"""
剧情演进服务 (Outline Evolution Service)

实现"抽卡式"的大纲演进机制：
1. 基于当前章节的大纲生成 N 个剧情演进选项（多模型抽卡）
2. 用户选择某个选项后更新大纲
3. 支持获取当前章节的所有可能走向

核心思想：不像传统方式一次性生成完整大纲，而是让用户与 AI 多轮互动，
通过"抽卡"式的大纲演进，逐步精炼剧情走向。
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..models.novel import ChapterOutline, NovelProject
from ..models.outline_alternative import (
    OutlineAlternative,
    OutlineEvolutionHistory,
    EvolutionStatus,
)
from .llm_service import LLMService
from ..utils.json_utils import remove_think_tags, sanitize_json_like_text, unwrap_markdown_json

logger = logging.getLogger(__name__)


# ==================== 提示词模板 ====================

EVOLVE_PROMPT = """\
你是一个故事架构专家。基于当前章节的大纲，请生成 {num_options} 个不同的剧情演进选项。

## 小说信息：
- 类型：{genre}
- 风格：{style}
- 标题：{title}

## 当前章节大纲（第{chapter_number}章）：
- 章节标题：{chapter_title}
- 章节摘要：{chapter_summary}

## 前后章节信息：
- 前一章：{prev_chapter}
- 后一章：{next_chapter}

## 已有角色：
{characters}

## 要求：
1. 每个选项都应该是合理且有吸引力的剧情发展方向
2. 选项之间应该有明显的差异性
3. 每个选项需要包含：
   - title: 演进方向标题（简短有力，20字以内）
   - description: 详细描述这个分支的剧情走向（100-200字）
   - new_outline: 更新后的章节大纲（包含 title 和 summary）
   - changes: 这个分支相比原大纲的主要变化（50字以内）
   - evolution_type: 演进类型（branch=分支剧情，extend=延伸剧情，twist=反转剧情）
   - score: 吸引力评分（0-100，基于剧情潜力、冲突性、情感张力评估）

请以JSON数组格式返回：
[
  {{
    "title": "选项标题",
    "description": "详细描述...",
    "new_outline": {{"title": "新标题", "summary": "新摘要"}},
    "changes": "主要变化...",
    "evolution_type": "branch",
    "score": 85
  }},
  ...
]

仅返回JSON数组，不要解释任何内容。
"""


class OutlineEvolutionService:
    """
    剧情演进服务

    负责生成剧情演进选项、选择演进方向、更新大纲。
    """

    def __init__(self, db: AsyncSession, llm_service: LLMService):
        self.db = db
        self.llm_service = llm_service

    async def evolve_outline(
        self,
        project_id: str,
        chapter_number: int,
        user_id: int,
        num_options: int = 3,
    ) -> List[OutlineAlternative]:
        """基于当前大纲，生成 N 个剧情演进选项"""
        project = await self.db.scalar(
            select(NovelProject)
            .options(
                selectinload(NovelProject.blueprint),
                selectinload(NovelProject.characters),
            )
            .where(NovelProject.id == project_id)
        )

        if not project:
            raise ValueError("项目不存在")

        blueprint = project.blueprint
        if not blueprint:
            raise ValueError("项目无蓝图")

        outline = None
        if chapter_number > 0:
            outline = await self.db.scalar(
                select(ChapterOutline).where(
                    ChapterOutline.project_id == project_id,
                    ChapterOutline.chapter_number == chapter_number,
                )
            )

        prev_outline = None
        if chapter_number > 1:
            prev_outline = await self.db.scalar(
                select(ChapterOutline).where(
                    ChapterOutline.project_id == project_id,
                    ChapterOutline.chapter_number == chapter_number - 1,
                )
            )

        next_outline = await self.db.scalar(
            select(ChapterOutline).where(
                ChapterOutline.project_id == project_id,
                ChapterOutline.chapter_number == chapter_number + 1,
            )
        )

        characters_data = project.characters or []
        characters = (
            "\n".join(
                f"- {getattr(character, 'name', '未知') or '未知'}: {getattr(character, 'identity', '') or ''}"
                for character in characters_data[:10]
            )
            if characters_data
            else "（无角色信息）"
        )

        if chapter_number == 0:
            chapter_title = "全书画纲"
            chapter_summary = blueprint.full_synopsis or ""
        else:
            chapter_title = outline.title if outline else ""
            chapter_summary = outline.summary if outline else ""

        prev_chapter = f"第{prev_outline.chapter_number}章: {prev_outline.title}" if prev_outline else "无"
        next_chapter = f"第{next_outline.chapter_number}章: {next_outline.title}" if next_outline else "无"

        prompt = EVOLVE_PROMPT.format(
            num_options=num_options,
            genre=blueprint.genre or "",
            style=blueprint.style or "",
            title=blueprint.title or "",
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            chapter_summary=chapter_summary,
            prev_chapter=prev_chapter,
            next_chapter=next_chapter,
            characters=characters,
        )

        try:
            response = await self.llm_service.generate(
                prompt=prompt,
                user_id=user_id,
                max_tokens=4000,
                temperature=0.8,
            )

            if response:
                options_data = self._parse_json_response(response)
                if options_data and isinstance(options_data, list):
                    batch_id = str(uuid.uuid4())

                    alternatives = []
                    for idx, opt in enumerate(options_data[:num_options]):
                        alt = await self._create_alternative(
                            project_id=project_id,
                            chapter_number=chapter_number,
                            batch_id=batch_id,
                            option_index=idx,
                            data=opt,
                        )
                        alternatives.append(alt)

                    await self.db.commit()
                    return alternatives

        except Exception as e:
            logger.error(f"生成剧情演进选项失败: {e}")
            await self.db.rollback()

        return []

    async def _create_alternative(
        self,
        project_id: str,
        chapter_number: int,
        batch_id: str,
        option_index: int,
        data: Dict[str, Any],
    ) -> OutlineAlternative:
        """创建单个演进选项"""
        alt = OutlineAlternative(
            project_id=project_id,
            chapter_number=chapter_number,
            batch_id=batch_id,
            option_index=option_index,
            title=data.get("title", ""),
            description=data.get("description"),
            new_outline=data.get("new_outline"),
            changes=data.get("changes"),
            evolution_type=data.get("evolution_type", "branch"),
            score=data.get("score"),
            status=EvolutionStatus.PENDING.value,
        )
        self.db.add(alt)
        await self.db.flush()
        return alt

    async def select_alternative(
        self,
        project_id: str,
        selected_option_id: int,
        user_id: int,
    ) -> Optional[ChapterOutline]:
        """选择某个演进选项，更新大纲"""
        selected_alt = await self.db.scalar(
            select(OutlineAlternative).where(
                OutlineAlternative.id == selected_option_id,
                OutlineAlternative.project_id == project_id,
            )
        )

        if not selected_alt:
            raise ValueError("选项不存在")

        batch_id = selected_alt.batch_id
        chapter_number = selected_alt.chapter_number or 0

        await self.db.execute(
            update(OutlineAlternative)
            .where(
                OutlineAlternative.batch_id == batch_id,
                OutlineAlternative.project_id == project_id,
            )
            .values(status=EvolutionStatus.REJECTED.value)
        )

        selected_alt.status = EvolutionStatus.SELECTED.value
        await self.db.flush()

        history = OutlineEvolutionHistory(
            project_id=project_id,
            batch_id=batch_id,
            selected_option_id=selected_option_id,
            chapter_number=chapter_number if chapter_number > 0 else None,
            user_id=user_id,
        )
        self.db.add(history)

        updated_outline = None
        new_outline_data = selected_alt.new_outline or {}

        if chapter_number == 0:
            project = await self.db.scalar(
                select(NovelProject)
                .options(selectinload(NovelProject.blueprint))
                .where(NovelProject.id == project_id)
            )
            if not project:
                raise ValueError("项目不存在")
            blueprint = project.blueprint
            if blueprint and "title" in new_outline_data:
                blueprint.title = new_outline_data["title"]
        else:
            outline = await self.db.scalar(
                select(ChapterOutline).where(
                    ChapterOutline.project_id == project_id,
                    ChapterOutline.chapter_number == chapter_number,
                )
            )

            if outline:
                history.previous_title = outline.title

                if "title" in new_outline_data:
                    outline.title = new_outline_data["title"]
                if "summary" in new_outline_data:
                    outline.summary = new_outline_data["summary"]

                history.new_title = outline.title
                updated_outline = outline
            else:
                outline = ChapterOutline(
                    project_id=project_id,
                    chapter_number=chapter_number,
                    title=new_outline_data.get("title", ""),
                    summary=new_outline_data.get("summary", ""),
                )
                self.db.add(outline)
                history.new_title = outline.title
                updated_outline = outline

        await self.db.commit()
        return updated_outline

    async def get_alternatives(
        self,
        project_id: str,
        chapter_number: Optional[int] = None,
        status: Optional[str] = None,
    ) -> List[OutlineAlternative]:
        """获取当前章节的所有可能走向"""
        stmt = select(OutlineAlternative).where(OutlineAlternative.project_id == project_id)

        if chapter_number is not None:
            stmt = stmt.where(OutlineAlternative.chapter_number == chapter_number)

        if status:
            stmt = stmt.where(OutlineAlternative.status == status)

        result = await self.db.execute(stmt.order_by(OutlineAlternative.created_at.desc()))
        return list(result.scalars().all())

    async def get_pending_alternatives(
        self,
        project_id: str,
        chapter_number: int,
    ) -> List[OutlineAlternative]:
        """获取某个章节的待选择演进选项"""
        result = await self.db.execute(
            select(OutlineAlternative)
            .where(
                OutlineAlternative.project_id == project_id,
                OutlineAlternative.chapter_number == chapter_number,
                OutlineAlternative.status == EvolutionStatus.PENDING.value,
            )
            .order_by(OutlineAlternative.option_index)
        )
        return list(result.scalars().all())

    async def get_latest_batch_alternatives(
        self,
        project_id: str,
        chapter_number: int,
    ) -> List[OutlineAlternative]:
        """获取最新的演进批次选项"""
        latest = await self.db.scalar(
            select(OutlineAlternative)
            .where(
                OutlineAlternative.project_id == project_id,
                OutlineAlternative.chapter_number == chapter_number,
            )
            .order_by(OutlineAlternative.created_at.desc())
        )

        if not latest:
            return []

        result = await self.db.execute(
            select(OutlineAlternative)
            .where(
                OutlineAlternative.project_id == project_id,
                OutlineAlternative.chapter_number == chapter_number,
                OutlineAlternative.batch_id == latest.batch_id,
            )
            .order_by(OutlineAlternative.option_index)
        )
        return list(result.scalars().all())

    async def clear_expired_alternatives(
        self,
        project_id: str,
        chapter_number: int,
        hours: int = 24,
    ) -> int:
        """清理过期的演进选项"""
        from datetime import datetime, timedelta

        cutoff = datetime.utcnow() - timedelta(hours=hours)

        result = await self.db.execute(
            update(OutlineAlternative)
            .where(
                OutlineAlternative.project_id == project_id,
                OutlineAlternative.chapter_number == chapter_number,
                OutlineAlternative.status == EvolutionStatus.PENDING.value,
                OutlineAlternative.created_at < cutoff,
            )
            .values(status=EvolutionStatus.EXPIRED.value)
        )

        await self.db.commit()
        return result.rowcount or 0

    def _parse_json_response(self, response: str) -> Any:
        """解析JSON响应"""
        import json

        content = sanitize_json_like_text(
            unwrap_markdown_json(remove_think_tags(response or ""))
        )

        candidates: list[str] = [content]

        json_array_start = content.find("[")
        json_array_end = content.rfind("]") + 1
        if json_array_start >= 0 and json_array_end > json_array_start:
            candidates.append(content[json_array_start:json_array_end])

        json_object_start = content.find("{")
        json_object_end = content.rfind("}") + 1
        if json_object_start >= 0 and json_object_end > json_object_start:
            candidates.append(content[json_object_start:json_object_end])

        last_error: json.JSONDecodeError | None = None
        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError as e:
                last_error = e
                continue

        if last_error:
            logger.error(f"JSON解析失败: {last_error}")
        return None

    async def get_evolution_history(
        self,
        project_id: str,
        chapter_number: Optional[int] = None,
        limit: int = 20,
    ) -> List[OutlineEvolutionHistory]:
        """获取演进历史"""
        stmt = select(OutlineEvolutionHistory).where(
            OutlineEvolutionHistory.project_id == project_id
        )

        if chapter_number is not None:
            stmt = stmt.where(OutlineEvolutionHistory.chapter_number == chapter_number)

        result = await self.db.execute(
            stmt.order_by(OutlineEvolutionHistory.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

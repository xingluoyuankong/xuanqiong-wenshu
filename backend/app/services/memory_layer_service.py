"""
记忆层服务

提供角色状态追踪、时间线管理、因果链维护的核心功能。
"""
from typing import Optional, List, Dict, Any
import json
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc, func

from ..models.memory_layer import (
    CharacterState,
    TimelineEvent,
    CausalChain,
    StoryTimeTracker
)
from ..models.novel import BlueprintCharacter
from .llm_service import LLMService
from .prompt_service import PromptService
from .generation_call_service import GenerationCallPolicy, call_generation_json, call_generation_text
from ..utils.json_utils import remove_think_tags, sanitize_json_like_text, unwrap_markdown_json

logger = logging.getLogger(__name__)


CAUSAL_CHAIN_EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["causal_chains"],
    "properties": {
        "causal_chains": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["cause_description", "effect_description"],
                "properties": {
                    "cause_description": {"type": "string"},
                    "cause_chapter": {"type": "integer"},
                    "effect_description": {"type": "string"},
                    "effect_chapter": {"type": ["integer", "null"]},
                    "cause_type": {"type": "string"},
                    "effect_type": {"type": "string"},
                    "involved_characters": {"type": "array", "items": {"type": "string"}},
                    "importance": {"type": "integer"},
                    "status": {"type": "string"},
                    "resolution_description": {"type": ["string", "null"]},
                },
            },
        }
    },
}


class MemoryLayerService:
    """记忆层服务"""

    def __init__(self, db: AsyncSession, llm_service: LLMService, prompt_service: PromptService):
        self.db = db
        self.llm_service = llm_service
        self.prompt_service = prompt_service

    # ===== 角色状态管理 =====

    async def get_character_state(
        self, 
        project_id: str, 
        character_name: str, 
        chapter_number: Optional[int] = None
    ) -> Optional[CharacterState]:
        """获取角色在指定章节的状态（默认最新）"""
        query = select(CharacterState).where(
            and_(
                CharacterState.project_id == project_id,
                CharacterState.character_name == character_name
            )
        )
        
        if chapter_number:
            query = query.where(CharacterState.chapter_number <= chapter_number)
        
        query = query.order_by(desc(CharacterState.chapter_number)).limit(1)
        
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_all_character_states(
        self, 
        project_id: str, 
        chapter_number: int
    ) -> List[CharacterState]:
        """获取所有角色在指定章节的最新状态"""
        # 使用子查询获取每个角色的最新状态
        subquery = (
            select(
                CharacterState.character_name,
                func.max(CharacterState.chapter_number).label("max_chapter")
            )
            .where(
                and_(
                    CharacterState.project_id == project_id,
                    CharacterState.chapter_number <= chapter_number
                )
            )
            .group_by(CharacterState.character_name)
            .subquery()
        )
        
        query = (
            select(CharacterState)
            .join(
                subquery,
                and_(
                    CharacterState.character_name == subquery.c.character_name,
                    CharacterState.chapter_number == subquery.c.max_chapter
                )
            )
            .where(CharacterState.project_id == project_id)
        )
        
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_character_state(
        self,
        project_id: str,
        character_name: str,
        chapter_number: int,
        state_updates: Dict[str, Any],
        character_id: Optional[int] = None,
        *,
        auto_commit: bool = True,
    ) -> CharacterState:
        """更新角色状态（创建新的状态快照）"""
        # 获取上一章的状态作为基础
        prev_state = await self.get_character_state(project_id, character_name, chapter_number - 1)
        resolved_character_id = character_id or (prev_state.character_id if prev_state else None)
        if resolved_character_id is None:
            blueprint_character = await self._resolve_or_create_blueprint_character(
                project_id=project_id,
                character_name=character_name,
                state_updates=state_updates,
                first_appearance_chapter=chapter_number,
            )
            resolved_character_id = blueprint_character.id

        # 创建新状态
        new_state = CharacterState(
            project_id=project_id,
            character_id=resolved_character_id,
            character_name=character_name,
            chapter_number=chapter_number,
            # 继承上一章的状态
            location=prev_state.location if prev_state else None,
            emotion=prev_state.emotion if prev_state else None,
            emotion_intensity=prev_state.emotion_intensity if prev_state else None,
            health_status=prev_state.health_status if prev_state else "healthy",
            inventory=prev_state.inventory if prev_state else [],
            power_level=prev_state.power_level if prev_state else None,
            known_secrets=prev_state.known_secrets if prev_state else [],
            current_goals=prev_state.current_goals if prev_state else [],
        )
        
        # 应用更新
        for key, value in state_updates.items():
            if hasattr(new_state, key):
                setattr(new_state, key, value)
        
        self.db.add(new_state)
        if auto_commit:
            await self.db.commit()
            await self.db.refresh(new_state)
        else:
            await self.db.flush()
        return new_state

    async def _resolve_or_create_blueprint_character(
        self,
        *,
        project_id: str,
        character_name: str,
        state_updates: Optional[Dict[str, Any]] = None,
        first_appearance_chapter: Optional[int] = None,
    ) -> BlueprintCharacter:
        normalized_name = (character_name or "").strip()
        if not normalized_name:
            raise ValueError("角色名不能为空")

        existing = await self.db.execute(
            select(BlueprintCharacter).where(
                and_(
                    BlueprintCharacter.project_id == project_id,
                    BlueprintCharacter.name == normalized_name,
                )
            )
        )
        blueprint_character = existing.scalar_one_or_none()
        if blueprint_character:
            return blueprint_character

        position_result = await self.db.execute(
            select(func.max(BlueprintCharacter.position)).where(BlueprintCharacter.project_id == project_id)
        )
        next_position = int(position_result.scalar() or 0) + 1
        updates = state_updates or {}
        inferred_emotion = str(updates.get("emotion") or "").strip()
        inferred_goal = updates.get("current_goals") or updates.get("goal_progress") or []
        if isinstance(inferred_goal, list):
            inferred_goal_text = "；".join(
                item.get("goal") if isinstance(item, dict) else str(item)
                for item in inferred_goal
                if item
            )
        else:
            inferred_goal_text = str(inferred_goal).strip()

        blueprint_character = BlueprintCharacter(
            project_id=project_id,
            name=normalized_name,
            identity="动态角色",
            personality=f"自动追踪角色，最近情绪：{inferred_emotion or '待识别'}",
            goals=inferred_goal_text or None,
            relationship_to_protagonist="待追踪",
            position=next_position,
            extra={
                "auto_created_from_memory": True,
                "first_appearance_chapter": first_appearance_chapter,
                "dynamic_role_policy": "正文首次识别后自动入池；后续必须继续同步角色状态、关系、势力或知识图谱节点。",
                "knowledge_boundary": "由写后记忆抽取继续补充，不能默认全知。",
            },
        )
        self.db.add(blueprint_character)
        await self.db.flush()
        return blueprint_character

    async def extract_character_states_from_chapter(
        self,
        project_id: str,
        chapter_number: int,
        chapter_content: str,
        character_names: List[str],
        user_id: int
    ) -> List[Dict[str, Any]]:
        """从章节内容中提取角色状态变化"""
        prompt = f"""分析以下章节内容，提取每个角色的状态变化。

[章节内容]
{chapter_content[:8000]}

[已登记角色（不是上限，正文出现的新角色也要识别）]
{json.dumps(character_names, ensure_ascii=False)}

请以 JSON 格式输出每个角色的状态变化：
```json
{{
  "character_states": [
    {{
      "character_name": "角色名",
      "location": "当前位置",
      "emotion": "主要情绪",
      "emotion_intensity": 1-10,
      "emotion_reason": "情绪原因",
      "health_status": "healthy/injured/critical",
      "injuries": ["受伤描述"],
      "inventory_changes": {{"gained": ["获得物品"], "lost": ["失去物品"]}},
      "relationship_changes": [{{"target": "对象", "change": "变化描述"}}],
      "new_knowledge": ["新获得的信息"],
      "goal_progress": [{{"goal": "目标", "progress": "进展"}}]
    }}
  ]
}}
```

只输出在本章中有变化、出场或首次登场的角色。若发现未在名单中的新角色，请正常输出其状态，系统会把它补入角色池。"""

        try:
            result = await call_generation_json(
                llm_service=self.llm_service,
                system_prompt="你是一个专业的小说分析助手，负责追踪角色状态变化。请严格按照 JSON 格式输出。",
                conversation_history=[{"role": "user", "content": prompt}],
                temperature=0.2,
                user_id=user_id,
                timeout=120.0,
                policy=GenerationCallPolicy(
                    stage_label="记忆回写-角色状态抽取",
                    progress_stage="memory_extract_character_states",
                    retry_attempts=2,
                    json_repair_attempts=1,
                ),
            )
            return result.data.get("character_states", [])
        except Exception as e:
            logger.warning(f"提取角色状态失败: {e}")
        
        return []

    # ===== 时间线管理 =====

    async def get_timeline(
        self, 
        project_id: str, 
        start_chapter: Optional[int] = None,
        end_chapter: Optional[int] = None
    ) -> List[TimelineEvent]:
        """获取时间线事件"""
        query = select(TimelineEvent).where(TimelineEvent.project_id == project_id)
        
        if start_chapter:
            query = query.where(TimelineEvent.chapter_number >= start_chapter)
        if end_chapter:
            query = query.where(TimelineEvent.chapter_number <= end_chapter)
        
        query = query.order_by(TimelineEvent.chapter_number, TimelineEvent.id)
        
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def add_timeline_event(
        self,
        project_id: str,
        chapter_number: int,
        event_title: str,
        event_description: str,
        event_type: str = "minor",
        story_time: Optional[str] = None,
        involved_characters: Optional[List[str]] = None,
        location: Optional[str] = None,
        importance: int = 5,
        is_turning_point: bool = False,
        *,
        auto_commit: bool = True,
    ) -> TimelineEvent:
        """添加时间线事件"""
        event = TimelineEvent(
            project_id=project_id,
            chapter_number=chapter_number,
            event_title=event_title,
            event_description=event_description,
            event_type=event_type,
            story_time=story_time,
            involved_characters=involved_characters,
            location=location,
            importance=importance,
            is_turning_point=is_turning_point
        )
        self.db.add(event)
        if auto_commit:
            await self.db.commit()
            await self.db.refresh(event)
        else:
            await self.db.flush()
        return event

    async def extract_timeline_events_from_chapter(
        self,
        project_id: str,
        chapter_number: int,
        chapter_content: str,
        user_id: int
    ) -> List[Dict[str, Any]]:
        """从章节内容中提取时间线事件"""
        prompt = f"""分析以下章节内容，提取关键事件。

[章节内容]
{chapter_content[:8000]}

请以 JSON 格式输出关键事件：
```json
{{
  "events": [
    {{
      "event_title": "事件标题（简短）",
      "event_description": "事件描述",
      "event_type": "major/minor/background",
      "story_time": "故事内时间（如'第三天早上'）",
      "involved_characters": ["涉及角色"],
      "location": "发生地点",
      "importance": 1-10,
      "is_turning_point": true/false
    }}
  ]
}}
```

只提取重要事件，不要列出琐碎细节。"""

        try:
            result = await call_generation_json(
                llm_service=self.llm_service,
                system_prompt="你是一个专业的小说分析助手，负责提取关键事件。请严格按照 JSON 格式输出。",
                conversation_history=[{"role": "user", "content": prompt}],
                temperature=0.2,
                user_id=user_id,
                timeout=120.0,
                policy=GenerationCallPolicy(
                    stage_label="记忆回写-时间线抽取",
                    progress_stage="memory_extract_timeline",
                    retry_attempts=2,
                    json_repair_attempts=1,
                ),
            )
            return result.data.get("events", [])
        except Exception as e:
            logger.warning(f"提取时间线事件失败: {e}")
        
        return []

    # ===== 因果链管理 =====

    async def get_pending_causal_chains(self, project_id: str) -> List[CausalChain]:
        """获取待解决的因果链"""
        result = await self.db.execute(
            select(CausalChain).where(
                and_(
                    CausalChain.project_id == project_id,
                    CausalChain.status == "pending"
                )
            ).order_by(CausalChain.cause_chapter)
        )
        return list(result.scalars().all())

    async def add_causal_chain(
        self,
        project_id: str,
        cause_description: str,
        cause_chapter: int,
        effect_description: str,
        cause_type: str = "event",
        effect_type: str = "event",
        involved_characters: Optional[List[str]] = None,
        importance: int = 5,
        effect_chapter: Optional[int] = None,
        status: Optional[str] = None,
        resolution_description: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
        *,
        auto_commit: bool = True,
    ) -> CausalChain:
        """添加因果链"""
        normalized_status = (status or ("resolved" if effect_chapter else "pending")).strip().lower()
        if normalized_status not in {"pending", "resolved", "abandoned"}:
            normalized_status = "pending"
        chain = CausalChain(
            project_id=project_id,
            cause_type=cause_type,
            cause_description=cause_description,
            cause_chapter=cause_chapter,
            effect_type=effect_type,
            effect_description=effect_description,
            effect_chapter=effect_chapter,
            involved_characters=involved_characters,
            importance=importance,
            status=normalized_status,
            resolution_description=resolution_description,
            extra=extra,
        )
        self.db.add(chain)
        if auto_commit:
            await self.db.commit()
            await self.db.refresh(chain)
        else:
            await self.db.flush()
        return chain

    @staticmethod
    def _coerce_int(
        value: Any,
        default: Optional[int] = None,
        *,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None,
    ) -> Optional[int]:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        if min_value is not None:
            parsed = max(min_value, parsed)
        if max_value is not None:
            parsed = min(max_value, parsed)
        return parsed

    @staticmethod
    def _clean_chain_text(value: Any, *, limit: int = 360) -> str:
        text = " ".join(str(value or "").split())
        return text[:limit].strip()

    def _normalize_causal_chain_payload(
        self,
        raw: Dict[str, Any],
        *,
        chapter_number: int,
    ) -> Optional[Dict[str, Any]]:
        cause = self._clean_chain_text(raw.get("cause_description"))
        effect = self._clean_chain_text(raw.get("effect_description"))
        if len(cause) < 6 or len(effect) < 6:
            return None

        cause_chapter = self._coerce_int(
            raw.get("cause_chapter"),
            chapter_number,
            min_value=1,
            max_value=max(1, chapter_number),
        )
        effect_chapter = self._coerce_int(
            raw.get("effect_chapter"),
            None,
            min_value=1,
        )
        importance = self._coerce_int(raw.get("importance"), 5, min_value=1, max_value=10) or 5

        involved_characters: List[str] = []
        for item in raw.get("involved_characters") or []:
            name = self._clean_chain_text(item, limit=80)
            if name and name not in involved_characters:
                involved_characters.append(name)
            if len(involved_characters) >= 8:
                break

        status = str(raw.get("status") or "").strip().lower()
        if status not in {"pending", "resolved", "abandoned"}:
            status = "resolved" if effect_chapter and effect_chapter <= chapter_number else "pending"

        return {
            "cause_description": cause,
            "cause_chapter": cause_chapter or chapter_number,
            "effect_description": effect,
            "effect_chapter": effect_chapter,
            "cause_type": self._clean_chain_text(raw.get("cause_type") or "event", limit=64) or "event",
            "effect_type": self._clean_chain_text(raw.get("effect_type") or "event", limit=64) or "event",
            "involved_characters": involved_characters,
            "importance": importance,
            "status": status,
            "resolution_description": self._clean_chain_text(raw.get("resolution_description"), limit=360) or None,
            "extra": {"source": "memory_layer_extraction", "chapter_number": chapter_number},
        }

    async def _causal_chain_exists(
        self,
        *,
        project_id: str,
        cause_chapter: int,
        cause_description: str,
        effect_description: str,
    ) -> bool:
        query = (
            select(CausalChain.id)
            .where(
                and_(
                    CausalChain.project_id == project_id,
                    CausalChain.cause_chapter == cause_chapter,
                    CausalChain.cause_description == cause_description,
                    CausalChain.effect_description == effect_description,
                )
            )
            .limit(1)
        )
        return bool(await self.db.scalar(query))

    async def extract_causal_chains_from_chapter(
        self,
        project_id: str,
        chapter_number: int,
        chapter_content: str,
        user_id: int,
    ) -> List[Dict[str, Any]]:
        """Extract cause/effect ledger updates from finalized chapter text."""
        pending_digest: List[Dict[str, Any]] = []
        try:
            pending = await self.get_pending_causal_chains(project_id)
            for chain in pending[:10]:
                pending_digest.append(
                    {
                        "cause_chapter": chain.cause_chapter,
                        "cause": self._clean_chain_text(chain.cause_description, limit=180),
                        "expected_effect": self._clean_chain_text(chain.effect_description, limit=180),
                        "characters": chain.involved_characters or [],
                    }
                )
        except Exception as exc:  # pragma: no cover - defensive fallback for lightweight tests/adapters.
            logger.debug("Skip pending causal chain digest during extraction: %s", exc)

        prompt = f"""请从已定稿章节中抽取“会影响后续章节连续性”的因果链。

要求：
1. 只记录会跨段落、跨章节或影响角色/伏笔/冲突走向的因果，不记录普通动作流水账。
2. 如果本章兑现了之前的待处理因果，请把 status 设为 resolved，并写 effect_chapter。
3. 如果本章制造了后续压力、误会、债务、秘密、关系变化或任务，请把 status 设为 pending。
4. 每条因果必须能帮助下一章生成时避免断裂：原因清楚、后果清楚、相关角色清楚。
5. 最多输出 6 条，宁缺毋滥。

[当前章节]
第 {chapter_number} 章

[正文]
{chapter_content[:9000]}

[已有待处理因果链]
{json.dumps(pending_digest, ensure_ascii=False)}

请只输出 JSON：
{{
  "causal_chains": [
    {{
      "cause_description": "导致后续变化的动作/决定/发现",
      "cause_chapter": {chapter_number},
      "effect_description": "已经发生或后续必须承接的结果",
      "effect_chapter": null,
      "cause_type": "event/action/decision/discovery",
      "effect_type": "event/state_change/relationship_change/plot_pressure",
      "involved_characters": ["角色名"],
      "importance": 1-10,
      "status": "pending/resolved",
      "resolution_description": null
    }}
  ]
}}"""

        try:
            result = await call_generation_json(
                llm_service=self.llm_service,
                system_prompt="你是长篇小说连续性审校，负责把定稿章节转成可追踪的因果账本。只输出 JSON。",
                conversation_history=[{"role": "user", "content": prompt}],
                temperature=0.2,
                user_id=user_id,
                timeout=120.0,
                policy=GenerationCallPolicy(
                    stage_label="记忆回写-因果链抽取",
                    progress_stage="memory_extract_causal_chains",
                    retry_attempts=2,
                    json_repair_attempts=1,
                    json_schema=CAUSAL_CHAIN_EXTRACTION_SCHEMA,
                    json_schema_name="causal_chain_extraction",
                    max_tokens=1800,
                ),
            )
            chains = result.data.get("causal_chains", [])
            if not isinstance(chains, list):
                return []
            normalized: List[Dict[str, Any]] = []
            for raw in chains[:8]:
                if not isinstance(raw, dict):
                    continue
                item = self._normalize_causal_chain_payload(raw, chapter_number=chapter_number)
                if item:
                    normalized.append(item)
            return normalized[:6]
        except Exception as e:
            logger.warning("提取因果链失败: %s", e)

        return []

    async def resolve_causal_chain(
        self,
        chain_id: int,
        effect_chapter: int,
        resolution_description: str
    ) -> Optional[CausalChain]:
        """解决因果链"""
        result = await self.db.execute(
            select(CausalChain).where(CausalChain.id == chain_id)
        )
        chain = result.scalar_one_or_none()
        
        if chain:
            chain.status = "resolved"
            chain.effect_chapter = effect_chapter
            chain.resolution_description = resolution_description
            await self.db.commit()
            await self.db.refresh(chain)
        
        return chain

    # ===== 故事时间追踪 =====

    async def get_or_create_time_tracker(self, project_id: str) -> StoryTimeTracker:
        """获取或创建故事时间追踪器"""
        result = await self.db.execute(
            select(StoryTimeTracker).where(StoryTimeTracker.project_id == project_id)
        )
        tracker = result.scalar_one_or_none()
        
        if not tracker:
            # 兼容 SQLite 上 BigInteger 主键不自增的历史表结构，手动分配 id
            next_id_result = await self.db.execute(select(func.max(StoryTimeTracker.id)))
            next_id = (next_id_result.scalar() or 0) + 1
            tracker = StoryTimeTracker(
                id=next_id,
                project_id=project_id,
                chapter_time_map={}
            )
            self.db.add(tracker)
            await self.db.commit()
            await self.db.refresh(tracker)
        
        return tracker

    async def update_chapter_time(
        self,
        project_id: str,
        chapter_number: int,
        start_time: str,
        end_time: str,
        duration: str
    ) -> StoryTimeTracker:
        """更新章节时间"""
        tracker = await self.get_or_create_time_tracker(project_id)
        
        chapter_time_map = tracker.chapter_time_map or {}
        chapter_time_map[str(chapter_number)] = {
            "start_time": start_time,
            "end_time": end_time,
            "duration": duration
        }
        tracker.chapter_time_map = chapter_time_map
        tracker.current_time = end_time
        
        await self.db.commit()
        await self.db.refresh(tracker)
        return tracker

    # ===== 综合上下文生成 =====

    async def get_memory_context(
        self,
        project_id: str,
        chapter_number: int,
        involved_characters: Optional[List[str]] = None
    ) -> str:
        """生成记忆层上下文（用于注入到写作提示词）"""
        lines = ["# 记忆层上下文\n"]
        
        # 1. 角色状态
        character_states = await self.get_all_character_states(project_id, chapter_number - 1)
        if character_states:
            lines.append("## 角色当前状态\n")
            for state in character_states:
                if involved_characters and state.character_name not in involved_characters:
                    continue
                lines.append(f"### {state.character_name}")
                if state.location:
                    lines.append(f"- 位置：{state.location}")
                if state.emotion:
                    lines.append(f"- 情绪：{state.emotion}（强度 {state.emotion_intensity}/10）")
                if state.health_status and state.health_status != "healthy":
                    lines.append(f"- 健康：{state.health_status}")
                if state.current_goals:
                    lines.append(f"- 当前目标：{', '.join(state.current_goals[:3])}")
                lines.append("")
        
        # 2. 最近事件
        recent_events = await self.get_timeline(
            project_id, 
            start_chapter=max(1, chapter_number - 5),
            end_chapter=chapter_number - 1
        )
        if recent_events:
            lines.append("## 最近事件\n")
            for event in recent_events[-10:]:  # 最多显示 10 个
                lines.append(f"- 第{event.chapter_number}章：{event.event_title}")
                if event.is_turning_point:
                    lines.append("  （转折点）")
            lines.append("")
        
        # 3. 待解决的因果链
        pending_chains = await self.get_pending_causal_chains(project_id)
        if pending_chains:
            lines.append("## 待解决的因果链\n")
            for chain in pending_chains[:5]:  # 最多显示 5 个
                lines.append(f"- 【第{chain.cause_chapter}章】{chain.cause_description}")
                lines.append(f"  → 预期效果：{chain.effect_description}")
            lines.append("")
        
        # 4. 故事时间
        tracker = await self.get_or_create_time_tracker(project_id)
        if tracker.current_time:
            lines.append("## 故事时间\n")
            lines.append(f"- 当前时间：{tracker.current_time}")
            if tracker.current_date:
                lines.append(f"- 当前日期：{tracker.current_date}")
            lines.append("")
        
        return "\n".join(lines) if len(lines) > 1 else "（无记忆层上下文）"

    async def update_memory_after_chapter(
        self,
        project_id: str,
        chapter_number: int,
        chapter_content: str,
        character_names: List[str],
        user_id: int
    ) -> Dict[str, Any]:
        """章节完成后更新记忆层"""
        with LLMService.daily_limit_scope(f"memory_update:{project_id}:{chapter_number}:{user_id}"):
            results = {
                "character_states_updated": 0,
                "timeline_events_added": 0,
                "causal_chains_added": 0,
                "dynamic_characters_created": 0,
                "dynamic_character_names": [],
            }
            known_character_names = {str(name or "").strip() for name in (character_names or []) if str(name or "").strip()}
            try:
                existing_result = await self.db.execute(
                    select(BlueprintCharacter.name).where(BlueprintCharacter.project_id == project_id)
                )
                known_character_names.update(
                    str(name or "").strip()
                    for name in existing_result.scalars().all()
                    if str(name or "").strip()
                )
            except Exception:
                # Some tests use a commit-only fake DB; the caller-provided cast list is enough there.
                pass

            # 1. 提取并更新角色状态
            character_states = await self.extract_character_states_from_chapter(
                project_id, chapter_number, chapter_content, character_names, user_id
            )
            for state_data in character_states:
                char_name = state_data.pop("character_name", None)
                if char_name:
                    normalized_name = str(char_name).strip()
                    is_dynamic_new = bool(normalized_name and normalized_name not in known_character_names)
                    await self.update_character_state(
                        project_id, normalized_name or char_name, chapter_number, state_data, auto_commit=False
                    )
                    results["character_states_updated"] += 1
                    if is_dynamic_new:
                        known_character_names.add(normalized_name)
                        results["dynamic_characters_created"] += 1
                        results["dynamic_character_names"].append(normalized_name)

            # 2. 提取并添加时间线事件
            events = await self.extract_timeline_events_from_chapter(
                project_id, chapter_number, chapter_content, user_id
            )
            for event_data in events:
                await self.add_timeline_event(
                    project_id=project_id,
                    chapter_number=chapter_number,
                    auto_commit=False,
                    **event_data
                )
                results["timeline_events_added"] += 1

            # 3. Extract causal chains that future chapters must carry forward.
            causal_chains = await self.extract_causal_chains_from_chapter(
                project_id, chapter_number, chapter_content, user_id
            )
            for chain_data in causal_chains:
                exists = await self._causal_chain_exists(
                    project_id=project_id,
                    cause_chapter=chain_data["cause_chapter"],
                    cause_description=chain_data["cause_description"],
                    effect_description=chain_data["effect_description"],
                )
                if exists:
                    continue
                await self.add_causal_chain(
                    project_id=project_id,
                    auto_commit=False,
                    **chain_data,
                )
                results["causal_chains_added"] += 1

            await self.db.commit()

            logger.info(
                f"项目 {project_id} 第 {chapter_number} 章记忆层更新完成: "
                f"角色状态 {results['character_states_updated']}, "
                f"时间线事件 {results['timeline_events_added']}"
            )

            logger.info(
                "Memory ledger causal chains updated: project=%s chapter=%s causal_chains=%s",
                project_id,
                chapter_number,
                results["causal_chains_added"],
            )

            return results

    async def check_consistency(
        self,
        project_id: str,
        chapter_number: int,
        chapter_content: str,
        user_id: int
    ) -> Dict[str, Any]:
        """检查章节与记忆层的一致性"""
        issues = []
        
        # 获取记忆层上下文
        memory_context = await self.get_memory_context(project_id, chapter_number)
        
        prompt = f"""检查以下章节内容与记忆层上下文的一致性。

[记忆层上下文]
{memory_context}

[章节内容]
{chapter_content[:6000]}

请检查以下方面的一致性：
1. 角色位置是否合理（不能瞬移）
2. 角色情绪是否连贯
3. 角色持有物品是否正确
4. 时间流逝是否合理
5. 事件因果是否自洽

以 JSON 格式输出检查结果：
```json
{{
  "consistent": true/false,
  "issues": [
    {{
      "type": "location/emotion/inventory/time/causality",
      "severity": "critical/warning/minor",
      "description": "问题描述",
      "suggestion": "修复建议"
    }}
  ]
}}
```"""

        try:
            result = await call_generation_json(
                llm_service=self.llm_service,
                system_prompt="你是一个专业的小说一致性检查助手。请严格按照 JSON 格式输出。",
                conversation_history=[{"role": "user", "content": prompt}],
                temperature=0.2,
                user_id=user_id,
                timeout=120.0,
                policy=GenerationCallPolicy(
                    stage_label="记忆层-连续性检查",
                    progress_stage="memory_continuity_check",
                    retry_attempts=2,
                    json_repair_attempts=1,
                ),
            )
            return result.data
        except Exception as e:
            logger.warning(f"一致性检查失败: {e}")

        return {"consistent": True, "issues": []}

    # ========== CoLong 动态记忆回写机制 ==========

    async def incremental_memory_update(
        self,
        project_id: str,
        chapter_number: int,
        new_global_summary: Optional[str] = None,
        new_plot_arcs: Optional[Dict[str, Any]] = None,
        new_timeline_events: Optional[List[Dict[str, Any]]] = None,
        character_states: Optional[Dict[str, Any]] = None,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        增量更新记忆 - 追加而非全量替换（CoLong 核心机制）

        核心思想：
        1. 保留已有记忆的基础
        2. 追加本章新产生的内容
        3. 自动递增版本号
        4. 创建快照以支持回溯
        """
        from datetime import datetime
        from ..models.project_memory import ProjectMemory, ChapterSnapshot

        # 1. 获取当前记忆
        result = await self.db.execute(
            select(ProjectMemory).where(ProjectMemory.project_id == project_id)
        )
        memory = result.scalar_one_or_none()

        if not memory:
            memory = ProjectMemory(project_id=project_id, version=0)
            self.db.add(memory)
            await self.db.flush()

        # 记录更新前的版本
        prev_version = memory.version or 0
        new_version = prev_version + 1

        # 2. 创建本章快照（用于回溯）
        snapshot = ChapterSnapshot(
            project_id=project_id,
            chapter_number=chapter_number,
            global_summary_snapshot=memory.global_summary,
            plot_arcs_snapshot=memory.plot_arcs,
            chapter_summary=new_global_summary,
            created_at=datetime.utcnow()
        )
        self.db.add(snapshot)

        # 3. 增量更新摘要（追加而非替换）
        if new_global_summary:
            if memory.global_summary:
                # 限制总长度，超过则压缩
                MAX_SUMMARY_LENGTH = 5000
                old_summary = memory.global_summary
                combined = f"{old_summary}\n\n--- 第{chapter_number}章 ---\n\n{new_global_summary}"
                if len(combined) > MAX_SUMMARY_LENGTH:
                    combined = await self._compress_summary(combined, user_id=user_id)
                memory.global_summary = combined
            else:
                memory.global_summary = new_global_summary

        # 4. 增量更新剧情线
        if new_plot_arcs:
            current_arcs = memory.plot_arcs or {}

            # 追加 unresolved_hooks
            if "unresolved_hooks" in new_plot_arcs:
                current_hooks = current_arcs.get("unresolved_hooks", [])
                current_hooks.extend(new_plot_arcs["unresolved_hooks"])
                current_arcs["unresolved_hooks"] = current_hooks

            # 追加 main_conflicts
            if "main_conflicts" in new_plot_arcs:
                current_conflicts = current_arcs.get("main_conflicts", [])
                current_conflicts.extend(new_plot_arcs["main_conflicts"])
                current_arcs["main_conflicts"] = current_conflicts

            # 更新 character_arcs
            if "character_arcs" in new_plot_arcs:
                current_arcs["character_arcs"] = new_plot_arcs["character_arcs"]

            memory.plot_arcs = current_arcs

        # 5. 添加时间线事件
        if new_timeline_events:
            for event_data in new_timeline_events:
                await self.add_timeline_event(
                    project_id=project_id,
                    chapter_number=chapter_number,
                    auto_commit=False,
                    **event_data
                )

        # 6. 更新角色状态
        if character_states:
            for char_name, state_data in character_states.items():
                char_id = state_data.get("character_id")
                await self.update_character_state(
                    project_id=project_id,
                    character_name=char_name,
                    chapter_number=chapter_number,
                    state_updates=state_data,
                    character_id=char_id,
                    auto_commit=False,
                )

        # 7. 更新元数据
        memory.last_updated_chapter = chapter_number
        memory.version = new_version
        memory.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(memory)

        return {
            "success": True,
            "prev_version": prev_version,
            "new_version": new_version,
            "chapter_number": chapter_number,
        }

    async def _compress_summary(
        self,
        summary: str,
        max_length: int = 3000,
        user_id: Optional[int] = None,
    ) -> str:
        """压缩摘要 - 使用 LLM 生成简洁版"""
        if len(summary) <= max_length:
            return summary

        prompt = f"""请将以下小说摘要压缩到 {max_length} 字以内，保留关键信息：

{summary[:8000]}

压缩后的摘要："""

        try:
            result = await call_generation_text(
                llm_service=self.llm_service,
                system_prompt="你是长篇小说记忆层摘要压缩助手，请保留事实、因果、伏笔和角色状态。",
                conversation_history=[{"role": "user", "content": prompt}],
                user_id=user_id or 0,
                temperature=0.3,
                timeout=90.0,
                policy=GenerationCallPolicy(
                    stage_label="记忆层-摘要压缩",
                    progress_stage="memory_compress_summary",
                    retry_attempts=2,
                    response_format=None,
                    max_tokens=1000,
                ),
            )
            cleaned = remove_think_tags(result.text) if result.text else ""
            return cleaned.strip() if cleaned else summary[:max_length]
        except Exception as e:
            logger.warning(f"摘要压缩失败: {e}")
            return summary[:max_length] + "..."

    async def get_memory_snapshots(
        self,
        project_id: str,
        chapter_number: Optional[int] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """获取记忆快照历史"""
        from ..models.project_memory import ProjectMemory, ChapterSnapshot

        query = select(ChapterSnapshot).where(
            ChapterSnapshot.project_id == project_id
        )

        if chapter_number:
            query = query.where(ChapterSnapshot.chapter_number <= chapter_number)

        query = query.order_by(ChapterSnapshot.created_at.desc(), ChapterSnapshot.id.desc()).limit(limit)

        result = await self.db.execute(query)
        snapshots = result.scalars().all()

        return [
            {
                "id": s.id,
                "chapter_number": s.chapter_number,
                "summary": s.chapter_summary,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in snapshots
        ]

    async def compress_memory(
        self,
        project_id: str,
        preserve_chapters: int = 5,
        user_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """压缩记忆 - 合并旧版本以节省空间"""
        with LLMService.daily_limit_scope(f"memory_compress:{project_id}:{preserve_chapters}:{user_id or 0}"):
            from ..models.project_memory import ProjectMemory, ChapterSnapshot

            # 1. 获取所有快照
            result = await self.db.execute(
                select(ChapterSnapshot).where(
                    ChapterSnapshot.project_id == project_id
                ).order_by(ChapterSnapshot.created_at.desc(), ChapterSnapshot.id.desc())
            )
            all_snapshots = result.scalars().all()

            if len(all_snapshots) <= preserve_chapters:
                return {"compressed": False, "reason": "snapshots_count <= preserve_chapters"}

            # 2. 保留最近的快照
            keep_snapshots = all_snapshots[:preserve_chapters]
            compress_snapshots = all_snapshots[preserve_chapters:]

            # 3. 合并旧快照为压缩摘要
            old_summaries = [s.global_summary_snapshot for s in compress_snapshots if s.global_summary_snapshot]
            if old_summaries:
                compressed_summary = await self._compress_summary(
                    "\n\n".join(old_summaries),
                    max_length=2000,
                    user_id=user_id,
                )
            else:
                compressed_summary = None

            # 4. 获取当前 memory 并更新
            mem_result = await self.db.execute(
                select(ProjectMemory).where(ProjectMemory.project_id == project_id)
            )
            memory = mem_result.scalar_one_or_none()

            if memory:
                if compressed_summary:
                    old_summary = memory.global_summary or ""
                    memory.global_summary = f"[早期摘要]\n{compressed_summary}\n\n---\n\n{old_summary}"
                memory.version = (memory.version or 0) + 1

            await self.db.commit()

            return {
                "compressed": True,
                "preserved_count": len(keep_snapshots),
                "compressed_count": len(compress_snapshots),
                "new_version": memory.version if memory else 0,
            }

    async def rollback_to_version(
        self,
        project_id: str,
        target_version: int,
    ) -> Dict[str, Any]:
        """回滚记忆到指定版本"""
        from ..models.project_memory import ProjectMemory, ChapterSnapshot

        # 1. 获取目标版本对应的快照
        result = await self.db.execute(
            select(ChapterSnapshot).where(
                ChapterSnapshot.project_id == project_id
            ).order_by(ChapterSnapshot.created_at.desc(), ChapterSnapshot.id.desc())
        )
        snapshots = result.scalars().all()

        if target_version > len(snapshots) or target_version < 1:
            raise ValueError(f"无效的目标版本: {target_version}, 最大版本: {len(snapshots)}")

        target_snapshot = snapshots[target_version - 1]

        # 2. 获取当前 memory 并恢复
        mem_result = await self.db.execute(
            select(ProjectMemory).where(ProjectMemory.project_id == project_id)
        )
        memory = mem_result.scalar_one_or_none()

        from datetime import datetime

        if memory:
            memory.global_summary = target_snapshot.global_summary_snapshot
            memory.plot_arcs = target_snapshot.plot_arcs_snapshot
            memory.last_updated_chapter = target_snapshot.chapter_number
            memory.version = target_version
            memory.updated_at = datetime.utcnow()

            await self.db.commit()
            await self.db.refresh(memory)

        return {
            "success": True,
            "rolled_back_to_version": target_version,
            "chapter_number": target_snapshot.chapter_number,
        }

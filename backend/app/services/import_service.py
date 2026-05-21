# AIMETA P=导入服务_小说导入业务逻辑|R=小说导入_格式转换|NR=不含内容生成|E=ImportService|X=internal|A=服务类|D=sqlalchemy|S=db,fs|RD=./README.ai
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import BlueprintCharacter, Chapter, ChapterSnapshot, CharacterState, Foreshadowing, ProjectMemory, TimelineEvent
from ..schemas.novel import Blueprint
from ..services.generation_call_service import GenerationCallPolicy, call_generation_json, call_generation_text, parse_llm_json_value
from ..services.knowledge_graph_service import KnowledgeGraphService
from ..services.clue_tracker_service import ClueTrackerService
from ..services.llm_service import LLMService
from ..services.novel_service import NovelService
from ..services.prompt_service import PromptService
from ..utils.json_utils import remove_think_tags, sanitize_json_like_text, unwrap_markdown_json

logger = logging.getLogger(__name__)

ImportProgressCallback = Callable[[str, str, Optional[Dict[str, Any]]], Awaitable[None]]
ImportCancelChecker = Callable[[], Awaitable[bool]]


class ImportCancelledError(Exception):
    """Raised when a background import job is cancelled before persistence starts."""


class ImportService:
    """处理小说文件导入、分章与AI分析的服务。"""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.novel_service = NovelService(session)
        self.llm_service = LLMService(session)
        self.prompt_service = PromptService(session)

    async def import_novel_from_file(
        self,
        user_id: int,
        file: UploadFile,
        progress_callback: Optional[ImportProgressCallback] = None,
        should_cancel: Optional[ImportCancelChecker] = None,
    ) -> str:
        """
        导入小说文件，执行分章、分析并创建项目。
        返回新创建的项目ID。
        """
        with LLMService.daily_limit_scope(f"import_novel:{user_id}:{getattr(file, 'filename', 'unknown')}"):
            await self._emit_import_progress(
                progress_callback,
                "import_reading",
                "正在读取旧稿文件",
                {"filename": getattr(file, "filename", "")},
            )
            content = await self._read_file_content(file)
            if not content:
                raise HTTPException(status_code=400, detail="文件内容为空")
            await self._raise_if_import_cancelled(should_cancel)

            # 1. 智能分段（分章）
            await self._emit_import_progress(
                progress_callback,
                "import_splitting",
                "正在识别章节边界",
                {"characters": len(content)},
            )
            chapters = self._split_into_chapters(content)
            if not chapters:
                # 如果无法分章，将整个文件作为一个章节
                chapters = [("第一章 全文", content)]
            await self._raise_if_import_cancelled(should_cancel)

            # 2. 准备分析用的文本样本
            # 策略改进：混合采样 (均匀剧情采样 + 角色高光采样)

            # A. 均匀剧情采样 (约 30k 字)
            MAX_PLOT_CHARS = 30000
            MAX_CHAPTER_CHARS = 1000

            plot_sample_text = ""
            chapter_titles = [title for title, _ in chapters]
            total_chapters = len(chapters)

            # 预提取人名 (基于全文)
            potential_characters = self._extract_potential_characters(content, top_n=150) # 扩大到150，广撒网
            await self._emit_import_progress(
                progress_callback,
                "import_sampling",
                "正在抽取剧情样本和角色高光片段",
                {
                    "chapter_count": len(chapters),
                    "potential_character_count": len(potential_characters),
                },
            )

            # 确定要采样的章节索引 (均匀分布)
            indices = []
            if total_chapters <= 10:
                indices = list(range(total_chapters))
            else:
                indices.extend([0, 1, 2]) # 前3章
                last_indices = [total_chapters - 2, total_chapters - 1] # 后2章

                start_mid = 3
                end_mid = total_chapters - 2
                mid_count = end_mid - start_mid

                if mid_count > 0:
                    target_mid_samples = 25 # 中间取25章
                    step = max(1, mid_count // target_mid_samples)
                    for i in range(start_mid, end_mid, step):
                        indices.append(i)

                indices.extend(last_indices)
                indices = sorted(list(set(indices)))

            for i in indices:
                if 0 <= i < len(chapters):
                    title, body = chapters[i]
                    clean_body = body[:MAX_CHAPTER_CHARS].strip()
                    plot_sample_text += f"第{i+1}章 {title}\n{clean_body}\n\n"

            if len(plot_sample_text) > MAX_PLOT_CHARS:
                plot_sample_text = plot_sample_text[:MAX_PLOT_CHARS] + "...\n(截断)"

            # B. 角色高光采样 (约 20k-30k 字)
            # 为每个潜在角色提取一段精彩片段
            # 优化：Top 150 采样，窗口适当缩小，只求证明存在
            char_highlights_text = self._extract_character_highlights(content, potential_characters, context_window=200)

            # 3. 分阶段分析
            # 阶段一：先筛选出确定的角色名单 (Stable Census)
            await self._raise_if_import_cancelled(should_cancel)
            await self._emit_import_progress(
                progress_callback,
                "import_character_verify",
                "正在筛选真实角色名单",
                {"potential_character_count": len(potential_characters)},
            )
            verified_characters = await self._filter_characters_only(user_id, potential_characters, char_highlights_text)
            logger.info(f"角色筛选完成，潜在 {len(potential_characters)} -> 确认 {len(verified_characters)}")

            # 阶段二：详细分析 (Deep Profiling)
            await self._raise_if_import_cancelled(should_cancel)
            await self._emit_import_progress(
                progress_callback,
                "import_blueprint_extract",
                "正在抽取故事蓝图、角色和章节大纲",
                {
                    "chapter_count": len(chapters),
                    "verified_character_count": len(verified_characters),
                },
            )
            blueprint_data = await self._analyze_content(
                user_id,
                plot_sample_text,
                chapter_titles,
                potential_characters, # 依然传入作为备选参考
                char_highlights_text,
                verified_characters   # 传入确定的名单
            )

            # 4. 创建项目
            await self._raise_if_import_cancelled(should_cancel)
            await self._emit_import_progress(
                progress_callback,
                "import_saving",
                "正在写入项目、蓝图和章节正文",
                {"chapter_count": len(chapters)},
            )
            title = blueprint_data.title or file.filename.rsplit('.', 1)[0]
            initial_prompt = f"导入自文件: {file.filename}"
            project = await self.novel_service.create_project(user_id, title, initial_prompt)

            # 5. 保存蓝图
            # 确保 blueprint_data 中的 chapter_outline 包含所有章节（如果AI没返回全部）
            if blueprint_data.chapter_outline:
                # 建立映射以合并AI生成的摘要和实际章节列表
                ai_outlines = {o.chapter_number: o for o in blueprint_data.chapter_outline}
                final_outlines = []
                for i, (chap_title, _) in enumerate(chapters, 1):
                    if i in ai_outlines:
                        outline = ai_outlines[i]
                        outline.title = chap_title # 优先使用解析出的真实标题
                    else:
                        # AI未生成的章节，使用默认占位
                        from ..schemas.novel import ChapterOutline as ChapterOutlineSchema
                        outline = ChapterOutlineSchema(
                            chapter_number=i,
                            title=chap_title,
                            summary=""
                        )
                    final_outlines.append(outline)
                blueprint_data.chapter_outline = final_outlines

            await self.novel_service.replace_blueprint(project.id, blueprint_data)

            # 6. 保存章节内容
            for i, (chap_title, chap_content) in enumerate(chapters, 1):
                chapter = await self.novel_service.get_or_create_chapter(project.id, i)
                # 创建初始版本
                await self.novel_service.replace_chapter_versions(
                    chapter,
                    [chap_content],
                    metadata=[{"source": "file_import"}]
                )
                # 自动选择第一个版本（即导入的内容）
                await self.novel_service.select_chapter_version(chapter, 0)

            # 更新项目状态
            await self._emit_import_progress(
                progress_callback,
                "import_ledger_rebuild",
                "正在重建角色、章节快照、记忆和知识图谱账本",
                {"chapter_count": len(chapters), "character_count": len(blueprint_data.characters or [])},
            )
            ledger_metrics = await self._rebuild_import_ledgers(
                project.id,
                blueprint_data,
                chapters,
                filename=file.filename or "",
            )

            project.status = "blueprint_ready"
            await self.session.commit()
            await self._emit_import_progress(
                progress_callback,
                "import_ledger_rebuild",
                "导入账本重建完成",
                ledger_metrics,
            )

            return project.id

    async def _emit_import_progress(
        self,
        callback: Optional[ImportProgressCallback],
        stage: str,
        message: str,
        metrics: Optional[Dict[str, Any]] = None,
    ) -> None:
        if callback is not None:
            await callback(stage, message, metrics or {})

    async def _raise_if_import_cancelled(self, should_cancel: Optional[ImportCancelChecker]) -> None:
        if should_cancel is not None and await should_cancel():
            raise ImportCancelledError("import job cancelled")

    async def _rebuild_import_ledgers(
        self,
        project_id: str,
        blueprint_data: Blueprint,
        chapters: List[Tuple[str, str]],
        *,
        filename: str,
    ) -> Dict[str, Any]:
        blueprint_payload = blueprint_data.model_dump(exclude_none=True) if hasattr(blueprint_data, "model_dump") else {}
        character_payloads = list(blueprint_payload.get("characters") or [])
        relationship_payloads = list(blueprint_payload.get("relationships") or [])
        foreshadowing_payloads = list(blueprint_payload.get("foreshadowing_system") or [])
        now = datetime.now(timezone.utc).isoformat()

        memory_result = await self.session.execute(select(ProjectMemory).where(ProjectMemory.project_id == project_id))
        memory = memory_result.scalars().first()
        if memory is None:
            memory = ProjectMemory(project_id=project_id)
            self.session.add(memory)

        memory.global_summary = blueprint_data.full_synopsis or blueprint_data.one_sentence_summary or ""
        memory.plot_arcs = {
            "main_conflicts": [
                {
                    "id": f"import_conflict_{index}",
                    "description": str(item.get("description") or item.get("relation_type") or item)[:240],
                    "status": "imported",
                }
                for index, item in enumerate(relationship_payloads[:12], start=1)
                if isinstance(item, dict)
            ],
            "unresolved_hooks": [
                {
                    "id": f"import_hook_{index}",
                    "description": str(item.get("setup") or item.get("description") or item.get("name") or item)[:240],
                    "planted_chapter": item.get("chapter") or item.get("planted_chapter") or 1,
                    "expected_payoff": item.get("payoff_window") or item.get("target_reveal_chapter"),
                    "status": "imported",
                }
                for index, item in enumerate(foreshadowing_payloads[:20], start=1)
                if isinstance(item, dict)
            ],
            "character_arcs": [
                {
                    "character": str(item.get("name") or item.get("character_name") or "")[:80],
                    "current_stage": str(item.get("arc") or item.get("motivation") or item.get("role") or "导入初始状态")[:240],
                    "next_milestone": str(item.get("goal") or item.get("development") or "等待后续生成承接")[:240],
                }
                for item in character_payloads[:24]
                if isinstance(item, dict) and str(item.get("name") or item.get("character_name") or "").strip()
            ],
        }
        memory.story_timeline_summary = self._build_import_timeline_summary(chapters)
        memory.last_updated_chapter = len(chapters)
        memory.version = (memory.version or 0) + 1
        memory.extra = {
            **dict(memory.extra or {}),
            "import_ledger_rebuild": {
                "source": "file_import",
                "filename": filename,
                "chapter_count": len(chapters),
                "character_count": len(character_payloads),
                "relationship_count": len(relationship_payloads),
                "foreshadowing_count": len(foreshadowing_payloads),
                "rebuilt_at": now,
            },
        }

        snapshot_count = 0
        for chapter_number, (title, content) in enumerate(chapters, start=1):
            self.session.add(ChapterSnapshot(
                project_id=project_id,
                chapter_number=chapter_number,
                global_summary_snapshot=memory.global_summary,
                character_states_snapshot={"source": "file_import", "character_count": len(character_payloads)},
                plot_arcs_snapshot=memory.plot_arcs,
                chapter_summary=self._make_import_chapter_summary(title, content),
                word_count=len(content or ""),
                extra={"source": "file_import", "title": title, "snapshot_kind": "import_baseline"},
            ))
            snapshot_count += 1

        await self.session.flush()

        character_result = await self.session.execute(
            select(BlueprintCharacter).where(BlueprintCharacter.project_id == project_id)
        )
        blueprint_characters = list(character_result.scalars().all())
        state_count = 0
        for character in blueprint_characters:
            self.session.add(CharacterState(
                project_id=project_id,
                character_id=character.id,
                character_name=character.name or "未命名角色",
                chapter_number=0,
                location="导入基线",
                emotion="初始",
                health_status="unknown",
                current_goals=[character.goals] if getattr(character, "goals", None) else [],
                relationship_changes=[],
                new_knowledge=[],
                extra={
                    "source": "file_import",
                    "identity": getattr(character, "identity", None),
                    "position": getattr(character, "position", None),
                    "created_at": now,
                },
            ))
            state_count += 1

        timeline_count = 0
        for chapter_number, (title, content) in enumerate(chapters[:200], start=1):
            self.session.add(TimelineEvent(
                project_id=project_id,
                chapter_number=chapter_number,
                story_time=f"导入章节 {chapter_number}",
                event_type="imported_chapter",
                event_title=title or f"第{chapter_number}章",
                event_description=self._make_import_chapter_summary(title, content),
                involved_characters=[],
                importance=5,
                is_turning_point=False,
                extra={"source": "file_import"},
            ))
            timeline_count += 1

        foreshadowing_count = await self._persist_import_foreshadowings(
            project_id,
            foreshadowing_payloads,
            chapter_count=len(chapters),
        )
        clue_metrics = await ClueTrackerService(self.session).sync_from_foreshadowings(project_id)
        graph_metrics = await KnowledgeGraphService(self.session).sync_from_story_memory(project_id)

        return {
            "memory_version": memory.version,
            "snapshot_count": snapshot_count,
            "character_state_count": state_count,
            "timeline_event_count": timeline_count,
            "foreshadowing_count": foreshadowing_count,
            "clue_tracker": clue_metrics,
            "knowledge_graph": graph_metrics,
        }

    async def _persist_import_foreshadowings(
        self,
        project_id: str,
        foreshadowing_payloads: List[Any],
        *,
        chapter_count: int,
    ) -> int:
        if not foreshadowing_payloads:
            return 0

        chapter_result = await self.session.execute(
            select(Chapter).where(Chapter.project_id == project_id)
        )
        chapters_by_number = {chapter.chapter_number: chapter for chapter in chapter_result.scalars().all()}
        if not chapters_by_number:
            return 0

        existing_result = await self.session.execute(
            select(Foreshadowing).where(Foreshadowing.project_id == project_id)
        )
        existing_keys = {
            (item.chapter_number, (item.name or "").strip(), (item.content or "").strip()[:512])
            for item in existing_result.scalars().all()
        }

        created = 0
        for index, raw_item in enumerate(foreshadowing_payloads, start=1):
            item = self._coerce_mapping(raw_item)
            if not item:
                continue

            planted_chapter = self._coerce_chapter_number(
                self._first_present(
                    item,
                    "chapter",
                    "chapter_number",
                    "planted_chapter",
                    "plant_chapter",
                    "setup_chapter",
                    "start_chapter",
                ),
                default=1,
                chapter_count=chapter_count,
            )
            chapter = chapters_by_number.get(planted_chapter) or chapters_by_number.get(1)
            if chapter is None:
                continue

            resolved_chapter_number = self._coerce_optional_chapter_number(
                self._first_present(
                    item,
                    "resolved_chapter_number",
                    "resolution_chapter",
                    "resolved_at_chapter",
                    "payoff_chapter",
                ),
                chapter_count=chapter_count,
                clamp=False,
            )
            target_reveal_chapter = self._coerce_optional_chapter_number(
                self._first_present(item, "target_reveal_chapter", "payoff_window", "expected_payoff"),
                chapter_count=chapter_count,
                clamp=False,
            )
            resolved_chapter = chapters_by_number.get(resolved_chapter_number) if resolved_chapter_number else None

            plant_text = self._compact_text(self._first_present(item, "plant", "setup", "content", "description"))
            payoff_text = self._compact_text(self._first_present(item, "payoff", "resolution", "reveal_method"))
            trigger_text = self._compact_text(item.get("trigger"))
            summary_text = self._compact_text(item.get("summary"))
            name = self._compact_text(self._first_present(item, "name", "title", "summary", "trigger", "plant"))[:255]
            if not name:
                name = f"imported_foreshadowing_{index}"

            content_parts = [part for part in [summary_text, plant_text, trigger_text] if part]
            content = " / ".join(content_parts).strip() or name
            dedupe_key = (planted_chapter, name.strip(), content[:512])
            if dedupe_key in existing_keys:
                continue

            status_text = str(item.get("status") or "").strip().lower()
            status_value = "revealed" if resolved_chapter_number or status_text in {"resolved", "revealed", "paid_off"} else "planted"

            self.session.add(
                Foreshadowing(
                    project_id=project_id,
                    chapter_id=chapter.id,
                    chapter_number=planted_chapter,
                    content=content,
                    type=self._normalise_import_foreshadowing_type(item),
                    keywords=self._extract_import_keywords(item),
                    status=status_value,
                    resolved_chapter_id=resolved_chapter.id if resolved_chapter else None,
                    resolved_chapter_number=resolved_chapter_number,
                    name=name,
                    target_reveal_chapter=target_reveal_chapter or resolved_chapter_number,
                    reveal_method=payoff_text or None,
                    reveal_impact=self._compact_text(item.get("impact") or item.get("reveal_impact")) or None,
                    related_characters=self._coerce_list(item.get("owner") or item.get("related_characters")),
                    related_plots=self._coerce_list(item.get("related_plots") or item.get("plotline") or item.get("arc")),
                    importance=self._normalise_import_importance(item.get("importance") or item.get("priority")),
                    urgency=self._coerce_urgency(item.get("urgency")),
                    is_manual=False,
                    ai_confidence=0.55,
                    author_note="source:file_import_blueprint",
                )
            )
            existing_keys.add(dedupe_key)
            created += 1

        if created:
            await self.session.flush()
        return created

    @staticmethod
    def _coerce_mapping(value: Any) -> Dict[str, Any]:
        if hasattr(value, "model_dump"):
            dumped = value.model_dump(exclude_none=True)
            return dumped if isinstance(dumped, dict) else {}
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value.strip():
            return {"summary": value.strip()}
        return {}

    @staticmethod
    def _first_present(item: Dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = item.get(key)
            if value not in (None, "", [], {}):
                return value
        return None

    @staticmethod
    def _compact_text(value: Any, *, limit: int = 800) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            text = json.dumps(value, ensure_ascii=False)
        else:
            text = str(value)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:limit]

    @classmethod
    def _coerce_chapter_number(cls, value: Any, *, default: int, chapter_count: int) -> int:
        parsed = cls._coerce_optional_chapter_number(value, chapter_count=chapter_count)
        return parsed or max(1, min(default, max(chapter_count, 1)))

    @staticmethod
    def _coerce_optional_chapter_number(value: Any, *, chapter_count: int, clamp: bool = True) -> Optional[int]:
        if value in (None, "", [], {}):
            return None
        if isinstance(value, dict):
            value = value.get("chapter") or value.get("chapter_number") or value.get("start") or value.get("end")
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        match = re.search(r"\d+", str(value or ""))
        if not match:
            return None
        number = int(match.group(0))
        if number < 1:
            return None
        return min(number, max(chapter_count, 1)) if clamp else number

    @staticmethod
    def _coerce_list(value: Any) -> List[str]:
        if value in (None, "", [], {}):
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, dict):
            return [str(part).strip() for part in value.values() if str(part).strip()]
        return [part.strip() for part in re.split(r"[,，、/|]", str(value)) if part.strip()]

    @classmethod
    def _extract_import_keywords(cls, item: Dict[str, Any]) -> List[str]:
        raw_keywords = item.get("keywords") or item.get("tags")
        keywords = cls._coerce_list(raw_keywords)
        for key in ("name", "title", "trigger", "owner"):
            text = cls._compact_text(item.get(key), limit=80)
            if text and text not in keywords:
                keywords.append(text)
        return keywords[:12]

    @staticmethod
    def _normalise_import_foreshadowing_type(item: Dict[str, Any]) -> str:
        raw = str(item.get("type") or item.get("kind") or "").strip().lower()
        if raw in {"question", "mystery", "hint", "clue", "setup"}:
            return raw
        if raw in {"secret", "character_secret"}:
            return "mystery"
        if raw in {"evidence", "key_evidence"}:
            return "clue"
        return "setup"

    @staticmethod
    def _normalise_import_importance(value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in {"major", "main", "high", "5", "4", "important"}:
            return "major"
        if text in {"minor", "medium", "3"}:
            return "minor"
        return "subtle"

    @staticmethod
    def _coerce_urgency(value: Any) -> Optional[int]:
        if value in (None, "", [], {}):
            return None
        match = re.search(r"\d+", str(value))
        if not match:
            return None
        return max(1, min(10, int(match.group(0))))

    def _build_import_timeline_summary(self, chapters: List[Tuple[str, str]], *, limit: int = 12) -> str:
        if not chapters:
            return "导入项目暂无章节。"
        total = len(chapters)
        if total <= limit:
            selected = list(enumerate(chapters, start=1))
        else:
            head = list(enumerate(chapters[:4], start=1))
            mid_index = max(4, total // 2)
            middle = list(enumerate(chapters[mid_index:mid_index + 4], start=mid_index + 1))
            tail_start = max(mid_index + 4, total - 4)
            tail = list(enumerate(chapters[tail_start:], start=tail_start + 1))
            selected = head + middle + tail
        return "\n".join(f"第{number}章：{title}" for number, (title, _) in selected[:limit])

    def _make_import_chapter_summary(self, title: str, content: str, *, limit: int = 220) -> str:
        cleaned = re.sub(r"\s+", " ", content or "").strip()
        if len(cleaned) > limit:
            cleaned = cleaned[:limit].rstrip() + "..."
        return f"{title}：{cleaned}" if title else cleaned

    async def _read_file_content(self, file: UploadFile) -> str:
        content_bytes = await file.read()
        try:
            return content_bytes.decode('utf-8')
        except UnicodeDecodeError:
            try:
                return content_bytes.decode('gbk')
            except UnicodeDecodeError:
                raise HTTPException(status_code=400, detail="文件编码不支持，请使用 UTF-8 或 GBK")

    def _extract_potential_characters(self, content: str, top_n: int = 100) -> List[str]:
        """
        基于正则和统计，从全文中提取最可能的人名。
        策略：寻找 "XXX说"、"XXX道" 等高频对话模式。
        """
        # 常见对话引导词
        verbs = r"(?:说|道|问|回答|冷笑|大笑|苦笑|点头|摇头|叹气|叹道|解释|怒道|吼道|低语|传音|喊道|叫道|哭道|骂道)"
        
        # 模式1: 名字+动词 (e.g. "张三笑道")
        # 限制名字长度为2-4字，排除单字名以减少误报
        p1 = fr"([\u4e00-\u9fa5]{{2,4}}){verbs}"
        
        # 模式2: 名字+空格/标点+说 (e.g. "张三：") - 剧本模式或特定排版
        p2 = r"([\u4e00-\u9fa5]{2,4})[：:]\s*“"
        
        # 模式3: “...”+名字+说 (e.g. “...”张三说道。)
        # 这种比较难用简单正则匹配准确，暂略
        
        matches = []
        matches.extend(re.findall(p1, content))
        matches.extend(re.findall(p2, content))
        
        # 统计频率
        from collections import Counter
        counter = Counter(matches)
        
        # 过滤黑名单（非人名的常用词）
        stop_words = {
            "自己", "怎么", "于是", "接着", "忽然", "突然", "虽然", "既然", "如果", "只要", "为了", 
            "并且", "而且", "不仅", "甚至", "难道", "毕竟", "到底", "终于", "立刻", "马上", 
            "缓缓", "轻轻", "大声", "小声", "连忙", "赶紧", "不禁", "不由", "只能", "只好", 
            "众人", "大家", "某人", "那个", "这个", "什么", "此时", "此刻", "随后", "然后",
            "原来", "其实", "顺便", "根本", "简直", "仿佛", "好像", "似乎", "一直", "曾经",
            "已经", "正在", "准备", "开始", "继续", "重新", "互相", "彼此", "对方", "两者",
            "一人", "两人", "三人", "四人", "五人", "少年", "少女", "男子", "女子", "老者", 
            "老头", "大汉", "青年", "中年", "小孩", "丫头", "家伙", "兄弟", "姐妹", "师父",
            "师兄", "师弟", "师姐", "师妹", "陛下", "殿下", "娘娘", "将军", "大人", "掌门",
            "宗主", "长老", "护法", "弟子", "属下", "奴才", "微臣", "老夫", "老朽", "在下",
            "贫道", "本座", "本王", "本宫", "朕", "寡人", "哀家", "这时候", "那个时候",
            "一声", "一把", "一眼", "一手", "一步", "一下", "一脚", "一口", "一个", "一名", "一位",
            "今日", "明日", "昨日", "每天", "白天", "晚上", "半夜", "清晨", "黄昏", "刚刚", "刚才",
            "这里", "那里", "哪里", "那边", "这边", "里面", "外面", "前面", "后面", "上面", "下面",
            "左边", "右边", "中间", "周围", "四处", "到处", "满脸", "满身", "全身", "浑身",
            "双手", "双眼", "双脚", "双腿", "两眼", "两手", "两脚", "两腿", "心中", "心里", "心头",
            "手中", "手里", "手头", "眼中", "眼里", "口中", "嘴里", "身上", "身下", "身边", "身旁",
            "此时此刻", "不得不", "能不能", "是不是", "会不会", "有没有", "想了想", "摇了摇头", "点了点头"
        }
        
        candidates = []
        for name, count in counter.most_common():
            if name not in stop_words and count >= 2: # 至少出现2次
                candidates.append(name)
                if len(candidates) >= top_n:
                    break
                    
        return candidates

    def _extract_character_highlights(self, content: str, characters: List[str], context_window: int = 300) -> str:
        """
        为每个潜在角色提取一段“高光时刻”。
        优先选择对话密集或有动作描写的段落。
        """
        highlights = []
        used_ranges = [] # 记录已使用的文本范围 (start, end)，避免重复
        
        # 简单的去重辅助函数
        def is_overlapping(start, end):
            for s, e in used_ranges:
                if not (end < s or start > e): # 如果有交集
                    return True
            return False

        for char in characters:
            # 查找该角色的所有出现位置
            # 为了性能，限制查找前N个匹配
            matches = list(re.finditer(re.escape(char), content))
            if not matches:
                continue
                
            best_score = -1
            best_snippet = ""
            best_range = (0, 0)
            
            # 简单的评分机制：找对话最多的片段
            # 只需要检查前几个和中间几个出现位置，不必遍历所有，节省时间
            # 采样点：前3次，中间3次，最后3次
            sample_indices = []
            total = len(matches)
            if total <= 10:
                sample_indices = range(total)
            else:
                sample_indices = list(range(3)) + list(range(total//2 - 1, total//2 + 2)) + list(range(total-3, total))
                
            for idx in sample_indices:
                if idx < 0 or idx >= total: continue
                
                m = matches[idx]
                start = max(0, m.start() - context_window)
                end = min(len(content), m.end() + context_window)
                
                # 如果这个范围已经被大幅占用了，跳过
                if is_overlapping(start + 50, end - 50): # 允许边缘少量重叠
                    continue
                    
                snippet = content[start:end]
                
                # 评分：双引号数量（对话）+ 标点符号丰富度
                score = snippet.count('“') * 2 + snippet.count('”') * 2 + snippet.count('！') + snippet.count('？')
                
                if score > best_score:
                    best_score = score
                    best_snippet = snippet
                    best_range = (start, end)
            
            if best_snippet:
                # 清理首尾不完整的句子
                # 简单处理：找到第一个换行符和最后一个换行符
                first_nl = best_snippet.find('\n')
                last_nl = best_snippet.rfind('\n')
                if first_nl != -1 and last_nl != -1 and first_nl < last_nl:
                    clean_snippet = best_snippet[first_nl:last_nl].strip()
                else:
                    clean_snippet = best_snippet.strip()
                
                if len(clean_snippet) > 50: # 太短的不要
                    highlights.append(f"--- 【{char}】的出场片段 ---\n{clean_snippet}\n")
                    used_ranges.append(best_range)
        
        return "\n".join(highlights)

    def _split_into_chapters(self, content: str) -> List[Tuple[str, str]]:
        """
        使用正则匹配章节标题。
        支持格式：
        第1章
        第一章
        Chapter 1
        """
        # 正则表达式匹配行首的章节标题
        # 常见格式：第xxx章、Chapter xxx、xxx、(xxx)
        pattern = r"(^\s*第[0-9零一二三四五六七八九十百千]+[章卷回节].*|^\s*Chapter\s+[0-9]+.*)"
        
        # 使用 split 保留分隔符（即标题）
        parts = re.split(pattern, content, flags=re.MULTILINE)
        
        chapters = []
        # split 后第一个元素通常是标题前的内容（序章或前言），如果非空也算一章
        if parts[0].strip():
             chapters.append(("序章", parts[0].strip()))
             
        # 后续元素是 标题, 内容, 标题, 内容...
        for i in range(1, len(parts), 2):
            title = parts[i].strip()
            body = parts[i+1].strip() if i+1 < len(parts) else ""
            if body:
                chapters.append((title, body))
                
        return chapters

    async def _filter_characters_only(self, user_id: int, potential_characters: List[str], char_highlights: str) -> List[str]:
        """
        阶段一：角色普查。
        只负责从潜在名单中筛选出真实存在的角色名，不做详细分析。
        """
        system_prompt = """
        你是一个严谨的网文角色鉴别师。
        任务：根据提供的【潜在角色名单】和【角色高光片段】，甄别出其中真正的角色。
        
        判断标准：
        1. 必须是具体的人物（排除地名、物品名、通用称呼如“师兄”、“掌门”等泛指）。
        2. 在高光片段中有明确的对话、动作或被他人提及。
        
        输出要求：
        仅返回一个 JSON 对象，包含所有确认的角色名。
        例如：{"characters": ["张三", "李四", "王五"]}
        不要输出任何其他解释或字段。
        """
        
        user_content = f"""
【潜在角色名单】
{", ".join(potential_characters)}

【参考证据：角色高光片段】
{char_highlights}
"""
        messages = [{"role": "user", "content": user_content}]
        
        try:
            result = await call_generation_text(
                llm_service=self.llm_service,
                system_prompt=system_prompt,
                conversation_history=messages,
                temperature=0.1, # 极低温度，追求稳定
                user_id=user_id,
                timeout=60.0,
                policy=GenerationCallPolicy(
                    stage_label="导入分析-角色名单鉴别",
                    progress_stage="import_character_verify",
                    retry_attempts=2,
                    json_repair_attempts=1,
                ),
            )
            data, _ = parse_llm_json_value(result.text)
            
            # 尝试多种可能的 JSON 结构
            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                # 可能是 {"characters": [...]} 或 {"names": [...]}
                for key in ["characters", "names", "list", "result"]:
                    if key in data and isinstance(data[key], list):
                        return data[key]
                # 如果都没有，尝试取第一个 value 是 list 的
                for val in data.values():
                    if isinstance(val, list):
                        return val
            
            return []
            
        except Exception as e:
            logger.error(f"角色筛选阶段失败: {e}", exc_info=True)
            return [] # 失败时返回空，后续流程将回退到仅使用潜在名单

    @staticmethod
    def _format_verified_character_names(verified_characters: List[Any]) -> str:
        names: List[str] = []
        for item in verified_characters or []:
            if isinstance(item, str):
                name = item.strip()
            elif isinstance(item, dict):
                name = str(item.get("name") or item.get("character_name") or item.get("display_name") or "").strip()
            else:
                name = str(getattr(item, "name", "") or "").strip()
            if name and name not in names:
                names.append(name)
        return ", ".join(names) if names else "无 (请自行分析)"

    async def _analyze_content(self, user_id: int, sample_text: str, chapter_titles: List[str], potential_characters: List[str] = [], char_highlights: str = "", verified_characters: List[Any] = []) -> Blueprint:
        prompt_template = await self.prompt_service.get_prompt("import_analysis")
        if not prompt_template:
            # Fallback prompt if file not found in DB
            prompt_template = """
            你是一个专业的网文编辑。请根据提供的小说样本和目录，分析并提取小说信息。
            返回 JSON 格式，包含：title, one_sentence_summary, full_synopsis, world_setting (core_rules, key_locations, factions, magic_system), characters, relationships, chapter_outline。
            注意 world_setting 的 key 必须是 core_rules 和 key_locations。
            请尽可能完整地提取所有出场角色，包括主要角色和重要的次要角色。
            """
        
        # 构造参考信息
        # 1. 潜在角色列表
        potential_chars_str = ", ".join(potential_characters) if potential_characters else "无"
        
        # 2. 章节目录 (提供更多，例如前500章)
        chapters_preview = "\n".join(chapter_titles[:500])
        if len(chapter_titles) > 500:
            chapters_preview += f"\n... (共 {len(chapter_titles)} 章)"

        # 3. 确定的角色名单 (Stringify)
        verified_chars_str = self._format_verified_character_names(verified_characters)

        system_prompt = f"""
{prompt_template}

【输入数据说明】
用户提供的输入分为两部分：
1. **剧情概览样本**：全书均匀采样的章节片段，用于分析剧情脉络、世界观和大纲。
2. **角色高光片段集**：针对全书出现频率较高的潜在角色专门提取的“出场片段”。这些片段是专门为了辅助你提取角色而提供的。

【任务要求】
1. **强制性角色档案生成**：
   我们已经预先确认了以下角色在书中真实存在：
   【{verified_chars_str}】
   
   请你**必须**为上述列表中的**每一个**角色生成详细档案（性格、外貌、目标等）。
   - 如果在“剧情概览样本”中找不到该角色的信息，请去“角色高光片段集”里找。
   - 如果还是找不到详细信息，请根据有限的上下文进行合理推断，或保留为“未知”，但**绝不要**将该角色从名单中剔除。
   - 除了上述名单，如果你发现了其他重要角色，也请一并补充。

2. **世界观与剧情**：请基于“剧情概览样本”进行常规分析。

【参考信息】
1. 潜在角色名录（线索）：
{potential_chars_str}

2. 章节目录概览：
{chapters_preview}
"""
        
        # 构造 prompt
        user_content = f"""
=== PART 1: 剧情概览样本 (Story Overview) ===
{sample_text}

=== PART 2: 角色高光片段集 (Character Highlights) ===
{char_highlights}
"""
        messages = [{"role": "user", "content": user_content}]
        
        try:
            result = await call_generation_json(
                llm_service=self.llm_service,
                system_prompt=system_prompt,
                conversation_history=messages,
                temperature=0.3,
                user_id=user_id,
                timeout=120.0,
                policy=GenerationCallPolicy(
                    stage_label="导入分析-故事蓝图抽取",
                    progress_stage="import_blueprint_extract",
                    retry_attempts=2,
                    json_repair_attempts=1,
                ),
            )
            data = result.data
            
            # --- 数据标准化处理 (Robustness Fixes) ---
            if "world_setting" in data:
                ws = data["world_setting"]
                # 1. 兼容旧的 key 名称
                if "rules" in ws and "core_rules" not in ws:
                    ws["core_rules"] = ws.pop("rules")
                if "locations" in ws and "key_locations" not in ws:
                    ws["key_locations"] = ws.pop("locations")
                
                # 2. 确保 core_rules 是字符串
                # 如果 AI 返回了 list，将其合并为字符串
                if "core_rules" in ws:
                    if isinstance(ws["core_rules"], list):
                        ws["core_rules"] = "\n".join(str(r) for r in ws["core_rules"])
                elif "core_rules" not in ws:
                     ws["core_rules"] = ""
                     
                # 3. 确保 key_locations 存在且结构正确
                # 格式是 list[dict]
                if "key_locations" in ws:
                    locs = ws["key_locations"]
                    if isinstance(locs, list):
                        new_locs = []
                        for loc in locs:
                            if isinstance(loc, str):
                                new_locs.append({"name": loc, "description": ""})
                            elif isinstance(loc, dict):
                                new_locs.append(loc)
                        ws["key_locations"] = new_locs
                else:
                    ws["key_locations"] = []

                # 4. 确保 factions 存在且结构正确
                # 格式是 list[dict]
                if "factions" in ws:
                    facts = ws["factions"]
                    if isinstance(facts, list):
                        new_facts = []
                        for f in facts:
                            if isinstance(f, str):
                                new_facts.append({"name": f, "description": ""})
                            elif isinstance(f, dict):
                                new_facts.append(f)
                        ws["factions"] = new_facts
                else:
                    ws["factions"] = []

            return Blueprint(**data)
            
        except Exception as e:
            logger.error(f"AI 分析失败: {e}", exc_info=True)
            # 分析失败时返回一个空的 Blueprint，但保留标题等基本信息
            return Blueprint(
                title="导入的项目",
                one_sentence_summary="AI分析失败，请手动补充",
                chapter_outline=[]
            )

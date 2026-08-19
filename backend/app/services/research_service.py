from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from openai import AsyncOpenAI, APITimeoutError
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.secret_store import decrypt_secret, encrypt_secret, mask_secret
from ..models.novel import ChapterOutline, NovelBlueprint, NovelProject
from ..models.research import ProjectResearchConfig, ResearchArtifact
from ..schemas.research import ResearchArtifactRead, ResearchConfigRead, ResearchConfigUpdate
from ..utils.json_utils import remove_think_tags, sanitize_json_like_text, unwrap_markdown_json
from .generation_call_service import GenerationCallPolicy, call_generation_json
from .llm_service import LLMService
from .research_archive import CATEGORY_LABELS, ResearchArchive
from .research_search import ResearchSearchClient

logger = logging.getLogger(__name__)

# Timeout constants for research operations
_RESEARCH_LLM_TIMEOUT_SECONDS = 90.0


class ResearchConsentRequired(RuntimeError):
    pass


class ProjectResearchService:
    ACTIVE_JOB_STALE_AFTER = timedelta(seconds=150)

    def __init__(self, session: AsyncSession):
        self.session = session
        self.search_client = ResearchSearchClient()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    async def get_or_create_config(self, project_id: str) -> ProjectResearchConfig:
        config = await self.session.get(ProjectResearchConfig, project_id)
        if config is None:
            config = ProjectResearchConfig(project_id=project_id)
            self.session.add(config)
            await self.session.commit()
            await self.session.refresh(config)
        return config

    @staticmethod
    def _config_read(config: ProjectResearchConfig) -> ResearchConfigRead:
        return ResearchConfigRead(
            project_id=config.project_id,
            mode=config.mode if config.mode in {"auto", "ask", "off"} else "auto",
            enabled=bool(config.enabled),
            search_provider=config.search_provider or "tavily",
            search_base_url=config.search_base_url,
            search_api_key_masked=mask_secret(config.search_api_key_encrypted),
            search_api_key_configured=bool(decrypt_secret(config.search_api_key_encrypted)),
            research_llm_base_url=config.research_llm_base_url,
            research_llm_model=config.research_llm_model,
            research_llm_api_key_masked=mask_secret(config.research_llm_api_key_encrypted),
            research_llm_api_key_configured=bool(decrypt_secret(config.research_llm_api_key_encrypted)),
            reuse_writing_llm=bool(config.reuse_writing_llm),
            local_model_enabled=False,
            global_research_enabled=bool(config.global_research_enabled),
            enhanced_research_enabled=bool(config.enhanced_research_enabled),
            chapter_research_enabled=bool(config.chapter_research_enabled),
            max_parallel_queries=max(1, min(8, int(config.max_parallel_queries or 4))),
            max_results_per_query=max(1, min(10, int(config.max_results_per_query or 5))),
            preferred_domains=list(config.preferred_domains or []),
            blocked_domains=list(config.blocked_domains or []),
            category_preferences=list(config.category_preferences or []),
        )

    async def read_config(self, project_id: str) -> ResearchConfigRead:
        return self._config_read(await self.get_or_create_config(project_id))

    async def update_config(self, project_id: str, payload: ResearchConfigUpdate) -> ResearchConfigRead:
        config = await self.get_or_create_config(project_id)
        values = payload.model_dump(exclude={
            "search_api_key", "clear_search_api_key",
            "research_llm_api_key", "clear_research_llm_api_key",
        })
        for key, value in values.items():
            setattr(config, key, value)
        config.local_model_enabled = False
        if payload.clear_search_api_key:
            config.search_api_key_encrypted = None
        elif payload.search_api_key is not None:
            config.search_api_key_encrypted = encrypt_secret(payload.search_api_key)
        if payload.clear_research_llm_api_key:
            config.research_llm_api_key_encrypted = None
        elif payload.research_llm_api_key is not None:
            config.research_llm_api_key_encrypted = encrypt_secret(payload.research_llm_api_key)
        await self.session.commit()
        await self.session.refresh(config)
        return self._config_read(config)

    @staticmethod
    def should_run(config: ProjectResearchConfig, scope: str, *, consent: bool = False, force: bool = False) -> tuple[bool, str]:
        if force:
            return True, "forced"
        if not config.enabled or config.mode == "off":
            return False, "disabled"
        scope_value = {
            "global": config.global_research_enabled,
            "enhanced": config.enhanced_research_enabled,
            "chapter": config.chapter_research_enabled,
        }.get(scope, False)
        scope_enabled = True if scope_value is None else bool(scope_value)
        if not scope_enabled:
            return False, f"{scope}_disabled"
        if config.mode == "ask" and not consent:
            return False, "consent_required"
        return True, "auto" if config.mode == "auto" else "consented"

    async def _build_project_context(self, project_id: str, chapter_number: Optional[int]) -> Dict[str, Any]:
        project = await self.session.get(NovelProject, project_id)
        blueprint = await self.session.get(NovelBlueprint, project_id)
        context: Dict[str, Any] = {
            "project_id": project_id,
            "title": getattr(project, "title", None),
            "initial_prompt": getattr(project, "initial_prompt", None),
        }
        if blueprint:
            context["blueprint"] = {
                "title": blueprint.title,
                "genre": blueprint.genre,
                "style": blueprint.style,
                "tone": blueprint.tone,
                "one_sentence_summary": blueprint.one_sentence_summary,
                "full_synopsis": (blueprint.full_synopsis or "")[:5000],
                "world_setting": blueprint.world_setting or {},
            }
        statement = select(ChapterOutline).where(ChapterOutline.project_id == project_id)
        if chapter_number:
            statement = statement.where(ChapterOutline.chapter_number == chapter_number)
        else:
            statement = statement.order_by(ChapterOutline.chapter_number).limit(80)
        outlines = list((await self.session.execute(statement)).scalars().all())
        context["chapter_outlines"] = [
            {"chapter_number": item.chapter_number, "title": item.title, "summary": item.summary, "metadata": item.metadata or {}}
            for item in outlines
        ]
        # Include previous research context to avoid duplicate queries
        context["previous_research"] = await self._load_previous_research_summary(project_id, chapter_number)
        return context

    async def _load_previous_research_summary(self, project_id: str, chapter_number: Optional[int]) -> Dict[str, Any]:
        """Load summaries from previous successful research to provide context."""
        result: Dict[str, Any] = {}
        scopes = ["global", "enhanced"]
        if chapter_number is not None:
            scopes.append("chapter")

        for scope in scopes:
            statement = (
                select(ResearchArtifact)
                .where(
                    ResearchArtifact.project_id == project_id,
                    ResearchArtifact.status.in_(("successful", "degraded")),
                    ResearchArtifact.scope == scope,
                )
                .order_by(desc(ResearchArtifact.created_at))
                .limit(1)
            )
            if scope == "chapter" and chapter_number is not None:
                statement = statement.where(ResearchArtifact.chapter_number == chapter_number)
            elif scope in ("global", "enhanced"):
                statement = statement.where(ResearchArtifact.chapter_number.is_(None))

            artifact = (await self.session.execute(statement)).scalar_one_or_none()
            if artifact and artifact.summary:
                result[scope] = {
                    "summary": artifact.summary[:2000],
                    "run_id": artifact.run_id,
                }
        return result

    @staticmethod
    def _context_text(context: Dict[str, Any], limit: int = 14000) -> str:
        return json.dumps(context, ensure_ascii=False, default=str)[:limit]

    @classmethod
    def build_query_plan(cls, context: Dict[str, Any], scope: str, category_preferences: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Build optimized search query plan with specific, targeted queries."""
        blueprint: Dict[str, Any] = {}
        # Runtime blueprint data is newer than the persisted row while a blueprint job is
        # still running. Prefer it so research uses the outline that triggered this stage.
        for key in ("blueprint", "blueprint_draft", "blueprint_with_chapter_outline"):
            candidate = context.get(key)
            if isinstance(candidate, dict):
                blueprint.update(candidate)

        # Extract key information for focused queries
        title = str(blueprint.get("title") or context.get("title") or "").strip()
        genre = str(blueprint.get("genre") or "").strip()
        style = str(blueprint.get("style") or "").strip()
        tone = str(blueprint.get("tone") or "").strip()
        summary = str(blueprint.get("one_sentence_summary") or "").strip()
        world_setting = blueprint.get("world_setting") or {}

        # Get chapter-specific context
        runtime_outlines = blueprint.get("chapter_outline")
        outline_items = runtime_outlines if isinstance(runtime_outlines, list) else context.get("chapter_outlines") or []
        chapter_contexts = []
        for item in outline_items[:6]:
            if isinstance(item, dict):
                ch_title = str(item.get("title") or "").strip()
                ch_summary = str(item.get("summary") or "").strip()
                ch_conflict = str(item.get("core_conflict") or "").strip()
                ch_turning = str(item.get("turning_point") or "").strip()
                if ch_title or ch_summary:
                    ctx = f"章节{ch_title}: {ch_summary[:300]}"
                    if ch_conflict:
                        ctx += f" 冲突: {ch_conflict[:150]}"
                    if ch_turning:
                        ctx += f" 转折: {ch_turning[:150]}"
                    chapter_contexts.append(ctx)

        # Build a focused seed for queries (max 500 chars for precision)
        seed_parts = [title, genre, style, tone, summary[:300]]
        seed = " ".join(p for p in seed_parts if p)[:500] or "小说创作"

        # Add chapter context if available
        chapter_context = " | ".join(chapter_contexts[:3]) if chapter_contexts else ""

        # Build world setting keywords
        world_keywords = []
        if isinstance(world_setting, dict):
            for k in ("era", "location", "technology", "magic_system", "social_structure"):
                v = world_setting.get(k)
                if v:
                    world_keywords.append(str(v)[:100])
        world_context = " ".join(world_keywords[:3])

        # Enhanced, more specific query templates with clear purposes
        templates = [
            ("history", f'"{seed}" {world_context} 历史背景 史料 时间线 具体年代 社会状况', "查找与题材相关的真实历史背景和社会状况"),
            ("culture", f'"{seed}" 文化习俗 日常生活 服饰 饮食 礼仪 节庆 民间传统', "查找相关的文化细节和日常生活描写素材"),
            ("philosophy", f'"{seed}" 哲学思想 伦理观 价值体系 人物动机 道德困境', "查找相关的思想体系和人物行为动机依据"),
            ("naming", f'"{seed}" 人名寓意 地名考据 器物命名 典故出处 词源学', "查找命名参考和文化典故"),
            ("domain_knowledge", f'"{seed}" {world_context} 专业术语 工作流程 技术规范 行业标准', "查找专业领域的准确知识和术语"),
            ("humor_dialogue", f'"{seed}" 对话技巧 幽默手法 语言风格 对白节奏 喜剧冲突', "查找对话写作技巧和幽默元素"),
            ("style_craft", f'"{seed}" 叙事手法 文学技巧 题材传统 写作指南 创作理论', "查找相关的写作技法和叙事传统"),
        ]

        # Add chapter-specific query if chapter context exists
        if chapter_context:
            templates.append(("chapter_specific", f'"{seed}" {chapter_context[:400]} 写作素材 背景细节', "查找与当前章节直接相关的素材"))

        limit = 4 if scope == "chapter" else 7 if scope == "enhanced" else 5
        # Include chapter-specific query if chapter context exists
        if chapter_context and len(templates) > limit:
            limit = min(len(templates), limit + 1)
        preferred = [item for item in (category_preferences or []) if item in CATEGORY_LABELS]
        if preferred:
            order = {category: index for index, category in enumerate(preferred)}
            original_order = {item[0]: index for index, item in enumerate(templates)}
            templates.sort(key=lambda item: (order.get(item[0], len(order)), original_order[item[0]]))

        return [
            {"category": category, "query": query, "purpose": purpose}
            for category, query, purpose in templates[:limit]
        ]

    async def _call_research_json(
        self,
        config: ProjectResearchConfig,
        *,
        user_id: int,
        system_prompt: str,
        user_prompt: str,
        stage_label: str,
        max_tokens: int,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Call research LLM with timeout protection."""
        api_key = decrypt_secret(config.research_llm_api_key_encrypted)
        model = str(config.research_llm_model or "").strip()
        if api_key and model:
            if config.research_llm_base_url:
                await self.search_client._validate_outbound_url(config.research_llm_base_url)
            client = AsyncOpenAI(
                api_key=api_key,
                base_url=(config.research_llm_base_url or None),
                timeout=75.0,
                max_retries=0,
            )
            request_kwargs = {
                "model": model,
                "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                "temperature": 0.2,
                "max_tokens": max_tokens,
            }
            json_mode = True
            try:
                # Apply asyncio timeout to prevent hanging
                async with asyncio.timeout(_RESEARCH_LLM_TIMEOUT_SECONDS):
                    response = await client.chat.completions.create(
                        **request_kwargs,
                        response_format={"type": "json_object"},
                    )
            except TimeoutError:
                raise RuntimeError(f"研究LLM调用超时（{_RESEARCH_LLM_TIMEOUT_SECONDS}秒），请稍后重试或使用更短的输入")
            except APITimeoutError:
                raise RuntimeError("研究LLM API超时，请检查网络连接或稍后重试")
            except Exception as exc:
                status_code = getattr(exc, "status_code", None)
                message = str(exc).lower()
                unsupported_json_mode = status_code in {400, 404, 422} and (
                    "response_format" in message or "json mode" in message or "json_object" in message
                )
                if not unsupported_json_mode:
                    raise
                json_mode = False
                try:
                    async with asyncio.timeout(_RESEARCH_LLM_TIMEOUT_SECONDS):
                        response = await client.chat.completions.create(**request_kwargs)
                except TimeoutError:
                    raise RuntimeError(f"研究LLM调用超时（{_RESEARCH_LLM_TIMEOUT_SECONDS}秒），请稍后重试")
            raw = remove_think_tags(response.choices[0].message.content or "{}")
            normalized = sanitize_json_like_text(unwrap_markdown_json(raw))
            return json.loads(normalized), {
                "llm_source": "research_llm_api_key",
                "model": model,
                "json_mode": json_mode,
            }
        if config.reuse_writing_llm:
            result = await call_generation_json(
                llm_service=LLMService(self.session),
                system_prompt=system_prompt,
                conversation_history=[{"role": "user", "content": user_prompt}],
                temperature=0.2,
                user_id=user_id,
                timeout=_RESEARCH_LLM_TIMEOUT_SECONDS,
                policy=GenerationCallPolicy(
                    stage_label=stage_label,
                    progress_stage="research",
                    retry_attempts=1,
                    retry_same_model_once=False,
                    json_repair_attempts=1,
                    max_tokens=max_tokens,
                    soft_timeout_seconds=min(60.0, _RESEARCH_LLM_TIMEOUT_SECONDS - 10),
                ),
            )
            return result.data, {"llm_source": "writing_llm_api_key", "model": result.llm_model}
        raise RuntimeError("未配置研究 LLM API Key，且已关闭复用正文 LLM")

    async def _synthesize(
        self,
        config: ProjectResearchConfig,
        context: Dict[str, Any],
        scope: str,
        sources: List[Dict[str, Any]],
        user_id: int,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """Synthesize search results into structured research cards."""
        if not sources:
            return {
                "summary": "未检索到可用联网来源。可能原因：搜索API未配置、网络故障、或查询词过于生僻。",
                "categories": {},
                "writing_constraints": [
                    "没有来源支撑时不得把研究建议写成确定事实",
                    "如必须写入专业知识，应使用模糊表述或标注为虚构",
                    "建议配置搜索API后重新运行研究",
                ],
                "fact_check_notes": [],
            }, {"synthesizer": "empty", "source_count": 0}

        # Track truncation info
        total_sources = len(sources)
        max_sources_for_prompt = 50
        used_sources = sources[:max_sources_for_prompt]
        was_truncated = total_sources > max_sources_for_prompt

        compact_sources = [{
            "title": item.get("title"),
            "url": item.get("url"),
            "snippet": str(item.get("snippet", ""))[:800],
            "category": item.get("category"),
            "trust_tier": item.get("trust_tier", "unknown"),
        } for item in used_sources]

        # Check for existing research to avoid duplication
        previous_research = context.get("previous_research", {})
        existing_context = ""
        if previous_research:
            existing_parts = []
            for scope_name, data in previous_research.items():
                if isinstance(data, dict) and data.get("summary"):
                    existing_parts.append(f"[{scope_name}已有研究] {data['summary'][:500]}")
            if existing_parts:
                existing_context = "\n已有研究摘要（避免重复，补充缺口）：\n" + "\n".join(existing_parts)

        truncation_note = f"\n注意：共找到{total_sources}条来源，以下展示前{max_sources_for_prompt}条。" if was_truncated else ""

        prompt = f"""你是一位专业的研究助理，负责为小说创作者提供有出处、可执行、低幻觉的参考资料。

## 任务
根据提供的联网搜索摘要，制作结构化的小说创作资料卡。

## 严格要求
1. 每条事实必须附带 source_urls（来源链接），无来源的建议标记为"创作建议"
2. 禁止编造来源中没有的精确数字、日期、人名
3. 禁止复制原文超过15个字；所有引用必须改写
4. 区分"可核验事实"与"创作建议"，前者必须有 source_urls
5. 不要模仿具体作者或作品的风格
6. 使用中文，简洁专业

## 输出格式
返回 JSON：
{{"summary":"研究摘要","categories":{{"history":[{{"insight":"具体发现","usage":"如何在小说中使用","source_urls":["https://..."],"fact_type":"fact/suggestion"}}]}},"writing_constraints":["注意事项"],"fact_check_notes":["待验证信息"]}}

## 研究范围
{scope}

## 项目上下文
{self._context_text(context, 6000)}
{existing_context}
{truncation_note}

## 联网来源（共{len(compact_sources)}条）
{json.dumps(compact_sources, ensure_ascii=False)[:20000]}"""

        try:
            return await self._call_research_json(
                config,
                user_id=user_id,
                system_prompt="你是一位严谨的小说研究助理。你的核心价值是：1) 所有事实必须有来源支撑 2) 明确区分事实与创作建议 3) 绝不编造不存在的信息。",
                user_prompt=prompt,
                stage_label="研究资料综合",
                max_tokens=4000 if scope == "enhanced" else 2800,
            )
        except Exception as exc:
            logger.warning("Research synthesis LLM failed, using fallback: %s", exc)
            categories: Dict[str, List[Dict[str, Any]]] = {}
            for item in sources:
                category = str(item.get("category") or "domain_knowledge")
                categories.setdefault(category, []).append({
                    "insight": str(item.get("snippet", ""))[:500],
                    "usage": "作为背景核验线索，写入正文前应再次核对原始页面。",
                    "source_urls": [str(item.get("url", ""))] if item.get("url") else [],
                    "fact_type": "unverified",
                })
            return {
                "summary": f"研究 LLM 不可用（{str(exc)[:100]}），已保留搜索摘要并按类别归档。以下信息未经LLM综合，使用需谨慎。",
                "categories": categories,
                "writing_constraints": [
                    "搜索摘要不是最终事实，使用精确数据前需核对原始来源",
                    "本次研究未经过LLM综合分析，信息完整度有限",
                ],
                "fact_check_notes": [f"LLM综合失败: {str(exc)[:200]}"],
            }, {"synthesizer": "deterministic_fallback", "error": str(exc)[:300], "source_count": len(sources)}

    @staticmethod
    def _source_trust(url: str) -> tuple[str, int]:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        path = (parsed.path or "").lower()
        if host.endswith((".gov", ".gov.cn", ".edu", ".edu.cn")):
            return "official_or_education", 90
        if host in {"doi.org", "arxiv.org", "pubmed.ncbi.nlm.nih.gov", "cnki.net"} or "journal" in path:
            return "academic_index", 85
        if host.endswith((".org", ".ac.cn", ".museum")):
            return "institutional", 75
        if host.endswith((".com.cn", ".net.cn")):
            return "verified_chinese_site", 65
        if "wikipedia" in host or "wiki" in host:
            return "wiki_reference", 60
        return "search_summary_unverified", 50

    @classmethod
    def _flatten_sources(cls, search_batches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen: set[str] = set()
        sources: List[Dict[str, Any]] = []
        category_hosts: Dict[str, set[str]] = {}
        for batch in search_batches:
            for item in batch.get("results", []) or []:
                if not isinstance(item, dict):
                    continue
                url = str(item.get("url") or "").strip()
                if not url or url in seen:
                    continue
                seen.add(url)
                host = (urlparse(url).hostname or "").lower()
                category = str(item.get("category") or "unknown")
                category_hosts.setdefault(category, set()).add(host)
                tier, score = cls._source_trust(url)
                preferred_bonus = 3 if bool(item.get("preferred_domain")) else 0
                sources.append({
                    **item,
                    "trust_tier": tier,
                    "credibility_score": min(100, score + preferred_bonus),
                    "verification_level": "source_page_required" if tier == "search_summary_unverified" else "candidate_fact_source",
                })
        for source in sources:
            host_count = len(category_hosts.get(str(source.get("category") or "unknown"), set()))
            source["cross_source_count"] = host_count
            if host_count >= 2:
                source["credibility_score"] = min(100, int(source.get("credibility_score") or 0) + 5)
        return sorted(sources, key=lambda item: int(item.get("credibility_score") or 0), reverse=True)

    @staticmethod
    def _artifact_read(artifact: ResearchArtifact) -> ResearchArtifactRead:
        return ResearchArtifactRead(
            id=artifact.id,
            run_id=artifact.run_id,
            project_id=artifact.project_id,
            scope=artifact.scope,
            chapter_number=artifact.chapter_number,
            status=artifact.status,
            trigger=artifact.trigger,
            query_plan=list(artifact.query_plan or []),
            sources=list(artifact.sources or []),
            category_payload=dict(artifact.category_payload or {}),
            summary=artifact.summary,
            file_manifest=dict(artifact.file_manifest or {}),
            provider_metadata=dict(artifact.provider_metadata or {}),
            error=artifact.error,
            started_at=artifact.started_at.isoformat() if artifact.started_at else None,
            finished_at=artifact.finished_at.isoformat() if artifact.finished_at else None,
        )

    async def create_pending_artifact(
        self,
        *,
        run_id: str,
        project_id: str,
        user_id: int,
        scope: str,
        chapter_number: Optional[int],
        trigger: str,
    ) -> ResearchArtifactRead:
        artifact = ResearchArtifact(
            run_id=run_id, project_id=project_id, user_id=user_id, scope=scope,
            chapter_number=chapter_number, status="queued", trigger=trigger,
            provider_metadata={"background_job": True, "heartbeat_at": self._now().isoformat()},
        )
        self.session.add(artifact)
        await self.session.commit()
        await self.session.refresh(artifact)
        return self._artifact_read(artifact)

    @classmethod
    def _artifact_heartbeat_at(cls, artifact: ResearchArtifact) -> datetime:
        raw = (artifact.provider_metadata or {}).get("heartbeat_at")
        if isinstance(raw, str):
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        fallback = artifact.updated_at or artifact.started_at or artifact.created_at or cls._now()
        return fallback if fallback.tzinfo else fallback.replace(tzinfo=timezone.utc)

    @classmethod
    def _artifact_is_stale(cls, artifact: ResearchArtifact) -> bool:
        return cls._now() - cls._artifact_heartbeat_at(artifact) > cls.ACTIVE_JOB_STALE_AFTER

    async def touch_artifact_heartbeat(self, project_id: str, run_id: str, *, status: Optional[str] = None) -> Optional[ResearchArtifactRead]:
        statement = select(ResearchArtifact).where(
            ResearchArtifact.project_id == project_id,
            ResearchArtifact.run_id == run_id,
        )
        artifact = (await self.session.execute(statement)).scalar_one_or_none()
        if not artifact:
            return None
        if status and artifact.status in {"queued", "running"}:
            artifact.status = status
        artifact.provider_metadata = {
            **(artifact.provider_metadata or {}),
            "heartbeat_at": self._now().isoformat(),
        }
        await self.session.commit()
        await self.session.refresh(artifact)
        return self._artifact_read(artifact)

    async def get_active_artifact(
        self,
        project_id: str,
        scope: str,
        chapter_number: Optional[int],
    ) -> Optional[ResearchArtifactRead]:
        statement = select(ResearchArtifact).where(
            ResearchArtifact.project_id == project_id,
            ResearchArtifact.scope == scope,
            ResearchArtifact.status.in_(("queued", "running")),
        )
        if scope == "chapter":
            statement = statement.where(ResearchArtifact.chapter_number == chapter_number)
        else:
            statement = statement.where(ResearchArtifact.chapter_number.is_(None))
        artifact = (await self.session.execute(statement.order_by(desc(ResearchArtifact.created_at)).limit(1))).scalar_one_or_none()
        if not artifact:
            return None
        if self._artifact_is_stale(artifact):
            return await self.mark_artifact_interrupted(project_id, artifact.run_id, force=True)
        return self._artifact_read(artifact)

    async def mark_artifact_interrupted(
        self,
        project_id: str,
        run_id: str,
        *,
        force: bool = False,
    ) -> Optional[ResearchArtifactRead]:
        statement = select(ResearchArtifact).where(
            ResearchArtifact.project_id == project_id,
            ResearchArtifact.run_id == run_id,
        )
        artifact = (await self.session.execute(statement)).scalar_one_or_none()
        if not artifact or artifact.status not in {"queued", "running"}:
            return self._artifact_read(artifact) if artifact else None
        if not force and not self._artifact_is_stale(artifact):
            return self._artifact_read(artifact)
        artifact.status = "failed"
        artifact.error = {
            "code": "research_job_interrupted",
            "message": "研究任务心跳超时，服务可能已重启或任务进程已中断，请重新运行",
            "retryable": True,
        }
        artifact.finished_at = self._now()
        await self.session.commit()
        await self.session.refresh(artifact)
        return self._artifact_read(artifact)

    async def mark_artifact_cancelled(self, project_id: str, run_id: str) -> Optional[ResearchArtifactRead]:
        statement = select(ResearchArtifact).where(
            ResearchArtifact.project_id == project_id,
            ResearchArtifact.run_id == run_id,
        )
        artifact = (await self.session.execute(statement)).scalar_one_or_none()
        if not artifact:
            return None
        if artifact.status not in {"queued", "running"}:
            return self._artifact_read(artifact)
        artifact.status = "cancelled"
        artifact.error = {"code": "research_cancelled", "message": "研究任务已取消"}
        artifact.finished_at = self._now()
        await self.session.commit()
        await self.session.refresh(artifact)
        return self._artifact_read(artifact)

    async def run_research(
        self,
        *,
        project_id: str,
        user_id: int,
        scope: str,
        chapter_number: Optional[int] = None,
        consent: bool = False,
        force: bool = False,
        trigger: str = "manual",
        context: Optional[Dict[str, Any]] = None,
        run_id: Optional[str] = None,
    ) -> ResearchArtifactRead:
        config = await self.get_or_create_config(project_id)
        pending_artifact = await self.session.execute(select(ResearchArtifact).where(ResearchArtifact.run_id == run_id)) if run_id else None
        pending = pending_artifact.scalar_one_or_none() if pending_artifact else None
        run, reason = self.should_run(config, scope, consent=consent, force=force)
        if not run:
            if reason == "consent_required":
                raise ResearchConsentRequired("当前项目研究模式为每次询问，需要用户同意后才能联网检索")
            return ResearchArtifactRead(
                id=0, run_id="", project_id=project_id, scope=scope,
                chapter_number=chapter_number, status="skipped", trigger=trigger, summary=reason,
            )
        if scope == "chapter" and not chapter_number:
            raise ValueError("chapter scope requires chapter_number")
        merged_context = await self._build_project_context(project_id, chapter_number)
        if context:
            merged_context.update(context)
        # Fingerprint based on project context only, not previous research state
        _fp_context = {k: v for k, v in merged_context.items() if k != "previous_research"}
        fingerprint = hashlib.sha256(self._context_text(_fp_context).encode("utf-8")).hexdigest()[:16]
        if not force:
            statement = select(ResearchArtifact).where(
                ResearchArtifact.project_id == project_id,
                ResearchArtifact.scope == scope,
                ResearchArtifact.status.in_(("successful", "degraded")),
            )
            if chapter_number is not None:
                statement = statement.where(ResearchArtifact.chapter_number == chapter_number)
            existing = (await self.session.execute(statement.order_by(desc(ResearchArtifact.created_at)).limit(1))).scalar_one_or_none()
            if existing and (existing.provider_metadata or {}).get("context_fingerprint") == fingerprint:
                if pending and pending.id != existing.id:
                    pending.status = existing.status
                    pending.query_plan = list(existing.query_plan or [])
                    pending.sources = list(existing.sources or [])
                    pending.category_payload = dict(existing.category_payload or {})
                    pending.summary = existing.summary
                    pending.file_manifest = dict(existing.file_manifest or {})
                    pending.provider_metadata = {
                        **(existing.provider_metadata or {}),
                        **(pending.provider_metadata or {}),
                        "context_fingerprint": fingerprint,
                        "execution_reason": reason,
                        "reused_from_run_id": existing.run_id,
                        "heartbeat_at": self._now().isoformat(),
                    }
                    pending.error = existing.error
                    pending.finished_at = self._now()
                    await self.session.commit()
                    await self.session.refresh(pending)
                    return self._artifact_read(pending)
                return self._artifact_read(existing)
        artifact = pending or ResearchArtifact(
            run_id=run_id or str(uuid.uuid4()), project_id=project_id, user_id=user_id,
            scope=scope, chapter_number=chapter_number, status="running", trigger=trigger,
            provider_metadata={"context_fingerprint": fingerprint, "execution_reason": reason},
        )
        artifact.status = "running"
        artifact.provider_metadata = {
            **(artifact.provider_metadata or {}),
            "context_fingerprint": fingerprint,
            "execution_reason": reason,
            "heartbeat_at": self._now().isoformat(),
        }
        if pending is None:
            self.session.add(artifact)
        await self.session.commit()
        await self.session.refresh(artifact)
        try:
            # Phase 1: Build query plan and execute searches
            plan = self.build_query_plan(merged_context, scope, list(config.category_preferences or []))
            search_batches = await self.search_client.search_all(config, plan)

            # Update heartbeat after search completes (prevents stale detection during synthesis)
            artifact.provider_metadata = {
                **(artifact.provider_metadata or {}),
                "heartbeat_at": self._now().isoformat(),
                "phase": "synthesizing",
                "search_completed": True,
            }
            await self.session.commit()
            await self.session.refresh(artifact)

            # Phase 2: Flatten and synthesize sources
            sources = self._flatten_sources(search_batches)

            # Update heartbeat before LLM call (synthesis can take time)
            artifact.provider_metadata = {
                **(artifact.provider_metadata or {}),
                "heartbeat_at": self._now().isoformat(),
                "phase": "llm_synthesis",
                "source_count": len(sources),
            }
            await self.session.commit()

            synthesis, synth_meta = await self._synthesize(config, merged_context, scope, sources, user_id)

            # Phase 3: Write archive and finalize
            manifest = ResearchArchive.write_run(
                project_id=project_id, run_id=artifact.run_id, scope=scope,
                chapter_number=chapter_number, plan=plan, search_batches=search_batches,
                sources=sources, synthesis=synthesis,
            )
            artifact.status = "successful" if sources else "degraded"
            artifact.query_plan = plan
            artifact.sources = sources[:100]  # Limit stored sources to prevent DB bloat
            artifact.category_payload = synthesis
            artifact.summary = str(synthesis.get("summary") or "")[:5000]
            artifact.file_manifest = manifest
            artifact.provider_metadata = {
                **(artifact.provider_metadata or {}), **synth_meta,
                "search_provider": config.search_provider,
                "search_batch_count": len(search_batches), "source_count": len(sources),
                "failed_query_count": sum(1 for item in search_batches if item.get("status") == "failed"),
                "provider_priority": ["search_api_key", "research_llm_api_key", "writing_llm_api_key"],
                "local_model_used": False,
                "heartbeat_at": self._now().isoformat(),
                "phase": "completed",
            }
            artifact.finished_at = self._now()
            await self.session.commit()
            await self.session.refresh(artifact)
            return self._artifact_read(artifact)
        except asyncio.CancelledError:
            artifact.status = "cancelled"
            artifact.error = {"code": "research_cancelled", "message": "研究任务已取消"}
            artifact.finished_at = self._now()
            await self.session.commit()
            await self.session.refresh(artifact)
            raise
        except Exception as exc:
            artifact.status = "failed"
            artifact.error = {"code": "research_failed", "message": str(exc)[:1000], "retryable": True}
            artifact.finished_at = self._now()
            await self.session.commit()
            await self.session.refresh(artifact)
            logger.exception("Project research failed: project=%s scope=%s chapter=%s", project_id, scope, chapter_number)
            return self._artifact_read(artifact)

    async def get_artifact(self, project_id: str, run_id: str) -> Optional[ResearchArtifactRead]:
        statement = select(ResearchArtifact).where(
            ResearchArtifact.project_id == project_id,
            ResearchArtifact.run_id == run_id,
        )
        artifact = (await self.session.execute(statement)).scalar_one_or_none()
        return self._artifact_read(artifact) if artifact else None

    async def list_artifacts(
        self,
        project_id: str,
        *,
        scope: Optional[str] = None,
        chapter_number: Optional[int] = None,
    ) -> List[ResearchArtifactRead]:
        statement = select(ResearchArtifact).where(ResearchArtifact.project_id == project_id)
        if scope:
            statement = statement.where(ResearchArtifact.scope == scope)
        if chapter_number is not None:
            statement = statement.where(ResearchArtifact.chapter_number == chapter_number)
        artifacts = list((await self.session.execute(statement.order_by(desc(ResearchArtifact.created_at)).limit(100))).scalars().all())
        return [self._artifact_read(item) for item in artifacts]

    async def build_prompt_context(
        self,
        project_id: str,
        chapter_number: Optional[int],
        *,
        scope: Optional[str] = None,
        max_chars: int = 6500,
    ) -> tuple[str, Dict[str, Any]]:
        """Build research context for novel generation prompt.

        Returns a tuple of (context_text, metadata) where context_text is
        formatted for inclusion in the generation prompt, and metadata
        provides information about the research artifacts used.
        """
        artifacts: List[ResearchArtifact] = []
        if scope:
            if scope == "chapter":
                chapter_filter = ResearchArtifact.chapter_number == chapter_number
            else:
                chapter_filter = ResearchArtifact.chapter_number.is_(None)
            scope_filters = ((scope, chapter_filter),)
        else:
            scope_filters = (
                ("global", ResearchArtifact.chapter_number.is_(None)),
                ("enhanced", ResearchArtifact.chapter_number.is_(None)),
                ("chapter", ResearchArtifact.chapter_number == chapter_number),
            )
        try:
            for requested_scope, chapter_filter in scope_filters:
                statement = (
                    select(ResearchArtifact)
                    .where(
                        ResearchArtifact.project_id == project_id,
                        ResearchArtifact.status.in_(("successful", "degraded")),
                        ResearchArtifact.scope == requested_scope,
                        chapter_filter,
                    )
                    .order_by(desc(ResearchArtifact.created_at), desc(ResearchArtifact.id))
                    .limit(1)
                )
                artifact = (await self.session.execute(statement)).scalar_one_or_none()
                if artifact is not None:
                    artifacts.append(artifact)
        except Exception as exc:  # archive context is an optional dependency of generation
            logger.warning("研究归档读取失败，降级为空上下文: project=%s error=%s", project_id, exc)
            return "", {
                "artifact_count": 0,
                "artifact_scopes": [],
                "artifact_run_ids": [],
                "source_urls": [],
                "context_chars": 0,
                "archive_error": str(exc),
            }

        if not artifacts:
            return "", {
                "artifact_count": 0,
                "artifact_scopes": [],
                "artifact_run_ids": [],
                "source_urls": [],
                "context_chars": 0,
            }

        sections: List[str] = []
        source_urls: List[str] = []
        total_insights = 0

        for artifact in artifacts:
            payload = artifact.category_payload or {}
            summary = str(payload.get("summary") or artifact.summary or "").strip()
            if summary:
                sections.append(f"[{artifact.scope}研究摘要]\n{summary}")

            categories = payload.get("categories") if isinstance(payload.get("categories"), dict) else {}
            for category, cards in categories.items():
                if not isinstance(cards, list):
                    continue
                for card in cards[:3]:
                    if not isinstance(card, dict):
                        continue
                    insight = str(card.get("insight") or "").strip()
                    usage = str(card.get("usage") or "").strip()
                    fact_type = str(card.get("fact_type") or "unknown")
                    if insight:
                        total_insights += 1
                        type_label = "事实" if fact_type == "fact" else "建议" if fact_type == "suggestion" else "待核验"
                        sections.append(
                            f"- [{type_label}]{CATEGORY_LABELS.get(category, category)}：{insight}\n"
                            f"  用法：{usage}\n"
                            f"  核验：使用前打开来源页复核"
                        )
                    for url in (card.get("source_urls") or []):
                        if url:
                            source_urls.append(str(url))

        if not sections:
            return "", {
                "artifact_count": len(artifacts),
                "artifact_scopes": [a.scope for a in artifacts],
                "artifact_run_ids": [a.run_id for a in artifacts],
                "source_urls": [],
                "context_chars": 0,
            }

        header = "## 研究资料（请结合以下资料创作，引用事实前需核验来源）\n"
        text = header + "\n".join(sections)
        return text[:max_chars], {
            "artifact_count": len(artifacts),
            "artifact_scopes": [artifact.scope for artifact in artifacts],
            "artifact_run_ids": [artifact.run_id for artifact in artifacts],
            "source_urls": list(dict.fromkeys(source_urls))[:30],
            "context_chars": min(len(text), max_chars),
            "insight_count": total_insights,
        }

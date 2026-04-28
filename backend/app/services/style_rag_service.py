# AIMETA P=风格学习RAG服务_文风提取和注入|R=风格提取_风格向量存储_风格注入|NR=不含持久化|E=StyleRAGService|X=internal|A=风格学习核心|D=llm_service,embedding_service|S=none|RD=./README.ai
"""
风格学习 RAG 服务 (StyleRAGService)

实现从用户文本中提取写作风格特征，并在生成时注入风格上下文。
核心思想：学习用户已有文风，让 AI 生成的内容更符合用户的写作风格。

功能：
1. 风格提取：分析用户选定章节，提取写作风格特征
2. 风格向量存储：将风格特征存入数据库
3. 风格注入：在生成时注入风格上下文
"""
import json
import logging
import zipfile
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict, List, Optional
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .llm_service import LLMService
from ..models.project_memory import ProjectMemory
from ..models.user_style_library import UserStyleLibrary
from ..utils.json_utils import remove_think_tags, sanitize_json_like_text, unwrap_markdown_json

logger = logging.getLogger(__name__)


# ==================== 提示词模板 ====================

STYLE_EXTRACTION_PROMPT = """\
请分析以下小说文本，提取作者的写作风格特征。

## 分析文本：
{text_content}

## 要求：
请忽略具体人物名、专有设定和情节事实，专注总结表达方式、叙事方式、句法节奏与描写偏好。
请从以下6个维度分析写作风格，返回JSON格式：

{{
    "vocabulary_preference": {{
        "common_words": ["常用词汇列表"],
        "formal_words": ["正式词汇"],
        "colloquial_words": ["口语化词汇"],
        "description": "词汇偏好描述（50字以内）"
    }},
    "sentence_pattern": {{
        "avg_length": "平均句子长度（短/中/长）",
        "complexity": "复杂程度（简单/中等/复杂）",
        "use_punctuation": "标点使用特点",
        "description": "句式特点描述（50字以内）"
    }},
    "narrative_voice": {{
        "perspective": "视角（第一人称/第三人称/全知视角等）",
        "tone": "语气（客观/主观/抒情等）",
        "distance": "叙事距离（近距离/远距离/自由切换）",
        "description": "叙事特点描述（50字以内）"
    }},
    "dialogue_style": {{
        "format": "对话格式（直接引语/间接引语/混合）",
        "dialect": "方言使用（无/少量/大量）",
        "informality": "正式程度（正式/随意/混合）",
        "description": "对话特点描述（50字以内）"
    }},
    "description_technique": {{
        "sensory_detail": "感官细节（视觉/听觉/嗅觉/触觉/味觉）",
        "metaphor_use": "比喻使用频率（少/中等/多）",
        "adjective_usage": "形容词使用（简洁/适中/丰富）",
        "description": "描写技巧描述（50字以内）"
    }},
    "rhythm_pacing": {{
        "scene_length": "场景长度（短/中/长）",
        "variation": "节奏变化（平稳/有变化/多变）",
        "action_frequency": "动作频率（频繁/适中/较少）",
        "description": "节奏特点描述（50字以内）"
    }}
}}

请仅返回JSON，不要其他内容。
"""


STYLE_INJECTION_PROMPT = """\
你是一位文风控制专家。请根据以下写作风格特征，以相近的表达气质续写小说。

## 写作风格特征：
{style_features}

## 续写要求：
- 借鉴表达风格，不要照搬参考文本原句
- 保持词汇偏好、句式特点、叙事视角的一致性
- 对话风格和描写技巧也要尽量贴近
- 风格必须服务于当前项目剧情，不能篡改既定人物、世界观和事实

## 已有内容：
{existing_content}

## 续写方向：
{direction}

请续写 500-1000 字：
"""


class StyleFeature:
    """风格特征数据类"""
    def __init__(self, data: Dict[str, Any]):
        self.vocabulary_preference = data.get("vocabulary_preference", {})
        self.sentence_pattern = data.get("sentence_pattern", {})
        self.narrative_voice = data.get("narrative_voice", {})
        self.dialogue_style = data.get("dialogue_style", {})
        self.description_technique = data.get("description_technique", {})
        self.rhythm_pacing = data.get("rhythm_pacing", {})

    def to_prompt_context(self) -> str:
        """转换为提示词上下文"""
        lines = ["写作风格特征："]
        lines.append(f"- 词汇偏好：{self.vocabulary_preference.get('description', '无')}")
        lines.append(f"- 句式特点：{self.sentence_pattern.get('description', '无')}")
        lines.append(f"- 叙事视角：{self.narrative_voice.get('description', '无')}")
        lines.append(f"- 对话风格：{self.dialogue_style.get('description', '无')}")
        lines.append(f"- 描写技巧：{self.description_technique.get('description', '无')}")
        lines.append(f"- 节奏特点：{self.rhythm_pacing.get('description', '无')}")
        return "\n".join(lines)

    def to_summary_dict(self) -> Dict[str, str]:
        return {
            "vocabulary": self.vocabulary_preference.get("description", ""),
            "sentence": self.sentence_pattern.get("description", ""),
            "narrative": self.narrative_voice.get("description", ""),
            "dialogue": self.dialogue_style.get("description", ""),
            "description": self.description_technique.get("description", ""),
            "rhythm": self.rhythm_pacing.get("description", ""),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vocabulary_preference": self.vocabulary_preference,
            "sentence_pattern": self.sentence_pattern,
            "narrative_voice": self.narrative_voice,
            "dialogue_style": self.dialogue_style,
            "description_technique": self.description_technique,
            "rhythm_pacing": self.rhythm_pacing,
        }


class StyleSource:
    """外部文风来源"""

    def __init__(self, data: Dict[str, Any]):
        self.id = data.get("id") or f"style-src-{uuid4().hex[:12]}"
        self.source_type = data.get("source_type", "external_text")
        self.title = data.get("title") or "未命名参考文本"
        self.content_text = data.get("content_text", "")
        self.char_count = int(data.get("char_count") or len(self.content_text))
        self.created_at = data.get("created_at") or datetime.now(timezone.utc).isoformat()
        self.updated_at = data.get("updated_at") or self.created_at
        self.extra = data.get("extra") or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_type": self.source_type,
            "title": self.title,
            "content_text": self.content_text,
            "char_count": self.char_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "extra": self.extra,
        }


class StyleProfile:
    """风格画像"""

    def __init__(self, data: Dict[str, Any]):
        self.id = data.get("id") or f"style-profile-{uuid4().hex[:12]}"
        self.name = data.get("name") or "外部参考文风"
        self.profile_type = data.get("profile_type", "external")
        self.source_ids = list(data.get("source_ids") or [])
        self.summary = data.get("summary") or {}
        self.style_feature = data.get("style_feature") or {}
        self.prompt_context = data.get("prompt_context") or ""
        self.quality_metrics = data.get("quality_metrics") or {}
        self.extra = data.get("extra") or {}
        self.created_at = data.get("created_at") or datetime.now(timezone.utc).isoformat()
        self.updated_at = data.get("updated_at") or self.created_at
        self.active = bool(data.get("active", False))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "profile_type": self.profile_type,
            "source_ids": self.source_ids,
            "summary": self.summary,
            "style_feature": self.style_feature,
            "prompt_context": self.prompt_context,
            "quality_metrics": self.quality_metrics,
            "extra": self.extra,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "active": self.active,
        }


# ==================== 数据库模型引用 ====================
# 注意：需要在 models 中创建 StyleProfile 表
# 这里使用简单的 JSON 存储，实际项目中可以用独立的数据库表


class StyleRAGService:
    """
    风格学习 RAG 服务

    负责提取用户写作风格、存储风格配置、在生成时注入风格。
    同时兼容外部参考文本、整本小说导入后的文风提取与激活。
    其中外部参考素材与画像为用户级永久资产，应用目标可选择全局或单项目。
    """

    SUPPORTED_TEXT_SUFFIXES = {'.txt', '.md', '.markdown', '.json', '.csv', '.log', '.text'}
    SUPPORTED_COMPLEX_SUFFIXES = {'.docx', '.epub'}

    def __init__(
        self,
        db: AsyncSession,
        llm_service: LLMService
    ):
        self.db = db
        self.llm_service = llm_service

    async def extract_style_from_chapters(
        self,
        project_id: str,
        chapter_numbers: List[int],
        user_id: int
    ) -> StyleFeature:
        """
        从指定章节提取写作风格特征

        Args:
            project_id: 项目ID
            chapter_numbers: 要分析的章节号列表
            user_id: 用户ID

        Returns:
            StyleFeature: 提取的风格特征
        """
        from ..models.novel import Chapter

        # 获取章节内容
        result = await self.db.execute(
            select(Chapter)
            .options(selectinload(Chapter.selected_version), selectinload(Chapter.versions))
            .where(
                Chapter.project_id == project_id,
                Chapter.chapter_number.in_(chapter_numbers)
            )
        )
        chapters = result.scalars().all()

        if not chapters:
            raise ValueError("未找到指定章节")

        # 合并章节内容（取前5000字，避免过长）
        combined_text = ""
        for ch in chapters:
            chapter_content = ""
            if ch.selected_version and ch.selected_version.content:
                chapter_content = ch.selected_version.content
            elif ch.versions:
                latest_version = sorted(ch.versions, key=lambda item: item.created_at or 0)[-1]
                chapter_content = latest_version.content or ""
            if chapter_content:
                combined_text += chapter_content + "\n\n"
                if len(combined_text) > 5000:
                    break

        if not combined_text.strip():
            raise ValueError("章节内容为空")

        # 调用 LLM 提取风格
        prompt = STYLE_EXTRACTION_PROMPT.format(
            text_content=combined_text[:3000]
        )

        try:
            response = await self.llm_service.generate(
                prompt=prompt,
                user_id=user_id,
                max_tokens=2000,
                temperature=0.3
            )

            if response:
                style_data = self._parse_json_response(response)
                if style_data:
                    style_feature = StyleFeature(style_data)
                    await self._save_style_feature(project_id, style_feature)
                    return style_feature

        except Exception as e:
            logger.error(f"风格提取失败: {e}")

        raise ValueError("风格提取失败")

    async def generate_with_style(
        self,
        project_id: str,
        existing_content: str,
        direction: str,
        user_id: int,
        max_tokens: int = 2000
    ) -> str:
        """
        带风格上下文的续写

        Args:
            project_id: 项目ID
            existing_content: 已有内容
            direction: 续写方向
            user_id: 用户ID
            max_tokens: 最大生成token数

        Returns:
            str: 续写内容
        """
        # 获取风格特征（优先使用当前激活的外部风格画像，其次回退到旧的项目内风格）
        style_feature = await self.get_effective_style_for_project(project_id, user_id)

        if not style_feature:
            logger.warning(f"项目 {project_id} 没有风格配置，使用默认生成")
            return existing_content

        style_context = style_feature.to_prompt_context()

        prompt = STYLE_INJECTION_PROMPT.format(
            style_features=style_context,
            existing_content=existing_content[-1000:] if existing_content else "",
            direction=direction
        )

        try:
            response = await self.llm_service.generate(
                prompt=prompt,
                user_id=user_id,
                max_tokens=max_tokens,
                temperature=0.7
            )

            cleaned = remove_think_tags(response) if response else ""
            return cleaned.strip() if cleaned else ""

        except Exception as e:
            logger.error(f"风格化生成失败: {e}")
            raise

    async def _get_project_memory(self, project_id: str) -> ProjectMemory:
        result = await self.db.execute(
            select(ProjectMemory).where(ProjectMemory.project_id == project_id)
        )
        memory = result.scalar_one_or_none()
        if memory is None:
            memory = ProjectMemory(project_id=project_id, version=1, extra={})
            self.db.add(memory)
            await self.db.flush()
        return memory

    async def _save_style_feature(
        self,
        project_id: str,
        style_feature: StyleFeature
    ) -> None:
        memory = await self._get_project_memory(project_id)
        extra = dict(memory.extra or {})
        extra["style_feature"] = style_feature.to_dict()
        memory.extra = extra
        await self.db.commit()
        await self.db.refresh(memory)

    async def _get_project_extra(self, project_id: str) -> Dict[str, Any]:
        result = await self.db.execute(
            select(ProjectMemory.extra).where(ProjectMemory.project_id == project_id)
        )
        extra = result.scalar_one_or_none()
        return extra if isinstance(extra, dict) else {}

    async def _save_project_extra(self, project_id: str, extra: Dict[str, Any]) -> None:
        memory = await self._get_project_memory(project_id)
        memory.extra = extra
        await self.db.commit()
        await self.db.refresh(memory)

    async def _get_user_style_library(self, user_id: int) -> UserStyleLibrary:
        library = await self.db.get(UserStyleLibrary, user_id)
        if library is None:
            library = UserStyleLibrary(user_id=user_id)
            self.db.add(library)
            await self.db.flush()
        return library

    @staticmethod
    def _deserialize_json_list(raw_value: Optional[str], item_cls):
        if not raw_value:
            return []
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError:
            logger.warning("用户文风素材库 JSON 解析失败，已按空列表回退")
            return []
        if not isinstance(payload, list):
            return []
        return [item_cls(item) for item in payload if isinstance(item, dict)]

    async def _save_user_sources(self, user_id: int, sources: List[StyleSource]) -> None:
        library = await self._get_user_style_library(user_id)
        library.style_sources_json = json.dumps([source.to_dict() for source in sources], ensure_ascii=False)
        await self.db.commit()
        await self.db.refresh(library)

    async def _save_user_profiles(self, user_id: int, profiles: List[StyleProfile]) -> None:
        library = await self._get_user_style_library(user_id)
        library.style_profiles_json = json.dumps([profile.to_dict() for profile in profiles], ensure_ascii=False)
        await self.db.commit()
        await self.db.refresh(library)

    async def _save_global_active_profile_id(self, user_id: int, profile_id: Optional[str]) -> None:
        library = await self._get_user_style_library(user_id)
        library.global_active_profile_id = profile_id
        await self.db.commit()
        await self.db.refresh(library)

    async def list_style_sources(self, user_id: int) -> List[StyleSource]:
        library = await self.db.get(UserStyleLibrary, user_id)
        if library is None:
            return []
        return self._deserialize_json_list(library.style_sources_json, StyleSource)

    def extract_text_from_uploaded_file(self, filename: str, content: bytes) -> Dict[str, Any]:
        suffix = self._get_file_suffix(filename)
        if suffix in self.SUPPORTED_TEXT_SUFFIXES:
            text = self._decode_text_bytes(content)
        elif suffix == '.docx':
            text = self._extract_docx_text(content)
        elif suffix == '.epub':
            text = self._extract_epub_text(content)
        else:
            raise ValueError('暂不支持该文件格式，请先转为 txt / md / docx / epub')

        normalized = text.replace('\r\n', '\n').strip()
        if not normalized:
            raise ValueError('文件内容为空或无法提取正文')

        return {
            'text': normalized,
            'format': suffix.lstrip('.'),
            'char_count': len(normalized),
        }

    def _get_file_suffix(self, filename: str) -> str:
        name = (filename or '').strip().lower()
        dot_index = name.rfind('.')
        return name[dot_index:] if dot_index >= 0 else ''

    def _decode_text_bytes(self, content: bytes) -> str:
        for encoding in ('utf-8', 'utf-8-sig', 'gb18030', 'gbk'):
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        return content.decode('utf-8', errors='ignore')

    def _extract_docx_text(self, content: bytes) -> str:
        try:
            from docx import Document
        except ImportError as exc:
            raise ValueError('服务器未安装 DOCX 解析依赖') from exc

        document = Document(BytesIO(content))
        paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text and paragraph.text.strip()]
        return '\n\n'.join(paragraphs)

    def _extract_epub_text(self, content: bytes) -> str:
        try:
            with zipfile.ZipFile(BytesIO(content)) as archive:
                html_entries = [
                    name for name in archive.namelist()
                    if name.lower().endswith(('.xhtml', '.html', '.htm')) and not name.startswith('__MACOSX/')
                ]
                texts: List[str] = []
                for name in html_entries:
                    raw = archive.read(name)
                    decoded = self._decode_text_bytes(raw)
                    cleaned = self._strip_html_tags(decoded)
                    if cleaned.strip():
                        texts.append(cleaned.strip())
                return '\n\n'.join(texts)
        except zipfile.BadZipFile as exc:
            raise ValueError('EPUB 文件损坏或格式非法') from exc

    def _strip_html_tags(self, html: str) -> str:
        import re
        no_scripts = re.sub(r'<(script|style)[^>]*?>[\s\S]*?</\1>', ' ', html, flags=re.IGNORECASE)
        no_tags = re.sub(r'<[^>]+>', ' ', no_scripts)
        collapsed = re.sub(r'\s+', ' ', no_tags)
        return collapsed.strip()

    async def create_external_style_source(
        self,
        user_id: int,
        *,
        title: str,
        content_text: str,
        source_type: str = "external_text",
        extra: Optional[Dict[str, Any]] = None,
    ) -> StyleSource:
        normalized_type = (source_type or "external_text").strip() or "external_text"
        cleaned_text = (content_text or "").strip()
        normalized_extra = dict(extra or {})
        is_batch_note = bool(normalized_extra.get("is_batch_note"))
        min_chars = 500
        max_chars = 50000
        default_title = "未命名参考文本"
        if normalized_type == "external_novel":
            min_chars = 5000
            max_chars = 200000
            default_title = "未命名整书参考"
        if is_batch_note:
            min_chars = 20
            max_chars = 50000

        if len(cleaned_text) < min_chars:
            raise ValueError(f"参考文本至少需要 {min_chars} 字")
        if len(cleaned_text) > max_chars:
            cleaned_text = cleaned_text[:max_chars]

        sources = await self.list_style_sources(user_id)
        source = StyleSource({
            "title": title.strip() or default_title,
            "source_type": normalized_type,
            "content_text": cleaned_text,
            "char_count": len(cleaned_text),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "extra": {
                "import_scope": "full_novel" if normalized_type == "external_novel" else "excerpt",
                **normalized_extra,
            },
        })
        sources.append(source)
        await self._save_user_sources(user_id, sources)
        return source

    async def delete_style_source(self, user_id: int, source_id: str) -> bool:
        sources = await self.list_style_sources(user_id)
        kept_sources = [source for source in sources if source.id != source_id]
        if len(kept_sources) == len(sources):
            return False

        profiles = await self.list_style_profiles(user_id)
        updated_profiles: List[StyleProfile] = []
        removed_profile_ids: set[str] = set()
        for profile in profiles:
            if source_id not in profile.source_ids:
                updated_profiles.append(profile)
                continue

            remaining_source_ids = [item for item in profile.source_ids if item != source_id]
            if not remaining_source_ids:
                removed_profile_ids.add(profile.id)
                continue

            profile.source_ids = remaining_source_ids
            if profile.extra.get("source_titles"):
                remaining_titles = [
                    source.title for source in kept_sources if source.id in remaining_source_ids and source.title
                ]
                profile.extra = {
                    **profile.extra,
                    "source_titles": remaining_titles,
                }
            profile.updated_at = datetime.now(timezone.utc).isoformat()
            updated_profiles.append(profile)

        await self._save_user_sources(user_id, kept_sources)
        await self._save_user_profiles(user_id, updated_profiles)

        library = await self._get_user_style_library(user_id)
        if library.global_active_profile_id in removed_profile_ids:
            await self._save_global_active_profile_id(user_id, None)

        result = await self.db.execute(select(ProjectMemory).where(ProjectMemory.extra.is_not(None)))
        memories = result.scalars().all()
        changed = False
        for memory in memories:
            extra = dict(memory.extra or {})
            if extra.get("applied_style_profile_id") in removed_profile_ids:
                extra.pop("applied_style_profile_id", None)
                extra.pop("style_application_mode", None)
                memory.extra = extra
                changed = True
        if changed:
            await self.db.commit()

        return True

    async def list_style_profiles(self, user_id: int) -> List[StyleProfile]:
        library = await self.db.get(UserStyleLibrary, user_id)
        if library is None:
            return []
        profiles = self._deserialize_json_list(library.style_profiles_json, StyleProfile)
        global_active_id = library.global_active_profile_id
        for profile in profiles:
            profile.active = profile.id == global_active_id
        return profiles

    async def create_profile_from_sources(
        self,
        user_id: int,
        *,
        source_ids: List[str],
        name: Optional[str] = None,
        append_to_profile_id: Optional[str] = None,
    ) -> StyleProfile:
        sources = await self.list_style_sources(user_id)
        selected = [source for source in sources if source.id in source_ids]
        if not selected:
            raise ValueError("未找到可用的参考文本")

        profiles = await self.list_style_profiles(user_id)
        existing_profile = next((profile for profile in profiles if profile.id == append_to_profile_id), None) if append_to_profile_id else None

        combined_segments: List[str] = []
        if existing_profile and existing_profile.prompt_context:
            combined_segments.append(f"已有画像摘要：\n{existing_profile.prompt_context}")
        combined_segments.extend(source.content_text for source in selected if source.content_text)
        combined_text = "\n\n".join(segment for segment in combined_segments if segment).strip()

        min_chars = 5000 if any(source.source_type == "external_novel" for source in selected) else 500
        if any(bool((source.extra or {}).get("is_batch_note")) for source in selected):
            min_chars = 20
        if len(combined_text) < min_chars:
            raise ValueError("参考文本内容不足，无法提取文风")

        prompt = STYLE_EXTRACTION_PROMPT.format(text_content=combined_text[:12000])
        response = await self.llm_service.generate(
            prompt=prompt,
            user_id=user_id,
            max_tokens=2000,
            temperature=0.3,
        )
        style_data = self._parse_json_response(response or "")
        if not style_data:
            raise ValueError("外部参考文风提取失败")

        style_feature = StyleFeature(style_data)
        source_titles = [source.title for source in selected if source.title]
        now = datetime.now(timezone.utc).isoformat()

        if existing_profile:
            merged_source_ids = list(dict.fromkeys([*existing_profile.source_ids, *[source.id for source in selected]]))
            merged_source_titles = list(dict.fromkeys([*(existing_profile.extra.get("source_titles", []) or []), *source_titles]))
            previous_chars = int((existing_profile.quality_metrics or {}).get("total_chars") or 0)
            existing_profile.name = (name or existing_profile.name or selected[0].title or "外部参考文风").strip()
            existing_profile.source_ids = merged_source_ids
            existing_profile.summary = style_feature.to_summary_dict()
            existing_profile.style_feature = style_feature.to_dict()
            existing_profile.prompt_context = style_feature.to_prompt_context()
            existing_profile.quality_metrics = {
                **(existing_profile.quality_metrics or {}),
                "source_count": len(merged_source_ids),
                "total_chars": previous_chars + sum(source.char_count for source in selected),
                "merge_rounds": int((existing_profile.quality_metrics or {}).get("merge_rounds") or 0) + 1,
            }
            existing_profile.extra = {
                **(existing_profile.extra or {}),
                "source_titles": merged_source_titles,
                "profile_mode": "incremental",
            }
            existing_profile.updated_at = now
            await self._save_user_profiles(user_id, profiles)
            return existing_profile

        profile = StyleProfile({
            "name": (name or selected[0].title or "外部参考文风").strip(),
            "profile_type": "external",
            "source_ids": [source.id for source in selected],
            "summary": style_feature.to_summary_dict(),
            "style_feature": style_feature.to_dict(),
            "prompt_context": style_feature.to_prompt_context(),
            "quality_metrics": {
                "source_count": len(selected),
                "total_chars": sum(source.char_count for source in selected),
                "merge_rounds": 1,
            },
            "created_at": now,
            "updated_at": now,
            "extra": {
                "source_titles": source_titles,
                "profile_mode": "incremental",
            },
        })

        for item in profiles:
            item.active = False
        profiles.append(profile)
        await self._save_user_profiles(user_id, profiles)
        return profile

    async def update_style_profile(
        self,
        user_id: int,
        *,
        profile_id: str,
        name: Optional[str] = None,
        summary: Optional[Dict[str, str]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> StyleProfile:
        profiles = await self.list_style_profiles(user_id)
        selected = next((profile for profile in profiles if profile.id == profile_id), None)
        if not selected:
            raise ValueError('未找到指定风格画像')

        if name is not None and name.strip():
            selected.name = name.strip()
        if summary:
            selected.summary = {**(selected.summary or {}), **summary}
        if extra:
            selected.extra = {**(selected.extra or {}), **extra}
        selected.updated_at = datetime.now(timezone.utc).isoformat()
        await self._save_user_profiles(user_id, profiles)
        return selected

    async def apply_style_profile(
        self,
        *,
        user_id: int,
        profile_id: str,
        scope: str,
        project_id: Optional[str] = None,
    ) -> StyleProfile:
        profiles = await self.list_style_profiles(user_id)
        selected = next((profile for profile in profiles if profile.id == profile_id), None)
        if not selected:
            raise ValueError("未找到指定风格画像")

        now = datetime.now(timezone.utc).isoformat()
        selected.updated_at = now
        if scope == "global":
            await self._save_global_active_profile_id(user_id, profile_id)
            return selected
        if scope == "project":
            if not project_id:
                raise ValueError("项目级应用缺少 project_id")
            extra = await self._get_project_extra(project_id)
            extra["style_application_mode"] = "project"
            extra["applied_style_profile_id"] = profile_id
            await self._save_project_extra(project_id, extra)
            return selected
        raise ValueError("不支持的应用范围")

    async def clear_style_application(self, *, user_id: int, scope: str, project_id: Optional[str] = None) -> None:
        if scope == "global":
            await self._save_global_active_profile_id(user_id, None)
            return
        if scope == "project":
            if not project_id:
                raise ValueError("项目级清理缺少 project_id")
            extra = await self._get_project_extra(project_id)
            extra.pop("style_application_mode", None)
            extra.pop("applied_style_profile_id", None)
            await self._save_project_extra(project_id, extra)
            return
        raise ValueError("不支持的清理范围")

    async def activate_style_profile(self, project_id: str, profile_id: str, user_id: int) -> StyleProfile:
        return await self.apply_style_profile(
            user_id=user_id,
            profile_id=profile_id,
            scope="project",
            project_id=project_id,
        )

    async def clear_active_style_profile(self, project_id: str, user_id: int) -> None:
        await self.clear_style_application(user_id=user_id, scope="project", project_id=project_id)

    async def get_active_style_profile(self, project_id: str, user_id: int) -> Optional[StyleProfile]:
        return await self.get_project_applied_style_profile(project_id, user_id)

    async def get_global_active_style_profile(self, user_id: int) -> Optional[StyleProfile]:
        library = await self.db.get(UserStyleLibrary, user_id)
        if library is None or not library.global_active_profile_id:
            return None
        profiles = await self.list_style_profiles(user_id)
        for profile in profiles:
            if profile.id == library.global_active_profile_id and profile.source_ids:
                profile.active = True
                return profile
        await self._save_global_active_profile_id(user_id, None)
        return None

    async def get_project_applied_style_profile(self, project_id: str, user_id: int) -> Optional[StyleProfile]:
        extra = await self._get_project_extra(project_id)
        profile_id = extra.get("applied_style_profile_id") if isinstance(extra, dict) else None
        if not profile_id:
            return None
        profiles = await self.list_style_profiles(user_id)
        for profile in profiles:
            if profile.id == profile_id and profile.source_ids:
                return profile
        extra.pop("applied_style_profile_id", None)
        extra.pop("style_application_mode", None)
        await self._save_project_extra(project_id, extra)
        return None

    async def get_effective_style_for_project(
        self,
        project_id: str,
        user_id: int,
    ) -> Optional[StyleFeature]:
        project_profile = await self.get_project_applied_style_profile(project_id, user_id)
        if project_profile and project_profile.style_feature:
            return StyleFeature(project_profile.style_feature)

        global_profile = await self.get_global_active_style_profile(user_id)
        if global_profile and global_profile.style_feature:
            return StyleFeature(global_profile.style_feature)

        return await self.get_style_for_project(project_id)

    async def get_style_for_project(
        self,
        project_id: str
    ) -> Optional[StyleFeature]:
        extra = await self._get_project_extra(project_id)
        style_data = extra.get("style_feature") if isinstance(extra, dict) else None
        if not style_data:
            return None
        return StyleFeature(style_data)

    async def clear_style_for_project(
        self,
        project_id: str
    ) -> None:
        memory = await self._get_project_memory(project_id)
        extra = dict(memory.extra or {})
        if "style_feature" in extra:
            del extra["style_feature"]
        extra.pop("active_style_profile_id", None)
        extra.pop("style_profiles", None)
        extra.pop("style_sources", None)
        extra.pop("style_application_mode", None)
        extra.pop("applied_style_profile_id", None)
        memory.extra = extra
        await self.db.commit()
        await self.db.refresh(memory)

    def _parse_json_response(self, response: str) -> Optional[Dict[str, Any]]:
        """解析JSON响应"""
        try:
            content = sanitize_json_like_text(
                unwrap_markdown_json(remove_think_tags(response or ""))
            )

            if content.startswith("{"):
                return json.loads(content)

        except json.JSONDecodeError as e:
            logger.error(f"JSON解析失败: {e}")

        return None

    async def get_style_summary(self, project_id: str, user_id: int) -> Dict[str, Any]:
        """获取项目当前生效文风摘要（用于前端展示）"""
        project_profile = await self.get_project_applied_style_profile(project_id, user_id)
        if project_profile:
            return {
                "has_style": True,
                "summary": project_profile.summary,
                "source": {
                    "mode": "external_project",
                    "label": "项目专属外部文风",
                    "profile_id": project_profile.id,
                    "profile_name": project_profile.name,
                    "source_ids": project_profile.source_ids,
                    "source_titles": project_profile.extra.get("source_titles", []),
                    "application_scope": "project",
                }
            }

        global_profile = await self.get_global_active_style_profile(user_id)
        if global_profile:
            return {
                "has_style": True,
                "summary": global_profile.summary,
                "source": {
                    "mode": "external_global",
                    "label": "全局外部文风",
                    "profile_id": global_profile.id,
                    "profile_name": global_profile.name,
                    "source_ids": global_profile.source_ids,
                    "source_titles": global_profile.extra.get("source_titles", []),
                    "application_scope": "global",
                }
            }

        style = await self.get_style_for_project(project_id)
        if not style:
            return {"has_style": False}

        return {
            "has_style": True,
            "summary": style.to_summary_dict(),
            "source": {
                "mode": "project_chapters",
                "label": "项目章节文风",
                "profile_id": None,
                "profile_name": None,
                "source_ids": [],
                "source_titles": [],
                "application_scope": "project_chapters",
            }
        }

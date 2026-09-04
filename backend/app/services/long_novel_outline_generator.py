# AIMETA P=长篇小说大纲生成器_多卷章节结构|R=大纲生成_多卷结构|NR=不含业务逻辑|E=LongNovelOutlineGenerator|X=internal|A=生成器类|D=llm_service|S=none|RD=./README.ai
"""
长篇小说大纲生成服务

支持生成多卷、多章节的长篇小说完整结构：
- 自动规划卷数、每卷章节数
- 生成卷大纲和章节大纲
- 确保卷与卷之间的连贯性
"""
import json
import logging
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ==================== 提示词模板 ====================

LONG_NOVEL_OUTLINE_PROMPT = '''
你是一位拥有多年创作经验的长篇小说架构师，专精于百万字级网络小说的结构设计。

请根据以下信息，为这部小说设计完整的多卷多章节结构。

## 小说核心信息：
- 标题：{title}
- 类型：{genre}
- 风格：{style}
- 目标总字数：{target_word_count}字
- 总卷数：{volume_count}卷
- 每卷章节数：{chapters_per_volume}章左右

## 核心设定：
- 主角：{protagonist}
- 核心冲突：{central_conflict}
- 世界观：{worldview}
- 核心配角：{characters}

## 设计原则（必须严格遵守）：
1. **主线和暗线**：每个卷必须有一条明确的"主线"和一条"暗线/支线"推进。
2. **人物弧光**：主角在每卷末尾必须有明显的成长/变化/抉择。标注角色阶段性目标。
3. **节奏控制**：开卷钩子(2-3章)→中段深化(冲突升级)→卷末高潮(1-2章铺垫下一卷)。
4. **伏笔系统**：每卷埋设2+个跨卷伏笔，每卷回收1+个旧伏笔。标注铺设和回收章节。
5. **情感曲线**：每章标注情感基调，卷间情绪波动有节奏感。
6. **字数分布**：转折章节5000-8000字，过渡章节3000-5000字。

## 输出格式（纯JSON）：
{{
  "novel_title": "标题",
  "total_chapters_estimate": 预估章数,
  "main_plot_line": "主线描述",
  "sub_plot_lines": [
    {{"name": "暗线名", "description": "描述", "planted_at_volume": 卷号, "resolved_at_volume": 卷号}}
  ],
  "character_arcs": [
    {{"name": "角色名", "starting_position": "起点", "growth_goal": "目标", "key_turning_volumes": [卷号]}}
  ],
  "foreshadowing_system": [
    {{"id": 1, "description": "描述", "planted_chapter": 章号, "expected_reveal_chapter": 章号, "type": "势力/秘密/物品/世界观"}}
  ],
  "volumes": [
    {{
      "volume_number": 1,
      "volume_title": "卷标题",
      "volume_theme": "核心主题",
      "volume_summary": "卷摘要(150-300字)",
      "main_line": "本卷主线",
      "sub_line": "本卷暗线",
      "emotional_arc": "开卷→中段→卷末情绪变化",
      "foreshadowing_planted": [伏笔ID],
      "foreshadowing_revealed": [伏笔ID],
      "chapters": [
        {{
          "chapter_number": 全局章号,
          "volume_number": 卷号,
          "title": "章标题",
          "summary": "章节摘要(80-150字)",
          "key_events": ["事件1","事件2","事件3"],
          "character_focus": ["主要角色"],
          "emotional_tone": "情绪基调",
          "pacing_role": "开卷钩子|中段推进|卷末高潮|过渡衔接",
          "word_count_estimate": 5000
        }}
      ]
    }}
  ]
}}

仅输出完整JSON，不添加额外内容。'''



class LongNovelOutlineGenerator:
    """长篇小说大纲生成器"""

    def __init__(self, llm_service=None):
        self.llm_service = llm_service

    async def generate_outline(
        self,
        *,
        blueprint_data: Dict,
        llm_service,
        user_id: int,
        volume_count: int = 6,
        chapters_per_volume: int = 15,
        progress_callback=None,
    ) -> Optional[Dict]:
        """生成长篇小说的完整大纲"""
        title = str(blueprint_data.get("title") or "未命名作品")
        genre = str(blueprint_data.get("genre") or "")
        style = str(blueprint_data.get("style") or "")
        target_word_count = blueprint_data.get("total_word_count") or blueprint_data.get("target_total_words") or 500000
        protagonist = str(blueprint_data.get("protagonist") or blueprint_data.get("main_character") or "主角")
        central_conflict = str(blueprint_data.get("central_conflict") or blueprint_data.get("core_conflict") or "")
        worldview = json.dumps(blueprint_data.get("world_setting") or {}, ensure_ascii=False, indent=2)
        
        characters_list = blueprint_data.get("characters") or []
        if isinstance(characters_list, list):
            characters_text = "\n".join([
                f"- {c.get('name', '未知')}: {c.get('description', c.get('role', ''))}"[:120]
                for c in characters_list[:10] if isinstance(c, dict)
            ])
        else:
            characters_text = str(characters_list)
        
        prompt = self.build_prompt(
            title=title,
            genre=genre,
            style=style,
            target_word_count=target_word_count,
            volume_count=volume_count,
            chapters_per_volume=chapters_per_volume,
            protagonist=protagonist,
            central_conflict=central_conflict,
            worldview=worldview[:2000],
            characters=characters_text[:2000],
        )
        
        if progress_callback:
            await progress_callback("blueprint_plot_threads", "正在生成长篇大纲骨架...")
        
        try:
            result = await llm_service.get_llm_response(
                system_prompt="你是一个专业的长篇小说大纲架构师。只输出JSON。",
                conversation_history=[{"role": "user", "content": prompt}],
                temperature=0.3,
                user_id=user_id,
                timeout=180.0,
                max_tokens=8000,
                response_format="json_object",
            )
            response_text = result if isinstance(result, str) else str(result)
            outline_data = self.parse_outline_response(response_text)
            
            if outline_data:
                errors = self.validate_outline_structure(outline_data)
                if errors:
                    logger.warning("长篇大纲结构问题: %s", errors)
                
                flattened = self.flatten_outline(outline_data)
                blueprint_data["novel_outline"] = flattened
                blueprint_data["outline_metadata"] = {
                    "generator": "LongNovelOutlineGenerator",
                    "volumes": volume_count,
                    "chapters_per_volume": chapters_per_volume,
                    "main_plot_line": outline_data.get("main_plot_line", ""),
                    "sub_plot_lines": outline_data.get("sub_plot_lines", []),
                    "character_arcs": outline_data.get("character_arcs", []),
                    "foreshadowing_system": outline_data.get("foreshadowing_system", []),
                }
                logger.info("长篇大纲生成成功: %s卷, %s章", volume_count, len(flattened))
                return blueprint_data
            
        except Exception as e:
            logger.warning("长篇大纲生成失败: %s", str(e))
        
        # fallback
        fallback = self.generate_fallback_outline(blueprint_data, volume_count, chapters_per_volume)
        blueprint_data["novel_outline"] = fallback
        return blueprint_data

    @staticmethod
    def estimate_structure(target_word_count: int, genre: str = "") -> Dict:
        """
        根据目标字数和类型估算小说结构
        
        Returns:
            {
                "volume_count": 卷数,
                "chapters_per_volume": 每卷章节数,
                "total_chapters": 总章节数,
                "words_per_chapter": 每章平均字数
            }
        """
        # 根据字数确定规模
        if target_word_count <= 50000:
            # 短篇：1-2卷，每卷5-8章
            volume_count = 1
            chapters_per_volume = min(8, max(5, target_word_count // 5000))
        elif target_word_count <= 200000:
            # 中篇：2-4卷，每卷8-12章
            volume_count = min(4, max(2, target_word_count // 80000))
            chapters_per_volume = min(12, max(8, target_word_count // (volume_count * 6000)))
        elif target_word_count <= 500000:
            # 长篇：3-6卷，每卷10-15章
            volume_count = min(6, max(3, target_word_count // 120000))
            chapters_per_volume = min(15, max(10, target_word_count // (volume_count * 7000)))
        else:
            # 超长篇：5-10卷，每章12-20章
            volume_count = min(10, max(5, target_word_count // 200000))
            chapters_per_volume = min(20, max(12, target_word_count // (volume_count * 8000)))

        total_chapters = volume_count * chapters_per_volume
        words_per_chapter = target_word_count // total_chapters if total_chapters > 0 else 5000

        return {
            "volume_count": volume_count,
            "chapters_per_volume": chapters_per_volume,
            "total_chapters": total_chapters,
            "words_per_chapter": words_per_chapter,
        }

    @staticmethod
    def build_prompt(
        title: str,
        genre: str,
        style: str,
        target_word_count: int,
        protagonist: str,
        central_conflict: str,
        worldview: str,
        characters: List[Dict],
        volume_count: Optional[int] = None,
        chapters_per_volume: Optional[int] = None,
    ) -> str:
        """构建生成提示词"""
        structure = LongNovelOutlineGenerator.estimate_structure(target_word_count, genre)
        vol_count = volume_count or structure["volume_count"]
        ch_per_vol = chapters_per_volume or structure["chapters_per_volume"]

        characters_text = "\n".join(
            f"- {c.get('name', '未知')}: {c.get('identity', '')} - {c.get('description', '')}"
            for c in characters[:15]
        ) if characters else "（暂无角色设定）"

        return LONG_NOVEL_OUTLINE_PROMPT.format(
            title=title,
            genre=genre,
            style=style,
            target_word_count=target_word_count,
            volume_count=vol_count,
            protagonist=protagonist or "（待设定）",
            central_conflict=central_conflict or "（待设定）",
            worldview=worldview or "（待设定）",
            characters=characters_text,
            chapters_per_volume=ch_per_vol,
        )

    @staticmethod
    def parse_outline_response(response: str) -> Optional[Dict]:
        """解析 LLM 返回的大纲 JSON"""
        if not response:
            return None

        import re
        # 清理响应
        cleaned = response.strip()
        # 移除 markdown 代码块
        if cleaned.startswith("`"):
            cleaned = re.sub(r"^`(?:json)?\s*\n?", "", cleaned)
            cleaned = re.sub(r"\n?`\s*$", "", cleaned)

        # 尝试解析 JSON
        try:
            data = json.loads(cleaned)
            if "volumes" in data:
                return data
        except json.JSONDecodeError:
            pass

        # 尝试提取 JSON 对象
        json_start = cleaned.find("{")
        json_end = cleaned.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            try:
                data = json.loads(cleaned[json_start:json_end])
                if "volumes" in data:
                    return data
            except json.JSONDecodeError:
                pass

        logger.error("无法解析大纲响应")
        return None

    @staticmethod
    def validate_outline_structure(data: Dict) -> List[str]:
        """验证大纲结构完整性，返回问题列表"""
        issues = []

        if not data.get("volumes"):
            issues.append("缺少卷结构")
            return issues

        total_chapters = 0
        for vol in data["volumes"]:
            if not vol.get("volume_title"):
                issues.append(f"第{vol.get('volume_number', '?')}卷缺少标题")
            if not vol.get("chapters"):
                issues.append(f"第{vol.get('volume_number', '?')}卷缺少章节")

            for ch in vol.get("chapters", []):
                total_chapters += 1
                if not ch.get("title"):
                    issues.append(f"第{ch.get('chapter_number', '?')}章缺少标题")
                if not ch.get("summary"):
                    issues.append(f"第{ch.get('chapter_number', '?')}章缺少摘要")

        if total_chapters == 0:
            issues.append("没有生成任何章节")

        return issues

    @staticmethod
    def flatten_outline(data: Dict) -> List[Dict]:
        """将嵌套的卷-章结构展平为章节列表"""
        chapters = []
        for vol in data.get("volumes", []):
            for ch in vol.get("chapters", []):
                chapters.append({
                    "chapter_number": ch.get("chapter_number", len(chapters) + 1),
                    "volume_number": vol.get("volume_number", 1),
                    "volume_title": vol.get("volume_title", ""),
                    "title": ch.get("title", ""),
                    "summary": ch.get("summary", ""),
                    "key_events": ch.get("key_events", []),
                    "character_focus": ch.get("character_focus", []),
                    "emotional_tone": ch.get("emotional_tone", ""),
                    "word_count_estimate": ch.get("word_count_estimate", 5000),
                })
        return chapters

    @staticmethod
    def generate_fallback_outline(
        title: str,
        genre: str,
        target_word_count: int,
        protagonist: str = "主角",
    ) -> Dict:
        """生成兜底大纲结构（当 LLM 调用失败时使用）"""
        structure = LongNovelOutlineGenerator.estimate_structure(target_word_count, genre)
        volumes = []

        for v in range(1, structure["volume_count"] + 1):
            chapters = []
            for c in range(1, structure["chapters_per_volume"] + 1):
                ch_num = (v - 1) * structure["chapters_per_volume"] + c
                chapters.append({
                    "chapter_number": ch_num,
                    "volume_number": v,
                    "title": f"第{ch_num}章",
                    "summary": f"第{ch_num}章内容...",
                    "key_events": ["待填充"],
                    "character_focus": [protagonist],
                    "emotional_tone": "中性",
                    "word_count_estimate": structure["words_per_chapter"],
                })

            volumes.append({
                "volume_number": v,
                "volume_title": f"第{v}卷",
                "volume_summary": f"第{v}卷内容概要...",
                "theme": f"第{v}卷主题",
                "chapters": chapters,
            })

        return {
            "novel_title": title,
            "volumes": volumes,
        }

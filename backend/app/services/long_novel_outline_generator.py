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
你是一位顶级的百万字级网络小说架构师，专精于超长篇多卷本作品的结构设计。

请为以下小说创建完整的多卷多章详细大纲。这个大纲是长篇创作的"圣经"，必须足够深入。

## 小说核心信息
- 标题：{title}
- 类型：{genre}
- 风格：{style}
- 目标总字数：{target_word_count}字
- 总卷数：{volume_count}卷
- 每卷章节数：{chapters_per_volume}章

## 核心设定
- 主角：{protagonist}
- 核心冲突：{central_conflict}
- 世界观：{worldview}
- 核心角色：{characters}

## 严格设计原则
### 多卷骨架
1. 各卷独立但有递进关系的主题和目标
2. 每卷3个阶段：开局钩子(2-3章)、中段深化(主体章节)、卷末高潮(2-3章)
3. 卷末必须带"下一卷钩子"，刺激读者继续
4. 每卷必须推进总体剧情至少1个大转折

### 主线与暗线
1. 总主线贯穿全书，每个卷有该卷的"阶段性目标"
2. 每卷至少1条暗线(势力博弈、身世秘密、能力成长等)并行推进
3. 暗线在该卷结尾给出实质性推进，不能空悬

### 人物设计
1. 主角每卷末尾必须有清晰的变化(实力/认知/关系/地位)
2. 每卷提出1-2个阶段性"配角锚"（该卷重点描述的配角）
3. 禁止配角一次性出场完毕——每卷有新的"卷入人物"

### 伏笔系统
1. 每卷埋设3+个跨卷伏笔——必须在本卷内写清埋设章号
2. 每卷回收1-2个前卷伏笔——必须写清回收章号和来源卷
3. 伏笔类型分类：势力伏笔、身份伏笔、物品伏笔、剧情反转

### 节奏控制
1. 凡有转折章 5000-12000字，过渡章 3000-6000字
2. 避免3章以上纯过渡——读者必须持续有事件发生
3. 卷末3章节奏必须收紧——冲突升级→结局→下一卷钩子

## 输出格式（纯JSON，严格遵守）
```json
{{
  "novel_title": "标题",
  "total_chapters_estimate": 总章数,
  "main_plot_line": "一百字的主线描述",
  "sub_plot_lines": [
    {{"name": "暗线名", "description": "描述", "planted_at_volume": 起始卷号, "resolved_at_volume": 预期终结卷号}}
  ],
  "character_arcs": [
    {{"name": "角色名", "arc_description": "角色弧线描述", "key_turning_volumes": [关键转折卷号], "volume_focus": [重点该角色的卷号]}}
  ],
  "foreshadowing_system": [
    {{"id": 1, "type": "势力/身份/世界观/感情", "description": "伏笔描述", "planted_chapter": 埋设章号, "expected_reveal_chapter": 预期回收章号, "forecasting_volume": 埋设卷号, "resolution_volume": 回收卷号}}"
  ],
  "volumes": [
    {{
      "volume_number": 1,
      "volume_title": "卷名",
      "volume_theme": "本卷核心主题",
      "volume_main_line": "本卷主线目标",
      "volume_sub_line": "本卷暗线推进",
      "emotional_arc": "本卷情绪曲线：开卷→发展→高潮→尾音",
      "volume_word_count_estimate": "预估本卷总字数",
      "next_volume_hint": "给下一卷的钩子",
      "protagonist_progress": "主角在本卷的成长/变化",
      "foreshadowing_planted_this_volume": [本卷埋设的伏笔ID],
      "foreshadowing_revealed_this_volume": [本卷回收的前卷伏笔ID],
      "chapters": [
        {{
          "chapter_number": 全局章号,
          "volume_number": 本卷号,
          "title": "章标题（有吸引力）",
          "summary": "70-150字章节摘要",
          "key_events": ["事件1", "事件2", "事件3"],
          "character_focus": ["主要角色"],
          "emotional_tone": "开场紧张 | 发展铺垫 | 冲突升级 | 高潮对决 | 结局过渡 | 反转揭晓",
          "pacing_role": "卷首钩子 | 中段推进 | 核心事件 | 卷末高潮 | 过渡衔接",
          "word_count_estimate": 章节字数预测
        }}
      ]
    }}
  ]
}}

仅输出完整有效JSON。'''




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
        volume_count: int = 8,
        chapters_per_volume: int = 25,
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
                timeout=300.0,
                max_tokens=16000,
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
            # 短篇：1-2卷，每卷8-15章
            volume_count = 1
            chapters_per_volume = min(15, max(8, target_word_count // 4000))
        elif target_word_count <= 200000:
            # 中篇：3-5卷，每卷15-25章
            volume_count = min(5, max(3, target_word_count // 50000))
            chapters_per_volume = min(25, max(12, target_word_count // (volume_count * 5000)))
        elif target_word_count <= 500000:
            # 长篇：5-8卷，每卷20-35章
            volume_count = min(8, max(5, target_word_count // 80000))
            chapters_per_volume = min(35, max(20, target_word_count // (volume_count * 5000)))
        else:
            # 超长篇：8-15卷，每卷25-50章
            volume_count = min(15, max(8, target_word_count // 120000))
            chapters_per_volume = min(50, max(25, target_word_count // (volume_count * 5000)))

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

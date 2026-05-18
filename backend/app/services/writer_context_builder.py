# AIMETA P=写作上下文构建_信息可见性过滤|R=角色登场检测_蓝图裁剪_已知未知分离|NR=不含LLM调用|E=none|X=internal|A=过滤_构建|D=none|S=none|RD=./README.ai
"""
WriterContextBuilder: 写作层信息可见性过滤服务

核心职责：
1. 检测已登场角色（从已完成章节中提取）
2. 检测本章计划登场的新角色（从大纲/导演脚本中提取）
3. 裁剪蓝图信息，移除剧透字段和未登场角色
4. 输出 Writer 可见的上下文，防止主角全知问题
"""

import re
from copy import deepcopy
from typing import Any, Dict, List, Optional, Set


def _detect_names(all_names: List[str], texts: List[str]) -> Set[str]:
    """
    从文本列表中检测出现过的角色名。
    使用简单的字符串匹配，后续可升级为 NER。
    """
    found = set()
    combined_text = "\n".join(t for t in texts if t)
    for name in all_names:
        if name and name in combined_text:
            found.add(name)
    return found


def _shallow_copy_blueprint(blueprint: dict) -> dict:
    """浅拷贝蓝图，避免修改原始数据。"""
    return deepcopy(blueprint)


class WriterContextBuilder:
    """
    构建写作层可见的上下文，实现信息可见性过滤。

    核心原则：
    - L3 Writer 只能看到「已公开」的信息
    - 未登场角色不能出现在 prompt 中（连名字都不出现）
    - full_synopsis 等剧透字段必须移除
    """

    def analyze_character_scope(
        self,
        *,
        blueprint: dict,
        completed_summaries: List[str],
        previous_tail: str,
        outline_title: str,
        outline_summary: str,
        writing_notes: str,
        allowed_new_characters: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """统一分析本章角色可见范围，供导演脚本与正文阶段共用。"""
        all_names = [
            c.get("name") for c in blueprint.get("characters", []) if c.get("name")
        ]

        introduced = _detect_names(all_names, completed_summaries + [previous_tail])
        planned = _detect_names(
            all_names, [outline_title, outline_summary, writing_notes]
        )

        allowed = introduced | planned
        if allowed_new_characters:
            allowed.update(
                name.strip()
                for name in allowed_new_characters
                if isinstance(name, str) and name.strip()
            )

        return {
            "all_names": all_names,
            "introduced": introduced,
            "planned": planned,
            "allowed": allowed,
            "introduced_characters": sorted(list(introduced)),
            "planned_characters": sorted(list(planned)),
            "allowed_characters": sorted(list(allowed)),
        }

    @staticmethod
    def _compact_text(value: Any, limit: int = 40) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        return text if len(text) <= limit else f"{text[:limit].rstrip()}…"

    @classmethod
    def _build_macro_continuity_context(
        cls,
        *,
        writer_blueprint: dict,
        introduced_characters: List[str],
        planned_characters: List[str],
        allowed_new_characters: Optional[List[str]],
    ) -> str:
        sections: List[str] = []

        if introduced_characters:
            sections.append("## 已登场角色\n- " + "、".join(introduced_characters[:8]))

        planned_new = [
            name for name in (allowed_new_characters or [])
            if isinstance(name, str) and name.strip() and name not in introduced_characters
        ]
        if planned_characters or planned_new:
            lines = []
            if planned_characters:
                lines.append("- 本章文本已提及角色：" + "、".join(planned_characters[:6]))
            if planned_new:
                lines.append("- 本章允许新登场角色：" + "、".join(planned_new[:4]))
            sections.append("## 本章角色范围\n" + "\n".join(lines))

        relationships = writer_blueprint.get("relationships") or []
        relationship_lines: List[str] = []
        for relation in relationships[:6]:
            if not isinstance(relation, dict):
                continue
            left = str(relation.get("from") or relation.get("character_from") or "").strip()
            right = str(relation.get("to") or relation.get("character_to") or "").strip()
            if not left or not right:
                continue
            desc = cls._compact_text(
                relation.get("core_conflict")
                or relation.get("description")
                or relation.get("status")
                or relation.get("relationship_type"),
                limit=36,
            )
            relationship_lines.append(f"- {left} ↔ {right}：{desc or '关系持续变化中'}")
        if relationship_lines:
            sections.append("## 当前关键关系\n" + "\n".join(relationship_lines))

        arc_lines: List[str] = []
        for arc in (writer_blueprint.get("story_arcs") or [])[:4]:
            if not isinstance(arc, dict):
                continue
            title = cls._compact_text(arc.get("title"), limit=20)
            conflict = cls._compact_text(arc.get("conflict") or arc.get("goal") or arc.get("summary"), limit=40)
            if title or conflict:
                arc_lines.append(f"- {title or '剧情线'}：{conflict or '持续推进'}")
        if arc_lines:
            sections.append("## 长线剧情压力\n" + "\n".join(arc_lines))

        stage_lines: List[str] = []
        for stage in (writer_blueprint.get("novel_outline") or [])[:3]:
            if not isinstance(stage, dict):
                continue
            title = cls._compact_text(stage.get("title"), limit=20)
            conflict = cls._compact_text(stage.get("main_conflict") or stage.get("goal") or stage.get("story_function"), limit=42)
            if title or conflict:
                stage_lines.append(f"- {title or '当前阶段'}：{conflict or '保持既定推进'}")
        if stage_lines:
            sections.append("## 当前阶段任务\n" + "\n".join(stage_lines))

        return "\n\n".join(section for section in sections if section).strip()

    # 禁止传递给 Writer 的蓝图字段（防剧透）
    FORBIDDEN_BLUEPRINT_KEYS = {
        "full_synopsis",
        "one_sentence_summary",
        "chapter_outline",  # 完整大纲也不能给
        "chapter_summaries",
        "chapter_details",
        "chapter_dialogues",
        "chapter_events",
        "conversation_history",
        "character_timelines",
    }

    def build_visibility_context(
        self,
        blueprint: dict,
        completed_summaries: List[str],
        previous_tail: str,
        outline_title: str,
        outline_summary: str,
        writing_notes: str,
        allowed_new_characters: Optional[List[str]] = None,
    ) -> Dict:
        """
        构建 Writer 可见的上下文。

        Args:
            blueprint: 原始蓝图数据
            completed_summaries: 已完成章节的摘要列表
            previous_tail: 上一章结尾文本
            outline_title: 当前章节标题
            outline_summary: 当前章节摘要
            writing_notes: 写作指令
            allowed_new_characters: 导演脚本指定的本章允许登场的新角色

        Returns:
            包含裁剪后蓝图和角色信息的字典
        """
        scope = self.analyze_character_scope(
            blueprint=blueprint,
            completed_summaries=completed_summaries,
            previous_tail=previous_tail,
            outline_title=outline_title,
            outline_summary=outline_summary,
            writing_notes=writing_notes,
            allowed_new_characters=allowed_new_characters,
        )
        all_names = scope["all_names"]
        introduced = scope["introduced"]
        planned = scope["planned"]
        allowed = scope["allowed"]

        # 5. 裁剪蓝图
        writer_blueprint = _shallow_copy_blueprint(blueprint)

        # 移除禁止字段
        for key in self.FORBIDDEN_BLUEPRINT_KEYS:
            writer_blueprint.pop(key, None)

        # 裁剪角色列表：只保留允许的角色
        if "characters" in writer_blueprint:
            writer_blueprint["characters"] = [
                c for c in writer_blueprint.get("characters", [])
                if c.get("name") in allowed
            ]

        # 裁剪关系列表：只保留与允许角色相关的关系
        if "relationships" in writer_blueprint:
            rels = writer_blueprint.get("relationships", [])
            writer_blueprint["relationships"] = [
                r for r in rels
                if r.get("from") in allowed and r.get("to") in allowed
            ]

        introduced_characters = scope["introduced_characters"]
        planned_characters = scope["planned_characters"]
        allowed_characters = scope["allowed_characters"]

        # 6. 计算禁止角色列表（用于 Guardrails 检查）
        forbidden = set(all_names) - allowed
        macro_continuity_context = self._build_macro_continuity_context(
            writer_blueprint=writer_blueprint,
            introduced_characters=introduced_characters,
            planned_characters=planned_characters,
            allowed_new_characters=allowed_new_characters,
        )

        return {
            "writer_blueprint": writer_blueprint,
            "introduced_characters": introduced_characters,
            "planned_characters": planned_characters,
            "allowed_characters": allowed_characters,
            "forbidden_characters": sorted(list(forbidden)),
            "macro_continuity_context": macro_continuity_context,
        }

    def get_forbidden_names_pattern(self, forbidden_characters: List[str]) -> Optional[re.Pattern]:
        """
        生成用于检测禁止角色名的正则表达式。
        
        Args:
            forbidden_characters: 禁止出现的角色名列表
            
        Returns:
            编译后的正则表达式，如果列表为空则返回 None
        """
        if not forbidden_characters:
            return None
        # 转义特殊字符并构建正则
        escaped = [re.escape(name) for name in forbidden_characters if name]
        if not escaped:
            return None
        pattern = "|".join(escaped)
        return re.compile(pattern)

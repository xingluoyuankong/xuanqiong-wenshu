from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..core.config import settings

CATEGORY_LABELS = {
    "history": "历史与真实数据",
    "culture": "文化与民俗",
    "philosophy": "哲学与思想",
    "naming": "命名与语义",
    "domain_knowledge": "专业学科与物质细节",
    "humor_dialogue": "趣味、幽默与对话机制",
    "style_craft": "文学技法与题材表达",
}


class ResearchArchive:
    @staticmethod
    def _safe_project_segment(project_id: str) -> str:
        normalized = re.sub(r"[^A-Za-z0-9_-]", "_", str(project_id or "").strip())[:80]
        if not normalized:
            raise ValueError("project_id is required")
        return normalized

    @classmethod
    def project_root(cls, project_id: str) -> Path:
        base = (settings.project_root / "storage" / "novel_projects").resolve()
        target = (base / cls._safe_project_segment(project_id) / "research").resolve()
        if base not in target.parents:
            raise ValueError("invalid project research path")
        target.mkdir(parents=True, exist_ok=True)
        return target

    @classmethod
    def write_run(
        cls,
        *,
        project_id: str,
        run_id: str,
        scope: str,
        chapter_number: Optional[int],
        plan: List[Dict[str, Any]],
        search_batches: List[Dict[str, Any]],
        sources: List[Dict[str, Any]],
        synthesis: Dict[str, Any],
    ) -> Dict[str, Any]:
        root = cls.project_root(project_id)
        relative_scope = (
            Path("chapters") / f"chapter_{chapter_number:04d}"
            if scope == "chapter" and chapter_number
            else Path("blueprint") / scope
        )
        run_dir = root / relative_scope / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        files: Dict[str, str] = {}

        def write_json(name: str, payload: Any) -> None:
            path = run_dir / name
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            files[name] = str(path.relative_to(root)).replace("\\", "/")

        write_json("query_plan.json", plan)
        write_json("search_results.json", search_batches)
        write_json("sources.json", sources)
        write_json("research_cards.json", synthesis)
        categories = synthesis.get("categories") if isinstance(synthesis.get("categories"), dict) else {}
        category_dir = run_dir / "categories"
        category_dir.mkdir(exist_ok=True)
        for category, label in CATEGORY_LABELS.items():
            lines = [f"# {label}", ""]
            for index, card in enumerate(categories.get(category) or [], 1):
                if not isinstance(card, dict):
                    continue
                lines.extend([
                    f"## {index}. {str(card.get('insight') or '').strip()}",
                    "",
                    f"- 创作用法：{str(card.get('usage') or '').strip()}",
                    f"- 来源：{', '.join(str(url) for url in (card.get('source_urls') or []) if url)}",
                    "",
                ])
            path = category_dir / f"{category}.md"
            path.write_text("\n".join(lines), encoding="utf-8")
            files[f"categories/{category}.md"] = str(path.relative_to(root)).replace("\\", "/")
        readme = run_dir / "README.md"
        readme.write_text(
            f"# 小说研究资料\n\n- 范围：{scope}\n- 章节：{chapter_number or '全局'}\n- 运行：{run_id}\n\n{synthesis.get('summary') or ''}\n",
            encoding="utf-8",
        )
        files["README.md"] = str(readme.relative_to(root)).replace("\\", "/")
        relative_run = str(run_dir.relative_to(root)).replace("\\", "/")
        return {"root": "research", "run_directory": relative_run, "files": files}

from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "backend" / "storage" / "arboris.db"
OUTPUT_DIR = ROOT / "output"
REPORT_PATH = ROOT / "docs" / "reports" / "generated-novel-quality-audit-2026-04-29.md"
RAW_PATH = ROOT / "docs" / "reports" / "generated-novel-quality-audit-2026-04-29.json"

MOJIBAKE_RE = re.compile(r"(\?{3,}|鍔|鐢|澶|辫|閫|璇|浼|搴|淇|缂|鏇|渚|閸|鏉|鎴|瑜|顫|闁|妤|娉|鈺|脳|Ã|Â|�)")
PLACEHOLDER_RE = re.compile(r"(TODO|TBD|待补|占位|示例文本|lorem ipsum)", re.I)


@dataclass
class ProjectAudit:
    project_id: str
    title: str
    status: str
    outline_count: int
    outline_min: int | None
    outline_max: int | None
    outline_missing: list[int]
    outline_duplicates: list[int]
    chapter_count: int
    version_count: int
    successful_chapters: int
    failed_chapters: int
    generating_chapters: int
    selected_missing: int
    selected_invalid: int
    export_blockers: int
    empty_versions: int
    short_versions: int
    mojibake_hits: int
    placeholder_hits: int
    word_count_mismatches: int
    metadata_mojibake_hits: int
    avg_version_chars: float
    max_version_chars: int
    issues: list[str]


def safe_json_loads(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return None


def read_rows(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    return list(conn.execute(sql, params))


def audit_database() -> tuple[list[ProjectAudit], dict[str, Any]]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    projects = read_rows(conn, "select * from novel_projects order by created_at")
    outlines_by_project: dict[str, list[sqlite3.Row]] = defaultdict(list)
    chapters_by_project: dict[str, list[sqlite3.Row]] = defaultdict(list)
    versions_by_chapter: dict[int, list[sqlite3.Row]] = defaultdict(list)

    for row in read_rows(conn, "select * from chapter_outlines order by project_id, chapter_number, id"):
        outlines_by_project[row["project_id"]].append(row)
    for row in read_rows(conn, "select * from chapters order by project_id, chapter_number, id"):
        chapters_by_project[row["project_id"]].append(row)
    for row in read_rows(conn, "select * from chapter_versions order by chapter_id, id"):
        versions_by_chapter[row["chapter_id"]].append(row)

    blueprint_count = dict(
        (row["project_id"], row["cnt"])
        for row in read_rows(conn, "select project_id, count(*) cnt from novel_blueprints group by project_id")
    )
    character_count = dict(
        (row["project_id"], row["cnt"])
        for row in read_rows(conn, "select project_id, count(*) cnt from blueprint_characters group by project_id")
    )
    conversation_mojibake = dict(
        (row["project_id"], row["cnt"])
        for row in read_rows(
            conn,
            """
            select project_id, count(*) cnt
            from novel_conversations
            where content like '%??%' or content like '%�%'
            group by project_id
            """,
        )
    )

    audits: list[ProjectAudit] = []
    totals = Counter()
    global_issue_samples: list[dict[str, Any]] = []

    for project in projects:
        pid = project["id"]
        outlines = outlines_by_project.get(pid, [])
        chapters = chapters_by_project.get(pid, [])
        outline_numbers = [int(r["chapter_number"]) for r in outlines]
        outline_counter = Counter(outline_numbers)
        outline_min = min(outline_numbers) if outline_numbers else None
        outline_max = max(outline_numbers) if outline_numbers else None
        missing: list[int] = []
        if outline_min is not None and outline_max is not None:
            missing = [n for n in range(outline_min, outline_max + 1) if n not in outline_counter]
        duplicates = sorted([num for num, cnt in outline_counter.items() if cnt > 1])

        issues: list[str] = []
        if not outlines:
            issues.append("缺少章节大纲")
        if missing:
            issues.append(f"章节大纲编号不连续：缺失 {missing[:12]}")
        if duplicates:
            issues.append(f"章节大纲编号重复：{duplicates[:12]}")
        if blueprint_count.get(pid, 0) == 0:
            issues.append("缺少 novel_blueprints 主蓝图记录")
        if outlines and character_count.get(pid, 0) == 0:
            issues.append("已有大纲但缺少蓝图角色记录")

        selected_missing = 0
        selected_invalid = 0
        export_blockers = 0
        empty_versions = 0
        short_versions = 0
        mojibake_hits = 0
        placeholder_hits = 0
        word_count_mismatches = 0
        metadata_mojibake_hits = 0
        version_lengths: list[int] = []
        status_counter = Counter([c["status"] for c in chapters])

        for text in [project["title"], project["initial_prompt"]]:
            if text and MOJIBAKE_RE.search(str(text)):
                metadata_mojibake_hits += 1
        for outline in outlines:
            for text in [outline["title"], outline["summary"]]:
                if text and MOJIBAKE_RE.search(str(text)):
                    metadata_mojibake_hits += 1
        metadata_mojibake_hits += int(conversation_mojibake.get(pid, 0))

        for chapter in chapters:
            chapter_versions = versions_by_chapter.get(int(chapter["id"]), [])
            selected_id = chapter["selected_version_id"]
            if selected_id is None:
                selected_missing += 1
            if selected_id is not None and int(selected_id) not in {int(v["id"]) for v in chapter_versions}:
                selected_invalid += 1
                issues.append(f"第 {chapter['chapter_number']} 章 selected_version_id 指向不存在版本")
            if chapter["status"] != "successful" or selected_id is None:
                export_blockers += 1

            for version in chapter_versions:
                content = version["content"] or ""
                length = len(content.strip())
                version_lengths.append(length)
                if length == 0:
                    empty_versions += 1
                    global_issue_samples.append({"project_id": pid, "chapter": chapter["chapter_number"], "issue": "空版本"})
                if 0 < length < 600:
                    short_versions += 1
                    global_issue_samples.append({"project_id": pid, "chapter": chapter["chapter_number"], "issue": f"版本过短({length}字)"})
                if MOJIBAKE_RE.search(content):
                    mojibake_hits += 1
                    global_issue_samples.append({"project_id": pid, "chapter": chapter["chapter_number"], "issue": "疑似乱码"})
                if PLACEHOLDER_RE.search(content):
                    placeholder_hits += 1
                if selected_id is not None and int(version["id"]) == int(selected_id):
                    recorded = int(chapter["word_count"] or 0)
                    if recorded and abs(recorded - length) > max(120, int(recorded * 0.18)):
                        word_count_mismatches += 1
                        global_issue_samples.append(
                            {
                                "project_id": pid,
                                "chapter": chapter["chapter_number"],
                                "issue": f"字数统计偏差：记录 {recorded} / 实际 {length}",
                            }
                        )

        if selected_missing:
            issues.append(f"章节未绑定 selected_version：{selected_missing} 个")
        if selected_invalid:
            issues.append(f"selected_version 无效：{selected_invalid} 个")
        if export_blockers:
            issues.append(f"导出硬阻断章节：{export_blockers} 个")
        if empty_versions:
            issues.append(f"空正文版本：{empty_versions} 个")
        if short_versions:
            issues.append(f"短正文版本(<600字)：{short_versions} 个")
        if mojibake_hits:
            issues.append(f"疑似乱码正文版本：{mojibake_hits} 个")
        if placeholder_hits:
            issues.append(f"占位文本命中：{placeholder_hits} 个")
        if word_count_mismatches:
            issues.append(f"选中版本字数统计明显偏差：{word_count_mismatches} 个")
        if metadata_mojibake_hits:
            issues.append(f"标题/提示词/大纲/对话疑似乱码：{metadata_mojibake_hits} 处")
        if status_counter.get("generating", 0):
            issues.append(f"存在生成中章节：{status_counter['generating']} 个，需要运行态恢复/终止")
        if status_counter.get("failed", 0):
            issues.append(f"存在失败章节：{status_counter['failed']} 个")

        audit = ProjectAudit(
            project_id=pid,
            title=project["title"] or "(未命名)",
            status=project["status"],
            outline_count=len(outlines),
            outline_min=outline_min,
            outline_max=outline_max,
            outline_missing=missing,
            outline_duplicates=duplicates,
            chapter_count=len(chapters),
            version_count=sum(len(versions_by_chapter.get(int(c["id"]), [])) for c in chapters),
            successful_chapters=status_counter.get("successful", 0),
            failed_chapters=status_counter.get("failed", 0),
            generating_chapters=status_counter.get("generating", 0),
            selected_missing=selected_missing,
            selected_invalid=selected_invalid,
            export_blockers=export_blockers,
            empty_versions=empty_versions,
            short_versions=short_versions,
            mojibake_hits=mojibake_hits,
            placeholder_hits=placeholder_hits,
            word_count_mismatches=word_count_mismatches,
            metadata_mojibake_hits=metadata_mojibake_hits,
            avg_version_chars=(sum(version_lengths) / len(version_lengths) if version_lengths else 0),
            max_version_chars=(max(version_lengths) if version_lengths else 0),
            issues=issues,
        )
        audits.append(audit)

        totals.update(
            {
                "projects": 1,
                "outlines": len(outlines),
                "chapters": len(chapters),
                "versions": audit.version_count,
                "projects_with_issues": 1 if issues else 0,
                "failed_chapters": audit.failed_chapters,
                "generating_chapters": audit.generating_chapters,
                "empty_versions": empty_versions,
                "short_versions": short_versions,
                "mojibake_hits": mojibake_hits,
                "word_count_mismatches": word_count_mismatches,
                "metadata_mojibake_hits": metadata_mojibake_hits,
                "export_blockers": export_blockers,
            }
        )

    conn.close()
    return audits, {"totals": dict(totals), "issue_samples": global_issue_samples[:80]}


def audit_output_files() -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for path in sorted(OUTPUT_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            results.append({"file": path.name, "valid_json": False, "error": str(exc)})
            continue
        text = json.dumps(data, ensure_ascii=False)
        result: dict[str, Any] = {
            "file": path.name,
            "valid_json": True,
            "bytes": path.stat().st_size,
            "top_keys": list(data.keys()) if isinstance(data, dict) else None,
            "mojibake_hits": len(MOJIBAKE_RE.findall(text)),
            "placeholder_hits": len(PLACEHOLDER_RE.findall(text)),
        }
        if isinstance(data, dict):
            result["project_id"] = data.get("project_id")
            result["terminal"] = data.get("terminal") or data.get("terminal_status")
            result["last_stage"] = data.get("last_stage") or (data.get("last_status") or {}).get("progress_stage")
            result["last_percent"] = (data.get("last_status") or {}).get("progress_percent") or (data.get("generation_runtime") or {}).get("progress_percent")
            result["snapshot_count"] = len(data.get("snapshots") or [])
            result["duration_ms"] = data.get("generate_request_duration_ms")
        results.append(result)
    return results


def render_markdown(audits: list[ProjectAudit], summary: dict[str, Any], output_audit: list[dict[str, Any]]) -> str:
    totals = summary["totals"]
    issue_ranked = sorted(audits, key=lambda a: (len(a.issues), a.generating_chapters, a.failed_chapters, a.mojibake_hits), reverse=True)
    lines: list[str] = []
    lines.append("# 生成小说与输出资产深度审计报告（托管模式）")
    lines.append("")
    lines.append(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 数据库：`{DB_PATH}`")
    lines.append(f"- 输出目录：`{OUTPUT_DIR}`")
    lines.append("")
    lines.append("## 1. 总览")
    lines.append("")
    lines.append("| 指标 | 数量 |")
    lines.append("|---|---:|")
    for key, label in [
        ("projects", "项目数"),
        ("outlines", "章节大纲数"),
        ("chapters", "章节数"),
        ("versions", "正文版本数"),
        ("projects_with_issues", "存在问题的项目数"),
        ("failed_chapters", "失败章节"),
        ("generating_chapters", "卡在生成中章节"),
        ("empty_versions", "空正文版本"),
        ("short_versions", "短正文版本(<600字)"),
        ("mojibake_hits", "疑似乱码版本"),
        ("word_count_mismatches", "字数统计偏差"),
        ("metadata_mojibake_hits", "元数据疑似乱码"),
        ("export_blockers", "导出硬阻断章节"),
    ]:
        lines.append(f"| {label} | {totals.get(key, 0)} |")
    lines.append("")
    lines.append("## 2. 每个项目的小说生成质量")
    lines.append("")
    lines.append("| 项目 | 状态 | 大纲 | 章节/版本 | 成功/失败/生成中 | 导出阻断 | 正文质量问题 |")
    lines.append("|---|---|---:|---:|---:|---:|---|")
    for a in issue_ranked:
        issue_text = "；".join(a.issues[:5]) if a.issues else "未发现结构性问题"
        if len(a.issues) > 5:
            issue_text += f"；另有 {len(a.issues) - 5} 项"
        outline_span = f"{a.outline_count}"
        if a.outline_min is not None:
            outline_span += f"（{a.outline_min}-{a.outline_max}）"
        lines.append(
            f"| {a.title}<br>`{a.project_id}` | {a.status} | {outline_span} | {a.chapter_count}/{a.version_count} | "
            f"{a.successful_chapters}/{a.failed_chapters}/{a.generating_chapters} | {a.export_blockers} | {issue_text} |"
        )
    lines.append("")
    lines.append("## 3. 输出 JSON 实测结果")
    lines.append("")
    lines.append("| 文件 | JSON | 终态 | 阶段/进度 | 快照 | 质量命中 |")
    lines.append("|---|---|---|---|---:|---|")
    for item in output_audit:
        if not item.get("valid_json"):
            lines.append(f"| {item['file']} | 否 | - | - | 0 | {item.get('error')} |")
            continue
        quality = []
        if item.get("mojibake_hits"):
            quality.append(f"疑似乱码 {item['mojibake_hits']}")
        if item.get("placeholder_hits"):
            quality.append(f"占位 {item['placeholder_hits']}")
        if not quality:
            quality.append("未命中乱码/占位")
        lines.append(
            f"| {item['file']} | 是 | {item.get('terminal')} | {item.get('last_stage')} / {item.get('last_percent')}% | "
            f"{item.get('snapshot_count', 0)} | {'；'.join(quality)} |"
        )
    lines.append("")
    lines.append("## 4. 缺陷判定（按视角）")
    lines.append("")
    lines.append("### 代码编写者视角")
    lines.append("- 历史生成任务存在 `generating` 残留，说明此前长任务缺少可靠的超时恢复、可观测状态与后台化队列闭环。")
    lines.append("- 数据库中项目、蓝图、大纲、章节、版本之间存在部分断链/缺失，需要在服务层增加一致性检查与修复入口。")
    lines.append("- 输出 JSON 只记录轮询快照，缺少最终章节正文、失败分类和可复现实验参数，不利于回归定位。")
    lines.append("")
    lines.append("### 作家视角")
    lines.append("- 部分项目只有灵感/蓝图或大纲，没有完成章节，写作流程容易在“大纲已生成→正文未落地”之间中断。")
    lines.append("- 失败章节的摘要多为系统故障提示，不是可继续创作的文学性摘要，恢复体验会破坏创作连续性。")
    lines.append("- 短正文版本与字数统计偏差会让作者误判章节完成度。")
    lines.append("")
    lines.append("### 读者视角")
    lines.append("- 已有成功正文整体可读，但项目间完成度差异很大；读者会遇到章节缺失、连载断裂或正文长度不稳定。")
    lines.append("- 若 UI 未显式标注生成失败/生成中残留，读者会以为小说内容缺章或质量失控。")
    lines.append("")
    lines.append("### 项目开发审批者视角")
    lines.append("- 核心风险不在单点 UI，而是端到端生成链路的完成率、恢复率、审计证据和自动化验收不足。")
    lines.append("- 当前已补入后台化、超时与 smoke 验证，但还应继续补数据库一致性修复工具和更完整的 E2E 生成验收。")
    lines.append("")
    lines.append("## 5. 下一步优化步骤")
    lines.append("1. 将历史 `generating` 章节统一迁移为 stale/failed，并保留可重试原因。")
    lines.append("2. 增加 `tools/repair_generation_state.py`：只修复明确断链、空正文、无效 selected_version 的可自动处理项。")
    lines.append("3. 在前端写作桌面增加“项目健康检查/生成链路状态”面板：大纲、章节、版本、失败、可重试一屏可见。")
    lines.append("4. 为灵感模式→蓝图→大纲→章节生成新增完整 E2E smoke：SQLite 隔离库、低字数 mock/真实兼容路径、截图和 JSON 报告。")
    lines.append("5. 输出 JSON 增加最终正文摘要、选中版本、错误分类、模型参数和重试建议，形成可审计产物。")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    audits, summary = audit_database()
    output_audit = audit_output_files()
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "database": str(DB_PATH),
        "summary": summary,
        "projects": [a.__dict__ for a in audits],
        "outputs": output_audit,
    }
    RAW_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(render_markdown(audits, summary, output_audit), encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(f"Wrote {RAW_PATH}")


if __name__ == "__main__":
    main()

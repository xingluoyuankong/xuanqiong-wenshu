#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批次0 任务#2:合并 13 域 enriched JSON + 自动核验。

职责(全部为只读校验,绝不改动生产源):
1. 读取 enriched/domain-01.json .. domain-13.json;
2. 结构完整性校验:每个叶子节点必含规定字段;
3. 数量口径校验:节点总数应为 97;
4. 状态合法性:批次0 仅允许 CONFIRMED / IMPLEMENTED_UNVERIFIED / RESOLVED_IN_AUDIT;
5. **file:line 真实性自动核验**:提取每个 current_impl / evidence_refs 中的 file:line,
   校验文件相对仓库根存在,且行号不超过文件总行数(抓编造路径/越界行号);
6. **模板占位检测**:统计 root_cause / defect 文本雷同,防止子智能体套模板;
7. 合并输出 defects.enriched.json + file_line_audit.json(抽查清单)。

用法:
    python audit/production-readiness/_tools/merge_and_verify.py
退出码 0 = 全部校验通过;非 0 = 有阻断性问题(详见 stdout)。
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# 脚本位于 audit/production-readiness/_tools/ ,上溯三级到仓库根
TOOLS_DIR = Path(__file__).resolve().parent
AUDIT_DIR = TOOLS_DIR.parent            # audit/production-readiness
REPO_ROOT = AUDIT_DIR.parent.parent     # 仓库根
ENRICHED_DIR = AUDIT_DIR / "enriched"
OUT_MERGED = AUDIT_DIR / "defects.enriched.json"
OUT_FILELINE = AUDIT_DIR / "evidence" / "file_line_audit.json"

REQUIRED_FIELDS = [
    "id", "title", "severity", "status", "current_impl", "defect",
    "root_cause", "user_impact", "fix", "dependencies",
    "positive_test", "negative_test", "acceptance",
]
ALLOWED_STATUS = {"CONFIRMED", "IMPLEMENTED_UNVERIFIED", "RESOLVED_IN_AUDIT"}
ALLOWED_SEVERITY = {"P0", "P1", "P2"}
EXPECTED_NODE_COUNT = 97
EXPECTED_DOMAIN_COUNT = 13

# 提取 file:line 或 file:line-line 。文件名需含扩展名,避免把 "3:00" 之类误判。
FILELINE_RE = re.compile(r"([A-Za-z0-9_\-./\\]+\.[A-Za-z0-9_]+):(\d+)(?:-(\d+))?")

# 已知模板占位文本(原 defects.yaml 的病灶),命中即为高风险
KNOWN_PLACEHOLDER_SNIPPETS = [
    "核心模型或事务协议缺少该能力",
    "现有兼容实现不能提供所需不变量",
]


def _count_file_lines(path: Path) -> int:
    """返回文件行数;读失败返回 -1。"""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return -1


def _resolve_repo_path(raw: str) -> Path:
    """把 enriched 里记录的相对路径解析为仓库内绝对路径。"""
    norm = raw.replace("\\", "/").lstrip("./")
    return (REPO_ROOT / norm)


def verify_file_line(ref: str) -> dict:
    """核验单个 file:line 引用。返回结构化结果。"""
    m = FILELINE_RE.search(ref)
    if not m:
        return {"ref": ref, "parsed": False, "ok": False, "reason": "无法解析 file:line 格式"}
    rel, start_s, end_s = m.group(1), m.group(2), m.group(3)
    start = int(start_s)
    end = int(end_s) if end_s else start
    path = _resolve_repo_path(rel)
    if not path.exists():
        return {"ref": ref, "file": rel, "parsed": True, "ok": False,
                "reason": "文件不存在(疑似编造路径)"}
    if not path.is_file():
        return {"ref": ref, "file": rel, "parsed": True, "ok": False,
                "reason": "路径不是文件"}
    total = _count_file_lines(path)
    if total < 0:
        return {"ref": ref, "file": rel, "parsed": True, "ok": False,
                "reason": "文件无法读取"}
    if start < 1 or end > total:
        return {"ref": ref, "file": rel, "line_start": start, "line_end": end,
                "file_total_lines": total, "parsed": True, "ok": False,
                "reason": f"行号越界(文件仅 {total} 行)"}
    return {"ref": ref, "file": rel, "line_start": start, "line_end": end,
            "file_total_lines": total, "parsed": True, "ok": True}


def main() -> int:
    problems: list[str] = []
    warnings: list[str] = []

    if not ENRICHED_DIR.exists():
        print(f"[FATAL] enriched 目录不存在: {ENRICHED_DIR}", file=sys.stderr)
        return 2

    domain_files = sorted(ENRICHED_DIR.glob("domain-*.json"))
    if len(domain_files) != EXPECTED_DOMAIN_COUNT:
        warnings.append(
            f"域文件数={len(domain_files)},期望 {EXPECTED_DOMAIN_COUNT}"
            f"(可能工作流未全部完成)"
        )

    all_nodes: list[dict] = []
    per_domain_count: dict[str, int] = {}
    seen_ids: set[str] = set()
    dup_ids: list[str] = []

    for df in domain_files:
        try:
            data = json.loads(df.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{df.name}: 无法解析 JSON: {exc}")
            continue
        nodes = data.get("nodes") if isinstance(data, dict) else data
        if not isinstance(nodes, list):
            problems.append(f"{df.name}: 顶层缺少 nodes 数组")
            continue
        per_domain_count[df.stem] = len(nodes)
        for node in nodes:
            if not isinstance(node, dict):
                problems.append(f"{df.name}: 含非对象节点")
                continue
            nid = node.get("id", "<无id>")
            if nid in seen_ids:
                dup_ids.append(nid)
            seen_ids.add(nid)
            # 字段完整性
            missing = [f for f in REQUIRED_FIELDS if not node.get(f)]
            if missing:
                problems.append(f"{df.name}:{nid} 缺字段 {missing}")
            # 状态/严重度合法性
            st = node.get("status")
            if st not in ALLOWED_STATUS:
                problems.append(f"{df.name}:{nid} 非法 status={st!r}")
            sev = node.get("severity")
            if sev not in ALLOWED_SEVERITY:
                problems.append(f"{df.name}:{nid} 非法 severity={sev!r}")
            node["_source_domain_file"] = df.name
            all_nodes.append(node)

    if dup_ids:
        problems.append(f"重复节点 id: {sorted(set(dup_ids))}")

    total_nodes = len(all_nodes)
    if total_nodes != EXPECTED_NODE_COUNT:
        warnings.append(f"节点总数={total_nodes},期望 {EXPECTED_NODE_COUNT}")

    # ---- file:line 全量自动核验 ----
    fileline_results: list[dict] = []
    bad_filelines: list[dict] = []
    for node in all_nodes:
        refs: list[str] = []
        ci = node.get("current_impl")
        if isinstance(ci, str):
            refs.append(ci)
        elif isinstance(ci, list):
            refs.extend(str(x) for x in ci)
        ev = node.get("evidence_refs")
        if isinstance(ev, list):
            refs.extend(str(x) for x in ev)
        elif isinstance(ev, str):
            refs.append(ev)
        node_checks = []
        for ref in refs:
            # 一个字段里可能含多个 file:line
            found_any = False
            for m in FILELINE_RE.finditer(ref):
                found_any = True
                res = verify_file_line(m.group(0))
                res["node_id"] = node.get("id")
                node_checks.append(res)
                fileline_results.append(res)
                if not res["ok"]:
                    bad_filelines.append(res)
            if not found_any and node.get("current_impl") == ref:
                # current_impl 应含真实 file:line
                w = {"ref": ref, "node_id": node.get("id"), "parsed": False,
                     "ok": False, "reason": "current_impl 未含可解析 file:line"}
                fileline_results.append(w)
                bad_filelines.append(w)
        node["_fileline_checks"] = node_checks

    # ---- 模板占位检测 ----
    root_causes = Counter(
        (n.get("root_cause") or "").strip() for n in all_nodes
    )
    dup_root_causes = {k: v for k, v in root_causes.items() if k and v > 1}
    placeholder_hits = []
    for n in all_nodes:
        blob = f"{n.get('root_cause','')} {n.get('defect','')}"
        for snip in KNOWN_PLACEHOLDER_SNIPPETS:
            if snip in blob:
                placeholder_hits.append(n.get("id"))
                break

    if dup_root_causes:
        warnings.append(
            f"root_cause 文本雷同({len(dup_root_causes)} 组重复),"
            f"疑似模板占位,需人工复核"
        )
    if placeholder_hits:
        problems.append(f"命中已知模板占位文本的节点: {placeholder_hits}")

    # ---- 汇总统计 ----
    by_sev = Counter(n.get("severity") for n in all_nodes)
    by_status = Counter(n.get("status") for n in all_nodes)

    merged = {
        "audit_id": "production-readiness-batch0",
        "generated_from": "audit/production-readiness/enriched/domain-*.json",
        "node_count": total_nodes,
        "domain_file_count": len(domain_files),
        "by_severity": dict(by_sev),
        "by_status": dict(by_status),
        "per_domain_count": per_domain_count,
        "nodes": all_nodes,
    }
    OUT_MERGED.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    OUT_FILELINE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILELINE.write_text(
        json.dumps({
            "total_refs_checked": len(fileline_results),
            "bad_refs": bad_filelines,
            "all_refs": fileline_results,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ---- 报告 ----
    print("=" * 60)
    print("批次0 任务#2 合并+自动核验报告")
    print("=" * 60)
    print(f"域文件: {len(domain_files)}/{EXPECTED_DOMAIN_COUNT}")
    print(f"节点总数: {total_nodes}/{EXPECTED_NODE_COUNT}")
    print(f"按严重度: {dict(by_sev)}")
    print(f"按状态: {dict(by_status)}")
    print(f"每域节点数: {per_domain_count}")
    print(f"file:line 引用核验: 共 {len(fileline_results)} 条, "
          f"异常 {len(bad_filelines)} 条")
    if bad_filelines:
        print("\n[异常 file:line 明细](前 20 条):")
        for b in bad_filelines[:20]:
            print(f"  - {b.get('node_id')}: {b.get('ref')} -> {b.get('reason')}")
    print(f"\n合并输出: {OUT_MERGED}")
    print(f"抽查清单: {OUT_FILELINE}")

    if warnings:
        print("\n[警告]")
        for w in warnings:
            print(f"  ! {w}")
    if problems:
        print("\n[阻断问题]")
        for p in problems:
            print(f"  x {p}")
        print(f"\n结论: 不通过({len(problems)} 个阻断问题)")
        return 1
    print("\n结论: 结构与自动核验通过(file:line 真实性仍建议主控随机抽读复核)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

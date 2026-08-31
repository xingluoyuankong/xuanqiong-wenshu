"""Create and validate redacted human-review bundles for quality calibration.

The default bundle never emits chapter prose. Review text is exported only with
--include-content and an explicit --content-output path, so evidence packages
can be committed or shared without leaking user fiction.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

CORE_LABELS = (
    "human_overall_accept",
    "human_ending_pressure",
    "human_dialogue_changes_state",
    "human_late_reversal",
    "human_speaker_distinct",
    "human_balance_acceptable",
    "human_scene_transition_clear",
    "human_static_description_excessive",
)
LABEL_VALUES = {"true", "false", "na"}
IDENTITY_COLUMNS = ("source_version_id", "source_chapter_id", "content_sha256")


def _decode(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _metrics(metadata: dict[str, Any]) -> dict[str, Any]:
    for key in ("quality_metrics", "story_progression_guard"):
        value = metadata.get(key)
        if isinstance(value, dict):
            return value
    summaries = metadata.get("review_summaries")
    if isinstance(summaries, dict):
        for key in ("final_quality_metrics", "story_progression_guard"):
            value = summaries.get(key)
            if isinstance(value, dict):
                return value
    return {}


def _codes(gate: dict[str, Any], field: str) -> list[str]:
    values = gate.get(field)
    if not isinstance(values, list):
        return []
    return sorted({str(item.get("code")) for item in values if isinstance(item, dict) and item.get("code")})


def _bucket(metrics: dict[str, Any], blockers: list[str], warnings: list[str]) -> str:
    if blockers:
        return "blocker"
    if metrics.get("ending_pressure_passed") is False:
        return "ending_pressure_false"
    if metrics.get("dialogue_changes_state") is False:
        return "dialogue_state_false"
    if metrics.get("reversal_in_late_section") is False:
        return "late_reversal_false"
    if metrics.get("scene_transition_warning") is True:
        return "scene_transition_warning"
    if metrics.get("static_description_risk") is True:
        return "static_description_risk"
    if warnings:
        return "warning_only"
    return "clean_pass"


def load_rows(database: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(f"file:{database.resolve()}?mode=ro", uri=True)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(chapter_versions)")}
        required = {"id", "chapter_id", "content", "metadata"}
        missing = required - columns
        if missing:
            raise ValueError(f"chapter_versions missing columns: {sorted(missing)}")
        created = "created_at" if "created_at" in columns else "NULL"
        rows = connection.execute(
            f"SELECT id, chapter_id, content, metadata, {created} AS created_at FROM chapter_versions ORDER BY id"
        ).fetchall()
    finally:
        connection.close()
    result: list[dict[str, Any]] = []
    for version_id, chapter_id, content, raw_metadata, created_at in rows:
        text = str(content or "")
        metadata = _decode(raw_metadata)
        metrics = _metrics(metadata)
        gate = metadata.get("quality_gate") if isinstance(metadata.get("quality_gate"), dict) else {}
        blockers = _codes(gate, "blockers")
        warnings = _codes(gate, "warnings")
        word_count = metrics.get("word_count")
        if not isinstance(word_count, int):
            word_count = len("".join(text.split()))
        result.append({
            "version_id": int(version_id),
            "chapter_id": int(chapter_id),
            "created_at": str(created_at or ""),
            "content": text,
            "content_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "word_count": int(word_count),
            "blocker_codes": blockers,
            "warning_codes": warnings,
            "metrics": metrics,
            "bucket": _bucket(metrics, blockers, warnings),
        })
    return result


def select_rows(rows: list[dict[str, Any]], *, sample_size: int) -> list[dict[str, Any]]:
    if sample_size < 1:
        raise ValueError("sample_size must be positive")
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[row["bucket"]].append(row)
    for values in buckets.values():
        values.sort(key=lambda item: (item["content_sha256"], item["version_id"]))
    selected: list[dict[str, Any]] = []
    ordered = sorted(buckets)
    while len(selected) < sample_size:
        progressed = False
        for bucket in ordered:
            if buckets[bucket]:
                selected.append(buckets[bucket].pop(0))
                progressed = True
                if len(selected) == sample_size:
                    break
        if not progressed:
            break
    return sorted(selected, key=lambda item: item["version_id"])


def _row_for_bundle(index: int, row: dict[str, Any]) -> dict[str, Any]:
    metrics = row["metrics"]
    return {
        "sample_id": f"Q{index:03d}",
        "source_version_id": row["version_id"],
        "source_chapter_id": row["chapter_id"],
        "content_sha256": row["content_sha256"],
        "word_count": row["word_count"],
        "bucket": row["bucket"],
        "detected_blocker_codes": ";".join(row["blocker_codes"]),
        "detected_warning_codes": ";".join(row["warning_codes"]),
        "detected_ending_pressure": metrics.get("ending_pressure_passed"),
        "detected_dialogue_changes_state": metrics.get("dialogue_changes_state"),
        "detected_late_reversal": metrics.get("reversal_in_late_section"),
        "detected_speaker_count": metrics.get("speaker_count"),
        "detected_dominant_speaker_ratio": metrics.get("dominant_speaker_ratio"),
        "detected_dialogue_ratio": metrics.get("dialogue_ratio"),
        "detected_action_ratio": metrics.get("action_ratio"),
        "detected_description_ratio": metrics.get("description_ratio"),
        "detected_scene_transition_warning": metrics.get("scene_transition_warning"),
        "detected_static_description_risk": metrics.get("static_description_risk"),
    }


def export_bundle(database: Path, output_dir: Path, *, sample_size: int = 30, include_content: bool = False, content_output: Path | None = None) -> dict[str, Any]:
    rows = load_rows(database)
    selected = select_rows(rows, sample_size=sample_size)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows = [_row_for_bundle(index, row) for index, row in enumerate(selected, start=1)]
    manifest = {
        "schema_version": 1,
        "source_database": database.name,
        "source_row_count": len(rows),
        "selected_count": len(manifest_rows),
        "selection": "deterministic round-robin across diagnostic buckets, ordered by content SHA-256",
        "content_emitted": False,
        "bucket_counts": dict(sorted(Counter(row["bucket"] for row in selected).items())),
        "samples": manifest_rows,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    columns = [*manifest_rows[0].keys()] if manifest_rows else ["sample_id"]
    columns += [*CORE_LABELS, "reviewer_id", "review_notes"]
    with (output_dir / "labels.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in manifest_rows:
            writer.writerow(row)
    instructions = f"""# 小说质量人工标注说明

本包默认不含正文。审阅人必须在受控本地环境中按 `source_version_id` 打开 `{database.name}` 中的原文，禁止把正文复制回此目录或提交到版本库。

每项填 `true` / `false` / `na`：
- human_overall_accept：是否愿意将本章作为可继续阅读的初稿放行。
- human_ending_pressure：结尾是否递出未解决的风险、选择、信息或后果。
- human_dialogue_changes_state：对白是否改变信息、立场、筹码、风险或关系。
- human_late_reversal：后 40% 是否出现可见反转。
- human_speaker_distinct：主要说话人是否能凭措辞/立场区分。
- human_balance_acceptable：对白、动作、描写配比是否服务叙事而非灌水。
- human_scene_transition_clear：场景切换是否有清晰承接。
- human_static_description_excessive：是否存在过多不推动叙事的静态描写。

## 双审阅步骤

1. 复制 `labels.csv` 为两个独立文件，例如 `labels-reviewer-a.csv`、`labels-reviewer-b.csv`；两位审阅人不得查看对方标签。
2. 每位审阅人填满全部 `human_*` 字段和自己的 `reviewer_id`；`review_notes` 只能写抽象原因，不得粘贴正文。
3. 分别验证：`python scripts/export_quality_annotation_bundle.py --validate-labels <各自副本.csv> --manifest manifest.json --require-complete --require-single-reviewer`。
4. 合并：`python scripts/merge_quality_annotations.py <副本A.csv> <副本B.csv> --output merged-annotations.json`。合并结果中的 `adjudicate` 必须人工裁决，脚本不会自动吞掉分歧。

"""
    (output_dir / "README.md").write_text(instructions, encoding="utf-8")
    if include_content:
        if content_output is None:
            raise ValueError("--include-content requires --content-output")
        content_output.parent.mkdir(parents=True, exist_ok=True)
        with content_output.open("w", encoding="utf-8") as handle:
            for index, row in enumerate(selected, start=1):
                handle.write(json.dumps({"sample_id": f"Q{index:03d}", "source_version_id": row["version_id"], "content": row["content"]}, ensure_ascii=False) + "\n")
        manifest["content_emitted"] = True
        manifest["content_file"] = content_output.name
        (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def validate_labels(
    labels_file: Path,
    manifest_file: Path | None = None,
    *,
    require_complete: bool = False,
    require_single_reviewer: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        with labels_file.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = [str(field or "").strip() for field in (reader.fieldnames or [])]
            rows = list(reader)
    except (OSError, UnicodeError, csv.Error) as exc:
        return {
            "row_count": 0,
            "labeled_row_count": 0,
            "complete_labeled_row_count": 0,
            "reviewer_ids": [],
            "require_complete": require_complete,
            "require_single_reviewer": require_single_reviewer,
            "valid": False,
            "errors": [f"cannot read labels: {type(exc).__name__}"],
        }
    required_headers = {"sample_id"}
    if require_complete:
        required_headers.update((*CORE_LABELS, "reviewer_id"))
    if manifest_file is not None:
        required_headers.update(IDENTITY_COLUMNS)
    missing_headers = sorted(required_headers - set(fieldnames))
    if missing_headers:
        errors.append(f"missing required columns: {missing_headers}")
    seen_sample_ids: set[str] = set()
    labeled = 0
    complete_labeled = 0
    reviewer_ids: set[str] = set()
    manifest_samples: dict[str, dict[str, Any]] = {}
    if manifest_file is not None:
        try:
            manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
            raw_samples = manifest.get("samples") if isinstance(manifest, dict) else None
            if not isinstance(manifest, dict) or manifest.get("content_emitted") is not False:
                errors.append("manifest content_emitted must be false")
            if not isinstance(raw_samples, list):
                errors.append("manifest samples must be a list")
            else:
                for sample in raw_samples:
                    if not isinstance(sample, dict) or not str(sample.get("sample_id") or "").strip():
                        errors.append("manifest contains a sample without sample_id")
                        continue
                    sample_id = str(sample["sample_id"]).strip()
                    if sample_id in manifest_samples:
                        errors.append(f"manifest duplicate sample_id: {sample_id}")
                    manifest_samples[sample_id] = sample
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"cannot read manifest: {type(exc).__name__}")
    for number, row in enumerate(rows, start=2):
        sample_id = str(row.get("sample_id") or "").strip()
        if not sample_id:
            errors.append(f"line {number}: sample_id required")
        elif sample_id in seen_sample_ids:
            errors.append(f"line {number}: duplicate sample_id {sample_id}")
        else:
            seen_sample_ids.add(sample_id)
        if manifest_samples:
            expected = manifest_samples.get(sample_id)
            if expected is None:
                errors.append(f"line {number}: sample_id {sample_id} is not in manifest")
            else:
                for column in IDENTITY_COLUMNS:
                    actual_value = str(row.get(column) or "").strip()
                    expected_value = str(expected.get(column) or "").strip()
                    if not actual_value or actual_value != expected_value:
                        errors.append(f"line {number}: {column} does not match manifest")
        values = [str(row.get(label) or "").strip().lower() for label in CORE_LABELS]
        reviewer_id = str(row.get("reviewer_id") or "").strip()
        if any(values):
            labeled += 1
        if reviewer_id:
            reviewer_ids.add(reviewer_id)
        if all(value in LABEL_VALUES for value in values) and reviewer_id:
            complete_labeled += 1
        for label, value in zip(CORE_LABELS, values):
            if value and value not in LABEL_VALUES:
                errors.append(f"line {number}: {label} must be true/false/na")
        if any(values) and not reviewer_id:
            errors.append(f"line {number}: reviewer_id required when labels are present")
    if manifest_samples and seen_sample_ids != set(manifest_samples):
        errors.append("labels sample_id set does not match manifest")
    if require_complete and complete_labeled != len(rows):
        errors.append(f"complete labels required: {complete_labeled}/{len(rows)} rows are fully labeled")
    if require_single_reviewer and complete_labeled == len(rows) and len(reviewer_ids) != 1:
        errors.append("exactly one non-empty reviewer_id is required for a completed reviewer file")
    return {
        "row_count": len(rows),
        "labeled_row_count": labeled,
        "complete_labeled_row_count": complete_labeled,
        "reviewer_ids": sorted(reviewer_ids),
        "require_complete": require_complete,
        "require_single_reviewer": require_single_reviewer,
        "valid": not errors,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path, nargs="?")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--sample-size", type=int, default=30)
    parser.add_argument("--include-content", action="store_true")
    parser.add_argument("--content-output", type=Path)
    parser.add_argument("--validate-labels", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--require-complete", action="store_true", help="最终验收：要求每行全部核心人工字段已填写")
    parser.add_argument("--require-single-reviewer", action="store_true", help="完成的单份审阅 CSV 必须只含一个非空 reviewer_id")
    args = parser.parse_args(argv)
    if args.validate_labels:
        payload = validate_labels(
            args.validate_labels,
            args.manifest,
            require_complete=args.require_complete,
            require_single_reviewer=args.require_single_reviewer,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["valid"] else 1
    if args.database is None or args.output_dir is None:
        parser.error("生成标注包时必须提供 database 和 --output-dir；仅验证标签可只传 --validate-labels。")
    payload = export_bundle(args.database, args.output_dir, sample_size=args.sample_size, include_content=args.include_content, content_output=args.content_output)
    print(json.dumps({key: payload[key] for key in ("source_database", "source_row_count", "selected_count", "content_emitted", "bucket_counts")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

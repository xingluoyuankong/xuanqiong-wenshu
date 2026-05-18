from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "backend" / "storage" / "arboris.db"
STALE_STATUSES = {"generating", "evaluating", "waiting_for_confirm"}


def content_len(text: str | None) -> int:
    return len((text or "").strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="修复历史章节生成状态断链：自动备份，默认只预演。")
    parser.add_argument("--apply", action="store_true", help="实际写入数据库；未提供时仅打印计划。")
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite 数据库路径")
    parser.add_argument("--stale-minutes", type=int, default=30, help="超过该时间未更新的运行态章节视为过期")
    args = parser.parse_args()

    db_path = Path(args.db)
    if args.apply:
        backup = db_path.with_suffix(db_path.suffix + f".backup_before_repair_{datetime.now():%Y%m%d_%H%M%S}")
        shutil.copy2(db_path, backup)
        print(f"[backup] {backup}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    now = datetime.now()
    stale_before = now - timedelta(minutes=args.stale_minutes)
    actions: list[str] = []

    chapters = list(
        cur.execute(
            """
            select c.*, p.title
            from chapters c
            join novel_projects p on p.id = c.project_id
            order by p.created_at, c.chapter_number
            """
        )
    )

    for chapter in chapters:
        cid = int(chapter["id"])
        versions = list(
            cur.execute(
                "select id, content, created_at from chapter_versions where chapter_id=? order by created_at, id",
                (cid,),
            )
        )
        non_empty_versions = [v for v in versions if content_len(v["content"]) > 0]
        latest = non_empty_versions[-1] if non_empty_versions else None
        status = chapter["status"]
        updated_at = datetime.fromisoformat(str(chapter["updated_at"]).replace("Z", "+00:00")).replace(tzinfo=None)
        selected_id = chapter["selected_version_id"]
        selected_valid = selected_id is not None and any(int(v["id"]) == int(selected_id) for v in versions)

        if status == "successful" and (selected_id is None or not selected_valid) and latest:
            new_wc = content_len(latest["content"])
            actions.append(f"[select] {chapter['title']} 第{chapter['chapter_number']}章：绑定最新非空版本 {latest['id']}，word_count={new_wc}")
            if args.apply:
                cur.execute(
                    "update chapters set selected_version_id=?, word_count=?, updated_at=CURRENT_TIMESTAMP where id=?",
                    (int(latest["id"]), new_wc, cid),
                )
            continue

        if status in STALE_STATUSES and updated_at < stale_before:
            if latest:
                new_wc = content_len(latest["content"])
                actions.append(
                    f"[finalize-stale] {chapter['title']} 第{chapter['chapter_number']}章：{status} 已过期，自动选版本 {latest['id']} 并标记 successful"
                )
                if args.apply:
                    cur.execute(
                        """
                        update chapters
                        set status='successful', selected_version_id=?, word_count=?, updated_at=CURRENT_TIMESTAMP
                        where id=?
                        """,
                        (int(latest["id"]), new_wc, cid),
                    )
            else:
                actions.append(f"[fail-stale] {chapter['title']} 第{chapter['chapter_number']}章：{status} 已过期且无正文，标记 failed")
                if args.apply:
                    cur.execute(
                        """
                        update chapters
                        set status='failed',
                            real_summary='后台生成任务已过期且未产生可用正文，系统自动终止；请重新生成本章。',
                            word_count=0,
                            updated_at=CURRENT_TIMESTAMP
                        where id=?
                        """,
                        (cid,),
                    )
            continue

        if selected_id is not None and selected_valid:
            selected = next(v for v in versions if int(v["id"]) == int(selected_id))
            actual_wc = content_len(selected["content"])
            if abs(int(chapter["word_count"] or 0) - actual_wc) > max(120, int(actual_wc * 0.18)):
                actions.append(
                    f"[sync-word-count] {chapter['title']} 第{chapter['chapter_number']}章：{chapter['word_count']} -> {actual_wc}"
                )
                if args.apply:
                    cur.execute("update chapters set word_count=?, updated_at=CURRENT_TIMESTAMP where id=?", (actual_wc, cid))

    if args.apply:
        conn.commit()
    conn.close()

    print(f"mode={'APPLY' if args.apply else 'DRY-RUN'} actions={len(actions)}")
    for action in actions:
        print(action)


if __name__ == "__main__":
    main()

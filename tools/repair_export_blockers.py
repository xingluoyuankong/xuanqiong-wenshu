from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "backend" / "storage" / "arboris.db"


def sanitize_text_label(value: str, fallback: str) -> str:
    text = (value or "").strip()
    if not text or "??" in text or "\ufffd" in text:
        return fallback
    return text


def build_restoration_draft(project_title: str, chapter_number: int, outline_title: str, summary: str) -> str:
    """为历史失败且无正文的章节生成一版明确标注的人工恢复稿。

    这不是伪造 AI 原始输出，而是为了让历史库重新具备可读、可导出、可继续编辑的正文基线。
    后续作者仍可在写作桌面中继续精修或重新生成。
    """
    story_name = sanitize_text_label(project_title, "未命名项目")
    title = sanitize_text_label(outline_title, f"第{chapter_number}章")
    seed = summary or "这一章需要承接既有大纲，补齐人物行动、场景推进与结尾钩子。"
    paragraphs = [
        f"【历史失败章节恢复稿】《{story_name}》第{chapter_number}章《{title}》。这一版由修复脚本根据章节大纲补齐，用于恢复可读基线，作者可继续精修或重新生成。",
        f"本章的核心大纲是：{seed} 因为上一轮后台生成没有留下可用正文，故事在这里必须重新找到落点：人物要有明确行动，场景要能承接前文，结尾也要把读者推向下一章。",
        "夜色压低的时候，主角终于意识到，真正危险的并不是眼前的敌人，而是那些被忽略的细节正在彼此呼应。空气里有一种近乎金属的冷意，像某个看不见的机制已经开始转动，逼迫所有人重新选择立场。",
        "他没有立刻说出自己的判断。沉默给了他几秒钟时间，让他把线索一条条摆回脑海：来路上的异常、对方话语里的停顿、以及那个看似无关却反复出现的符号。每一处都很轻，却一起指向同一个答案。",
        "旁人的反应比他预想得更复杂。有人急于否认，有人下意识后退，也有人在恐惧里露出短暂的兴奋。主角从这些反应里确认，自己并不是唯一一个察觉真相的人；只是其他人比他更早学会了装作不知道。",
        "于是他改变了策略。不再硬闯，不再追问，而是顺着对方设计好的台阶往下走。他需要让局面看起来仍在对方掌控之中，只有这样，隐藏在暗处的规则才会继续显形。",
        "场景里的每一次声响都被放大：门轴的轻颤、远处机器的低鸣、纸页翻动时细小的摩擦声。它们像一串断续的提示，把人物情绪推到更紧的地方，也让本章的冲突从表层对峙转向更深的心理角力。",
        "当最后一个关键细节浮出水面时，主角终于明白，这一章不是胜利，也不是失败，而是进入真正谜面的入口。他收起最后的犹豫，留下一个只有自己能读懂的标记，然后转身走向更深处。",
        "结尾处，旧线索得到暂时安置，新问题被明确抛出：谁在操控规则？谁在借主角之手推进局面？下一章必须回答其中一个问题，同时埋下更大的反转。",
    ]
    return "\n\n".join(paragraphs)


def main() -> None:
    parser = argparse.ArgumentParser(description="为剩余导出阻断章节生成人工恢复稿并绑定 selected_version。")
    parser.add_argument("--apply", action="store_true", help="实际写入数据库；默认仅 dry-run。")
    parser.add_argument("--db", default=str(DB_PATH), help="SQLite 数据库路径")
    parser.add_argument("--refresh-existing", action="store_true", help="刷新既有 codex_repair 恢复稿，清理因历史乱码标题带入正文的问题。")
    args = parser.parse_args()

    db_path = Path(args.db)
    if args.apply:
        backup = db_path.with_suffix(db_path.suffix + f".backup_before_export_blocker_repair_{datetime.now():%Y%m%d_%H%M%S}")
        shutil.copy2(db_path, backup)
        print(f"[backup] {backup}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    blockers = list(
        cur.execute(
            """
            select c.id chapter_id, c.project_id, c.chapter_number, c.status, c.selected_version_id,
                   p.title project_title, o.title outline_title, o.summary outline_summary,
                   count(v.id) version_count
            from chapters c
            join novel_projects p on p.id = c.project_id
            left join chapter_outlines o on o.project_id = c.project_id and o.chapter_number = c.chapter_number
            left join chapter_versions v on v.chapter_id = c.id
            group by c.id
            having c.status != 'successful' or c.selected_version_id is null
            order by p.title, c.chapter_number
            """
        )
    )

    if args.refresh_existing:
        existing = list(
            cur.execute(
                """
                select v.id version_id, c.id chapter_id, c.project_id, c.chapter_number,
                       p.title project_title, o.title outline_title, o.summary outline_summary
                from chapter_versions v
                join chapters c on c.id = v.chapter_id
                join novel_projects p on p.id = c.project_id
                left join chapter_outlines o on o.project_id = c.project_id and o.chapter_number = c.chapter_number
                where v.provider = 'codex_repair'
                order by p.title, c.chapter_number
                """
            )
        )
        print(f"refresh_existing={len(existing)}")
        for item in existing:
            content = build_restoration_draft(
                item["project_title"] or "",
                int(item["chapter_number"]),
                item["outline_title"] or "",
                item["outline_summary"] or "",
            )
            print(f"[refresh] version={item['version_id']} chapter={item['chapter_id']} chars={len(content)}")
            if args.apply:
                cur.execute(
                    "update chapter_versions set content=?, metadata=? where id=?",
                    (
                        content,
                        '{"source":"repair_export_blockers.py","kind":"manual_restoration","refreshed":true}',
                        int(item["version_id"]),
                    ),
                )
                cur.execute(
                    "update chapters set word_count=?, real_summary=?, updated_at=CURRENT_TIMESTAMP where id=?",
                    (
                        len(content),
                        "历史失败章节已刷新人工恢复稿，可继续精修或重新生成。",
                        int(item["chapter_id"]),
                    ),
                )

    print(f"mode={'APPLY' if args.apply else 'DRY-RUN'} blockers={len(blockers)}")
    for item in blockers:
        content = build_restoration_draft(
            item["project_title"] or "",
            int(item["chapter_number"]),
            item["outline_title"] or "",
            item["outline_summary"] or "",
        )
        print(f"[restore] {item['project_title']} 第{item['chapter_number']}章 status={item['status']} versions={item['version_count']} chars={len(content)}")
        if args.apply:
            cur.execute(
                """
                insert into chapter_versions(chapter_id, version_label, provider, content, metadata, created_at)
                values(?, 'manual_restoration', 'codex_repair', ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    int(item["chapter_id"]),
                    content,
                    '{"source":"repair_export_blockers.py","kind":"manual_restoration"}',
                ),
            )
            version_id = cur.lastrowid
            cur.execute(
                """
                update chapters
                set status='successful',
                    selected_version_id=?,
                    word_count=?,
                    real_summary=?,
                    updated_at=CURRENT_TIMESTAMP
                where id=?
                """,
                (
                    version_id,
                    len(content),
                    "历史失败章节已生成人工恢复稿，可继续精修或重新生成。",
                    int(item["chapter_id"]),
                ),
            )

    if args.apply:
        conn.commit()
    conn.close()


if __name__ == "__main__":
    main()

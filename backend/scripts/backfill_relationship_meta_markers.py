import argparse
import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(BACKEND_DIR / ".env")

from app.db.session import AsyncSessionLocal
from app.models.novel import BlueprintRelationship
from app.services.novel_service import (
    _LEGACY_RELATIONSHIP_META_MARKER,
    _RELATIONSHIP_META_MARKER,
    _extract_marker_payload,
)


def _build_updated_description(original: str) -> str:
    return original.replace(_LEGACY_RELATIONSHIP_META_MARKER, _RELATIONSHIP_META_MARKER)


async def backfill(*, apply: bool, project_id: str | None, limit: int | None) -> int:
    async with AsyncSessionLocal() as session:
        stmt = select(BlueprintRelationship).where(
            BlueprintRelationship.description.contains(_LEGACY_RELATIONSHIP_META_MARKER)
        )
        if project_id:
            stmt = stmt.where(BlueprintRelationship.project_id == project_id)
        stmt = stmt.order_by(BlueprintRelationship.id)
        if limit:
            stmt = stmt.limit(limit)

        rows = list((await session.execute(stmt)).scalars())
        if not rows:
            print("未找到需要回填的旧版关系标记记录。")
            return 0

        changed = 0
        skipped = 0
        for relation in rows:
            original = relation.description or ""
            updated = _build_updated_description(original)
            if updated == original:
                skipped += 1
                print(f"[跳过] id={relation.id} project={relation.project_id} 原因：无需变更")
                continue

            old_description, old_meta = _extract_marker_payload(original)
            new_description, new_meta = _extract_marker_payload(updated)
            if old_description != new_description or old_meta != new_meta:
                skipped += 1
                print(f"[跳过] id={relation.id} project={relation.project_id} 原因：标记载荷不一致")
                continue

            changed += 1
            print(
                f"[{'执行' if apply else '预演'}] id={relation.id} project={relation.project_id} "
                f"from={relation.character_from} to={relation.character_to}"
            )
            if apply:
                relation.description = updated

        if apply and changed:
            await session.commit()
            print(f"已更新 {changed} 条记录；跳过 {skipped} 条。")
        else:
            await session.rollback()
            print(f"预演结果：将更新 {changed} 条记录；跳过 {skipped} 条。")
        return changed


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="回填蓝图关系中的旧版关系元标记。")
    parser.add_argument("--apply", action="store_true", help="实际写入变更；不带该参数时仅执行预演。")
    parser.add_argument("--project-id", help="仅处理指定项目 ID 的记录。")
    parser.add_argument("--limit", type=int, help="限制扫描记录数。")
    return parser.parse_args()


async def main() -> None:
    args = _parse_args()
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit 必须大于 0")
    await backfill(apply=args.apply, project_id=args.project_id, limit=args.limit)


if __name__ == "__main__":
    asyncio.run(main())

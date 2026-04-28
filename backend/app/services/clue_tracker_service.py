# 线索追踪服务层
from __future__ import annotations

from typing import Optional, List, Dict, Any

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.clue_tracker import StoryClue, ClueChapterLink, ClueThread, ClueType, ClueStatus, ClueAppearanceType
from ..models.foreshadowing import Foreshadowing


class ClueTrackerService:
    """线索追踪服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============ 线索 CRUD ============

    async def create_clue(
        self,
        project_id: str,
        name: str,
        clue_type: str,
        description: Optional[str] = None,
        importance: int = 3,
        planted_chapter: Optional[int] = None,
        is_red_herring: bool = False,
        red_herring_explanation: Optional[str] = None,
        clue_content: Optional[str] = None,
        hint_level: int = 2,
        design_intent: Optional[str] = None
    ) -> StoryClue:
        """创建新线索"""
        clue = StoryClue(
            project_id=project_id,
            name=name,
            clue_type=clue_type,
            description=description,
            importance=importance,
            planted_chapter=planted_chapter,
            is_red_herring=is_red_herring,
            red_herring_explanation=red_herring_explanation,
            clue_content=clue_content,
            hint_level=hint_level,
            design_intent=design_intent,
            status=ClueStatus.RED_HERRING.value if is_red_herring else ClueStatus.ACTIVE.value
        )
        self.db.add(clue)
        await self.db.commit()
        await self.db.refresh(clue)
        return clue

    async def sync_from_foreshadowings(self, project_id: str) -> Dict[str, int]:
        """把伏笔系统中的数据同步成线索追踪数据，避免详情页长期为空壳。"""
        result = await self.db.execute(
            select(Foreshadowing)
            .where(Foreshadowing.project_id == project_id)
            .order_by(Foreshadowing.chapter_number.asc(), Foreshadowing.id.asc())
        )
        foreshadowings = list(result.scalars().all())
        created = 0
        updated = 0

        for item in foreshadowings:
            clue_name = (item.name or item.content or f"第{item.chapter_number}章线索").strip()[:255]
            existing_result = await self.db.execute(
                select(StoryClue).where(
                    and_(
                        StoryClue.project_id == project_id,
                        StoryClue.name == clue_name,
                    )
                )
            )
            clue = existing_result.scalar_one_or_none()
            mapped_status = (
                ClueStatus.RESOLVED.value if item.status in {"revealed", "resolved"}
                else ClueStatus.ABANDONED.value if item.status == "abandoned"
                else ClueStatus.ACTIVE.value
            )
            payload = {
                "clue_type": ClueType.PLOT_HOOK.value if item.type in {"question", "mystery", "setup"} else ClueType.KEY_EVIDENCE.value,
                "description": item.content,
                "importance": 5 if item.importance == "major" else 4 if item.importance == "minor" else 3,
                "planted_chapter": item.chapter_number,
                "resolution_chapter": item.resolved_chapter_number,
                "status": mapped_status,
                "clue_content": item.reveal_method or item.content,
                "design_intent": item.reveal_impact,
            }
            if clue is None:
                clue = StoryClue(project_id=project_id, name=clue_name, **payload)
                self.db.add(clue)
                await self.db.flush()
                created += 1
            else:
                for key, value in payload.items():
                    setattr(clue, key, value)
                updated += 1

            link_result = await self.db.execute(
                select(ClueChapterLink).where(
                    and_(
                        ClueChapterLink.clue_id == clue.id,
                        ClueChapterLink.chapter_number == item.chapter_number,
                    )
                )
            )
            link = link_result.scalar_one_or_none()
            if link is None:
                self.db.add(
                    ClueChapterLink(
                        clue_id=clue.id,
                        chapter_id=item.chapter_id,
                        chapter_number=item.chapter_number,
                        appearance_type=ClueAppearanceType.MENTION.value,
                        content_excerpt=(item.content or "")[:500],
                        chapter_role="setup",
                    )
                )

        await self.db.commit()
        return {"created": created, "updated": updated}

    async def get_project_clues(
        self,
        project_id: str,
        status: Optional[str] = None,
        clue_type: Optional[str] = None,
        include_red_herring: bool = True
    ) -> List[StoryClue]:
        """获取项目的所有线索"""
        query = select(StoryClue).where(StoryClue.project_id == project_id)

        if status:
            query = query.where(StoryClue.status == status)
        if clue_type:
            query = query.where(StoryClue.clue_type == clue_type)
        if not include_red_herring:
            query = query.where(StoryClue.is_red_herring == False)

        query = query.order_by(StoryClue.importance.desc(), StoryClue.created_at.desc())

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_clue_by_id(self, clue_id: int) -> Optional[StoryClue]:
        """根据ID获取线索"""
        result = await self.db.execute(
            select(StoryClue).where(StoryClue.id == clue_id)
        )
        return result.scalar_one_or_none()

    async def update_clue(
        self,
        clue_id: int,
        **kwargs
    ) -> Optional[StoryClue]:
        """更新线索"""
        clue = await self.get_clue_by_id(clue_id)
        if not clue:
            return None

        for key, value in kwargs.items():
            if hasattr(clue, key) and value is not None:
                setattr(clue, key, value)

        await self.db.commit()
        await self.db.refresh(clue)
        return clue

    async def delete_clue(self, clue_id: int) -> bool:
        """删除线索"""
        clue = await self.get_clue_by_id(clue_id)
        if not clue:
            return False

        await self.db.delete(clue)
        await self.db.commit()
        return True

    # ============ 线索关联章节 ============

    async def link_clue_to_chapter(
        self,
        clue_id: int,
        chapter_id: int,
        chapter_number: int,
        appearance_type: str,
        content_excerpt: Optional[str] = None,
        detail_level: int = 3,
        chapter_role: Optional[str] = None
    ) -> ClueChapterLink:
        """将线索关联到章节"""
        link = ClueChapterLink(
            clue_id=clue_id,
            chapter_id=chapter_id,
            chapter_number=chapter_number,
            appearance_type=appearance_type,
            content_excerpt=content_excerpt,
            detail_level=detail_level,
            chapter_role=chapter_role
        )
        self.db.add(link)
        await self.db.commit()
        await self.db.refresh(link)
        return link

    async def get_clue_chapter_links(self, clue_id: int) -> List[ClueChapterLink]:
        """获取线索的所有章节关联"""
        result = await self.db.execute(
            select(ClueChapterLink).where(ClueChapterLink.clue_id == clue_id).order_by(ClueChapterLink.chapter_number)
        )
        return result.scalars().all()

    async def unlink_clue_from_chapter(self, link_id: int) -> bool:
        """解除线索与章节的关联"""
        result = await self.db.execute(
            select(ClueChapterLink).where(ClueChapterLink.id == link_id)
        )
        link = result.scalar_one_or_none()
        if not link:
            return False

        await self.db.delete(link)
        await self.db.commit()
        return True

    # ============ 线索分析 ============

    async def get_clue_timeline(self, clue_id: int) -> Optional[Dict[str, Any]]:
        """获取线索的时间线（所有出现章节）"""
        clue = await self.get_clue_by_id(clue_id)
        if not clue:
            return None

        links = await self.get_clue_chapter_links(clue_id)

        return {
            "clue_id": clue.id,
            "clue_name": clue.name,
            "clue_type": clue.clue_type,
            "status": clue.status,
            "planted_chapter": clue.planted_chapter,
            "resolution_chapter": clue.resolution_chapter,
            "is_red_herring": clue.is_red_herring,
            "appearances": [
                {
                    "link_id": link.id,
                    "chapter_number": link.chapter_number,
                    "appearance_type": link.appearance_type,
                    "detail_level": link.detail_level,
                    "chapter_role": link.chapter_role,
                    "content_excerpt": link.content_excerpt[:200] if link.content_excerpt else None
                }
                for link in links
            ]
        }

    async def analyze_clue_threads(self, project_id: str) -> Dict[str, Any]:
        """分析项目的线索网络"""
        clues = await self.get_project_clues(project_id, include_red_herring=True)

        # 分类统计
        type_counts: Dict[str, int] = {}
        status_counts: Dict[str, int] = {}
        red_herring_count = 0
        unresolved_count = 0

        for clue in clues:
            # 类型统计
            type_counts[clue.clue_type] = type_counts.get(clue.clue_type, 0) + 1
            # 状态统计
            status_counts[clue.status] = status_counts.get(clue.status, 0) + 1
            # 红鲱鱼
            if clue.is_red_herring:
                red_herring_count += 1
            # 未回收
            if clue.status == ClueStatus.ACTIVE.value and not clue.is_red_herring:
                unresolved_count += 1

        return {
            "project_id": project_id,
            "total_clues": len(clues),
            "type_counts": type_counts,
            "status_counts": status_counts,
            "red_herring_count": red_herring_count,
            "unresolved_count": unresolved_count,
            "threads": await self._analyze_threads(project_id, clues)
        }

    async def _analyze_threads(self, project_id: str, clues: List[StoryClue]) -> List[Dict[str, Any]]:
        """分析线索网络（简化版：按类型分组）"""
        # 简化实现：按线索类型分组
        threads: Dict[str, List[int]] = {}

        for clue in clues:
            if clue.is_red_herring:
                thread_type = "red_herring"
            elif clue.status == ClueStatus.RESOLVED.value:
                thread_type = "resolved"
            else:
                thread_type = clue.clue_type

            if thread_type not in threads:
                threads[thread_type] = []
            threads[thread_type].append(clue.id)

        return [
            {
                "thread_type": thread_type,
                "clue_count": len(clue_ids),
                "clue_ids": clue_ids
            }
            for thread_type, clue_ids in threads.items()
        ]

    async def identify_red_herrings(self, project_id: str) -> List[Dict[str, Any]]:
        """识别红鲱鱼线索"""
        result = await self.db.execute(
            select(StoryClue).where(
                and_(
                    StoryClue.project_id == project_id,
                    StoryClue.is_red_herring == True
                )
            )
        )
        clues = result.scalars().all()

        return [
            {
                "id": clue.id,
                "name": clue.name,
                "clue_type": clue.clue_type,
                "description": clue.description,
                "red_herring_explanation": clue.red_herring_explanation,
                "planted_chapter": clue.planted_chapter,
                "importance": clue.importance,
                "hint_level": clue.hint_level
            }
            for clue in clues
        ]

    async def find_unresolved_clues(self, project_id: str) -> List[Dict[str, Any]]:
        """找出未回收的伏笔"""
        result = await self.db.execute(
            select(StoryClue).where(
                and_(
                    StoryClue.project_id == project_id,
                    StoryClue.status == ClueStatus.ACTIVE.value,
                    StoryClue.is_red_herring == False
                )
            ).order_by(StoryClue.importance.desc())
        )
        clues = result.scalars().all()

        unresolved = []
        for clue in clues:
            links = await self.get_clue_chapter_links(clue.id)
            has_resolution = any(link.appearance_type == ClueAppearanceType.RESOLUTION.value for link in links)

            if not has_resolution:
                unresolved.append({
                    "id": clue.id,
                    "name": clue.name,
                    "clue_type": clue.clue_type,
                    "description": clue.description,
                    "importance": clue.importance,
                    "planted_chapter": clue.planted_chapter,
                    "appearance_count": len(links),
                    "hint_level": clue.hint_level
                })

        return unresolved

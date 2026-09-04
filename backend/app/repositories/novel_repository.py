# AIMETA P=小说仓库_小说和章节数据访问|R=小说CRUD_章节CRUD|NR=不含业务逻辑|E=NovelRepository|X=internal|A=仓库类|D=sqlalchemy|S=db|RD=./README.ai
from typing import Iterable, Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload

from .base import BaseRepository
from ..models import Chapter, NovelProject, ProjectMember


class NovelRepository(BaseRepository[NovelProject]):
    model = NovelProject

    async def get_by_id(self, project_id: str) -> Optional[NovelProject]:
        stmt = (
            select(NovelProject)
            .where(NovelProject.id == project_id)
            .execution_options(populate_existing=True)
            .options(
                selectinload(NovelProject.blueprint),
                selectinload(NovelProject.characters),
                selectinload(NovelProject.relationships_),
                selectinload(NovelProject.factions),
                selectinload(NovelProject.outlines),
                selectinload(NovelProject.conversations),
                selectinload(NovelProject.chapters).selectinload(Chapter.versions),
                selectinload(NovelProject.chapters).selectinload(Chapter.evaluations),
                selectinload(NovelProject.chapters).selectinload(Chapter.selected_version),
            )
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_user(self, user_id: int) -> Iterable[NovelProject]:
        result = await self.session.execute(
            select(NovelProject)
            .outerjoin(
                ProjectMember,
                and_(
                    ProjectMember.project_id == NovelProject.id,
                    ProjectMember.user_id == user_id,
                    ProjectMember.deleted_at.is_(None),
                ),
            )
            .where(
                or_(
                    NovelProject.user_id == user_id,
                    ProjectMember.id.is_not(None),
                )
            )
            .order_by(NovelProject.updated_at.desc())
            .options(
                selectinload(NovelProject.blueprint),
                selectinload(NovelProject.outlines),
                selectinload(NovelProject.chapters).selectinload(Chapter.selected_version),
            )
        )
        return result.scalars().all()

    async def list_all(self) -> Iterable[NovelProject]:
        result = await self.session.execute(
            select(NovelProject)
            .order_by(NovelProject.updated_at.desc())
            .options(
                selectinload(NovelProject.owner),
                selectinload(NovelProject.blueprint),
                selectinload(NovelProject.outlines),
                selectinload(NovelProject.chapters).selectinload(Chapter.selected_version),
            )
        )
        return result.scalars().all()

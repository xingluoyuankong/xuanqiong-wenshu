from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import NovelProject, ProjectMember, ProjectMemberRole, User


@dataclass(frozen=True)
class ProjectAccess:
    """Resolved project access for one request principal."""

    project: NovelProject
    user_id: int
    role: str
    is_admin: bool = False
    is_legacy_owner: bool = False

    @property
    def can_read(self) -> bool:
        return True

    @property
    def can_write(self) -> bool:
        return self.is_admin or self.role in {
            ProjectMemberRole.owner.value,
            ProjectMemberRole.editor.value,
        }

    @property
    def can_manage_members(self) -> bool:
        return self.is_admin or self.role == ProjectMemberRole.owner.value


class ProjectAccessService:
    """Resolve project visibility and write access without breaking legacy owners."""

    _WRITE_ROLES = {ProjectMemberRole.owner.value, ProjectMemberRole.editor.value}
    _VALID_ROLES = {role.value for role in ProjectMemberRole}

    def __init__(self, session: AsyncSession):
        self.session = session

    @staticmethod
    def is_admin(user: Any) -> bool:
        """Return whether a user-like object carries the administrator flag."""
        if isinstance(user, dict):
            return bool(user.get("is_admin", False))
        return bool(getattr(user, "is_admin", False))

    @staticmethod
    def _user_id(user: Any) -> int | None:
        if isinstance(user, int):
            return user
        value = user.get("id") if isinstance(user, dict) else getattr(user, "id", None)
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    async def _resolve_user(self, user: Any) -> Any:
        user_id = self._user_id(user)
        if user_id is None:
            return user
        if hasattr(user, "is_admin") and hasattr(user, "is_active"):
            return user
        return (await self.session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()

    @staticmethod
    def _is_active(user: Any) -> bool:
        if user is None:
            return False
        if isinstance(user, dict):
            return bool(user.get("is_active", True))
        return bool(getattr(user, "is_active", True))

    async def get_project(self, project_id: str) -> NovelProject | None:
        result = await self.session.execute(select(NovelProject).where(NovelProject.id == project_id))
        return result.scalar_one_or_none()

    async def _get_project(self, project_id: str) -> NovelProject | None:
        return await self.get_project(project_id)

    async def get_membership(
        self,
        project_id: str,
        user_id: int,
        *,
        include_deleted: bool = False,
    ) -> ProjectMember | None:
        conditions = [
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        ]
        if not include_deleted:
            conditions.append(ProjectMember.deleted_at.is_(None))
        result = await self.session.execute(select(ProjectMember).where(*conditions))
        return result.scalar_one_or_none()

    async def _get_active_member(self, project_id: str, user_id: int) -> ProjectMember | None:
        return await self.get_membership(project_id, user_id)

    async def _resolve_access(self, project_id: str, user: Any) -> ProjectAccess:
        user = await self._resolve_user(user)
        project = await self.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
        user_id = self._user_id(user)
        if user_id is None or not self._is_active(user):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前用户未激活或缺少有效身份")
        if self.is_admin(user):
            return ProjectAccess(project=project, user_id=user_id, role="admin", is_admin=True)

        membership = await self.get_membership(project_id, user_id, include_deleted=True)
        if membership is not None:
            if membership.deleted_at is not None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该项目")
            role = str(membership.role)
            if role not in self._VALID_ROLES:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="项目成员角色无效")
            return ProjectAccess(project=project, user_id=user_id, role=role)

        # Compatibility for databases created before project_members existed.
        if project.user_id == user_id:
            return ProjectAccess(
                project=project,
                user_id=user_id,
                role=ProjectMemberRole.owner.value,
                is_legacy_owner=True,
            )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问该项目")

    async def require_member(self, project_id: str, user: Any) -> ProjectMember | None:
        """Require project visibility and return the active membership when present."""
        access = await self._resolve_access(project_id, user)
        if access.is_admin or access.is_legacy_owner:
            return None
        return await self.get_membership(project_id, access.user_id)

    async def require_project_read(self, project_id: str, user: Any) -> ProjectAccess:
        return await self._resolve_access(project_id, user)

    async def require_project_write(self, project_id: str, user: Any) -> ProjectAccess:
        access = await self._resolve_access(project_id, user)
        if not access.can_write:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前项目为只读成员")
        return access

    async def can_read_project(self, project_id: str, user: Any) -> bool:
        try:
            await self.require_project_read(project_id, user)
            return True
        except HTTPException:
            return False

    async def can_write_project(self, project_id: str, user: Any) -> bool:
        try:
            await self.require_project_write(project_id, user)
            return True
        except HTTPException:
            return False

    async def add_or_restore_member(
        self,
        project_id: str,
        user_id: int,
        role: ProjectMemberRole | str,
        actor: Any,
    ) -> ProjectMember:
        access = await self.require_project_read(project_id, actor)
        if not access.can_manage_members:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权管理项目成员")
        role_value = role.value if isinstance(role, ProjectMemberRole) else str(role)
        if role_value not in self._VALID_ROLES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目成员角色无效")
        # Ownership remains anchored to NovelProject.user_id until an explicit
        # ownership-transfer workflow exists. This prevents multiple owners.
        if role_value == ProjectMemberRole.owner.value and user_id != access.project.user_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目所有者角色不可转授")
        target = (await self.session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        if target is None or not bool(target.is_active):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="成员用户不存在或未激活")
        member = await self.get_membership(project_id, user_id, include_deleted=True)
        if member is not None and member.role == ProjectMemberRole.owner.value and role_value != ProjectMemberRole.owner.value:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目所有者角色不可降级")
        if member is None:
            member = ProjectMember(
                id=str(uuid4()), project_id=project_id, user_id=user_id, role=role_value
            )
            self.session.add(member)
        else:
            member.role = role_value
            member.deleted_at = None
            member.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(member)
        return member

    async def update_member_role(
        self,
        project_id: str,
        user_id: int,
        role: ProjectMemberRole | str,
        actor: Any,
    ) -> ProjectMember:
        """Update an active member role without allowing ownership corruption."""
        access = await self.require_project_read(project_id, actor)
        if not access.can_manage_members:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权管理项目成员")
        role_value = role.value if isinstance(role, ProjectMemberRole) else str(role)
        if role_value not in self._VALID_ROLES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目成员角色无效")
        member = await self.get_membership(project_id, user_id)
        if member is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目成员不存在")
        if member.role == ProjectMemberRole.owner.value and role_value != ProjectMemberRole.owner.value:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目所有者角色不可降级")
        if role_value == ProjectMemberRole.owner.value and user_id != access.project.user_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目所有者角色不可转授")
        member.role = role_value
        member.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(member)
        return member

    async def remove_member(self, project_id: str, user_id: int, actor: Any) -> ProjectMember:
        access = await self.require_project_read(project_id, actor)
        if not access.can_manage_members:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权管理项目成员")
        member = await self.get_membership(project_id, user_id, include_deleted=True)
        if member is None or member.deleted_at is not None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目成员不存在")
        if member.role == ProjectMemberRole.owner.value or user_id == access.project.user_id:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="项目所有者不可移除")
        member.deleted_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(member)
        return member

    async def list_members(self, project_id: str, actor: Any) -> list[ProjectMember]:
        # Membership is project metadata: every active project reader may view
        # it, while mutations remain owner/admin-only.
        await self.require_project_read(project_id, actor)
        result = await self.session.execute(
            select(ProjectMember)
            .where(ProjectMember.project_id == project_id, ProjectMember.deleted_at.is_(None))
            .order_by(ProjectMember.created_at.asc(), ProjectMember.id.asc())
        )
        return list(result.scalars().all())

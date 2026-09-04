from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...models import ProjectMember, ProjectMemberRole
from ...schemas.user import UserInDB
from ...services.project_access_service import ProjectAccessService


router = APIRouter(
    prefix="/api/projects/{project_id}/members",
    tags=["Project Members"],
)


class ProjectMemberMutation(BaseModel):
    user_id: int
    role: ProjectMemberRole = ProjectMemberRole.viewer


class ProjectMemberRoleUpdate(BaseModel):
    role: ProjectMemberRole


class ProjectMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    user_id: int
    role: ProjectMemberRole
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class ProjectMemberListResponse(BaseModel):
    members: list[ProjectMemberRead]
    count: int


@router.get("", response_model=ProjectMemberListResponse)
async def list_project_members(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ProjectMemberListResponse:
    members = await ProjectAccessService(session).list_members(project_id, current_user)
    return ProjectMemberListResponse(
        members=[ProjectMemberRead.model_validate(member) for member in members],
        count=len(members),
    )


@router.post("", response_model=ProjectMemberRead, status_code=status.HTTP_200_OK)
async def add_or_restore_project_member(
    project_id: str,
    payload: ProjectMemberMutation,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ProjectMember:
    return await ProjectAccessService(session).add_or_restore_member(
        project_id=project_id,
        user_id=payload.user_id,
        role=payload.role,
        actor=current_user,
    )


@router.patch("/{user_id}", response_model=ProjectMemberRead)
async def update_project_member_role(
    project_id: str,
    user_id: int,
    payload: ProjectMemberRoleUpdate,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ProjectMember:
    return await ProjectAccessService(session).update_member_role(
        project_id=project_id,
        user_id=user_id,
        role=payload.role,
        actor=current_user,
    )


@router.delete("/{user_id}", response_model=ProjectMemberRead)
async def remove_project_member(
    project_id: str,
    user_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ProjectMember:
    return await ProjectAccessService(session).remove_member(
        project_id=project_id,
        user_id=user_id,
        actor=current_user,
    )

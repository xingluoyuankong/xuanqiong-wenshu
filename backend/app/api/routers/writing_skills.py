from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...schemas.user import UserInDB
from ...services.novel_service import NovelService
from ...services.writing_skills_service import WritingSkillsService

router = APIRouter(tags=["writing-skills"])


class SkillItemResponse(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    overview: Optional[str] = None
    category: Optional[str] = None
    version: str
    author: Optional[str] = None
    source_url: Optional[str] = None
    use_cases: list[str] = Field(default_factory=list)
    input_guide: Optional[str] = None
    output_format: list[str] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)
    example_prompt: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    installed: Optional[bool] = None
    installed_at: Optional[str] = None


class InstallSkillRequest(BaseModel):
    name: str
    description: Optional[str] = None
    category: Optional[str] = None
    version: str = "0.1.0"
    author: Optional[str] = None
    source_url: Optional[str] = None


class ExecuteSkillRequest(BaseModel):
    prompt: str
    project_id: Optional[str] = None
    chapter_number: Optional[int] = None


@router.get("/skills", response_model=list[SkillItemResponse])
async def get_skills(
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> list[dict]:
    service = WritingSkillsService(session)
    skills = await service.get_installed_skills()
    return [
        {
            "id": skill.id,
            "name": skill.name,
            "description": skill.description,
            "overview": None,
            "category": skill.category,
            "version": skill.version,
            "author": skill.author,
            "source_url": skill.source_url,
            "use_cases": [],
            "input_guide": None,
            "output_format": [],
            "tips": [],
            "example_prompt": None,
            "tags": [],
            "enabled": skill.enabled,
            "installed": True,
            "installed_at": skill.installed_at.isoformat() if skill.installed_at else None,
        }
        for skill in skills
    ]


@router.get("/skills/catalog", response_model=list[SkillItemResponse])
async def get_skill_catalog(
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> list[dict]:
    service = WritingSkillsService(session)
    return await service.fetch_skill_catalog()


@router.get("/skills/{skill_id}", response_model=SkillItemResponse)
async def get_skill_detail(
    skill_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> dict:
    service = WritingSkillsService(session)
    skill = await service.get_skill_detail(skill_id)
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="技能不存在")
    definition = service.get_skill_definition(skill.id)
    return {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "overview": definition.get("overview") if definition else None,
        "category": skill.category,
        "version": skill.version,
        "author": skill.author,
        "source_url": skill.source_url,
        "use_cases": definition.get("use_cases", []) if definition else [],
        "input_guide": definition.get("input_guide") if definition else None,
        "output_format": definition.get("output_format", []) if definition else [],
        "tips": definition.get("tips", []) if definition else [],
        "example_prompt": definition.get("example_prompt") if definition else None,
        "tags": definition.get("tags", []) if definition else [],
        "enabled": skill.enabled,
        "installed": True,
        "installed_at": skill.installed_at.isoformat() if skill.installed_at else None,
    }


@router.post("/skills/{skill_id}/install", response_model=SkillItemResponse)
async def install_skill(
    skill_id: str,
    request: InstallSkillRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> dict:
    service = WritingSkillsService(session)
    try:
        skill = await service.install_skill(
            skill_id=skill_id,
            name=request.name,
            description=request.description,
            category=request.category,
            version=request.version,
            author=request.author,
            source_url=request.source_url,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    definition = service.get_skill_definition(skill.id)
    return {
        "id": skill.id,
        "name": skill.name,
        "description": skill.description,
        "overview": definition.get("overview") if definition else None,
        "category": skill.category,
        "version": skill.version,
        "author": skill.author,
        "source_url": skill.source_url,
        "use_cases": definition.get("use_cases", []) if definition else [],
        "input_guide": definition.get("input_guide") if definition else None,
        "output_format": definition.get("output_format", []) if definition else [],
        "tips": definition.get("tips", []) if definition else [],
        "example_prompt": definition.get("example_prompt") if definition else None,
        "tags": definition.get("tags", []) if definition else [],
        "enabled": skill.enabled,
        "installed": True,
        "installed_at": skill.installed_at.isoformat() if skill.installed_at else None,
    }


@router.delete("/skills/{skill_id}/uninstall")
async def uninstall_skill(
    skill_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> dict:
    service = WritingSkillsService(session)
    success = await service.uninstall_skill(skill_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="技能不存在")
    return {"status": "success", "message": f"技能 {skill_id} 已卸载"}


@router.post("/skills/{skill_id}/execute")
async def execute_skill(
    skill_id: str,
    request: ExecuteSkillRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> dict:
    if request.project_id:
        novel_service = NovelService(session)
        await novel_service.ensure_project_owner(request.project_id, current_user.id)

    service = WritingSkillsService(session)
    try:
        return await service.execute_skill(
            skill_id=skill_id,
            prompt=request.prompt,
            project_id=request.project_id,
            chapter_number=request.chapter_number,
            user_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

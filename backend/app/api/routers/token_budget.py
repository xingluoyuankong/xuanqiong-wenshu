# Token 预算管理 API
from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...schemas.user import UserInDB
from ...services.novel_service import NovelService
from ...services.token_budget_service import TokenBudgetService

router = APIRouter(prefix="/projects", tags=["token-budget"])


# ============ Schema 定义 ============

class BudgetConfigSchema(BaseModel):
    """预算配置 Schema"""
    project_id: str
    total_budget: float
    chapter_budget: float
    module_allocation: dict
    warning_threshold: float


class UpdateBudgetRequest(BaseModel):
    """更新预算请求"""
    total_budget: Optional[float] = None
    chapter_budget: Optional[float] = None
    module_allocation: Optional[dict] = None
    warning_threshold: Optional[float] = None


class ModuleAllocationRequest(BaseModel):
    """模块分配请求"""
    module: str  # world/character/outline/content
    allocation_percent: int  # 百分比 0-100


class RecordUsageRequest(BaseModel):
    """记录使用请求"""
    module: str
    tokens_used: int
    cost: float
    model_name: Optional[str] = None
    chapter_id: Optional[int] = None
    operation_type: Optional[str] = None
    description: Optional[str] = None


class UsageStatsResponse(BaseModel):
    """使用统计响应"""
    project_id: str
    total_budget: float
    budget_remaining: float
    usage_percent: float
    total_tokens: int
    total_cost: float
    module_stats: dict
    record_count: int


class ModuleUsageResponse(BaseModel):
    """模块使用响应"""
    project_id: str
    module_usage: dict
    total_budget: float
    warning_threshold: float


class AlertSchema(BaseModel):
    """预警 Schema"""
    id: int
    alert_type: str
    threshold_percent: float
    current_usage: float
    budget_limit: float
    message: str
    is_resolved: bool
    created_at: str


# ============ 路由端点 ============

@router.get("/{project_id}/token-budget", response_model=BudgetConfigSchema)
async def get_token_budget(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user)
) -> dict:
    """获取项目的 Token 预算配置"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    service = TokenBudgetService(session)
    config = await service.get_budget_config(project_id)
    return config


@router.put("/{project_id}/token-budget", response_model=BudgetConfigSchema)
async def update_token_budget(
    project_id: str,
    request: UpdateBudgetRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user)
) -> dict:
    """更新项目的 Token 预算配置"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    service = TokenBudgetService(session)
    budget = await service.update_budget(
        project_id=project_id,
        total_budget=request.total_budget,
        chapter_budget=request.chapter_budget,
        module_allocation=request.module_allocation,
        warning_threshold=request.warning_threshold
    )
    return {
        "project_id": budget.project_id,
        "total_budget": budget.total_budget,
        "chapter_budget": budget.chapter_budget,
        "module_allocation": budget.module_allocation,
        "warning_threshold": budget.warning_threshold
    }


@router.post("/{project_id}/token-budget/usage")
async def record_token_usage(
    project_id: str,
    request: RecordUsageRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user)
) -> dict:
    """记录一次 Token 使用"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    service = TokenBudgetService(session)
    usage = await service.record_usage(
        project_id=project_id,
        module=request.module,
        tokens_used=request.tokens_used,
        cost=request.cost,
        model_name=request.model_name,
        chapter_id=request.chapter_id,
        operation_type=request.operation_type,
        description=request.description
    )

    # 检查是否触发预警
    await service.check_and_create_alert(project_id)

    return {
        "id": usage.id,
        "project_id": usage.project_id,
        "module": usage.module,
        "tokens_used": usage.tokens_used,
        "cost": usage.cost,
        "created_at": usage.created_at.isoformat()
    }


@router.get("/{project_id}/token-budget/usage", response_model=UsageStatsResponse)
async def get_token_usage(
    project_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    chapter_id: Optional[int] = None,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user)
) -> dict:
    """获取项目的 Token 使用统计"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    service = TokenBudgetService(session)

    # 解析日期参数
    start = datetime.fromisoformat(start_date) if start_date else None
    end = datetime.fromisoformat(end_date) if end_date else None

    stats = await service.get_usage_stats(
        project_id=project_id,
        start_date=start,
        end_date=end,
        chapter_id=chapter_id
    )
    return stats


@router.get("/{project_id}/token-budget/usage-by-module", response_model=ModuleUsageResponse)
async def get_module_usage(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user)
) -> dict:
    """获取各模块的使用量"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    service = TokenBudgetService(session)
    usage = await service.get_module_usage(project_id)
    return usage


@router.get("/{project_id}/token-budget/alerts", response_model=List[AlertSchema])
async def get_budget_alerts(
    project_id: str,
    include_resolved: bool = False,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user)
) -> List[dict]:
    """获取项目的预算预警列表"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    service = TokenBudgetService(session)
    alerts = await service.get_alerts(project_id, include_resolved)
    return alerts


@router.post("/{project_id}/token-budget/alerts/{alert_id}/resolve")
async def resolve_budget_alert(
    project_id: str,
    alert_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user)
) -> dict:
    """标记预警为已处理"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    service = TokenBudgetService(session)
    success = await service.resolve_alert(alert_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"预警 ID {alert_id} 不存在"
        )

    return {"status": "success", "message": f"预警 {alert_id} 已标记为已处理"}


@router.post("/{project_id}/token-budget/allocate")
async def allocate_module_budget(
    project_id: str,
    allocations: List[ModuleAllocationRequest],
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user)
) -> dict:
    """批量分配模块预算"""
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)
    service = TokenBudgetService(session)

    # 构建模块分配字典
    allocation_dict = {}
    total_percent = 0

    for alloc in allocations:
        allocation_dict[alloc.module] = alloc.allocation_percent
        total_percent += alloc.allocation_percent

    # 验证总分配是否为 100%
    if total_percent != 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"模块分配总和必须为 100%，当前为 {total_percent}%"
        )

    # 更新预算配置
    budget = await service.update_budget(
        project_id=project_id,
        module_allocation=allocation_dict
    )

    return {
        "status": "success",
        "message": "模块预算分配已更新",
        "module_allocation": budget.module_allocation
    }
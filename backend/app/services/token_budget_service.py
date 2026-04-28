# Token 预算管理服务层
from __future__ import annotations

from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.token_budget import TokenBudget, TokenUsage, TokenBudgetAlert


class TokenBudgetService:
    """Token 预算服务"""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ============ 预算配置管理 ============

    async def get_or_create_budget(self, project_id: str) -> TokenBudget:
        """获取项目的预算配置，如果不存在则创建默认配置"""
        result = await self.db.execute(
            select(TokenBudget).where(TokenBudget.project_id == project_id)
        )
        budget = result.scalar_one_or_none()

        if not budget:
            budget = TokenBudget(
                project_id=project_id,
                total_budget=100.0,
                chapter_budget=5.0,
                module_allocation={"world": 20, "character": 15, "outline": 10, "content": 55},
                warning_threshold=80.0
            )
            self.db.add(budget)
            await self.db.commit()
            await self.db.refresh(budget)

        return budget

    async def update_budget(
        self,
        project_id: str,
        total_budget: Optional[float] = None,
        chapter_budget: Optional[float] = None,
        module_allocation: Optional[dict] = None,
        warning_threshold: Optional[float] = None
    ) -> TokenBudget:
        """更新项目预算配置"""
        budget = await self.get_or_create_budget(project_id)

        if total_budget is not None:
            budget.total_budget = total_budget
        if chapter_budget is not None:
            budget.chapter_budget = chapter_budget
        if module_allocation is not None:
            budget.module_allocation = module_allocation
        if warning_threshold is not None:
            budget.warning_threshold = warning_threshold

        await self.db.commit()
        await self.db.refresh(budget)
        return budget

    async def get_budget_config(self, project_id: str) -> dict:
        """获取预算配置（返回字典格式）"""
        budget = await self.get_or_create_budget(project_id)
        return {
            "project_id": budget.project_id,
            "total_budget": budget.total_budget,
            "chapter_budget": budget.chapter_budget,
            "module_allocation": budget.module_allocation,
            "warning_threshold": budget.warning_threshold
        }

    # ============ 使用记录管理 ============

    async def record_usage(
        self,
        project_id: str,
        module: str,
        tokens_used: int,
        cost: float,
        model_name: Optional[str] = None,
        chapter_id: Optional[int] = None,
        operation_type: Optional[str] = None,
        description: Optional[str] = None
    ) -> TokenUsage:
        """记录一次 Token 使用"""
        usage = TokenUsage(
            project_id=project_id,
            chapter_id=chapter_id,
            module=module,
            tokens_used=tokens_used,
            cost=cost,
            model_name=model_name,
            operation_type=operation_type,
            description=description
        )
        self.db.add(usage)
        await self.db.commit()
        await self.db.refresh(usage)
        return usage

    async def get_usage_stats(
        self,
        project_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        chapter_id: Optional[int] = None
    ) -> dict:
        """获取使用统计"""
        # 构建查询
        query = select(TokenUsage).where(TokenUsage.project_id == project_id)

        if start_date:
            query = query.where(TokenUsage.created_at >= start_date)
        if end_date:
            query = query.where(TokenUsage.created_at <= end_date)
        if chapter_id:
            query = query.where(TokenUsage.chapter_id == chapter_id)

        result = await self.db.execute(query)
        usages = result.scalars().all()

        # 统计各模块使用量
        module_stats: Dict[str, Dict[str, float]] = {
            "world": {"tokens": 0, "cost": 0.0},
            "character": {"tokens": 0, "cost": 0.0},
            "outline": {"tokens": 0, "cost": 0.0},
            "content": {"tokens": 0, "cost": 0.0},
            "other": {"tokens": 0, "cost": 0.0}
        }

        total_tokens = 0
        total_cost = 0.0

        for usage in usages:
            module_key = usage.module if usage.module in module_stats else "other"
            module_stats[module_key]["tokens"] += usage.tokens_used
            module_stats[module_key]["cost"] += usage.cost
            total_tokens += usage.tokens_used
            total_cost += usage.cost

        # 获取预算信息
        budget = await self.get_or_create_budget(project_id)
        budget_remaining = budget.total_budget - total_cost
        usage_percent = (total_cost / budget.total_budget * 100) if budget.total_budget > 0 else 0

        return {
            "project_id": project_id,
            "total_budget": budget.total_budget,
            "budget_remaining": budget_remaining,
            "usage_percent": round(usage_percent, 2),
            "total_tokens": total_tokens,
            "total_cost": round(total_cost, 4),
            "module_stats": module_stats,
            "record_count": len(usages)
        }

    async def get_module_usage(self, project_id: str) -> dict:
        """获取各模块的当前使用量"""
        result = await self.db.execute(
            select(
                TokenUsage.module,
                func.sum(TokenUsage.tokens_used).label("total_tokens"),
                func.sum(TokenUsage.cost).label("total_cost")
            ).where(TokenUsage.project_id == project_id).group_by(TokenUsage.module)
        )

        usage_by_module = {}
        for row in result:
            usage_by_module[row.module] = {
                "tokens": row.total_tokens or 0,
                "cost": round(row.total_cost or 0, 4)
            }

        # 获取预算配置
        budget = await self.get_or_create_budget(project_id)

        # 计算各模块使用占比
        module_usage = {}
        allocation = budget.module_allocation or {}

        for module_name in ["world", "character", "outline", "content"]:
            used = usage_by_module.get(module_name, {}).get("cost", 0)
            allocated = allocation.get(module_name, 0) / 100 * budget.total_budget
            module_usage[module_name] = {
                "used": used,
                "allocated": allocated,
                "remaining": max(0, allocated - used),
                "percent": round(used / allocated * 100, 2) if allocated > 0 else 0
            }

        return {
            "project_id": project_id,
            "module_usage": module_usage,
            "total_budget": budget.total_budget,
            "warning_threshold": budget.warning_threshold
        }

    # ============ 预警管理 ============

    async def check_and_create_alert(self, project_id: str) -> Optional[TokenBudgetAlert]:
        """检查使用量是否触发预警阈值"""
        stats = await self.get_usage_stats(project_id)
        budget = await self.get_or_create_budget(project_id)

        usage_percent = stats["usage_percent"]
        threshold = budget.warning_threshold

        if usage_percent >= 100:
            alert_type = "exceeded"
        elif usage_percent >= threshold:
            alert_type = "critical" if usage_percent >= 90 else "warning"
        else:
            return None  # 不需要预警

        # 检查是否已有未处理的同类预警
        result = await self.db.execute(
            select(TokenBudgetAlert).where(
                TokenBudgetAlert.project_id == project_id,
                TokenBudgetAlert.alert_type == alert_type,
                TokenBudgetAlert.is_resolved == False
            )
        )
        existing_alert = result.scalar_one_or_none()

        if existing_alert:
            return None  # 已有未处理的预警

        # 创建新预警
        alert = TokenBudgetAlert(
            project_id=project_id,
            alert_type=alert_type,
            threshold_percent=usage_percent,
            current_usage=stats["total_cost"],
            budget_limit=budget.total_budget,
            message=self._generate_alert_message(alert_type, usage_percent, stats["total_cost"], budget.total_budget)
        )
        self.db.add(alert)
        await self.db.commit()
        await self.db.refresh(alert)
        return alert

    def _generate_alert_message(self, alert_type: str, percent: float, used: float, budget: float) -> str:
        """生成预警消息"""
        if alert_type == "exceeded":
            return f"预算已超标！当前使用 {percent:.1f}%，已花费 ¥{used:.2f}，超过预算 ¥{budget:.2f}"
        elif alert_type == "critical":
            return f"预算即将耗尽！当前使用 {percent:.1f}%，已花费 ¥{used:.2f}，剩余 ¥{budget - used:.2f}"
        else:
            return f"预算预警：已使用 {percent:.1f}%，花费 ¥{used:.2f}"

    async def get_alerts(self, project_id: str, include_resolved: bool = False) -> List[dict]:
        """获取项目的预警列表"""
        query = select(TokenBudgetAlert).where(TokenBudgetAlert.project_id == project_id)

        if not include_resolved:
            query = query.where(TokenBudgetAlert.is_resolved == False)

        query = query.order_by(TokenBudgetAlert.created_at.desc())

        result = await self.db.execute(query)
        alerts = result.scalars().all()

        return [
            {
                "id": alert.id,
                "alert_type": alert.alert_type,
                "threshold_percent": alert.threshold_percent,
                "current_usage": alert.current_usage,
                "budget_limit": alert.budget_limit,
                "message": alert.message,
                "is_resolved": alert.is_resolved,
                "created_at": alert.created_at.isoformat()
            }
            for alert in alerts
        ]

    async def resolve_alert(self, alert_id: int) -> bool:
        """标记预警为已处理"""
        result = await self.db.execute(
            select(TokenBudgetAlert).where(TokenBudgetAlert.id == alert_id)
        )
        alert = result.scalar_one_or_none()

        if alert:
            alert.is_resolved = True
            alert.resolved_at = datetime.utcnow()
            await self.db.commit()
            return True
        return False
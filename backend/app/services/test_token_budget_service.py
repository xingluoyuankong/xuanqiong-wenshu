import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.novel import NovelProject
from app.models.token_budget import TokenUsage
from app.models.user import User
from app.services.token_budget_service import TokenBudgetService


@pytest.fixture
def anyio_backend():
    return "asyncio"


def test_token_cost_estimate_and_module_aliases():
    assert TokenBudgetService.normalize_usage_module("draft") == "content"
    assert TokenBudgetService.normalize_usage_module("blueprint") == "outline"
    assert TokenBudgetService.normalize_usage_module("unknown") == "other"
    assert TokenBudgetService.estimate_cost_from_tokens(4200) == 0.042
    assert TokenBudgetService.estimate_cost_from_tokens(4200, cny_per_1k=0) == 0.0


@pytest.mark.anyio
async def test_record_generation_call_metrics_persists_estimated_usage(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'token-budget.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            session.add(User(id=1, username="tester", email="tester@example.com", hashed_password="hash"))
            session.add(NovelProject(id="p-budget", user_id=1, title="Budget", initial_prompt="test", status="draft"))
            await session.commit()

            summary = await TokenBudgetService(session).record_generation_call_metrics(
                project_id="p-budget",
                module="draft",
                operation_type="generation",
                description_prefix="第 1 章正文候选",
                metrics=[
                    {
                        "label": "draft_candidate_1",
                        "attempts": 2,
                        "estimated_total_tokens": 4200,
                        "effective_max_tokens": 16800,
                        "provider_error_type": "output_token_limit",
                    },
                    {"label": "empty_metric", "estimated_total_tokens": 0},
                ],
            )

            assert summary["record_count"] == 1
            assert summary["module"] == "content"
            assert summary["total_tokens"] == 4200
            assert summary["estimated_cost"] == 0.042

            usages = (await session.execute(select(TokenUsage).where(TokenUsage.project_id == "p-budget"))).scalars().all()
            assert len(usages) == 1
            usage = usages[0]
            assert usage.module == "content"
            assert usage.tokens_used == 4200
            assert usage.cost == 0.042
            assert usage.operation_type == "generation"
            assert "draft_candidate_1" in (usage.description or "")
            assert "provider_error=output_token_limit" in (usage.description or "")

            stats = await TokenBudgetService(session).get_usage_stats("p-budget")
            assert stats["total_tokens"] == 4200
            assert stats["module_stats"]["content"]["tokens"] == 4200
    finally:
        await engine.dispose()

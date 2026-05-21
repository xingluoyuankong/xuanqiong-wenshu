import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.knowledge_graph import EventEdge
from app.models.memory_layer import CausalChain
from app.models.novel import BlueprintCharacter, NovelProject
from app.models.user import User
from app.services.knowledge_graph_service import KnowledgeGraphService


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_knowledge_graph_sync_backfills_causal_chain_edges(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'knowledge-graph-causal.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            session.add(User(id=1, username="tester", email="tester@example.com", hashed_password="hash"))
            session.add(NovelProject(id="p-causal-kg", user_id=1, title="Causal KG", initial_prompt="test", status="draft"))
            session.add(BlueprintCharacter(project_id="p-causal-kg", name="Lin Qi", identity="lead", position=0))
            session.add(BlueprintCharacter(project_id="p-causal-kg", name="Shen Fang", identity="ally", position=1))
            session.add(
                CausalChain(
                    project_id="p-causal-kg",
                    cause_description="Lin Qi steals the ledger code.",
                    cause_chapter=4,
                    effect_description="Shen Fang is traced by the archive and must answer for the missing code.",
                    effect_chapter=None,
                    cause_type="action",
                    effect_type="plot_pressure",
                    involved_characters=["Lin Qi", "Shen Fang"],
                    importance=9,
                    status="pending",
                )
            )
            await session.commit()

        async with session_factory() as session:
            result = await KnowledgeGraphService(session).sync_from_story_memory("p-causal-kg")
            assert result["created_nodes"] == 2
            assert result["created_edges"] == 1

            edge = (await session.execute(select(EventEdge).where(EventEdge.project_id == "p-causal-kg"))).scalar_one()
            assert edge.event_type == "causality"
            assert edge.importance == 9
            assert edge.causality == "Lin Qi steals the ledger code."
            assert edge.extra["source"] == "causal_chain"
            assert "missing code" in edge.extra["effect"]

            graph = await KnowledgeGraphService(session).get_project_graph("p-causal-kg")
            lin_node = next(node for node in graph["nodes"] if node["name"] == "Lin Qi")
            causal_edge = graph["edges"][0]
            assert lin_node["fact_source"] == "blueprint_character"
            assert lin_node["first_chapter"] == 4
            assert lin_node["latest_chapter"] == 4
            assert lin_node["relationship_count"] == 1
            assert causal_edge["fact_source"] == "causal_chain"
            assert causal_edge["source_chapter"] == 4
            assert causal_edge["latest_chapter"] == 4
            assert causal_edge["confidence"] >= 90
    finally:
        await engine.dispose()

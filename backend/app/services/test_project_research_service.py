import json
import asyncio
import socket
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.secret_store import decrypt_secret, encrypt_secret
from app.db.base import Base
from app.models.novel import NovelProject
from app.models.research import ProjectResearchConfig, ResearchArtifact
from app.models.user import User
from app.schemas.research import ResearchConfigUpdate
from app.services.research_archive import ResearchArchive
from app.services.research_search import ResearchSearchClient
from app.services.research_service import ProjectResearchService


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_research_config_encrypts_keys_and_disables_local_model(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'research.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        async with factory() as session:
            session.add(User(id=7, username="research-owner", hashed_password="x"))
            session.add(NovelProject(id="project-1", user_id=7, title="test"))
            await session.commit()
            service = ProjectResearchService(session)
            result = await service.update_config("project-1", ResearchConfigUpdate(
                search_api_key="search-secret",
                research_llm_api_key="llm-secret",
                research_llm_model="cloud-model",
            ))
            stored = await session.get(ProjectResearchConfig, "project-1")
            assert stored.search_api_key_encrypted != "search-secret"
            assert decrypt_secret(stored.search_api_key_encrypted) == "search-secret"
            assert decrypt_secret(stored.research_llm_api_key_encrypted) == "llm-secret"
            assert result.search_api_key_configured is True
            assert result.local_model_enabled is False
            assert result.provider_priority == ["search_api_key", "research_llm_api_key", "writing_llm_api_key"]
    finally:
        await engine.dispose()


def test_research_mode_requires_consent_and_force_overrides():
    config = ProjectResearchConfig(project_id="p", mode="ask", enabled=True)
    assert ProjectResearchService.should_run(config, "chapter") == (False, "consent_required")
    assert ProjectResearchService.should_run(config, "chapter", consent=True) == (True, "consented")
    config.mode = "off"
    assert ProjectResearchService.should_run(config, "chapter") == (False, "disabled")
    assert ProjectResearchService.should_run(config, "chapter", force=True) == (True, "forced")


def test_research_archive_uses_project_scope_chapter_and_category_folders(tmp_path, monkeypatch):
    monkeypatch.setattr(ResearchArchive, "project_root", classmethod(lambda cls, _project_id: tmp_path / "storage" / "novel_projects" / "project-1" / "research"))
    manifest = ResearchArchive.write_run(
        project_id="project-1",
        run_id="run-1",
        scope="chapter",
        chapter_number=12,
        plan=[{"category": "history", "query": "q"}],
        search_batches=[],
        sources=[],
        synthesis={"summary": "s", "categories": {"history": [{"insight": "i", "usage": "u", "source_urls": ["https://example.test"]}]}},
    )
    research_root = tmp_path / "storage" / "novel_projects" / "project-1" / "research"
    run_dir = research_root / manifest["run_directory"]
    assert manifest["root"] == "research"
    assert Path(manifest["run_directory"]).parts == ("chapters", "chapter_0012", "run-1")
    assert (run_dir / "categories" / "history.md").exists()
    assert (run_dir / "query_plan.json").exists()


@pytest.mark.anyio
async def test_parallel_search_failure_is_per_query_not_global():
    client = ResearchSearchClient()
    calls = []

    async def fake_one(_config, item):
        calls.append(item["query"])
        if item["query"] == "bad":
            raise RuntimeError("provider down")
        return {**item, "status": "successful", "results": [{"url": "https://example.test", "title": "ok"}]}

    client.search_one = fake_one
    config = ProjectResearchConfig(project_id="p", max_parallel_queries=3)
    result = await client.search_all(config, [{"query": "ok", "category": "history"}, {"query": "bad", "category": "culture"}])
    assert calls == ["ok", "bad"]
    assert result[0]["status"] == "successful"
    assert result[1]["status"] == "failed"
    assert "provider down" in result[1]["error"]


def test_chapter_query_plan_is_bounded_and_multidisciplinary():
    plan = ProjectResearchService.build_query_plan({"title": "长安夜行", "blueprint": {"genre": "历史悬疑"}}, "chapter")
    assert len(plan) == 4
    assert {item["category"] for item in plan} == {"history", "culture", "philosophy", "naming"}
    assert all("长安夜行" in item["query"] for item in plan)


def test_enhanced_query_plan_prefers_runtime_blueprint_and_chapter_outline():
    plan = ProjectResearchService.build_query_plan(
        {
            "title": "旧项目名",
            "blueprint": {"genre": "旧题材"},
            "blueprint_with_chapter_outline": {
                "title": "长安夜行",
                "genre": "历史悬疑",
                "one_sentence_summary": "女仵作追查宫城密案",
                "chapter_outline": [{
                    "title": "朱雀门尸案",
                    "summary": "死者留下伪造的官印",
                    "turning_point": "官印来自尚书省内库",
                }],
            },
        },
        "enhanced",
    )
    queries = "\n".join(item["query"] for item in plan)
    assert "长安夜行" in queries
    assert "朱雀门尸案" in queries
    assert "尚书省内库" in queries


def test_research_config_rejects_private_and_non_http_base_urls():
    for url in ("file:///tmp/search", "http://localhost:8080", "http://127.0.0.1", "http://10.0.0.4"):
        with pytest.raises(ValueError):
            ResearchConfigUpdate(search_base_url=url)
    assert ResearchConfigUpdate(search_base_url="https://api.example.com/search").search_base_url == "https://api.example.com/search"


@pytest.mark.anyio
async def test_search_runtime_rejects_dns_resolution_to_private_network(monkeypatch):
    client = ResearchSearchClient()
    loop = asyncio.get_running_loop()

    async def fake_getaddrinfo(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.20", 443))]

    monkeypatch.setattr(loop, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError, match="non-public"):
        await client._validate_outbound_url("https://search.example.test/api")


def test_source_trust_ranking_prefers_official_and_cross_checked_sources():
    sources = ProjectResearchService._flatten_sources([{"results": [
        {"url": "https://example.com/post", "category": "history", "title": "blog"},
        {"url": "https://archives.gov.cn/doc", "category": "history", "title": "archive"},
        {"url": "https://museum.org/item", "category": "history", "title": "museum"},
    ]}])
    assert sources[0]["trust_tier"] == "official_or_education"
    assert sources[0]["credibility_score"] > sources[-1]["credibility_score"]
    assert all(source["cross_source_count"] == 3 for source in sources)
    assert sources[-1]["verification_level"] == "source_page_required"


def test_category_preferences_reorder_query_plan_without_expanding_scope():
    plan = ProjectResearchService.build_query_plan(
        {"title": "测试"}, "global", ["naming", "history"],
    )
    assert len(plan) == 5
    assert [item["category"] for item in plan[:2]] == ["naming", "history"]


def test_secret_round_trip_and_plaintext_backward_compatibility():
    encrypted = encrypt_secret("sk-example")
    assert encrypted.startswith("enc:v1:")
    assert decrypt_secret(encrypted) == "sk-example"
    assert decrypt_secret("legacy-plain") == "legacy-plain"

@pytest.mark.anyio
async def test_preferred_domains_sort_without_filtering_and_blocked_domains_filter(monkeypatch):
    client = ResearchSearchClient()

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [
                {"title": "normal high score", "url": "https://example.com/a", "score": 0.99},
                {"title": "blocked", "url": "https://blocked.example.net/b", "score": 1.0},
                {"title": "preferred", "url": "https://archive.gov.cn/c", "score": 0.2},
            ]}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return _Response()

    async def allow_endpoint(url):
        return url

    monkeypatch.setattr(client, "_validate_outbound_url", allow_endpoint)
    monkeypatch.setattr("app.services.research_search.httpx.AsyncClient", lambda **_kwargs: _Client())
    config = ProjectResearchConfig(
        project_id="p", search_provider="tavily", search_api_key_encrypted=encrypt_secret("key"),
        search_base_url="https://search.example.com", preferred_domains=["gov.cn"],
        blocked_domains=["blocked.example.net"], max_results_per_query=5,
    )

    batch = await client.search_one(config, {"query": "q", "category": "history"})

    assert [item["title"] for item in batch["results"]] == ["preferred", "normal high score"]
    assert batch["results"][0]["preferred_domain"] is True
    assert batch["results"][1]["preferred_domain"] is False


def test_flatten_sources_gives_preferred_domain_only_a_small_bonus():
    sources = ProjectResearchService._flatten_sources([{"results": [
        {"url": "https://preferred.example.com/post", "category": "history", "preferred_domain": True},
        {"url": "https://archives.gov.cn/doc", "category": "history", "preferred_domain": False},
    ]}])
    preferred = next(item for item in sources if item["preferred_domain"])
    official = next(item for item in sources if item["trust_tier"] == "official_or_education")
    assert preferred["credibility_score"] == 58
    assert official["credibility_score"] > preferred["credibility_score"]

@pytest.mark.anyio
async def test_background_reuse_keeps_current_run_id_and_copies_existing_artifact(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'reuse.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        async with factory() as session:
            session.add(User(id=7, username="owner-reuse", hashed_password="x"))
            session.add(NovelProject(id="project-reuse", user_id=7, title="test"))
            await session.commit()
            service = ProjectResearchService(session)
            context = await service._build_project_context("project-reuse", None)
            _fp_ctx = {k: v for k, v in context.items() if k != "previous_research"}
            fingerprint = __import__("hashlib").sha256(service._context_text(_fp_ctx).encode("utf-8")).hexdigest()[:16]
            existing = ResearchArtifact(
                run_id="old-run", project_id="project-reuse", user_id=7, scope="global",
                chapter_number=None, status="successful", trigger="automatic",
                summary="old summary", sources=[{"url": "https://example.com"}],
                provider_metadata={"context_fingerprint": fingerprint},
            )
            session.add(existing)
            await session.commit()
            await service.create_pending_artifact(
                run_id="new-run", project_id="project-reuse", user_id=7, scope="global",
                chapter_number=None, trigger="manual_ui",
            )

            result = await service.run_research(
                project_id="project-reuse", user_id=7, scope="global", run_id="new-run",
            )

            assert result.run_id == "new-run"
            assert result.status == "successful"
            assert result.summary == "old summary"
            assert result.provider_metadata["reused_from_run_id"] == "old-run"
            assert await service.get_artifact("project-reuse", "new-run") is not None
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_fresh_heartbeat_survives_status_recovery_and_stale_heartbeat_interrupts(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'heartbeat.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        async with factory() as session:
            session.add(User(id=7, username="owner-heartbeat", hashed_password="x"))
            session.add(NovelProject(id="project-heartbeat", user_id=7, title="test"))
            await session.commit()
            service = ProjectResearchService(session)
            fresh = await service.create_pending_artifact(
                run_id="fresh-run", project_id="project-heartbeat", user_id=7,
                scope="global", chapter_number=None, trigger="manual_ui",
            )
            recovered = await service.mark_artifact_interrupted("project-heartbeat", fresh.run_id)
            assert recovered and recovered.status == "queued"

            artifact = (await session.execute(
                __import__("sqlalchemy").select(ResearchArtifact).where(ResearchArtifact.run_id == "fresh-run")
            )).scalar_one()
            artifact.provider_metadata = {
                **(artifact.provider_metadata or {}),
                "heartbeat_at": (service._now() - service.ACTIVE_JOB_STALE_AFTER - timedelta(seconds=1)).isoformat(),
            }
            await session.commit()

            interrupted = await service.mark_artifact_interrupted("project-heartbeat", fresh.run_id)
            assert interrupted and interrupted.status == "failed"
            assert interrupted.error and interrupted.error["code"] == "research_job_interrupted"
    finally:

        await engine.dispose()
@pytest.mark.anyio
async def test_prompt_context_keeps_latest_artifact_per_scope(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'prompt-context.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        async with factory() as session:
            session.add(User(id=7, username="owner-context", hashed_password="x"))
            session.add(NovelProject(id="project-context", user_id=7, title="test"))
            await session.commit()

            artifacts = [
                ResearchArtifact(
                    run_id="global-old", project_id="project-context", user_id=7,
                    scope="global", chapter_number=None, status="successful", trigger="automatic",
                    summary="过期全局资料",
                ),
                ResearchArtifact(
                    run_id="global-latest", project_id="project-context", user_id=7,
                    scope="global", chapter_number=None, status="successful", trigger="automatic",
                    summary="最新全局资料",
                ),
                ResearchArtifact(
                    run_id="enhanced-latest", project_id="project-context", user_id=7,
                    scope="enhanced", chapter_number=None, status="degraded", trigger="automatic",
                    summary="最新增强资料",
                ),
            ]
            artifacts.extend(
                ResearchArtifact(
                    run_id=f"chapter-{number}", project_id="project-context", user_id=7,
                    scope="chapter", chapter_number=number, status="successful", trigger="automatic",
                    summary=f"第{number}章资料",
                )
                for number in range(1, 10)
            )
            session.add_all(artifacts)
            await session.commit()

            text, metadata = await ProjectResearchService(session).build_prompt_context(
                "project-context", 9, max_chars=10000,
            )

            assert "最新全局资料" in text
            assert "最新增强资料" in text
            assert "第9章资料" in text
            assert "过期全局资料" not in text
            assert "第8章资料" not in text
            assert metadata["artifact_count"] == 3
            assert metadata["artifact_scopes"] == ["global", "enhanced", "chapter"]
            assert metadata["artifact_run_ids"] == ["global-latest", "enhanced-latest", "chapter-9"]
    finally:
        await engine.dispose()
@pytest.mark.anyio
async def test_prompt_context_keeps_archived_context_when_new_research_is_skipped(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'pipeline-archive.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        async with factory() as session:
            session.add(User(id=7, username="owner-pipeline-archive", hashed_password="x"))
            session.add(NovelProject(id="project-pipeline-archive", user_id=7, title="test"))
            session.add(ResearchArtifact(
                run_id="archived-global", project_id="project-pipeline-archive", user_id=7,
                scope="global", chapter_number=None, status="successful", trigger="automatic",
                summary="可复用的全局文化资料",
            ))
            await session.commit()
            text, metadata = await ProjectResearchService(session).build_prompt_context(
                "project-pipeline-archive", 12,
            )
            assert "可复用的全局文化资料" in text
            assert metadata["artifact_count"] == 1
            assert metadata["artifact_scopes"] == ["global"]
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_prompt_context_degrades_without_interrupting_generation():
    class BrokenSession:
        async def execute(self, *_args, **_kwargs):
            raise RuntimeError("archive database unavailable")

    text, metadata = await ProjectResearchService(BrokenSession()).build_prompt_context("project-1", 3)
    assert text == ""
    assert metadata["artifact_count"] == 0
    assert "archive database unavailable" in metadata["archive_error"]


@pytest.mark.anyio
async def test_prompt_context_filters_requested_research_scope(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'blueprint-archive.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with session_factory() as session:
            session.add(User(id=1, username="archive", email="archive@example.com", hashed_password="hash"))
            session.add(NovelProject(id="p-blueprint-archive", user_id=1, title="Archive", initial_prompt="test", status="draft"))
            session.add_all([
                ResearchArtifact(run_id="global-run", project_id="p-blueprint-archive", user_id=1, scope="global", status="successful", trigger="test", summary="全局历史文化资料"),
                ResearchArtifact(run_id="enhanced-run", project_id="p-blueprint-archive", user_id=1, scope="enhanced", status="successful", trigger="test", summary="强化章节结构资料"),
            ])
            await session.commit()
            service = ProjectResearchService(session)
            global_text, global_meta = await service.build_prompt_context("p-blueprint-archive", 1, scope="global")
            enhanced_text, enhanced_meta = await service.build_prompt_context("p-blueprint-archive", 1, scope="enhanced")
            assert "全局历史文化资料" in global_text
            assert "强化章节结构资料" not in global_text
            assert global_meta["artifact_run_ids"] == ["global-run"]
            assert "强化章节结构资料" in enhanced_text
            assert "全局历史文化资料" not in enhanced_text
            assert enhanced_meta["artifact_run_ids"] == ["enhanced-run"]
    finally:
        await engine.dispose()

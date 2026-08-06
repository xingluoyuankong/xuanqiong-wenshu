from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.writer_persona import WriterPersona
from app.services.writer_persona_service import WriterPersonaService


@pytest.mark.anyio
async def test_generation_persona_uses_in_memory_default_without_writes():
    session = MagicMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    service = WriterPersonaService(session, MagicMock(), MagicMock())
    default_persona = WriterPersona.create_default_qidian_writer("project-1")
    service.get_active_persona = AsyncMock(return_value=default_persona)

    persona = await service.get_active_persona("project-1")

    assert isinstance(persona, WriterPersona)
    assert persona.project_id == "project-1"
    assert persona.name == "起点爽文写手"
    session.add.assert_not_called()
    session.commit.assert_not_awaited()
    session.refresh.assert_not_awaited()


@pytest.mark.anyio
async def test_generation_persona_returns_active_persona_without_writes():
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    active = WriterPersona.create_default_qidian_writer("project-1")
    active.name = "项目专属作者"
    service = WriterPersonaService(session, MagicMock(), MagicMock())
    service.get_active_persona = AsyncMock(return_value=active)

    persona = await service.get_active_persona("project-1")

    assert persona is active
    session.add.assert_not_called()
    session.commit.assert_not_awaited()
    session.refresh.assert_not_awaited()


@pytest.mark.anyio
async def test_ensure_default_persona_keeps_explicit_persistence_path():
    session = MagicMock()
    service = WriterPersonaService(session, MagicMock(), MagicMock())
    service.get_active_persona = AsyncMock(return_value=None)
    persisted = WriterPersona.create_default_qidian_writer("project-1")
    service.create_default_qidian_persona = AsyncMock(return_value=persisted)

    persona = await service.ensure_default_persona("project-1")

    assert persona is persisted
    service.create_default_qidian_persona.assert_awaited_once_with("project-1")

"""
novel_service.py core tests: create_project, get_outline, get_or_create_chapter, delete_chapters
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.novel_service import NovelService
from app.models.novel import NovelProject, Chapter

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_session():
    session = AsyncMock(spec=AsyncSession)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def novel_service(mock_session):
    return NovelService(mock_session)


async def test_create_project_returns_correct_title(novel_service, mock_session):
    dummy_project = MagicMock(spec=NovelProject)
    dummy_project.id = "p-1"
    dummy_project.title = "Test Novel"
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = dummy_project
    mock_session.execute.return_value = mock_result
    project = await novel_service.create_project(1, "Test Novel", "prompt")
    assert len(project.id) == 36  # UUID
    assert project.title == "Test Novel"


async def test_ensure_owner_raises_on_missing(novel_service, mock_session):
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        await novel_service.ensure_project_owner("missing", 1)


async def test_get_outline_none_when_missing(novel_service, mock_session):
    mock_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.first.return_value = None
    mock_result = MagicMock()
    mock_result.scalars.return_value = scalars_mock
    mock_session.execute.return_value = mock_result
    outline = await novel_service.get_outline("p-1", 1)
    assert outline is None


async def test_get_or_create_chapter_creates_new(novel_service, mock_session):
    mock_result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.first.return_value = None
    mock_result = MagicMock()
    mock_result.scalars.return_value = scalars_mock
    mock_session.execute.return_value = mock_result
    def refresh_cb(chapter, attr=None):
        chapter.id = 1
    mock_session.refresh.side_effect = refresh_cb
    chapter = await novel_service.get_or_create_chapter("p-1", 3)
    assert chapter is not None
    assert mock_session.add.called


async def test_get_or_create_chapter_returns_existing(novel_service, mock_session):
    existing = MagicMock(spec=Chapter)
    existing.id = 5
    existing.chapter_number = 5
    existing.status = "successful"
    scalars_mock = MagicMock()
    scalars_mock.first.return_value = existing
    mock_result = MagicMock()
    mock_result.scalars.return_value = scalars_mock
    mock_session.execute.return_value = mock_result
    chapter = await novel_service.get_or_create_chapter("p-1", 5)
    assert chapter is existing


async def test_delete_chapters_calls_sql(novel_service, mock_session):
    await novel_service.delete_chapters("p-1", [1, 2, 3])
    assert mock_session.execute.call_count >= 1
    assert mock_session.commit.called

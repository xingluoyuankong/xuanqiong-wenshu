import os
import sys
import types
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.base import Base


TEST_STORAGE = Path(__file__).resolve().parent / "storage" / "pytest.db"
TEST_STORAGE.parent.mkdir(parents=True, exist_ok=True)

os.environ["XUANQIONG_TEST_LIGHT_IMPORTS"] = "1"
os.environ["DB_PROVIDER"] = "sqlite"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_STORAGE.as_posix()}"
os.environ.setdefault("SECRET_KEY", "pytest-secret-key-for-local-quality-regressions-123456")
os.environ.setdefault("ALLOW_USER_REGISTRATION", "true")


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def task_session():
    """Provide an isolated async database session for task-runtime tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


if "langchain_text_splitters" not in sys.modules:
    splitters_module = types.ModuleType("langchain_text_splitters")

    class RecursiveCharacterTextSplitter:
        def __init__(
            self,
            chunk_size=1000,
            chunk_overlap=100,
            separators=None,
            **kwargs,
        ):
            self.chunk_size = max(1, int(chunk_size or 1000))
            self.chunk_overlap = max(0, min(int(chunk_overlap or 0), self.chunk_size - 1))

        def split_text(self, text):
            source = text or ""
            if not source:
                return []
            chunks = []
            step = max(1, self.chunk_size - self.chunk_overlap)
            for start in range(0, len(source), step):
                chunks.append(source[start : start + self.chunk_size])
                if start + self.chunk_size >= len(source):
                    break
            return chunks

    splitters_module.RecursiveCharacterTextSplitter = RecursiveCharacterTextSplitter
    sys.modules["langchain_text_splitters"] = splitters_module

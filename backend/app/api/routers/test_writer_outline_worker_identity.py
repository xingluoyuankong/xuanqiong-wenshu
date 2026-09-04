"""Regression contract for rehydrating outline worker principals."""
from __future__ import annotations

import pytest

from app.api.routers import writer
from app.models.user import User


@pytest.mark.asyncio
async def test_outline_worker_rehydrates_admin_identity(task_session):
    admin = User(
        id=95701,
        username="outline-worker-admin",
        email="outline-admin@example.com",
        hashed_password="hashed",
        is_admin=True,
        is_active=True,
    )
    task_session.add(admin)
    await task_session.commit()

    principal = await writer._load_worker_user(
        task_session,
        admin.id,
        purpose="章节大纲生成",
    )

    assert principal.id == admin.id
    assert principal.username == admin.username
    assert principal.email == admin.email
    assert principal.hashed_password == admin.hashed_password
    assert principal.is_admin is True
    assert principal.is_active is True


@pytest.mark.asyncio
async def test_outline_worker_missing_user_is_rejected(task_session):
    with pytest.raises(Exception) as missing:
        await writer._load_worker_user(
            task_session,
            95702,
            purpose="章节大纲重写",
        )

    assert getattr(missing.value, "status_code", None) == 404

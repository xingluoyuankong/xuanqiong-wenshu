from datetime import timedelta

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core import dependencies
from app.core.security import create_access_token, hash_password
from app.models import User


@pytest.mark.asyncio
async def test_get_current_user_accepts_valid_jwt_and_loads_subject(task_session):
    user = User(username="jwt-user", email="jwt-user@example.com", hashed_password=hash_password("secret123"), is_active=True)
    task_session.add(user)
    await task_session.commit()
    await task_session.refresh(user)
    token = create_access_token(str(user.id))

    current = await dependencies.get_current_user(
        task_session,
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
    )

    assert current.id == user.id
    assert current.username == "jwt-user"


@pytest.mark.asyncio
async def test_get_current_user_rejects_invalid_or_expired_jwt(task_session):
    with pytest.raises(HTTPException) as invalid:
        await dependencies.get_current_user(
            task_session,
            HTTPAuthorizationCredentials(scheme="Bearer", credentials="not-a-token"),
        )
    assert invalid.value.status_code == 401

    expired = create_access_token("1", expires_delta=timedelta(seconds=-1))
    with pytest.raises(HTTPException) as expired_error:
        await dependencies.get_current_user(
            task_session,
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=expired),
        )
    assert expired_error.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_rejects_inactive_subject(task_session):
    user = User(username="inactive-user", email="inactive@example.com", hashed_password=hash_password("secret123"), is_active=False)
    task_session.add(user)
    await task_session.commit()
    await task_session.refresh(user)

    with pytest.raises(HTTPException) as error:
        await dependencies.get_current_user(
            task_session,
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=create_access_token(str(user.id))),
        )
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_requires_token_in_production(task_session, monkeypatch):
    monkeypatch.setattr(dependencies.settings, "environment", "production")
    with pytest.raises(HTTPException) as error:
        await dependencies.get_current_user(task_session, None)
    assert error.value.status_code == 401
    assert error.value.detail["code"] == "AUTH_REQUIRED"


@pytest.mark.asyncio
async def test_get_current_user_keeps_development_single_user_fallback(task_session, monkeypatch):
    monkeypatch.setattr(dependencies.settings, "environment", "development")
    user = User(username="default-admin", email="default@example.com", hashed_password=hash_password("secret123"), is_admin=True, is_active=True)
    task_session.add(user)
    await task_session.commit()
    monkeypatch.setattr(dependencies.settings, "admin_default_username", "default-admin")

    current = await dependencies.get_current_user(task_session, None)
    assert current.id == user.id
    assert current.is_admin is True

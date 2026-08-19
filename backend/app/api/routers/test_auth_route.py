import pytest
from fastapi import HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from app.api.routers.auth import login
from app.core.security import hash_password
from app.models import User

@pytest.mark.asyncio
async def test_login_rejects_inactive_user(task_session):
    task_session.add(User(username="inactive-login", email="inactive-login@example.com", hashed_password=hash_password("secret123"), is_active=False))
    await task_session.commit()
    form = OAuth2PasswordRequestForm(username="inactive-login", password="secret123", scope="", client_id=None, client_secret=None)
    with pytest.raises(HTTPException) as error:
        await login(form, task_session)
    assert error.value.status_code == 401

@pytest.mark.asyncio
async def test_login_returns_token_for_active_user(task_session):
    task_session.add(User(username="active-login", email="active-login@example.com", hashed_password=hash_password("secret123"), is_active=True))
    await task_session.commit()
    form = OAuth2PasswordRequestForm(username="active-login", password="secret123", scope="", client_id=None, client_secret=None)
    response = await login(form, task_session)
    assert response.token_type == "bearer"
    assert response.access_token

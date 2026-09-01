from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI
from jose import jwt

from app.api.routers.agent import router as agent_router
from app.core import dependencies
from app.core.security import create_access_token, hash_password
from app.db.session import get_session
from app.models import User


@pytest.mark.asyncio
async def test_agent_http_authentication_failure_matrix_is_structured_and_consistent(task_session, monkeypatch):
    """Every real Agent route request must cross the same production JWT gate."""
    monkeypatch.setattr(dependencies.settings, "environment", "production")
    active = User(
        id=1951,
        username="agent-auth-active",
        email="agent-auth-active@example.com",
        hashed_password=hash_password("auth-matrix-password"),
        is_active=True,
    )
    inactive = User(
        id=1952,
        username="agent-auth-inactive",
        email="agent-auth-inactive@example.com",
        hashed_password=hash_password("auth-matrix-password"),
        is_active=False,
    )
    task_session.add_all([active, inactive])
    await task_session.commit()

    local_app = FastAPI()
    local_app.include_router(agent_router)

    async def override_session():
        yield task_session

    local_app.dependency_overrides[get_session] = override_session
    transport = httpx.ASGITransport(app=local_app, raise_app_exceptions=True)

    valid = create_access_token(str(active.id))
    expired = create_access_token(str(active.id), expires_delta=timedelta(seconds=-1))
    wrong_signature = jwt.encode(
        {"sub": str(active.id)},
        "wrong-signing-key-that-is-long-enough-for-the-test",
        algorithm=dependencies.settings.jwt_algorithm,
    )
    missing_subject = jwt.encode(
        {"exp": 4_102_444_800},
        dependencies.settings.secret_key,
        algorithm=dependencies.settings.jwt_algorithm,
    )
    nonexistent_subject = create_access_token("999999")
    inactive_subject = create_access_token(str(inactive.id))

    protected_paths = (
        "/api/agent/tools",
        "/api/agent/sessions/session-1/runs/run-1/events",
        "/api/agent/runs/run-1/activity",
        "/api/agent/sessions/session-1/runs/run-1/stream",
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://agent-auth") as client:
        cases = [
            ("no credentials", {}, "AUTH_REQUIRED"),
            ("wrong scheme", {"Authorization": "Basic Zm9vOmJhcg=="}, "INVALID_AUTH_SCHEME"),
            ("malformed token", {"Authorization": "Bearer not-a-jwt"}, "INVALID_ACCESS_TOKEN"),
            ("expired token", {"Authorization": f"Bearer {expired}"}, "INVALID_ACCESS_TOKEN"),
            ("wrong signature", {"Authorization": f"Bearer {wrong_signature}"}, "INVALID_ACCESS_TOKEN"),
            ("missing subject", {"Authorization": f"Bearer {missing_subject}"}, "INVALID_ACCESS_TOKEN"),
            ("unknown subject", {"Authorization": f"Bearer {nonexistent_subject}"}, "USER_NOT_ACTIVE"),
            ("inactive subject", {"Authorization": f"Bearer {inactive_subject}"}, "USER_NOT_ACTIVE"),
        ]
        for label, headers, expected_code in cases:
            for path in protected_paths:
                response = await client.get(path, headers=headers)
                assert response.status_code == 401, f"{label}: {path}"
                assert response.json()["detail"]["code"] == expected_code, f"{label}: {path}"
                assert response.headers.get("www-authenticate") == "Bearer", f"{label}: {path}"

        valid_response = await client.get("/api/agent/tools", headers={"Authorization": f"Bearer {valid}"})

    assert valid_response.status_code == 200
    assert valid_response.json()["count"] >= 1

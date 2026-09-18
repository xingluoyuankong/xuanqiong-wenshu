#!/usr/bin/env python3
"""Live HTTP contract smoke for the US-010 budget gate.

The caller must provide an authenticated local environment through
ADMIN_DEFAULT_USERNAME/ADMIN_DEFAULT_PASSWORD and may override XQ_BASE_URL.
The script creates one tagged project, exercises the budget-not-allocated gate,
and deletes the project in a finally block.
"""
from __future__ import annotations

import asyncio
import os
import secrets
import sys
from typing import Any

import httpx

BASE_URL = os.getenv("XQ_BASE_URL", "http://127.0.0.1:8013").rstrip("/")


async def main() -> int:
    result: dict[str, Any] = {}
    username = os.getenv("ADMIN_DEFAULT_USERNAME", "admin")
    password = os.getenv("ADMIN_DEFAULT_PASSWORD", "")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        login = await client.post("/api/auth/login", data={"username": username, "password": password})
        result["login"] = login.status_code
        if login.status_code != 200:
            print(result, login.text[:300], file=sys.stderr)
            return 2
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        project_id: str | None = None
        try:
            tag = secrets.token_hex(4)
            created = await client.post(
                "/api/novels",
                json={
                    "title": f"US010 budget smoke {tag}",
                    "genre": "玄幻",
                    "description": "US-010 live budget gate contract smoke",
                    "initial_prompt": "预算门验收项目",
                },
                headers=headers,
            )
            result["create"] = created.status_code
            if created.status_code not in (200, 201):
                print(result, created.text[:300], file=sys.stderr)
                return 3
            project_id = str(created.json()["id"])
            budget = await client.put(
                f"/api/projects/{project_id}/token-budget",
                json={"total_budget": 0, "chapter_budget": 0},
                headers=headers,
            )
            result["budget_update"] = budget.status_code
            blueprint = await client.post(
                f"/api/novels/{project_id}/blueprint/save",
                json={
                    "title": "US010 budget smoke",
                    "genre": "玄幻",
                    "one_sentence_summary": "预算门 smoke",
                    "full_synopsis": "预算门 smoke",
                    "chapter_outline": [{
                        "chapter_number": 1,
                        "title": "预算门",
                        "summary": "冲突发生，角色做出选择并留下悬念。",
                    }],
                },
                headers=headers,
            )
            result["blueprint"] = blueprint.status_code
            generated = await client.post(
                f"/api/writer/novels/{project_id}/chapters/generate",
                json={"chapter_number": 1, "target_word_count": 300, "min_word_count": 100},
                headers=headers,
            )
            result["generate"] = generated.status_code
            body = generated.json() if generated.headers.get("content-type", "").startswith("application/json") else {}
            runtime = body.get("generation_runtime") or {}
            result.update({
                "status": runtime.get("status"),
                "budget_gate_reason": runtime.get("budget_gate_reason"),
                "allowed_actions": runtime.get("allowed_actions"),
                "queued": runtime.get("queued"),
            })
        finally:
            if project_id:
                deleted = await client.request("DELETE", "/api/novels", json=[project_id], headers=headers)
                result["delete"] = deleted.status_code
    print(result)
    expected = {
        "login": 200, "create": 201, "budget_update": 200, "blueprint": 200,
        "generate": 200, "status": "budget_not_allocated",
        "budget_gate_reason": "budget_not_allocated",
        "allowed_actions": ["pause"], "queued": False, "delete": 200,
    }
    return 0 if all(result.get(key) == value for key, value in expected.items()) else 10


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

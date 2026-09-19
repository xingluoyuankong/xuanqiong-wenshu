#!/usr/bin/env python3
"""Read-only embedding capability probe with redacted provider status."""
from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from app.db.session import AsyncSessionLocal
from app.services.llm_service import LLMService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", default="玄穹文枢 embedding capability probe")
    parser.add_argument("--user-id", type=int, default=1)
    return parser.parse_args()


async def run_probe(text: str, user_id: int) -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        service = LLMService(session)
        vector = await service.get_embedding(text, user_id=user_id)
        status = service.get_embedding_status()
        return {
            "vector_nonempty": bool(vector),
            "vector_dimension": len(vector),
            "status": status,
        }


def main() -> int:
    args = parse_args()
    result = asyncio.run(run_probe(args.text, args.user_id))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("vector_nonempty") else 10


if __name__ == "__main__":
    raise SystemExit(main())
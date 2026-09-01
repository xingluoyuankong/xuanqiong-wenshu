"""Run the durable Agent worker as a separate process.

Usage (from backend):
    python scripts/agent_worker.py --worker-id agent-worker-1

Database migrations are intentionally not run here. Run Alembic separately so
worker startup cannot mutate schema unexpectedly.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import socket
import sys
from pathlib import Path

# Direct execution (python scripts/agent_worker.py) does not put backend/
# on sys.path, unlike python -m scripts.agent_worker.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent.worker import AgentWorker, handle_agent_execution_job, handle_visible_response_job
from app.core.config import settings
from app.db.session import AsyncSessionLocal, engine


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="玄穹文枢 durable Agent worker")
    parser.add_argument("--worker-id", default=settings.agent_worker_id or f"agent-worker-{socket.gethostname()}")
    parser.add_argument("--lease-seconds", type=int, default=settings.agent_worker_lease_seconds)
    parser.add_argument("--poll-interval", type=float, default=settings.agent_worker_poll_interval)
    parser.add_argument("--once", action="store_true", help="claim at most one job and exit; diagnostic mode")
    return parser.parse_args()


async def _run() -> None:
    args = _parse_args()
    logging.basicConfig(level=settings.console_logging_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log = logging.getLogger("agent_worker")
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            pass
    worker = AgentWorker(
        AsyncSessionLocal,
        worker_id=args.worker_id,
        handlers={"agent_execution": handle_agent_execution_job, "visible_response": handle_visible_response_job},
        lease_seconds=args.lease_seconds,
        poll_interval=args.poll_interval,
    )
    log.info("Agent worker started: worker_id=%s", worker.worker_id)
    try:
        if args.once:
            worked = await worker.poll_once()
            log.info("Agent worker once completed: worked=%s", worked)
        else:
            await worker.run_forever(stop_event)
    finally:
        # Match the command-worker lifecycle: Windows/aiosqlite may retain a
        # background connection thread after --once unless the global engine is
        # explicitly disposed before process exit.
        await engine.dispose()
        log.info("Agent worker stopped: worker_id=%s", worker.worker_id)


if __name__ == "__main__":
    asyncio.run(_run())

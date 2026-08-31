"""Run the durable Agent Run Command Worker as a separate process."""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import socket
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agent.command_worker import CommandWorker
from app.core.config import settings
from app.db.session import AsyncSessionLocal


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="玄穹文枢 Agent Run Command worker")
    default_worker_id = settings.agent_worker_id or f"command-worker-{socket.gethostname()}"
    parser.add_argument("--worker-id", default=default_worker_id)
    parser.add_argument("--lease-seconds", type=int, default=settings.agent_worker_lease_seconds)
    parser.add_argument("--poll-interval", type=float, default=settings.agent_worker_poll_interval)
    parser.add_argument("--once", action="store_true", help="claim at most one command and exit")
    return parser.parse_args()


async def _run() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=settings.console_logging_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    log = logging.getLogger("agent_command_worker")
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            pass
    worker = CommandWorker(
        AsyncSessionLocal,
        worker_id=args.worker_id,
        lease_seconds=args.lease_seconds,
        poll_interval=args.poll_interval,
    )
    log.info("Agent command worker started: worker_id=%s", worker.worker_id)
    if args.once:
        worked = await worker.poll_once()
        log.info("Agent command worker once completed: worked=%s", worked)
    else:
        await worker.run_forever(stop_event)
    log.info("Agent command worker stopped: worker_id=%s", worker.worker_id)


if __name__ == "__main__":
    asyncio.run(_run())

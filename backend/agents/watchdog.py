"""Background self-healing loop (replaces the APScheduler job; same behaviour, no overlap)."""
from __future__ import annotations

import asyncio
import logging

from agents.factory import build_monitoring_agent
from agents.pipeline import get_pipeline
from database import get_sessionmaker
from settings import get_settings

log = logging.getLogger(__name__)


async def run_scan():
    settings = get_settings()
    async with get_sessionmaker()() as session:
        return await build_monitoring_agent(session, settings).scan(get_pipeline().schedule)


async def watchdog_loop() -> None:
    interval = get_settings().watchdog_interval_seconds
    log.info("Self-healing watchdog started", extra={"interval_seconds": interval})
    while True:
        try:
            result = await run_scan()
            if result.healed or result.failed:
                log.warning("Watchdog acted", extra={"healed": result.healed, "failed": result.failed,
                                                     "actions": [a.model_dump() for a in result.actions]})
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Watchdog scan failed")
        await asyncio.sleep(interval)

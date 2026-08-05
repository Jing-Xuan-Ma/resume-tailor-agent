"""Background ingest scheduler for the shared job index (JR-1)."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.config import settings
from app.modules.job_discovery import job_index

logger = structlog.get_logger()

_task: asyncio.Task | None = None
_stop: asyncio.Event | None = None


async def run_ingest_once(**kwargs: Any) -> dict[str, Any]:
    result = await job_index.ingest_queries(**kwargs)
    logger.info(
        "job_index_ingest_done",
        fetched=result.get("fetched"),
        created=result.get("created"),
        updated=result.get("updated"),
        active_total=result.get("active_total"),
        errors=len(result.get("errors") or []),
    )
    return result


async def _loop(interval_minutes: int) -> None:
    assert _stop is not None
    # Stagger first run slightly so startup isn't blocked.
    try:
        await asyncio.wait_for(_stop.wait(), timeout=5)
        return
    except asyncio.TimeoutError:
        pass

    if settings.JOB_INDEX_INGEST_ON_STARTUP:
        try:
            await run_ingest_once()
        except Exception as exc:  # noqa: BLE001
            logger.warning("job_index_startup_ingest_failed", error=str(exc))

    while not _stop.is_set():
        try:
            await asyncio.wait_for(_stop.wait(), timeout=max(60, interval_minutes * 60))
            break
        except asyncio.TimeoutError:
            try:
                await run_ingest_once()
            except Exception as exc:  # noqa: BLE001
                logger.warning("job_index_scheduled_ingest_failed", error=str(exc))


def start_scheduler() -> None:
    global _task, _stop
    if not settings.JOB_INDEX_ENABLED:
        logger.info("job_index_scheduler_disabled")
        return
    if _task and not _task.done():
        return
    interval = max(1, int(settings.JOB_INDEX_INGEST_INTERVAL_MINUTES))
    _stop = asyncio.Event()
    _task = asyncio.create_task(_loop(interval), name="job-index-ingest")
    logger.info("job_index_scheduler_started", interval_minutes=interval)


async def stop_scheduler() -> None:
    global _task, _stop
    if _stop:
        _stop.set()
    if _task:
        try:
            await asyncio.wait_for(_task, timeout=5)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            _task.cancel()
    _task = None
    _stop = None

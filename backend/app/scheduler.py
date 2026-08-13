import asyncio
import logging

from app import storage
from app.sync_service import run_sync

logger = logging.getLogger("inventcompare.scheduler")

_task: asyncio.Task | None = None


async def _loop() -> None:
    while True:
        interval_minutes = storage.get_settings_data().get("sync_interval_minutes", 15)
        try:
            await run_sync()
            logger.info("Automatischer Sync abgeschlossen")
        except Exception:
            logger.exception("Automatischer Sync fehlgeschlagen")
        await asyncio.sleep(max(1, interval_minutes) * 60)


def start() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


def stop() -> None:
    if _task is not None:
        _task.cancel()

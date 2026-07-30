"""Periodic expiry cleanup for short-lived directory data."""
from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.db import get_session
from app.directory.service import cleanup_expired_directory_data

logger = logging.getLogger(__name__)


async def run_directory_cleanup() -> None:
    interval = max(60, settings.directory_cleanup_interval_seconds)
    while True:
        try:
            def _run() -> None:
                db = get_session()
                try:
                    cleanup_expired_directory_data(db)
                finally:
                    db.close()

            await asyncio.to_thread(_run)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("directory cleanup failed: %s", type(exc).__name__)
        await asyncio.sleep(interval)

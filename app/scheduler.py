"""Optional background scan scheduler."""

from __future__ import annotations

import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler

from app import storage
from scraper.runner import run_portal_scan

logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None


def _job() -> None:
    try:
        result = run_portal_scan(
            existing=storage.load_properties(),
            config=storage.load_config(),
            catalog_fallback=None,
        )
        storage.save_properties(result["properties"])
        logger.info(
            "Scheduled scan finished source=%s added=%s accepted=%s",
            result.get("source"),
            result.get("added_count"),
            result.get("accepted_count"),
        )
    except Exception:
        logger.exception("Scheduled scan failed")


def start_scheduler() -> None:
    """Start APScheduler when SCAN_INTERVAL_MINUTES > 0."""
    global _scheduler
    raw = os.getenv("SCAN_INTERVAL_MINUTES", "0").strip()
    try:
        minutes = int(raw)
    except ValueError:
        minutes = 0
    if minutes <= 0:
        return
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(_job, "interval", minutes=minutes, id="portal-scan")
    _scheduler.start()
    logger.info("Scheduler started every %s minutes", minutes)

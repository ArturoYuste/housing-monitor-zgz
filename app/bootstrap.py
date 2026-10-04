"""Startup bootstrap helpers for empty environments."""

from __future__ import annotations

import logging

from app.storage import CONFIG_PATH, PROPERTIES_PATH, _read_json, load_config, load_properties, save_config, save_properties
from app.supabase_store import supabase_enabled

logger = logging.getLogger(__name__)


def ensure_seed_data() -> None:
    """Ensure config/properties are available; seed Supabase when empty."""
    local_config = _read_json(CONFIG_PATH)
    local_properties = _read_json(PROPERTIES_PATH)

    if not supabase_enabled():
        # Local JSON files already ship with the repo.
        _ = load_config()
        _ = load_properties()
        return

    try:
        remote_config = load_config()
        if not remote_config:
            save_config(local_config)
            logger.info("Seeded Supabase app_config from local JSON")
    except Exception:
        try:
            save_config(local_config)
            logger.info("Seeded Supabase app_config after load failure")
        except Exception:
            logger.exception("Could not seed Supabase config")

    try:
        remote_properties = load_properties()
        if not remote_properties:
            save_properties(local_properties)
            logger.info("Seeded Supabase properties from local JSON (%s rows)", len(local_properties))
    except Exception:
        try:
            save_properties(local_properties)
            logger.info("Seeded Supabase properties after load failure")
        except Exception:
            logger.exception("Could not seed Supabase properties")

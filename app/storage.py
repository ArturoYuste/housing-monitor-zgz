"""Persistence helpers for config and properties (JSON local, optional Supabase)."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

from app.supabase_store import SupabaseStore, supabase_enabled

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
PROPERTIES_PATH = DATA_DIR / "properties.json"
CONFIG_PATH = DATA_DIR / "config.json"
DEMO_CATALOG_PATH = DATA_DIR / "demo_catalog.json"

_lock = Lock()


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _write_json(path: Path, payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    bom = chr(0xFEFF)
    crlf_text = text.replace(chr(10), chr(13) + chr(10)) + (chr(13) + chr(10))
    path.write_bytes((bom + crlf_text).encode("utf-8"))


def load_properties() -> list[dict[str, Any]]:
    if supabase_enabled():
        try:
            return SupabaseStore().load_properties()
        except Exception:
            pass
    with _lock:
        return _read_json(PROPERTIES_PATH)


def save_properties(properties: list[dict[str, Any]]) -> None:
    with _lock:
        _write_json(PROPERTIES_PATH, properties)
    if supabase_enabled():
        try:
            SupabaseStore().save_properties(properties)
        except Exception:
            pass


def load_config() -> dict[str, Any]:
    if supabase_enabled():
        try:
            remote = SupabaseStore().load_config()
            if remote:
                return remote
        except Exception:
            pass
    with _lock:
        return _read_json(CONFIG_PATH)


def save_config(config: dict[str, Any]) -> None:
    with _lock:
        _write_json(CONFIG_PATH, config)
    if supabase_enabled():
        try:
            SupabaseStore().save_config(config)
        except Exception:
            pass


def load_demo_catalog() -> list[dict[str, Any]]:
    with _lock:
        return _read_json(DEMO_CATALOG_PATH)


def find_property(property_id: str) -> dict[str, Any] | None:
    for item in load_properties():
        if item.get("id") == property_id:
            return item
    return None


def update_property(property_id: str, **changes: Any) -> dict[str, Any] | None:
    """Update one property in the active store (Supabase when enabled)."""
    with _lock:
        if supabase_enabled():
            try:
                properties = SupabaseStore().load_properties()
            except Exception:
                properties = _read_json(PROPERTIES_PATH)
        else:
            properties = _read_json(PROPERTIES_PATH)

        updated: dict[str, Any] | None = None
        for item in properties:
            if item.get("id") == property_id:
                item.update(changes)
                updated = item
                break
        if updated is None:
            return None

        # Always keep local JSON as fallback mirror.
        _write_json(PROPERTIES_PATH, properties)
        snapshot = list(properties)

    if supabase_enabled():
        try:
            SupabaseStore().save_properties(snapshot)
        except Exception:
            # Still return updated local view; next load may fall back.
            pass
    return updated

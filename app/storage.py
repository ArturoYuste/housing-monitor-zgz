"""JSON persistence helpers for config and properties."""

from __future__ import annotations

import json
from pathlib import Path
from threading import Lock
from typing import Any

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
    # Persist with UTF-8 BOM and CRLF to match project file preferences.
    encoded = ("\ufeff" + text.replace("\n", "\r\n") + "\r\n").encode("utf-8")
    path.write_bytes(encoded)


def load_properties() -> list[dict[str, Any]]:
    with _lock:
        return _read_json(PROPERTIES_PATH)


def save_properties(properties: list[dict[str, Any]]) -> None:
    with _lock:
        _write_json(PROPERTIES_PATH, properties)


def load_config() -> dict[str, Any]:
    with _lock:
        return _read_json(CONFIG_PATH)


def save_config(config: dict[str, Any]) -> None:
    with _lock:
        _write_json(CONFIG_PATH, config)


def load_demo_catalog() -> list[dict[str, Any]]:
    with _lock:
        return _read_json(DEMO_CATALOG_PATH)


def find_property(property_id: str) -> dict[str, Any] | None:
    for item in load_properties():
        if item.get("id") == property_id:
            return item
    return None


def update_property(property_id: str, **changes: Any) -> dict[str, Any] | None:
    with _lock:
        properties = _read_json(PROPERTIES_PATH)
        updated: dict[str, Any] | None = None
        for item in properties:
            if item.get("id") == property_id:
                item.update(changes)
                updated = item
                break
        if updated is None:
            return None
        _write_json(PROPERTIES_PATH, properties)
        return updated

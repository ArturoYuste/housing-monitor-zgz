"""Demo scan runner that applies filters to a local catalog."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from scraper.filter_engine import filter_properties


def run_demo_scan(
    catalog: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Filter catalog items and merge new matches into existing properties."""
    accepted, rejected = filter_properties(catalog, config)
    known_ids = {item.get("id") for item in existing}
    added: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    merged = list(existing)
    for item in accepted:
        if item.get("id") in known_ids:
            continue
        entry = deepcopy(item)
        entry.setdefault("status", "pending")
        entry.setdefault("user_notes", "")
        entry["date_detected"] = entry.get("date_detected") or now
        if entry.get("price_per_m2") is None and entry.get("price") and entry.get("size_m2"):
            entry["price_per_m2"] = round(entry["price"] / entry["size_m2"])
        merged.append(entry)
        added.append(entry)

    return {
        "properties": merged,
        "added_count": len(added),
        "rejected_count": len(rejected),
        "accepted_count": len(accepted),
        "added": added,
        "rejected": rejected,
    }

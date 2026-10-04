"""Multi-portal scan runner with demo fallback."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable

from scraper import fotocasa, habitaclia, idealista, pisos
from scraper.email_inbox import imap_enabled
from scraper.filter_engine import filter_properties


PortalFetcher = Callable[[dict[str, Any]], list[dict[str, Any]]]


def _merge_new(
    existing: list[dict[str, Any]],
    accepted: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
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
    return merged, added


def collect_from_portals(config: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Collect raw listings from each enabled portal module."""
    return {
        "idealista": idealista.fetch_listings(),
        "fotocasa": fotocasa.fetch_listings(config),
        "habitaclia": habitaclia.fetch_listings(config),
        "pisos.com": pisos.fetch_listings(config),
    }


def run_demo_scan(
    catalog: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    """Filter demo catalog items and merge new matches into existing properties."""
    accepted, rejected = filter_properties(catalog, config)
    merged, added = _merge_new(existing, accepted)
    return {
        "properties": merged,
        "added_count": len(added),
        "rejected_count": len(rejected),
        "accepted_count": len(accepted),
        "added": added,
        "rejected": rejected,
        "source": "demo_catalog",
        "imap_enabled": imap_enabled(),
    }


def run_portal_scan(
    existing: list[dict[str, Any]],
    config: dict[str, Any],
    catalog_fallback: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run multi-portal collection; fall back to demo catalog when all portals are empty."""
    by_portal = collect_from_portals(config)
    combined: list[dict[str, Any]] = []
    for listings in by_portal.values():
        combined.extend(listings)

    source = "portals"
    if not combined and catalog_fallback is not None:
        combined = catalog_fallback
        source = "demo_catalog"

    accepted, rejected = filter_properties(combined, config)
    merged, added = _merge_new(existing, accepted)
    return {
        "properties": merged,
        "added_count": len(added),
        "rejected_count": len(rejected),
        "accepted_count": len(accepted),
        "added": added,
        "rejected": rejected,
        "source": source,
        "by_portal_counts": {name: len(items) for name, items in by_portal.items()},
        "imap_enabled": imap_enabled(),
    }

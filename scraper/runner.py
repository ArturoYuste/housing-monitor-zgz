"""Multi-portal scan runner with demo fallback."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable

from scraper import fotocasa, habitaclia, idealista, pisos
from scraper.email_inbox import imap_enabled
from scraper.filter_engine import filter_properties

PortalFetcher = Callable[[dict[str, Any]], list[dict[str, Any]]]

PORTAL_FETCHERS: dict[str, PortalFetcher] = {
    "idealista": lambda config: idealista.fetch_listings(),
    "fotocasa": fotocasa.fetch_listings,
    "habitaclia": habitaclia.fetch_listings,
    "pisos.com": pisos.fetch_listings,
}


def _merge_new(
    existing: list[dict[str, Any]],
    accepted: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    known_ids = {item.get("id") for item in existing}
    known_urls = {item.get("url") for item in existing if item.get("url")}
    added: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    merged = list(existing)
    for item in accepted:
        if item.get("id") in known_ids or (item.get("url") and item.get("url") in known_urls):
            continue
        entry = deepcopy(item)
        entry.setdefault("status", "pending")
        entry.setdefault("user_notes", "")
        entry["date_detected"] = entry.get("date_detected") or now
        if entry.get("price_per_m2") is None and entry.get("price") and entry.get("size_m2"):
            entry["price_per_m2"] = round(entry["price"] / entry["size_m2"])
        merged.append(entry)
        added.append(entry)
        known_ids.add(entry.get("id"))
        if entry.get("url"):
            known_urls.add(entry.get("url"))
    return merged, added


def _prepare_config(config: dict[str, Any]) -> dict[str, Any]:
    prepared = deepcopy(config)
    max_towns = prepared.get("scan_max_towns")
    towns = list(prepared.get("towns") or prepared.get("locations") or [])
    if isinstance(max_towns, int) and max_towns > 0:
        prepared["towns"] = towns[:max_towns]
    else:
        prepared["towns"] = towns
    return prepared


def collect_from_portals(config: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, str]]:
    """Collect listings from enabled portals; capture per-portal errors."""
    prepared = _prepare_config(config)
    enabled = prepared.get("enabled_portals") or list(PORTAL_FETCHERS)
    by_portal: dict[str, list[dict[str, Any]]] = {}
    errors: dict[str, str] = {}

    def _run(name: str) -> tuple[str, list[dict[str, Any]]]:
        fetcher = PORTAL_FETCHERS[name]
        return name, fetcher(prepared)

    selected = [name for name in enabled if name in PORTAL_FETCHERS]
    if not selected:
        return {}, {"portals": "No enabled portals configured"}

    with ThreadPoolExecutor(max_workers=min(4, len(selected))) as pool:
        futures = {pool.submit(_run, name): name for name in selected}
        for future in as_completed(futures):
            name = futures[future]
            try:
                portal_name, listings = future.result()
                by_portal[portal_name] = listings
            except Exception as exc:  # noqa: BLE001
                by_portal[name] = []
                errors[name] = str(exc)
    return by_portal, errors


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
        "by_portal_counts": {},
        "errors": {},
    }


def run_portal_scan(
    existing: list[dict[str, Any]],
    config: dict[str, Any],
    catalog_fallback: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run multi-portal collection; fall back to demo catalog when all portals are empty."""
    by_portal, errors = collect_from_portals(config)
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
        "errors": errors,
        "imap_enabled": imap_enabled(),
    }

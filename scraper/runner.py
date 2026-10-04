"""Multi-portal scan runner with cheapest-duplicate selection."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable

from scraper import fotocasa, habitaclia, idealista, pisos
from scraper.dedupe import dedupe_keep_cheapest, listing_fingerprint
from scraper.email_inbox import imap_enabled
from scraper.filter_engine import filter_properties

PortalFetcher = Callable[[dict[str, Any]], list[dict[str, Any]]]

PORTAL_FETCHERS: dict[str, PortalFetcher] = {
    "idealista": lambda config: idealista.fetch_listings(),
    "fotocasa": fotocasa.fetch_listings,
    "habitaclia": habitaclia.fetch_listings,
    "pisos.com": pisos.fetch_listings,
}

PROTECTED_STATUSES = {"saved", "discarded"}


def _normalize_status(status: str | None) -> str:
    value = (status or "pending").strip().lower()
    if value in {"favorite", "contacted", "guardado", "guardados"}:
        return "saved"
    if value in {"pending", "saved", "discarded"}:
        return value
    return "pending"


def migrate_property_statuses(properties: list[dict[str, Any]]) -> list[dict[str, Any]]:
    migrated: list[dict[str, Any]] = []
    for item in properties:
        entry = dict(item)
        entry["status"] = _normalize_status(entry.get("status"))
        entry.setdefault("images", [entry["main_image"]] if entry.get("main_image") else [])
        entry.setdefault("defects", "")
        entry.setdefault("price_notes", "")
        entry.setdefault("negotiation_notes", "")
        entry.setdefault("alt_offers", [])
        migrated.append(entry)
    return migrated


def _merge_new(
    existing: list[dict[str, Any]],
    accepted: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    existing = migrate_property_statuses(existing)
    accepted = dedupe_keep_cheapest(accepted)

    known_ids = {item.get("id") for item in existing}
    known_urls = {item.get("url") for item in existing if item.get("url")}
    fingerprint_index = {
        listing_fingerprint(item): item for item in existing
    }

    added: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    merged = list(existing)

    for item in accepted:
        if item.get("id") in known_ids or (item.get("url") and item.get("url") in known_urls):
            continue

        key = listing_fingerprint(item)
        current = fingerprint_index.get(key)
        if current is not None:
            current_status = _normalize_status(current.get("status"))
            if current_status in PROTECTED_STATUSES:
                # Keep user decision; attach cheaper alt offer metadata if useful.
                alts = list(current.get("alt_offers") or [])
                alts.append(
                    {
                        "portal": str(item.get("portal") or ""),
                        "url": str(item.get("url") or ""),
                        "price": str(item.get("price") or ""),
                    }
                )
                current["alt_offers"] = alts
                continue

            # Replace pending duplicate if the new one is cheaper.
            try:
                new_price = int(item.get("price") or 10**12)
                old_price = int(current.get("price") or 10**12)
            except (TypeError, ValueError):
                new_price, old_price = 10**12, 10**12
            if new_price < old_price:
                replaced_id = current.get("id")
                entry = deepcopy(item)
                entry["status"] = "pending"
                entry.setdefault("defects", "")
                entry.setdefault("price_notes", "")
                entry.setdefault("negotiation_notes", "")
                entry["date_detected"] = entry.get("date_detected") or now
                if entry.get("price_per_m2") is None and entry.get("price") and entry.get("size_m2"):
                    entry["price_per_m2"] = round(entry["price"] / entry["size_m2"])
                alts = list(entry.get("alt_offers") or [])
                alts.append(
                    {
                        "portal": str(current.get("portal") or ""),
                        "url": str(current.get("url") or ""),
                        "price": str(current.get("price") or ""),
                    }
                )
                entry["alt_offers"] = alts
                merged = [entry if x.get("id") == replaced_id else x for x in merged]
                fingerprint_index[key] = entry
                known_ids.add(entry.get("id"))
                if entry.get("url"):
                    known_urls.add(entry.get("url"))
                added.append(entry)
            continue

        entry = deepcopy(item)
        entry["status"] = "pending"
        entry.setdefault("defects", "")
        entry.setdefault("price_notes", "")
        entry.setdefault("negotiation_notes", "")
        entry["date_detected"] = entry.get("date_detected") or now
        if entry.get("price_per_m2") is None and entry.get("price") and entry.get("size_m2"):
            entry["price_per_m2"] = round(entry["price"] / entry["size_m2"])
        merged.append(entry)
        added.append(entry)
        known_ids.add(entry.get("id"))
        if entry.get("url"):
            known_urls.add(entry.get("url"))
        fingerprint_index[key] = entry

    return merged, added


def _prepare_config(config: dict[str, Any]) -> dict[str, Any]:
    prepared = deepcopy(config)
    max_towns = prepared.get("scan_max_towns")
    towns = list(prepared.get("towns") or prepared.get("locations") or [])
    if isinstance(max_towns, int) and max_towns > 0:
        prepared["towns"] = towns[:max_towns]
    else:
        prepared["towns"] = towns
    # Idealista deferred: ignore unless explicitly forced later.
    enabled = [p for p in (prepared.get("enabled_portals") or []) if p != "idealista"]
    if not enabled:
        enabled = ["fotocasa", "habitaclia", "pisos.com"]
    prepared["enabled_portals"] = enabled
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


def run_portal_scan(
    existing: list[dict[str, Any]],
    config: dict[str, Any],
    catalog_fallback: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run multi-portal collection; optional fallback catalog (disabled in prod UX)."""
    by_portal, errors = collect_from_portals(config)
    combined: list[dict[str, Any]] = []
    for listings in by_portal.values():
        combined.extend(listings)

    source = "portals"
    if not combined and catalog_fallback:
        combined = catalog_fallback
        source = "demo_catalog"

    accepted, rejected = filter_properties(combined, config)
    accepted = dedupe_keep_cheapest(accepted)
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

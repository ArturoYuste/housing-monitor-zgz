"""Multi-portal scan runner with cheapest-duplicate selection."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Callable

from scraper import fotocasa, habitaclia, idealista, pisos
from scraper.dedupe import dedupe_keep_cheapest, listing_fingerprint, merge_alt_offers
from scraper.email_inbox import imap_enabled
from scraper.filter_engine import filter_properties, reapply_filters_to_pending
from scraper.pisos import enrich_missing_images

PortalFetcher = Callable[[dict[str, Any]], list[dict[str, Any]]]

PORTAL_FETCHERS: dict[str, PortalFetcher] = {
    "idealista": idealista.fetch_listings,
    "fotocasa": fotocasa.fetch_listings,
    "habitaclia": habitaclia.fetch_listings,
    "pisos.com": pisos.fetch_listings,
}

PROTECTED_STATUSES = {"saved", "discarded"}

# Fields refreshed from live portal data on rescan.
REFRESH_FIELDS = (
    "title",
    "price",
    "price_per_m2",
    "size_m2",
    "plot_m2",
    "rooms",
    "baths",
    "location",
    "description",
    "main_image",
    "images",
    "url",
    "portal",
    "has_garden",
    "has_plot",
    "has_elevator",
    "floor",
)

TRACKED_CHANGE_FIELDS = (
    "price",
    "title",
    "size_m2",
    "plot_m2",
    "rooms",
    "baths",
    "location",
    "description",
    "main_image",
    "url",
)


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
        entry.setdefault("updated_at", "")
        entry.setdefault("change_summary", [])
        entry.setdefault("is_withdrawn", False)
        entry.setdefault("preferred_contact_portal", "")
        primary = str(entry.get("portal") or "")
        entry["alt_offers"] = [
            alt
            for alt in merge_alt_offers(list(entry.get("alt_offers") or []))
            if alt.get("portal") and alt.get("portal") != primary
        ]
        migrated.append(entry)
    return migrated


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _norm_url(url: str | None) -> str:
    """Stable identity helper: strip noise so the same listing matches across syncs."""
    text = str(url or "").strip().lower()
    if not text:
        return ""
    text = text.split("#", 1)[0]
    text = text.split("?", 1)[0]
    return text.rstrip("/")


def _norm_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "|".join(str(x) for x in value)
    return str(value).strip()


def _diff_changes(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    changes: list[str] = []
    labels = {
        "price": "precio",
        "title": "título",
        "size_m2": "metros",
        "plot_m2": "parcela",
        "rooms": "habitaciones",
        "baths": "baños",
        "location": "ubicación",
        "description": "descripción",
        "main_image": "foto principal",
        "url": "enlace",
    }
    for field in TRACKED_CHANGE_FIELDS:
        if _norm_value(old.get(field)) != _norm_value(new.get(field)):
            if field == "price":
                old_p = old.get("price")
                new_p = new.get("price")
                changes.append(f"precio {old_p or '—'} → {new_p or '—'}")
            elif field == "description":
                changes.append("descripción")
            elif field == "main_image":
                changes.append("fotos")
            else:
                changes.append(labels.get(field, field))
    # Image count / set changes even if main stays same.
    old_imgs = old.get("images") or []
    new_imgs = new.get("images") or []
    if _norm_value(old_imgs) != _norm_value(new_imgs) and "fotos" not in changes:
        changes.append("fotos")
    return changes


def _apply_refresh(current: dict[str, Any], fresh: dict[str, Any], now: str) -> bool:
    """Update stored listing from fresh portal data. Returns True if modified."""
    changes = _diff_changes(current, fresh)
    if not changes:
        # Still refresh non-tracked fields quietly if needed, but no modified flag.
        for field in REFRESH_FIELDS:
            if field in fresh and fresh.get(field) is not None:
                current[field] = fresh.get(field)
        if current.get("price_per_m2") is None and current.get("price") and current.get("size_m2"):
            current["price_per_m2"] = round(current["price"] / current["size_m2"])
        return False

    for field in REFRESH_FIELDS:
        if field in fresh and fresh.get(field) is not None:
            current[field] = fresh.get(field)
    if current.get("price_per_m2") is None and current.get("price") and current.get("size_m2"):
        current["price_per_m2"] = round(current["price"] / current["size_m2"])

    current["updated_at"] = now
    current["change_summary"] = changes
    current["is_modified"] = True
    return True


def _find_existing(
    item: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
    by_url: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    prop_id = item.get("id")
    if prop_id and prop_id in by_id:
        return by_id[prop_id]
    url = _norm_url(item.get("url"))
    if url and url in by_url:
        return by_url[url]
    return None


def _merge_new(
    existing: list[dict[str, Any]],
    accepted: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    existing = migrate_property_statuses(existing)
    accepted = dedupe_keep_cheapest(accepted)

    by_id = {item.get("id"): item for item in existing if item.get("id")}
    by_url = {_norm_url(item.get("url")): item for item in existing if _norm_url(item.get("url"))}
    fingerprint_index = {listing_fingerprint(item): item for item in existing}

    added: list[dict[str, Any]] = []
    modified: list[dict[str, Any]] = []
    now = _now_iso()
    merged = list(existing)

    for item in accepted:
        current = _find_existing(item, by_id, by_url)
        if current is not None:
            # Identity match by stable id or URL: never auto-change user status.
            preserved = _normalize_status(current.get("status"))
            if _apply_refresh(current, item, now):
                modified.append(current)
            current["status"] = preserved
            if preserved == "saved":
                current["is_withdrawn"] = False
            continue

        key = listing_fingerprint(item)
        current = fingerprint_index.get(key)
        if current is not None:
            current_status = _normalize_status(current.get("status"))
            if current_status in PROTECTED_STATUSES:
                # Keep saved/discarded forever unless the user changes status.
                current["status"] = current_status
                primary = str(current.get("portal") or "")
                current["alt_offers"] = [
                    alt
                    for alt in merge_alt_offers(
                        list(current.get("alt_offers") or []),
                        [
                            {
                                "portal": str(item.get("portal") or ""),
                                "url": str(item.get("url") or ""),
                                "price": item.get("price"),
                            }
                        ],
                    )
                    if alt.get("portal") and alt.get("portal") != primary
                ]
                if current_status == "saved":
                    current["is_withdrawn"] = False
                continue

            # Replace pending duplicate if the new one is cheaper, else refresh current.
            try:
                new_price = int(item.get("price") or 10**12)
                old_price = int(current.get("price") or 10**12)
            except (TypeError, ValueError):
                new_price, old_price = 10**12, 10**12
            if new_price < old_price:
                replaced_id = current.get("id")
                entry = deepcopy(item)
                entry["status"] = "pending"
                entry.setdefault("defects", current.get("defects") or "")
                entry.setdefault("price_notes", current.get("price_notes") or "")
                entry.setdefault("negotiation_notes", current.get("negotiation_notes") or "")
                entry["preferred_contact_portal"] = current.get("preferred_contact_portal") or ""
                entry["date_detected"] = current.get("date_detected") or entry.get("date_detected") or now
                entry["updated_at"] = now
                entry["is_modified"] = True
                entry["change_summary"] = ["reemplazado por oferta más barata"] + _diff_changes(current, entry)
                if entry.get("price_per_m2") is None and entry.get("price") and entry.get("size_m2"):
                    entry["price_per_m2"] = round(entry["price"] / entry["size_m2"])
                primary = str(entry.get("portal") or "")
                entry["alt_offers"] = [
                    alt
                    for alt in merge_alt_offers(
                        list(entry.get("alt_offers") or []),
                        list(current.get("alt_offers") or []),
                        [
                            {
                                "portal": str(current.get("portal") or ""),
                                "url": str(current.get("url") or ""),
                                "price": current.get("price"),
                            }
                        ],
                    )
                    if alt.get("portal") and alt.get("portal") != primary
                ]
                merged = [entry if x.get("id") == replaced_id else x for x in merged]
                fingerprint_index[key] = entry
                by_id[entry.get("id")] = entry
                norm = _norm_url(entry.get("url"))
                if norm:
                    by_url[norm] = entry
                added.append(entry)
                modified.append(entry)
            else:
                if _apply_refresh(current, item, now):
                    modified.append(current)
            continue

        entry = deepcopy(item)
        entry["status"] = "pending"
        entry.setdefault("defects", "")
        entry.setdefault("price_notes", "")
        entry.setdefault("negotiation_notes", "")
        entry["date_detected"] = entry.get("date_detected") or now
        entry["updated_at"] = ""
        entry["is_modified"] = False
        entry["change_summary"] = []
        if entry.get("price_per_m2") is None and entry.get("price") and entry.get("size_m2"):
            entry["price_per_m2"] = round(entry["price"] / entry["size_m2"])
        merged.append(entry)
        added.append(entry)
        by_id[entry.get("id")] = entry
        norm = _norm_url(entry.get("url"))
        if norm:
            by_url[norm] = entry
        fingerprint_index[key] = entry

    return merged, added, modified


def _prepare_config(config: dict[str, Any]) -> dict[str, Any]:
    prepared = deepcopy(config)
    max_towns = prepared.get("scan_max_towns")
    towns = list(prepared.get("towns") or prepared.get("locations") or [])
    if isinstance(max_towns, int) and max_towns > 0:
        prepared["towns"] = towns[:max_towns]
    else:
        prepared["towns"] = towns
    enabled = [p for p in (prepared.get("enabled_portals") or []) if p]
    # Strip stale idealista flag from saved config; re-add only when IMAP is on.
    enabled = [p for p in enabled if p != "idealista"]
    if not enabled:
        enabled = ["fotocasa", "habitaclia", "pisos.com"]
    if imap_enabled() and "idealista" not in enabled:
        enabled.append("idealista")
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
    """Refresh listings from portals, merge changes, and clean pending mismatches."""
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
    # Only hit detail pages for accepted ads still missing photos.
    accepted = enrich_missing_images(accepted, limit=24, min_images=1)
    merged, added, modified = _merge_new(existing, accepted)
    # Keep pending list aligned with current criteria after every refresh.
    # Never touches saved/discarded statuses.
    cleaned, kept_pending, removed_pending = reapply_filters_to_pending(merged, config)

    # Mark saved listings as withdrawn when portals no longer return them.
    # Only when we actually got portal data (avoid false positives on empty/failed scans).
    if combined:
        live_ids = {item.get("id") for item in combined if item.get("id")}
        live_urls = {_norm_url(item.get("url")) for item in combined if _norm_url(item.get("url"))}
        for prop in cleaned:
            if _normalize_status(prop.get("status")) != "saved":
                continue
            still_live = (prop.get("id") in live_ids) or (_norm_url(prop.get("url")) in live_urls)
            prop["is_withdrawn"] = not still_live

    return {
        "properties": cleaned,
        "added_count": len(added),
        "modified_count": len(modified),
        "removed_pending_count": removed_pending,
        "kept_pending_count": kept_pending,
        "rejected_count": len(rejected),
        "accepted_count": len(accepted),
        "added": added,
        "modified": modified,
        "rejected": rejected,
        "source": source,
        "by_portal_counts": {name: len(items) for name, items in by_portal.items()},
        "errors": errors,
        "imap_enabled": imap_enabled(),
        "synced_at": _now_iso(),
    }

"""Deduplicate listings and keep the cheapest option."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def _norm(text: str) -> str:
    text = _strip_accents(text).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def listing_fingerprint(item: dict[str, Any]) -> str:
    """Build a coarse fingerprint for cross-portal duplicates."""
    location = _norm(str(item.get("location") or ""))
    title = _norm(str(item.get("title") or ""))
    # Keep a short title stem without generic words.
    stop = {"casa", "chalet", "venta", "en", "con", "jardin", "terreno", "de", "la", "el"}
    tokens = [t for t in title.split() if t not in stop][:4]
    title_stem = " ".join(tokens)
    size = item.get("size_m2")
    try:
        size_bucket = int(round(float(size) / 5.0) * 5) if size is not None else 0
    except (TypeError, ValueError):
        size_bucket = 0
    rooms = item.get("rooms") or 0
    return f"{location}|{size_bucket}|{rooms}|{title_stem}"


def _price_key(item: dict[str, Any]) -> tuple[int, int]:
    price = item.get("price")
    try:
        price_i = int(price) if price is not None else 10**12
    except (TypeError, ValueError):
        price_i = 10**12
    images = item.get("images") or []
    # Prefer cheaper, then more images.
    return price_i, -len(images)


def _as_price(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _alt_entry(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "portal": str(item.get("portal") or ""),
        "url": str(item.get("url") or ""),
        "price": _as_price(item.get("price")),
    }


def merge_alt_offers(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate alternate portal offers by portal, keeping the cheapest URL."""
    by_portal: dict[str, dict[str, Any]] = {}
    for group in groups:
        for raw in group or []:
            if not isinstance(raw, dict):
                continue
            portal = str(raw.get("portal") or "").strip()
            if not portal:
                continue
            price = _as_price(raw.get("price"))
            url = str(raw.get("url") or "")
            current = by_portal.get(portal)
            if current is None:
                by_portal[portal] = {"portal": portal, "url": url, "price": price}
                continue
            current_price = current.get("price")
            if price is not None and (current_price is None or price < current_price):
                current["price"] = price
                if url:
                    current["url"] = url
            elif not current.get("url") and url:
                current["url"] = url
    return sorted(
        by_portal.values(),
        key=lambda item: (
            item.get("price") is None,
            item.get("price") if item.get("price") is not None else 10**12,
            item.get("portal") or "",
        ),
    )


def dedupe_keep_cheapest(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one listing per fingerprint: the cheapest (then richest media)."""
    best: dict[str, dict[str, Any]] = {}
    alts: dict[str, list[dict[str, Any]]] = {}
    for item in listings:
        key = listing_fingerprint(item)
        current = best.get(key)
        if current is None:
            best[key] = item
            alts[key] = []
            continue
        if _price_key(item) < _price_key(current):
            alts[key].append(_alt_entry(current))
            # Keep previous alts from the displaced winner.
            alts[key].extend(list(current.get("alt_offers") or []))
            best[key] = item
        else:
            alts[key].append(_alt_entry(item))
            alts[key].extend(list(item.get("alt_offers") or []))
    result: list[dict[str, Any]] = []
    for key, item in best.items():
        entry = dict(item)
        primary_portal = str(entry.get("portal") or "")
        merged_alts = merge_alt_offers(list(entry.get("alt_offers") or []), alts.get(key, []))
        entry["alt_offers"] = [
            alt for alt in merged_alts if alt.get("portal") and alt.get("portal") != primary_portal
        ]
        result.append(entry)
    return result

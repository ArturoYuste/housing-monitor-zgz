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


def dedupe_keep_cheapest(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one listing per fingerprint: the cheapest (then richest media)."""
    best: dict[str, dict[str, Any]] = {}
    alts: dict[str, list[dict[str, str]]] = {}
    for item in listings:
        key = listing_fingerprint(item)
        current = best.get(key)
        if current is None:
            best[key] = item
            alts[key] = []
            continue
        if _price_key(item) < _price_key(current):
            alts[key].append(
                {
                    "portal": str(current.get("portal") or ""),
                    "url": str(current.get("url") or ""),
                    "price": str(current.get("price") or ""),
                }
            )
            best[key] = item
        else:
            alts[key].append(
                {
                    "portal": str(item.get("portal") or ""),
                    "url": str(item.get("url") or ""),
                    "price": str(item.get("price") or ""),
                }
            )
    result: list[dict[str, Any]] = []
    for key, item in best.items():
        entry = dict(item)
        existing_alts = list(entry.get("alt_offers") or [])
        entry["alt_offers"] = existing_alts + alts.get(key, [])
        result.append(entry)
    return result

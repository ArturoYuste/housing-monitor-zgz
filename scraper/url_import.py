"""Manual listing import from a portal URL."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from scraper.filter_engine import fold_text, location_matches_any_town, matches_filters
from scraper.http_client import fetch_html, parse_euro_number
from scraper.portals import normalize_listing

OG_RE = re.compile(
    r'<meta[^>]+property=["\']og:(title|description|image|url)["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
OG_RE_SWAP = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:(title|description|image|url)["\']',
    re.I,
)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)
PRICE_RE = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d{4,7})\s*€")
SIZE_RE = re.compile(r"(\d{2,4})\s*m(?:2|²)", re.I)
ROOMS_RE = re.compile(r"(\d{1,2})\s*(?:hab|dorm|rooms?)", re.I)
BATHS_RE = re.compile(r"(\d{1,2})\s*(?:baño|banos|bath)", re.I)
INMUEBLE_RE = re.compile(r"idealista\.com/.*/?inmueble/(\d+)", re.I)
FOTOCASA_RE = re.compile(r"fotocasa\.es/[^\"'\s]+/(\d{5,})", re.I)
HABITACLIA_RE = re.compile(r"habitaclia\.com/[^\"'\s]+/([a-f0-9-]{8,})", re.I)
PISOS_RE = re.compile(r"pisos\.com/[^\"'\s]*?(\d{6,}_\d+)", re.I)


def detect_portal(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    if "idealista." in host:
        return "idealista"
    if "fotocasa." in host:
        return "fotocasa"
    if "habitaclia." in host:
        return "habitaclia"
    if "pisos." in host:
        return "pisos.com"
    return None


def _meta_og(html: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for match in OG_RE.finditer(html or ""):
        found[match.group(1).lower()] = match.group(2).strip()
    for match in OG_RE_SWAP.finditer(html or ""):
        found[match.group(2).lower()] = match.group(1).strip()
    return found


def _walk_jsonld(node: Any, bag: list[dict[str, Any]]) -> None:
    if isinstance(node, list):
        for item in node:
            _walk_jsonld(item, bag)
        return
    if isinstance(node, dict):
        bag.append(node)
        for value in node.values():
            _walk_jsonld(value, bag)


def _from_jsonld(html: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for match in JSONLD_RE.finditer(html or ""):
        raw = match.group(1).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        nodes: list[dict[str, Any]] = []
        _walk_jsonld(data, nodes)
        for node in nodes:
            types = node.get("@type")
            type_l = " ".join(types) if isinstance(types, list) else str(types or "")
            type_l = type_l.lower()
            if "product" in type_l or "offer" in type_l or "residence" in type_l or "place" in type_l or "apartment" in type_l or "house" in type_l:
                if node.get("name") and not out.get("title"):
                    out["title"] = str(node.get("name"))
                if node.get("description") and not out.get("description"):
                    out["description"] = str(node.get("description"))
                if node.get("image") and not out.get("image"):
                    image = node.get("image")
                    if isinstance(image, list) and image:
                        out["image"] = str(image[0] if not isinstance(image[0], dict) else image[0].get("url") or "")
                    elif isinstance(image, dict):
                        out["image"] = str(image.get("url") or "")
                    else:
                        out["image"] = str(image)
                offers = node.get("offers")
                if isinstance(offers, dict):
                    price = parse_euro_number(offers.get("price"))
                    if price and not out.get("price"):
                        out["price"] = price
                address = node.get("address")
                if isinstance(address, dict) and not out.get("location"):
                    parts = [
                        address.get("addressLocality") or address.get("addressRegion"),
                        address.get("streetAddress"),
                    ]
                    out["location"] = ", ".join(str(p) for p in parts if p)
                floor_size = node.get("floorSize") or node.get("size")
                if isinstance(floor_size, dict) and not out.get("size_m2"):
                    out["size_m2"] = parse_euro_number(floor_size.get("value"))
    return out


def _external_id(url: str, portal: str) -> str:
    if portal == "idealista":
        match = INMUEBLE_RE.search(url)
        if match:
            return match.group(1)
    if portal == "fotocasa":
        match = FOTOCASA_RE.search(url)
        if match:
            return match.group(1)
    if portal == "habitaclia":
        match = HABITACLIA_RE.search(url)
        if match:
            return match.group(1)
    if portal == "pisos.com":
        match = PISOS_RE.search(url)
        if match:
            return match.group(1)
    return re.sub(r"[^a-zA-Z0-9]+", "-", urlparse(url).path).strip("-")[:48] or "import"


def _guess_location(blob: str, towns: list[str]) -> str:
    for town in towns:
        if location_matches_any_town(blob, [town]):
            return town
    # Fallback: last comma segment if short.
    parts = [p.strip() for p in (blob or "").split(",") if p.strip()]
    if parts:
        return parts[-1][:80]
    return ""


def _property_type(blob: str) -> str:
    folded = fold_text(blob)
    if any(token in folded for token in ("piso", "apartamento", "atico", "estudio", "duplex")) and not any(
        token in folded for token in ("casa", "chalet", "adosado", "pareado")
    ):
        return "flat"
    if "chalet" in folded or "adosado" in folded or "pareado" in folded:
        return "chalet"
    return "house"


def fetch_listing_from_url(url: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Fetch and normalize a single listing URL into the shared property shape."""
    clean = (url or "").strip()
    if not clean.startswith(("http://", "https://")):
        raise ValueError("La URL debe empezar por http:// o https://")
    portal = detect_portal(clean)
    if not portal:
        raise ValueError("Portal no soportado. Usa Idealista, Fotocasa, Habitaclia o Pisos.com")

    html = fetch_html(clean, timeout=28.0, retries=2)
    og = _meta_og(html)
    ld = _from_jsonld(html)
    title_match = TITLE_RE.search(html or "")
    page_title = re.sub(r"\s+", " ", title_match.group(1)).strip() if title_match else ""
    blob = " ".join(
        [
            og.get("title") or "",
            og.get("description") or "",
            ld.get("title") or "",
            ld.get("description") or "",
            page_title,
        ]
    )
    price = ld.get("price") or parse_euro_number(PRICE_RE.search(blob) or PRICE_RE.search(html[:12000] if html else ""))
    size = ld.get("size_m2")
    if size is None:
        size_match = SIZE_RE.search(blob) or SIZE_RE.search(html[:12000] if html else "")
        size = int(size_match.group(1)) if size_match else None
    rooms_match = ROOMS_RE.search(blob) or ROOMS_RE.search(html[:12000] if html else "")
    baths_match = BATHS_RE.search(blob) or BATHS_RE.search(html[:12000] if html else "")
    towns = list((config or {}).get("towns") or (config or {}).get("locations") or [])
    location = ld.get("location") or _guess_location(blob, towns)
    image = og.get("image") or ld.get("image") or ""
    title = (og.get("title") or ld.get("title") or page_title or f"Anuncio {portal}")[:140]
    description = og.get("description") or ld.get("description") or ""
    external_id = _external_id(clean, portal)
    listing = normalize_listing(
        {
            "id": f"{portal}-{external_id}",
            "external_id": external_id,
            "title": title,
            "description": description,
            "price": price,
            "size_m2": size,
            "rooms": int(rooms_match.group(1)) if rooms_match else None,
            "baths": int(baths_match.group(1)) if baths_match else None,
            "location": location,
            "url": og.get("url") or clean,
            "main_image": image,
            "images": [image] if image else [],
            "property_type": _property_type(f"{title} {description} {clean}"),
            "has_garden": any(token in fold_text(f"{title} {description}") for token in ("jardin", "terreno", "parcela", "patio")),
            "has_plot": any(token in fold_text(f"{title} {description}") for token in ("terreno", "parcela")),
            "ingestion_source": "manual_url",
        },
        portal=portal,
    )
    return listing


def import_url(
    url: str,
    *,
    config: dict[str, Any],
    existing: list[dict[str, Any]],
) -> dict[str, Any]:
    """Import one URL: fetch, filter, merge into pending when accepted."""
    listing = fetch_listing_from_url(url, config)
    ok, reason = matches_filters(listing, config)
    if not ok:
        return {
            "ok": False,
            "reason": reason,
            "listing": listing,
            "properties": existing,
        }

    # Reuse merge path from runner for identity / cheaper duplicate handling.
    from scraper.runner import _merge_new

    merged, added, modified = _merge_new(existing, [listing])
    # Ensure status pending for newly added.
    for item in merged:
        if item.get("id") == listing.get("id") and (item.get("status") or "pending") not in {"saved", "discarded"}:
            item["status"] = "pending"
    return {
        "ok": True,
        "reason": "ok",
        "listing": listing,
        "properties": merged,
        "added_count": len(added),
        "modified_count": len(modified),
        "already_present": not added and not modified,
    }

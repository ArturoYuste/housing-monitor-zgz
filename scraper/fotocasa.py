"""Fotocasa extractor via public search HTML embedded JSON."""

from __future__ import annotations

import json
import re
from typing import Any

from scraper.http_client import feature_map, fetch_html, parse_euro_number, slugify_town
from scraper.portals import normalize_listing

HOUSE_SUBTYPES = {
    "house_chalet",
    "house",
    "chalet",
    "semidetachedhouse",
    "terracedhouse",
    "countryhouse",
}


def _extract_real_estates(html: str) -> list[dict[str, Any]]:
    match = re.search(r'"realEstates"\s*:\s*\[', html)
    if not match:
        return []
    start = match.end() - 1
    depth = 0
    end = None
    for index, char in enumerate(html[start:], start):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end is None:
        return []
    payload = json.loads(html[start:end])
    return payload if isinstance(payload, list) else []


def _map_item(item: dict[str, Any], town: str) -> dict[str, Any] | None:
    features = feature_map(item.get("features"))
    subtype = str(item.get("buildingSubtype") or "").lower()
    dynamic = {str(x).lower() for x in (item.get("dynamicFeatures") or [])}
    is_house = (
        subtype in HOUSE_SUBTYPES
        or "house" in subtype
        or "chalet" in subtype
        or "is_single_family_home" in dynamic
    )
    if not is_house:
        # Keep unknown subtypes if title/description clearly say house/chalet.
        blob = f"{item.get('description', '')} {item.get('location', '')}".lower()
        if not any(token in blob for token in ("casa", "chalet", "adosado", "unifamiliar")):
            return None

    detail = item.get("detail") or {}
    path = ""
    if isinstance(detail, dict):
        path = detail.get("es-ES") or next(iter(detail.values()), "") or ""
    url = f"https://www.fotocasa.es{path}" if path.startswith("/") else path
    image = ""
    for media in item.get("multimedia") or []:
        if media.get("type") == "image" and media.get("src"):
            image = media["src"]
            break

    price = item.get("rawPrice")
    if price is None:
        price = parse_euro_number(item.get("price"))

    garden_keys = {"private_garden", "garden", "yard", "terrace"}
    has_garden = any(key in features for key in garden_keys)
    plot_m2 = features.get("land") or features.get("plot") or features.get("surfaceLand")
    description = str(item.get("description") or "")
    if not has_garden and any(token in description.lower() for token in ("jardin", "jardín", "terreno", "parcela", "patio")):
        has_garden = True

    address = item.get("address") or {}
    location = (
        item.get("location")
        or address.get("municipality")
        or address.get("city")
        or town
    )
    listing_id = item.get("id")
    title = description.split("\n")[0].strip() if description else f"Casa en {location}"
    return normalize_listing(
        {
            "id": f"fotocasa-{listing_id}",
            "external_id": listing_id,
            "property_type": "chalet" if "chalet" in subtype else "house",
            "title": title[:120] or f"Fotocasa {listing_id}",
            "price": price,
            "size_m2": features.get("surface"),
            "plot_m2": plot_m2,
            "rooms": features.get("rooms"),
            "baths": features.get("bathrooms"),
            "has_garden": has_garden,
            "has_plot": bool(plot_m2) or "terreno" in description.lower() or "parcela" in description.lower(),
            "location": location,
            "url": url,
            "main_image": image,
            "description": description,
        },
        portal="fotocasa",
    )


def build_search_url(town: str, config: dict[str, Any]) -> str:
    slug = slugify_town(town)
    max_price = config.get("max_price") or 180000
    min_surface = config.get("min_size_m2") or 100
    return (
        f"https://www.fotocasa.es/es/comprar/chalets/{slug}/todas-las-zonas/l"
        f"?maxPrice={max_price}&minSurface={min_surface}"
    )


def fetch_listings(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Fetch Fotocasa chalet/house listings for configured towns."""
    config = config or {}
    towns = config.get("towns") or config.get("locations") or []
    if not towns:
        return []

    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for town in towns:
        try:
            html = fetch_html(build_search_url(str(town), config))
        except Exception:
            continue
        for item in _extract_real_estates(html):
            mapped = _map_item(item, str(town))
            if not mapped:
                continue
            listing_id = mapped["id"]
            if listing_id in seen:
                continue
            seen.add(listing_id)
            collected.append(mapped)
    return collected

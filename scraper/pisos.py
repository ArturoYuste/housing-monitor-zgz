"""Pisos.com extractor via public search HTML cards."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.http_client import fetch_html, parse_euro_number, slugify_town
from scraper.portals import normalize_listing

BASE = "https://www.pisos.com"


def build_search_url(town: str) -> str:
    slug = slugify_town(town).replace("-", "_")
    return f"{BASE}/venta/casas_y_chalets-{slug}/"


def _parse_card(card, town: str) -> dict[str, Any] | None:
    link_el = card.select_one("a[href*='/comprar/']")
    if not link_el:
        return None
    href = link_el.get("href") or ""
    lower = href.lower()
    if "/piso-" in lower and "/chalet-" not in lower and "/casa-" not in lower:
        return None

    text = card.get_text(" ", strip=True)
    price_el = card.select_one(".ad-preview__price")
    if price_el:
        price = parse_euro_number(price_el.get_text(" ", strip=True))
    else:
        price_match = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*€", text)
        price = parse_euro_number(price_match.group(1) if price_match else None)

    title_el = card.select_one(".ad-preview__title")
    title = title_el.get_text(" ", strip=True) if title_el else text[:100]
    desc_el = card.select_one(".ad-preview__description")
    description = desc_el.get_text(" ", strip=True) if desc_el else text

    size_match = re.search(r"(\d+)\s*m²", text)
    rooms_match = re.search(r"(\d+)\s*hab", text, re.I)
    baths_match = re.search(r"(\d+)\s*baño", text, re.I)
    image = ""
    img = card.select_one("img[src]")
    if img and img.get("src"):
        image = img["src"]

    external_id = href.rstrip("/").split("-")[-1] if href else title
    blob = f"{title} {description}".lower()
    has_garden = any(token in blob for token in ("jardin", "jardín", "terreno", "parcela", "patio"))
    property_type = "chalet" if "/chalet-" in lower else "house"

    return normalize_listing(
        {
            "id": f"pisos-{external_id}",
            "external_id": external_id,
            "property_type": property_type,
            "title": title,
            "price": price,
            "size_m2": int(size_match.group(1)) if size_match else None,
            "rooms": int(rooms_match.group(1)) if rooms_match else None,
            "baths": int(baths_match.group(1)) if baths_match else None,
            "has_garden": has_garden,
            "has_plot": "terreno" in blob or "parcela" in blob,
            "location": town,
            "url": urljoin(BASE, href),
            "main_image": image,
            "description": description,
        },
        portal="pisos.com",
    )


def fetch_listings(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Fetch Pisos.com house/chalet listings for configured towns."""
    config = config or {}
    towns = config.get("towns") or config.get("locations") or []
    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for town in towns:
        urls = [
            build_search_url(str(town)),
            f"{BASE}/venta/casas-{slugify_town(str(town)).replace('-', '_')}/",
        ]
        html = None
        for url in urls:
            try:
                html = fetch_html(url)
                break
            except Exception:
                continue
        if not html:
            continue
        soup = BeautifulSoup(html, "lxml")
        for card in soup.select("div.ad-preview"):
            mapped = _parse_card(card, str(town))
            if not mapped or mapped["id"] in seen:
                continue
            seen.add(mapped["id"])
            collected.append(mapped)
    return collected

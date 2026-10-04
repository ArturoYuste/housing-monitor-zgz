"""Habitaclia extractor via public search HTML cards."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.http_client import fetch_html, parse_euro_number, slugify_town
from scraper.portals import normalize_listing

BASE = "https://www.habitaclia.com"


def build_search_url(town: str) -> str:
    slug = slugify_town(town)
    return f"{BASE}/comprar/casas/zaragoza-provincia/{slug}/s"


def _parse_card(article, town: str) -> dict[str, Any] | None:
    link = None
    for anchor in article.select("a[href]"):
        href = anchor.get("href") or ""
        if "/comprar/" in href and href.rstrip("/").endswith("/d"):
            link = href
            break
    if not link:
        return None

    lower_link = link.lower()
    if any(
        token in lower_link
        for token in (
            "/piso/",
            "/planta-intermedia/",
            "/atico/",
            "/apartamento/",
            "/estudio/",
            "/duplex/",
            "/loft/",
        )
    ):
        return None

    text = article.get_text(" ", strip=True)
    price_match = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*€", text)
    price = parse_euro_number(price_match.group(1) if price_match else None)
    size_match = re.search(r"(\d+)\s*m²", text)
    rooms_match = re.search(r"(\d+)\s*hab", text, re.I)
    baths_match = re.search(r"(\d+)\s*bañ", text, re.I)
    title = article.get("aria-label") or text[:80]
    images: list[str] = []
    for img in article.select("img"):
        for attr in ("src", "data-src", "data-lazy", "data-original"):
            src = img.get(attr) or ""
            if src and src not in images and "data:" not in src and "logo" not in src.lower():
                images.append(src)
                break
    image = images[0] if images else ""

    external_id = link.rstrip("/").split("/")[-2] if "/d" in link else link
    description = text
    lowered = description.lower()
    has_garden = any(token in lowered for token in ("jardin", "jardín", "terreno", "parcela", "patio"))
    property_type = "chalet" if "/chalet/" in lower_link else "house"

    return normalize_listing(
        {
            "id": f"habitaclia-{external_id}",
            "external_id": external_id,
            "property_type": property_type,
            "title": title,
            "price": price,
            "size_m2": int(size_match.group(1)) if size_match else None,
            "rooms": int(rooms_match.group(1)) if rooms_match else None,
            "baths": int(baths_match.group(1)) if baths_match else None,
            "has_garden": has_garden,
            "has_plot": "terreno" in lowered or "parcela" in lowered,
            "location": town,
            "url": urljoin(BASE, link),
            "main_image": image,
            "images": images,
            "description": description,
        },
        portal="habitaclia",
    )


def fetch_listings(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Fetch Habitaclia house listings for configured towns."""
    config = config or {}
    towns = config.get("towns") or config.get("locations") or []
    def _fetch_town(town: str) -> list[dict[str, Any]]:
        try:
            html = fetch_html(build_search_url(str(town)))
        except Exception:
            return []
        soup = BeautifulSoup(html, "lxml")
        found: list[dict[str, Any]] = []
        for article in soup.select("article"):
            mapped = _parse_card(article, str(town))
            if mapped:
                found.append(mapped)
        return found

    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    if towns:
        with ThreadPoolExecutor(max_workers=min(6, len(towns))) as pool:
            futures = [pool.submit(_fetch_town, str(town)) for town in towns]
            for future in as_completed(futures):
                try:
                    batch = future.result()
                except Exception:
                    continue
                for mapped in batch:
                    if mapped["id"] in seen:
                        continue
                    seen.add(mapped["id"])
                    collected.append(mapped)
    return collected

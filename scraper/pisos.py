"""Pisos.com extractor via public search HTML cards."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper.http_client import fetch_html, parse_euro_number, slugify_town
from scraper.portals import normalize_listing

BASE = "https://www.pisos.com"
LOGO_MARKERS = ("/logos/", "logo_", "/logo/", "sprite", "placeholder", "data:image")


def build_search_url(town: str) -> str:
    slug = slugify_town(town).replace("-", "_")
    return f"{BASE}/venta/casas_y_chalets-{slug}/"


def _is_photo_url(url: str) -> bool:
    lower = url.lower()
    if not url.startswith("http"):
        return False
    if any(marker in lower for marker in LOGO_MARKERS):
        return False
    return any(
        token in lower
        for token in (
            "fotos.imghs.net",
            "/mm-wp/",
            "/m-wp/",
            "/fchm-wp/",
            "/fch-wp/",
            ".jpg",
            ".jpeg",
            ".webp",
            ".png",
        )
    )


def _photo_key(url: str) -> str:
    name = url.split("?")[0].rstrip("/").split("/")[-1]
    return name.lower()


def _prefer_photo_url(current: str, candidate: str) -> str:
    """Prefer medium/large CDN variants over tiny app thumbs."""
    rank = {
        "fchm-wp": 5,
        "mm-wp": 4,
        "fch-wp": 3,
        "m-wp": 2,
        "appswm-wp": 1,
        "apps-wp": 0,
    }

    def score(url: str) -> int:
        for key, value in rank.items():
            if f"/{key}/" in url:
                return value
        return 0

    return candidate if score(candidate) > score(current) else current


def _collect_images(root) -> list[str]:
    chosen: dict[str, str] = {}

    def add(url: str | None) -> None:
        if not url:
            return
        url = url.strip().split()[0].strip("'\"")
        if not _is_photo_url(url):
            return
        key = _photo_key(url)
        if key in chosen:
            chosen[key] = _prefer_photo_url(chosen[key], url)
        else:
            chosen[key] = url

    for img in root.select("img"):
        add(img.get("src"))
        add(img.get("data-src"))
        add(img.get("data-lazy"))
        add(img.get("data-original"))
        srcset = img.get("srcset") or img.get("data-srcset")
        if srcset:
            add(srcset.split(",")[0])

    for source in root.select("source"):
        add(source.get("srcset"))
        add(source.get("data-srcset"))
        add(source.get("src"))

    return list(chosen.values())


def _extract_detail_images(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    images = _collect_images(soup)
    if len(images) >= 3:
        return images
    # Fallback: harvest CDN urls from raw HTML.
    found: dict[str, str] = {}
    for match in re.findall(r"https://fotos\.imghs\.net/[^\"'\s]+", html):
        url = match.replace("\\/", "/")
        if not _is_photo_url(url):
            continue
        key = _photo_key(url)
        if key in found:
            found[key] = _prefer_photo_url(found[key], url)
        else:
            found[key] = url
    return list(found.values()) or images


def _enrich_images(listing: dict[str, Any]) -> dict[str, Any]:
    url = listing.get("url")
    if not url:
        return listing
    try:
        html = fetch_html(str(url))
    except Exception:
        return listing
    images = _extract_detail_images(html)
    if not images:
        return listing
    listing["images"] = images
    listing["main_image"] = images[0]
    return listing


def _parse_card(card, town: str) -> dict[str, Any] | None:
    link_el = card.select_one("a[href*='/comprar/']")
    href = ""
    if link_el:
        href = link_el.get("href") or ""
    if not href:
        href = card.get("data-lnk-href") or ""
    if not href:
        return None
    lower = href.lower()
    if any(marker in lower for marker in ("/piso-", "/apartamento-", "/estudio-", "/atico-", "/ático-", "/duplex-", "/dúplex-")):
        if "/chalet-" not in lower and "/casa-" not in lower and "/casa_" not in lower:
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
    images = _collect_images(card)
    image = images[0] if images else ""

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
            "images": images,
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

    # Detail pages expose the full gallery; enrich listings with few/no photos.
    needs_enrichment = [item for item in collected if len(item.get("images") or []) < 3]
    if needs_enrichment:
        max_workers = min(6, len(needs_enrichment))
        enriched_by_id: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(_enrich_images, dict(item)): item["id"] for item in needs_enrichment}
            for future in as_completed(futures):
                listing_id = futures[future]
                try:
                    enriched_by_id[listing_id] = future.result()
                except Exception:
                    continue
        collected = [enriched_by_id.get(item["id"], item) for item in collected]

    return collected

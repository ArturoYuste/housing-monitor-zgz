"""Idealista ingestion via alert emails (IMAP)."""

from __future__ import annotations

import re
from typing import Any

from scraper.email_inbox import fetch_alert_links, imap_enabled, unique_urls
from scraper.http_client import parse_euro_number
from scraper.portals import normalize_listing

INMUEBLE_ID_RE = re.compile(r"/inmueble/(\d+)", re.I)
PRICE_RE = re.compile(r"(\d{1,3}(?:\.\d{3})+|\d+)\s*€")
SIZE_RE = re.compile(r"(\d{2,4})\s*m(?:2|²)", re.I)


def _infer_fields(subject: str, url: str) -> dict[str, Any]:
    blob = f"{subject} {url}"
    price_match = PRICE_RE.search(subject or "")
    size_match = SIZE_RE.search(subject or "")
    inmueble = INMUEBLE_ID_RE.search(url or "")
    external_id = inmueble.group(1) if inmueble else (url.rstrip("/").split("/")[-1] or "unknown")
    lowered = blob.lower()
    has_garden = any(
        token in lowered
        for token in ("jardin", "jardín", "terreno", "parcela", "patio", "huerto")
    )
    is_chalet = "chalet" in lowered or "adosado" in lowered or "pareado" in lowered
    is_flat = bool(re.search(r"\bpiso\b|\bapartamento\b|\bático\b|\batico\b", lowered))
    return {
        "external_id": external_id,
        "price": parse_euro_number(price_match.group(1)) if price_match else None,
        "size_m2": int(size_match.group(1)) if size_match else None,
        "has_garden": has_garden,
        "has_plot": "terreno" in lowered or "parcela" in lowered,
        "property_type": "flat" if is_flat and not is_chalet else ("chalet" if is_chalet else "house"),
    }


def _guess_location(subject: str, towns: list[str]) -> str:
    lowered = (subject or "").lower()
    for town in towns:
        if town and town.lower() in lowered:
            return town
    return ""


def fetch_listings_from_email(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Read Idealista links from the configured IMAP inbox."""
    if not imap_enabled():
        return []

    config = config or {}
    towns = list(config.get("towns") or config.get("locations") or [])
    links = [link for link in unique_urls(fetch_alert_links(limit=40)) if link.portal == "idealista"]
    listings: list[dict[str, Any]] = []
    for link in links:
        inferred = _infer_fields(link.subject, link.url)
        location = _guess_location(link.subject, towns)
        title = (link.subject or "").strip() or f"Idealista {inferred['external_id']}"
        listings.append(
            normalize_listing(
                {
                    "id": f"idealista-{inferred['external_id']}",
                    "external_id": inferred["external_id"],
                    "title": title[:140],
                    "url": link.url,
                    "description": f"Alerta Idealista por email: {link.subject}",
                    "property_type": inferred["property_type"],
                    "price": inferred["price"],
                    "size_m2": inferred["size_m2"],
                    "has_garden": inferred["has_garden"],
                    "has_plot": inferred["has_plot"],
                    "location": location,
                    "ingestion_source": "email_alert",
                },
                portal="idealista",
            )
        )
    return listings


def fetch_listings(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Public entrypoint used by the multi-portal runner."""
    return fetch_listings_from_email(config)

"""Shared HTTP helpers for portal fetchers."""

from __future__ import annotations

import re
import time
from typing import Any

import httpx

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}


def fetch_html(url: str, *, timeout: float = 25.0, retries: int = 2) -> str:
    """GET an HTML page with browser-like headers and light retries."""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with httpx.Client(
                headers=DEFAULT_HEADERS,
                follow_redirects=True,
                timeout=timeout,
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                return response.text
        except Exception as exc:  # noqa: BLE001 - portal network variance
            last_error = exc
            time.sleep(0.6 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last_error}")


def slugify_town(name: str) -> str:
    """Convert a Spanish town name into a URL slug."""
    table = str.maketrans(
        {
            "á": "a",
            "à": "a",
            "ä": "a",
            "é": "e",
            "è": "e",
            "ë": "e",
            "í": "i",
            "ì": "i",
            "ï": "i",
            "ó": "o",
            "ò": "o",
            "ö": "o",
            "ú": "u",
            "ù": "u",
            "ü": "u",
            "ñ": "n",
            "Á": "a",
            "É": "e",
            "Í": "i",
            "Ó": "o",
            "Ú": "u",
            "Ñ": "n",
        }
    )
    text = (name or "").translate(table).lower().strip()
    cleaned = []
    prev_dash = False
    for char in text:
        if char.isalnum():
            cleaned.append(char)
            prev_dash = False
        elif char in {" ", "-", "_", "/"}:
            if not prev_dash:
                cleaned.append("-")
                prev_dash = True
    return "".join(cleaned).strip("-")


def parse_euro_number(value: Any) -> int | None:
    """Parse values like '174.000 €' or 174000 into int euros."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if hasattr(value, "group"):
        value = value.group(1) if value.lastindex else value.group(0)
    text = str(value).strip()
    match = re.search(r"(\d{1,3}(?:\.\d{3})+|\d+)", text)
    if not match:
        return None
    return int(match.group(1).replace(".", ""))


def feature_map(features: list[dict[str, Any]] | None) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in features or []:
        key = item.get("key")
        if key:
            result[str(key)] = item.get("value")
    return result

"""Fotocasa extractor (HTTP phase — scaffold)."""

from __future__ import annotations

from typing import Any

from scraper.portals import normalize_listing


def fetch_listings(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Fetch Fotocasa listings matching config.

    Live HTTP calls will be implemented in the next ingestion slice.
    Keeping a stable entrypoint avoids rewiring the runner later.
    """
    _ = config
    return []


def example_normalized_listing() -> dict[str, Any]:
    """Shape reference for future HTTP mapping."""
    return normalize_listing(
        {
            "id": "fotocasa-example",
            "title": "Example house",
            "price": 150000,
            "size_m2": 120,
            "plot_m2": 200,
            "has_garden": True,
            "location": "Utebo",
            "url": "https://www.fotocasa.es/es/example",
            "property_type": "house",
        },
        portal="fotocasa",
    )

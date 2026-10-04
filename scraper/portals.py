"""Portal registry and shared listing shape helpers."""

from __future__ import annotations

from typing import Any

SUPPORTED_PORTALS = (
    "idealista",
    "fotocasa",
    "habitaclia",
    "pisos.com",
)


def normalize_listing(raw: dict[str, Any], portal: str) -> dict[str, Any]:
    """Normalize a portal-specific payload into the shared property shape."""
    price = raw.get("price")
    size = raw.get("size_m2")
    price_per_m2 = raw.get("price_per_m2")
    if price_per_m2 is None and price and size:
        price_per_m2 = round(float(price) / float(size))

    listing_id = raw.get("id") or f"{portal}-{raw.get('external_id') or raw.get('url')}"
    return {
        "id": str(listing_id),
        "portal": portal,
        "property_type": raw.get("property_type") or "house",
        "title": raw.get("title") or "Untitled listing",
        "price": price,
        "size_m2": size,
        "plot_m2": raw.get("plot_m2"),
        "price_per_m2": price_per_m2,
        "rooms": raw.get("rooms"),
        "baths": raw.get("baths"),
        "has_garden": bool(raw.get("has_garden")),
        "has_plot": bool(raw.get("has_plot") or (raw.get("plot_m2") or 0) > 0),
        "has_elevator": bool(raw.get("has_elevator")),
        "floor": raw.get("floor"),
        "location": raw.get("location") or "",
        "url": raw.get("url") or "",
        "main_image": raw.get("main_image") or "",
        "description": raw.get("description") or "",
        "date_detected": raw.get("date_detected"),
        "status": raw.get("status") or "pending",
        "user_notes": raw.get("user_notes") or "",
    }

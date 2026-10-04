"""Dynamic filter engine driven by config.json."""

from __future__ import annotations

import re
from typing import Any


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _parse_floor(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).lower()
    if "bajo" in text or "ground" in text:
        return 0
    match = re.search(r"-?\d+", text)
    if not match:
        return None
    return int(match.group())


def matches_filters(property_item: dict[str, Any], config: dict[str, Any]) -> tuple[bool, str]:
    """Return whether a property matches config and a rejection reason."""
    price = property_item.get("price")
    size = property_item.get("size_m2")
    price_per_m2 = property_item.get("price_per_m2")
    if price_per_m2 is None and price and size:
        price_per_m2 = round(price / size)

    min_price = config.get("min_price")
    max_price = config.get("max_price")
    if min_price is not None and price is not None and price < min_price:
        return False, "below_min_price"
    if max_price is not None and price is not None and price > max_price:
        return False, "above_max_price"

    min_size = config.get("min_size_m2")
    if min_size is not None and size is not None and size < min_size:
        return False, "below_min_size"

    max_ppm2 = config.get("max_price_per_m2")
    if max_ppm2 is not None and price_per_m2 is not None and price_per_m2 > max_ppm2:
        return False, "above_max_price_per_m2"

    min_floor = config.get("min_floor")
    floor = _parse_floor(property_item.get("floor"))
    if min_floor is not None and floor is not None and floor < min_floor:
        return False, "below_min_floor"

    if config.get("require_elevator") and not property_item.get("has_elevator"):
        return False, "missing_elevator"

    min_rooms = config.get("min_rooms")
    rooms = property_item.get("rooms")
    if min_rooms is not None and rooms is not None and rooms < min_rooms:
        return False, "below_min_rooms"

    min_baths = config.get("min_baths")
    baths = property_item.get("baths")
    if min_baths is not None and baths is not None and baths < min_baths:
        return False, "below_min_baths"

    haystack = _normalize(
        " ".join(
            [
                str(property_item.get("title", "")),
                str(property_item.get("description", "")),
                str(property_item.get("location", "")),
            ]
        )
    )
    for keyword in config.get("excluded_keywords") or []:
        needle = _normalize(str(keyword))
        if needle and needle in haystack:
            return False, f"excluded_keyword:{keyword}"

    locations = [_normalize(x) for x in (config.get("locations") or []) if str(x).strip()]
    if locations:
        location = _normalize(str(property_item.get("location", "")))
        if not any(loc in location or location in loc for loc in locations):
            return False, "location_not_allowed"

    return True, "ok"


def filter_properties(
    properties: list[dict[str, Any]], config: dict[str, Any]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split properties into accepted and rejected lists."""
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for item in properties:
        ok, reason = matches_filters(item, config)
        if ok:
            accepted.append(item)
        else:
            rejected.append({**item, "reject_reason": reason})
    return accepted, rejected

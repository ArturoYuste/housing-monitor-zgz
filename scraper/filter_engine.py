"""Dynamic filter engine driven by config.json."""

from __future__ import annotations

import re
from typing import Any


HOUSE_TYPE_TOKENS = {
    "house",
    "casa",
    "chalet",
    "villa",
    "adosado",
    "pareado",
    "unifamiliar",
    "countryhouse",
    "semidetachedhouse",
    "terracedhouse",
    "house_chalet",
}

APARTMENT_TYPE_TOKENS = {
    "flat",
    "apartment",
    "piso",
    "apartamento",
    "studio",
    "estudio",
    "loft",
    "attic",
    "penthouse",
    "duplex",  # usually in-building in ES portals
    "dúplex",
}

# URL path fragments that indicate an in-building dwelling.
APARTMENT_URL_MARKERS = (
    "/piso-",
    "/piso/",
    "/apartamento-",
    "/apartamento/",
    "/planta-intermedia/",
    "/atico/",
    "/ático/",
    "/estudio-",
    "/estudio/",
    "/loft-",
    "/loft/",
    "/duplex-",
    "/dúplex-",
)

# Strong text signals of flats in a building (not detached houses).
APARTMENT_TEXT_PATTERNS = (
    r"\bpiso\s+en\b",
    r"\bapartamento\s+en\b",
    r"\bestudio\s+en\b",
    r"\bvivienda\s+en\s+planta\b",
    r"\bplanta\s+(baja|[1-9]\d*|primera|segunda|tercera|cuarta|quinta)\b",
    r"\bcon\s+ascensor\b",
    r"\bgastos\s+de\s+comunidad\b",
    r"\bedificio\s+de\s+viviendas\b",
    r"\bbloque\s+de\s+pisos\b",
    r"\burbanizaci[oó]n\s+de\s+pisos\b",
    r"\bpiso\s+reformado\b",
    r"\bpiso\s+exterior\b",
    r"\bpiso\s+luminoso\b",
)

# Phrases that look apartment-like but are valid for houses/chalets.
HOUSE_EXCEPTION_PATTERNS = (
    r"\bapartamento\s+independiente\b",
    r"\bcasa\s+con\s+apartamento\b",
    r"\bchalet\s+con\s+apartamento\b",
    r"\bsin\s+ascensor\b",
    r"\bplanta\s+baja\s+de\s+(casa|chalet)\b",
)


GARDEN_TOKENS = (
    "jardin",
    "jardín",
    "garden",
    "terreno",
    "parcela",
    "patio",
    "huerto",
    "plot",
    "exterior",
)


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


def _haystack(property_item: dict[str, Any]) -> str:
    return _normalize(
        " ".join(
            [
                str(property_item.get("title", "")),
                str(property_item.get("description", "")),
                str(property_item.get("location", "")),
                str(property_item.get("property_type", "")),
                str(property_item.get("url", "")),
            ]
        )
    )


def _is_apartment_in_building(property_item: dict[str, Any]) -> bool:
    """Detect flats / dwellings inside a multi-unit building."""
    explicit = _normalize(str(property_item.get("property_type", "")))
    if explicit in APARTMENT_TYPE_TOKENS:
        return True

    url = _normalize(str(property_item.get("url", "")))
    if any(marker in url for marker in APARTMENT_URL_MARKERS):
        # Keep casa/chalet URLs that also contain a misleading fragment.
        if not any(token in url for token in ("/casa-", "/casa/", "/chalet-", "/chalet/", "casas_y_chalets")):
            return True

    text = _haystack(property_item)
    if any(re.search(pattern, text) for pattern in HOUSE_EXCEPTION_PATTERNS):
        # Still reject if URL clearly says piso/apartamento.
        if any(marker in url for marker in ("/piso-", "/piso/", "/apartamento-", "/apartamento/")):
            return True
        return False

    if property_item.get("has_elevator") is True and explicit not in HOUSE_TYPE_TOKENS:
        # Elevator is a strong building signal when type is not clearly a house.
        return True

    hits = sum(1 for pattern in APARTMENT_TEXT_PATTERNS if re.search(pattern, text))
    if hits >= 2:
        return True
    if hits >= 1 and explicit and explicit not in HOUSE_TYPE_TOKENS:
        return True

    # Title starting with "Piso ..." is almost always a flat.
    title = _normalize(str(property_item.get("title", "")))
    if title.startswith("piso ") or title.startswith("apartamento ") or title.startswith("estudio "):
        return True

    return False


def _is_house_like(property_item: dict[str, Any], config: dict[str, Any]) -> bool:
    if _is_apartment_in_building(property_item):
        return False

    wanted = {_normalize(x) for x in (config.get("property_types") or []) if str(x).strip()}
    if not wanted:
        wanted = set(HOUSE_TYPE_TOKENS)

    explicit = _normalize(str(property_item.get("property_type", "")))
    if explicit in APARTMENT_TYPE_TOKENS:
        return False
    if explicit and (explicit in wanted or explicit in HOUSE_TYPE_TOKENS):
        return True

    text = _haystack(property_item)
    url = _normalize(str(property_item.get("url", "")))
    url_house = any(token in url for token in ("/casa-", "/casa/", "/chalet-", "/chalet/", "/casas/", "/chalets/"))
    text_house = any(token in text for token in HOUSE_TYPE_TOKENS)
    return bool(url_house or text_house)


def _has_garden_or_plot(property_item: dict[str, Any]) -> bool:
    if property_item.get("has_garden") is True or property_item.get("has_plot") is True:
        return True
    plot_m2 = property_item.get("plot_m2")
    if isinstance(plot_m2, (int, float)) and plot_m2 > 0:
        return True
    text = _haystack(property_item)
    return any(token in text for token in GARDEN_TOKENS)


def matches_filters(property_item: dict[str, Any], config: dict[str, Any]) -> tuple[bool, str]:
    """Return whether a property matches config and a rejection reason."""
    price = property_item.get("price")
    size = property_item.get("size_m2")
    price_per_m2 = property_item.get("price_per_m2")
    if price_per_m2 is None and price and size:
        price_per_m2 = round(price / size)

    if _is_apartment_in_building(property_item):
        return False, "apartment_in_building"

    # Idealista email alerts often lack full structured fields. Keep hard safety
    # checks (not a flat, price cap when known) and skip unknown garden/town/size.
    if str(property_item.get("ingestion_source") or "") == "email_alert":
        if not _is_house_like(property_item, config) and _normalize(
            str(property_item.get("property_type") or "")
        ) not in {"house", "chalet", "casa"}:
            return False, "not_house_like"
        max_price = config.get("max_price")
        if max_price is not None and price is not None and price > max_price:
            return False, "above_max_price"
        min_price = config.get("min_price")
        if min_price is not None and price is not None and price < min_price:
            return False, "below_min_price"
        haystack = _haystack(property_item)
        for keyword in config.get("excluded_keywords") or []:
            needle = _normalize(str(keyword))
            if needle and needle in haystack:
                return False, f"excluded_keyword:{keyword}"
        return True, "ok"

    if not _is_house_like(property_item, config):
        return False, "not_house_like"

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
    if min_floor is not None:
        floor = _parse_floor(property_item.get("floor"))
        if floor is not None and floor < min_floor:
            return False, "below_min_floor"

    # Elevator requirement is for flats; we seek houses, so ignore require_elevator.
    if config.get("require_garden_or_plot") and not _has_garden_or_plot(property_item):
        return False, "missing_garden_or_plot"

    min_rooms = config.get("min_rooms")
    rooms = property_item.get("rooms")
    if min_rooms is not None and rooms is not None and rooms < min_rooms:
        return False, "below_min_rooms"

    min_baths = config.get("min_baths")
    baths = property_item.get("baths")
    if min_baths is not None and baths is not None and baths < min_baths:
        return False, "below_min_baths"

    haystack = _haystack(property_item)
    for keyword in config.get("excluded_keywords") or []:
        needle = _normalize(str(keyword))
        if needle and needle in haystack:
            return False, f"excluded_keyword:{keyword}"

    excluded_locations = [
        _normalize(x) for x in (config.get("excluded_locations") or []) if str(x).strip()
    ]
    location = _normalize(str(property_item.get("location", "")))
    if excluded_locations and any(item in location or location in item for item in excluded_locations):
        return False, "location_excluded"

    # Prefer explicit towns list; fall back to legacy "locations" key.
    towns = [
        _normalize(x)
        for x in (config.get("towns") or config.get("locations") or [])
        if str(x).strip()
    ]
    if towns:
        if not any(town in location or location in town for town in towns):
            return False, "town_not_allowed"

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


def reapply_filters_to_pending(
    properties: list[dict[str, Any]],
    config: dict[str, Any],
) -> tuple[list[dict[str, Any]], int, int]:
    """Keep saved items; discard pending listings that no longer match filters.

    Returns (updated_properties, kept_pending_count, discarded_count).
    """
    kept: list[dict[str, Any]] = []
    discarded_count = 0
    kept_pending = 0
    for item in properties:
        entry = dict(item)
        status = (entry.get("status") or "pending").strip().lower()
        if status in {"saved", "discarded"}:
            kept.append(entry)
            continue
        ok, reason = matches_filters(entry, config)
        if ok:
            entry["status"] = "pending"
            kept.append(entry)
            kept_pending += 1
        else:
            entry["status"] = "discarded"
            entry["is_modified"] = False
            summary = list(entry.get("change_summary") or [])
            note = f"filtrado: {reason}"
            if note not in summary:
                summary = [note] + summary
            entry["change_summary"] = summary[:6]
            kept.append(entry)
            discarded_count += 1
    return kept, kept_pending, discarded_count


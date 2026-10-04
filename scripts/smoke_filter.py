"""Quick smoke checks for the filter engine."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scraper.filter_engine import matches_filters


def main() -> None:
    config = {
        "min_price": 100000,
        "max_price": 300000,
        "min_size_m2": 60,
        "max_price_per_m2": 3200,
        "min_floor": 1,
        "require_elevator": True,
        "min_rooms": 2,
        "min_baths": 1,
        "excluded_keywords": ["okupado"],
        "locations": ["Centro"],
    }
    good = {
        "title": "Nice flat",
        "description": "Renovated",
        "price": 200000,
        "size_m2": 80,
        "price_per_m2": 2500,
        "floor": "3",
        "rooms": 3,
        "baths": 1,
        "has_elevator": True,
        "location": "Centro",
    }
    bad = {**good, "description": "Piso okupado"}
    assert matches_filters(good, config)[0] is True
    assert matches_filters(bad, config)[0] is False
    print("smoke_filter: ok")


if __name__ == "__main__":
    main()

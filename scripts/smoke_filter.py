"""Quick smoke checks for the filter engine."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scraper.filter_engine import matches_filters


def main() -> None:
    config = {
        "property_types": ["house", "chalet"],
        "min_price": 50000,
        "max_price": 180000,
        "min_size_m2": 100,
        "max_price_per_m2": None,
        "require_garden_or_plot": True,
        "min_rooms": 2,
        "min_baths": 1,
        "excluded_keywords": ["okupado"],
        "excluded_locations": ["Centro", "Delicias"],
        "towns": ["Utebo", "Cuarte de Huerva", "Alagón"],
    }
    good = {
        "property_type": "house",
        "title": "Casa con jardin en Utebo",
        "description": "Para reformar integralmente, con terreno",
        "price": 160000,
        "size_m2": 120,
        "plot_m2": 200,
        "rooms": 3,
        "baths": 1,
        "has_garden": True,
        "location": "Utebo",
    }
    city_flat = {
        **good,
        "property_type": "flat",
        "title": "Piso en Centro",
        "location": "Centro",
        "has_garden": False,
        "plot_m2": 0,
    }
    assert matches_filters(good, config)[0] is True
    assert matches_filters(city_flat, config)[0] is False
    print("smoke_filter: ok")


if __name__ == "__main__":
    main()

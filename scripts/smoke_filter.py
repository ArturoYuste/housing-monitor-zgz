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
        "url": "https://www.pisos.com/comprar/casa-utebo-123/",
    }
    city_flat = {
        **good,
        "property_type": "flat",
        "title": "Piso en Centro",
        "location": "Centro",
        "has_garden": False,
        "plot_m2": 0,
        "url": "https://www.pisos.com/comprar/piso-centro-999/",
    }
    building_flat = {
        **good,
        "property_type": "house",  # mislabeled
        "title": "Piso luminoso con ascensor",
        "description": "Piso en planta tercera con ascensor y gastos de comunidad",
        "url": "https://www.fotocasa.es/es/comprar/vivienda/utebo/123/d",
        "has_elevator": True,
    }
    house_with_apartment = {
        **good,
        "title": "Chalet con apartamento independiente",
        "description": "Casa con apartamento independiente y jardin",
        "url": "https://www.fotocasa.es/es/comprar/vivienda/utebo/456/d",
    }
    assert matches_filters(good, config)[0] is True
    assert matches_filters(city_flat, config)[0] is False
    assert matches_filters(building_flat, config)[0] is False
    assert matches_filters(house_with_apartment, config)[0] is True
    print("smoke_filter: ok")


if __name__ == "__main__":
    main()

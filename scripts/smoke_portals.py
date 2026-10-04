"""Smoke test live portal fetchers on a single town."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scraper import fotocasa, habitaclia, pisos
from scraper.http_client import parse_euro_number


def main() -> None:
    assert parse_euro_number("174.000 €") == 174000
    cfg = {"towns": ["Utebo"], "max_price": 180000, "min_size_m2": 100}
    f_items = fotocasa.fetch_listings(cfg)
    h_items = habitaclia.fetch_listings(cfg)
    p_items = pisos.fetch_listings(cfg)
    assert f_items, "Fotocasa returned no listings for Utebo"
    assert h_items, "Habitaclia returned no listings for Utebo"
    assert p_items, "Pisos.com returned no listings for Utebo"
    assert all((item.get("price") or 0) < 10_000_000 for item in h_items)
    print(
        "smoke_portals: ok",
        f"fotocasa={len(f_items)}",
        f"habitaclia={len(h_items)}",
        f"pisos={len(p_items)}",
    )


if __name__ == "__main__":
    main()

"""Smoke test for alert email URL parsing (no network)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scraper.email_inbox import extract_alert_links


def main() -> None:
    body = """
    Nueva vivienda: https://www.idealista.com/inmueble/12345678/
    También mira https://www.fotocasa.es/es/compra/vivienda/utebo/agua/123
    """
    links = extract_alert_links("Alerta Idealista", body, "1")
    portals = {link.portal for link in links}
    assert "idealista" in portals
    assert "fotocasa" in portals
    print("smoke_email_parse: ok")


if __name__ == "__main__":
    main()

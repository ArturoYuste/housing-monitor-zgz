"""Idealista ingestion via alert emails (primary) and future enrichment."""

from __future__ import annotations

from typing import Any

from scraper.email_inbox import fetch_alert_links, imap_enabled, unique_urls
from scraper.portals import normalize_listing


def fetch_listings_from_email() -> list[dict[str, Any]]:
    """Read Idealista links from the configured IMAP inbox.

    Full detail enrichment (price/size/garden) will be added once mailbox access
    is available. For now we return normalized stubs from alert URLs.
    """
    if not imap_enabled():
        return []

    links = [link for link in unique_urls(fetch_alert_links()) if link.portal == "idealista"]
    listings: list[dict[str, Any]] = []
    for link in links:
        external_id = link.url.rstrip("/").split("/")[-1] or link.message_id
        listings.append(
            normalize_listing(
                {
                    "id": f"idealista-{external_id}",
                    "external_id": external_id,
                    "title": link.subject or "Idealista alert listing",
                    "url": link.url,
                    "description": f"Imported from Idealista email alert: {link.subject}",
                    "property_type": "house",
                },
                portal="idealista",
            )
        )
    return listings


def fetch_listings() -> list[dict[str, Any]]:
    """Public entrypoint used by the multi-portal runner."""
    return fetch_listings_from_email()

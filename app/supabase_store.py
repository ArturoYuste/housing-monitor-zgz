"""Optional Supabase persistence (REST). Falls back when not configured."""

from __future__ import annotations

import os
from typing import Any

import httpx


def supabase_enabled() -> bool:
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_KEY"))


class SupabaseStore:
    """Minimal REST client for properties/config tables."""

    def __init__(self) -> None:
        self.base_url = os.getenv("SUPABASE_URL", "").rstrip("/")
        self.api_key = os.getenv("SUPABASE_SERVICE_KEY", "")
        self.properties_table = os.getenv("SUPABASE_PROPERTIES_TABLE", "properties")
        self.config_table = os.getenv("SUPABASE_CONFIG_TABLE", "app_config")

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        }

    def load_properties(self) -> list[dict[str, Any]]:
        url = f"{self.base_url}/rest/v1/{self.properties_table}?select=*"
        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, headers=self._headers())
            response.raise_for_status()
            rows = response.json()
        return [row.get("data", row) for row in rows]

    def save_properties(self, properties: list[dict[str, Any]]) -> None:
        # Upsert each property row keyed by id.
        url = f"{self.base_url}/rest/v1/{self.properties_table}"
        rows = [{"id": item.get("id"), "data": item} for item in properties if item.get("id")]
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, headers=self._headers(), json=rows)
            response.raise_for_status()

    def load_config(self) -> dict[str, Any] | None:
        url = f"{self.base_url}/rest/v1/{self.config_table}?select=data&id=eq.main&limit=1"
        with httpx.Client(timeout=20.0) as client:
            response = client.get(url, headers=self._headers())
            response.raise_for_status()
            rows = response.json()
        if not rows:
            return None
        return rows[0].get("data")

    def save_config(self, config: dict[str, Any]) -> None:
        url = f"{self.base_url}/rest/v1/{self.config_table}"
        payload = [{"id": "main", "data": config}]
        with httpx.Client(timeout=20.0) as client:
            response = client.post(url, headers=self._headers(), json=payload)
            response.raise_for_status()

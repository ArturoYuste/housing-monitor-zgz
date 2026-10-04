"""Optional Supabase persistence (REST). Falls back when not configured."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

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

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.api_key,
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def load_properties(self) -> list[dict[str, Any]]:
        url = f"{self.base_url}/rest/v1/{self.properties_table}?select=id,data"
        with httpx.Client(timeout=30.0) as client:
            response = client.get(url, headers=self._headers())
            response.raise_for_status()
            rows = response.json()
        result: list[dict[str, Any]] = []
        for row in rows:
            data = row.get("data") or {}
            if "id" not in data and row.get("id"):
                data["id"] = row["id"]
            result.append(data)
        return result

    def save_properties(self, properties: list[dict[str, Any]]) -> None:
        """Upsert current properties and delete ids that are no longer present."""
        url = f"{self.base_url}/rest/v1/{self.properties_table}"
        rows = [{"id": item.get("id"), "data": item} for item in properties if item.get("id")]
        keep_ids = {str(row["id"]) for row in rows}

        with httpx.Client(timeout=60.0) as client:
            existing = client.get(
                f"{url}?select=id",
                headers=self._headers(),
            )
            existing.raise_for_status()
            existing_ids = {str(row.get("id")) for row in existing.json() if row.get("id")}
            stale_ids = sorted(existing_ids - keep_ids)

            # Delete stale rows in chunks (PostgREST in. filter).
            for index in range(0, len(stale_ids), 50):
                chunk = stale_ids[index : index + 50]
                if not chunk:
                    continue
                # Use quoted list for ids that may contain special chars.
                encoded = ",".join(quote(item, safe="") for item in chunk)
                delete_url = f"{url}?id=in.({encoded})"
                deleted = client.delete(delete_url, headers=self._headers())
                deleted.raise_for_status()

            if rows:
                upsert = client.post(
                    f"{url}?on_conflict=id",
                    headers=self._headers(prefer="resolution=merge-duplicates,return=minimal"),
                    json=rows,
                )
                upsert.raise_for_status()

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
        url = f"{self.base_url}/rest/v1/{self.config_table}?on_conflict=id"
        payload = [{"id": "main", "data": config}]
        with httpx.Client(timeout=20.0) as client:
            response = client.post(
                url,
                headers=self._headers(prefer="resolution=merge-duplicates,return=minimal"),
                json=payload,
            )
            response.raise_for_status()

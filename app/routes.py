"""HTTP routes for the housing monitor dashboard."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app import storage
from scraper.email_inbox import imap_enabled
from scraper.filter_engine import reapply_filters_to_pending
from scraper.runner import migrate_property_statuses, run_portal_scan

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

STATUSES = [
    ("pending", "Por revisar"),
    ("saved", "Guardados"),
    ("discarded", "Descartados"),
]

DESC_PREVIEW_LEN = 220


def _format_last_sync(value: str | None) -> str:
    if not value:
        return "Aún no actualizado"
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        from datetime import datetime, timezone
        when = datetime.fromisoformat(text)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        local = when.astimezone()
        return local.strftime("Última actualización: %d/%m/%Y %H:%M")
    except Exception:
        return f"Última actualización: {value}"


def _counts(properties: list[dict[str, Any]]) -> dict[str, int]:
    counts = {key: 0 for key, _ in STATUSES}
    for item in properties:
        status = item.get("status") or "pending"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _sorted_for_status(properties: list[dict[str, Any]], status: str) -> list[dict[str, Any]]:
    filtered = [item for item in properties if (item.get("status") or "pending") == status]
    modified = [item for item in filtered if item.get("is_modified")]
    rest = [item for item in filtered if not item.get("is_modified")]
    modified_sorted = sorted(
        modified,
        key=lambda item: item.get("updated_at") or item.get("date_detected") or "",
        reverse=True,
    )
    rest_sorted = sorted(
        rest,
        key=lambda item: item.get("date_detected") or "",
        reverse=True,
    )
    return modified_sorted + rest_sorted


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if text == "":
        return None
    return int(text)


def _load_properties() -> list[dict[str, Any]]:
    properties = migrate_property_statuses(storage.load_properties())
    return properties


def _list_context(
    active: str,
    properties: list[dict[str, Any]] | None = None,
    *,
    swap_tab_counts: bool = False,
) -> dict[str, Any]:
    props = properties if properties is not None else _load_properties()
    return {
        "active_status": active,
        "statuses": STATUSES,
        "counts": _counts(props),
        "properties": _sorted_for_status(props, active),
        "desc_preview_len": DESC_PREVIEW_LEN,
        "swap_tab_counts": swap_tab_counts,
    }


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, status: str = "pending") -> HTMLResponse:
    valid = {key for key, _ in STATUSES}
    active = status if status in valid else "pending"
    properties = _load_properties()
    # Persist migrated statuses if needed.
    if any((p.get("status") in {"favorite", "contacted"}) for p in storage.load_properties()):
        storage.save_properties(properties)
    ctx = _list_context(active, properties)
    ctx["flash"] = request.query_params.get("flash")
    config = storage.load_config()
    ctx["last_sync_label"] = _format_last_sync(config.get("last_sync_at"))
    return templates.TemplateResponse(request, "dashboard.html", ctx)


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    config = storage.load_config()
    portals = [p for p in (config.get("enabled_portals") or []) if p != "idealista"]
    if not portals:
        portals = ["fotocasa", "habitaclia", "pisos.com"]
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "config": config,
            "excluded_keywords_text": "\n".join(config.get("excluded_keywords") or []),
            "excluded_locations_text": ", ".join(config.get("excluded_locations") or []),
            "towns_text": "\n".join(config.get("towns") or config.get("locations") or []),
            "enabled_portals_text": ", ".join(portals),
            "saved": request.query_params.get("saved") == "1",
        },
    )


@router.post("/settings")
async def save_settings(
    province: str = Form("Zaragoza"),
    min_price: int = Form(...),
    max_price: int = Form(...),
    min_size_m2: int = Form(...),
    max_price_per_m2: str = Form(""),
    min_rooms: int = Form(...),
    min_baths: int = Form(...),
    require_garden_or_plot: str | None = Form(None),
    allow_full_renovation: str | None = Form(None),
    search_outside_city: str | None = Form(None),
    excluded_keywords: str = Form(""),
    excluded_locations: str = Form(""),
    towns: str = Form(""),
    enabled_portals: str = Form("fotocasa, habitaclia, pisos.com"),
    scan_max_towns: str = Form(""),
) -> RedirectResponse:
    keywords = [line.strip() for line in excluded_keywords.splitlines() if line.strip()]
    excluded_location_list = [
        part.strip() for part in excluded_locations.replace("\n", ",").split(",") if part.strip()
    ]
    town_list = [line.strip() for line in towns.replace(",", "\n").splitlines() if line.strip()]
    portals = [
        part.strip()
        for part in enabled_portals.split(",")
        if part.strip() and part.strip() != "idealista"
    ]
    storage.save_config(
        {
            "province": province.strip() or "Zaragoza",
            "search_outside_city": search_outside_city == "on",
            "property_types": ["house", "chalet"],
            "min_price": min_price,
            "max_price": max_price,
            "min_size_m2": min_size_m2,
            "max_price_per_m2": _optional_int(max_price_per_m2),
            "min_floor": None,
            "require_elevator": False,
            "require_garden_or_plot": require_garden_or_plot == "on",
            "allow_full_renovation": allow_full_renovation == "on",
            "min_rooms": min_rooms,
            "min_baths": min_baths,
            "excluded_keywords": keywords,
            "excluded_locations": excluded_location_list,
            "towns": town_list,
            "enabled_portals": portals or ["fotocasa", "habitaclia", "pisos.com"],
            "scan_max_towns": _optional_int(scan_max_towns),
        }
    )
    return RedirectResponse(url="/settings?saved=1", status_code=303)


@router.post("/properties/{property_id}/status", response_class=HTMLResponse)
async def update_status(
    request: Request,
    property_id: str,
    status: str = Form(...),
    current_status: str = Form("pending"),
) -> HTMLResponse:
    valid = {key for key, _ in STATUSES}
    if status not in valid:
        status = "pending"
    storage.update_property(property_id, status=status)
    ctx = _list_context(
        current_status if current_status in valid else "pending",
        swap_tab_counts=True,
    )
    return templates.TemplateResponse(request, "partials/property_list.html", ctx)


@router.post("/properties/{property_id}/manage", response_class=HTMLResponse)
async def update_management(
    request: Request,
    property_id: str,
    defects: str = Form(""),
    price_notes: str = Form(""),
    negotiation_notes: str = Form(""),
    current_status: str = Form("saved"),
) -> HTMLResponse:
    storage.update_property(
        property_id,
        defects=defects.strip(),
        price_notes=price_notes.strip(),
        negotiation_notes=negotiation_notes.strip(),
    )
    ctx = _list_context(
        current_status if current_status in {k for k, _ in STATUSES} else "saved",
        swap_tab_counts=True,
    )
    return templates.TemplateResponse(request, "partials/property_list.html", ctx)


@router.post("/scan", response_class=HTMLResponse)
async def run_scan(request: Request) -> HTMLResponse:
    config = storage.load_config()
    result = run_portal_scan(
        existing=_load_properties(),
        config=config,
        catalog_fallback=None,
    )
    storage.save_properties(result["properties"])
    synced_at = result.get("synced_at")
    if synced_at:
        config = dict(config)
        config["last_sync_at"] = synced_at
        config["last_sync_summary"] = {
            "added": result.get("added_count", 0),
            "updated": result.get("modified_count", 0),
            "removed_pending": result.get("removed_pending_count", 0),
        }
        storage.save_config(config)
    properties = migrate_property_statuses(result["properties"])
    by_portal = result.get("by_portal_counts") or {}
    errors = result.get("errors") or {}
    portal_summary = ", ".join(f"{name}={count}" for name, count in by_portal.items())
    errors_summary = "; ".join(f"{name}: {msg}" for name, msg in errors.items())
    ctx = _list_context("pending", properties)
    return templates.TemplateResponse(
        request,
        "partials/scan_result.html",
        {
            **ctx,
            "added_count": result["added_count"],
            "modified_count": result.get("modified_count", 0),
            "removed_pending_count": result.get("removed_pending_count", 0),
            "rejected_count": result["rejected_count"],
            "accepted_count": result["accepted_count"],
            "source": result.get("source", "portals"),
            "imap_enabled": result.get("imap_enabled", False),
            "portal_summary": portal_summary,
            "errors_summary": errors_summary,
            "last_sync_label": _format_last_sync(synced_at),
        },
    )


@router.post("/filters/apply", response_class=HTMLResponse)
async def apply_filters(request: Request) -> HTMLResponse:
    """Re-apply current criteria to pending listings and hide mismatches."""
    config = storage.load_config()
    properties = _load_properties()
    updated, kept_pending, discarded_count = reapply_filters_to_pending(properties, config)
    storage.save_properties(updated)
    properties = migrate_property_statuses(updated)
    ctx = _list_context("pending", properties)
    return templates.TemplateResponse(
        request,
        "partials/filter_apply_result.html",
        {
            **ctx,
            "kept_pending": kept_pending,
            "discarded_count": discarded_count,
        },
    )


@router.post("/filters/apply-redirect")
async def apply_filters_redirect() -> RedirectResponse:
    config = storage.load_config()
    properties = _load_properties()
    updated, kept_pending, discarded_count = reapply_filters_to_pending(properties, config)
    storage.save_properties(updated)
    flash = (
        f"Filtros aplicados: {kept_pending} pendientes se mantienen, "
        f"{discarded_count} descartados."
    )
    return RedirectResponse(url=f"/?status=pending&flash={quote(flash)}", status_code=303)

@router.get("/healthz")
async def health_status() -> dict[str, Any]:
    """Public health + IMAP readiness (never returns secrets)."""
    user_set = bool(os.getenv("IMAP_USER", "").strip())
    password_set = bool(os.getenv("IMAP_PASSWORD", "").strip())
    host = (os.getenv("IMAP_HOST") or "imap.gmail.com").strip()
    folder = (os.getenv("IMAP_FOLDER") or "INBOX").strip()
    enabled = imap_enabled()
    return {
        "status": "ok",
        "imap": {
            "enabled": enabled,
            "configured": bool(enabled and user_set and password_set),
            "user_set": user_set,
            "password_set": password_set,
            "host": host,
            "folder": folder,
            "idealista_active": bool(enabled and user_set and password_set),
        },
    }


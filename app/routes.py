"""HTTP routes for the housing monitor dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app import storage
from scraper.runner import run_demo_scan

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

STATUSES = [
    ("pending", "Pendientes"),
    ("favorite", "Favoritos"),
    ("contacted", "Contactados"),
    ("discarded", "Descartados"),
]


def _counts(properties: list[dict[str, Any]]) -> dict[str, int]:
    counts = {key: 0 for key, _ in STATUSES}
    for item in properties:
        status = item.get("status") or "pending"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _sorted_for_status(properties: list[dict[str, Any]], status: str) -> list[dict[str, Any]]:
    filtered = [item for item in properties if (item.get("status") or "pending") == status]
    return sorted(filtered, key=lambda item: item.get("date_detected") or "", reverse=True)


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, status: str = "pending") -> HTMLResponse:
    valid = {key for key, _ in STATUSES}
    active = status if status in valid else "pending"
    properties = storage.load_properties()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "active_status": active,
            "statuses": STATUSES,
            "counts": _counts(properties),
            "properties": _sorted_for_status(properties, active),
            "flash": request.query_params.get("flash"),
        },
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request) -> HTMLResponse:
    config = storage.load_config()
    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "config": config,
            "excluded_keywords_text": "\n".join(config.get("excluded_keywords") or []),
            "locations_text": ", ".join(config.get("locations") or []),
            "saved": request.query_params.get("saved") == "1",
        },
    )


@router.post("/settings")
async def save_settings(
    min_price: int = Form(...),
    max_price: int = Form(...),
    min_size_m2: int = Form(...),
    max_price_per_m2: int = Form(...),
    min_floor: int = Form(...),
    min_rooms: int = Form(...),
    min_baths: int = Form(...),
    require_elevator: str | None = Form(None),
    excluded_keywords: str = Form(""),
    locations: str = Form(""),
) -> RedirectResponse:
    keywords = [line.strip() for line in excluded_keywords.splitlines() if line.strip()]
    location_list = [part.strip() for part in locations.split(",") if part.strip()]
    storage.save_config(
        {
            "min_price": min_price,
            "max_price": max_price,
            "min_size_m2": min_size_m2,
            "max_price_per_m2": max_price_per_m2,
            "min_floor": min_floor,
            "require_elevator": require_elevator == "on",
            "min_rooms": min_rooms,
            "min_baths": min_baths,
            "excluded_keywords": keywords,
            "locations": location_list,
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
    properties = storage.load_properties()
    return templates.TemplateResponse(
        request,
        "partials/property_list.html",
        {
            "active_status": current_status if current_status in valid else "pending",
            "properties": _sorted_for_status(properties, current_status),
            "statuses": STATUSES,
        },
    )


@router.post("/properties/{property_id}/notes", response_class=HTMLResponse)
async def update_notes(
    request: Request,
    property_id: str,
    user_notes: str = Form(""),
    current_status: str = Form("pending"),
) -> HTMLResponse:
    updated = storage.update_property(property_id, user_notes=user_notes.strip())
    return templates.TemplateResponse(
        request,
        "partials/notes_saved.html",
        {
            "property": updated,
            "active_status": current_status,
        },
    )


@router.post("/scan", response_class=HTMLResponse)
async def run_scan(request: Request) -> HTMLResponse:
    result = run_demo_scan(
        catalog=storage.load_demo_catalog(),
        existing=storage.load_properties(),
        config=storage.load_config(),
    )
    storage.save_properties(result["properties"])
    properties = result["properties"]
    return templates.TemplateResponse(
        request,
        "partials/scan_result.html",
        {
            "added_count": result["added_count"],
            "rejected_count": result["rejected_count"],
            "accepted_count": result["accepted_count"],
            "active_status": "pending",
            "statuses": STATUSES,
            "counts": _counts(properties),
            "properties": _sorted_for_status(properties, "pending"),
        },
    )

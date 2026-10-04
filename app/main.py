"""FastAPI entrypoint for the housing monitor."""

from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes import router
from app.scheduler import start_scheduler
from app.bootstrap import ensure_seed_data


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_seed_data()
    start_scheduler()
    yield


app = FastAPI(title="Housing Monitor", version="0.4.0", lifespan=lifespan)
static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
app.include_router(router)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}

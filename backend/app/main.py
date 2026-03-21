"""FastAPI application entrypoint for media-forge.

This module wires together routing, configuration, and static file
serving for the minimal frontend.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .api.routes_jobs import router as jobs_router
from .core.config import settings


logging.basicConfig(level=logging.INFO)

app = FastAPI(title=settings.project_name)


# In a real production deployment we'd lock this down, but for a
# self-contained demo we allow all origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(jobs_router)


# Serve the minimal frontend from / (index.html, app.js, styles.css).
frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
if frontend_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")


@app.get("/health")
async def health_check() -> dict:
    """Basic health endpoint for orchestration and monitoring."""

    return {"status": "ok"}

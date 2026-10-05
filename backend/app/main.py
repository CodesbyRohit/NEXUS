"""NEXUS backend entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.routes import router
from app.config import settings
from app.graph import client, seed as seeder

log = logging.getLogger("nexus")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Verify the database and seed it on first run."""
    health = client.health()
    if not health["ok"]:
        log.warning("FalkorDB unreachable: %s", health.get("error"))
    else:
        try:
            if not seeder.is_seeded():
                log.info("Graph empty -- seeding synthetic dataset...")
                stats = seeder.seed(reset=False)
                log.info("Seeded %s nodes / %s relationships", stats["nodes"], stats["relationships"])
        except Exception as exc:  # pragma: no cover
            log.warning("Seeding skipped: %s", exc)
    yield


app = FastAPI(
    title="NEXUS",
    description="A graph-native incident commander. FalkorDB is the agent's context and memory.",
    version=__version__,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

# Optionally serve a built frontend (npm run build) from the same origin.
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_DIST / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_DIST / "index.html")


@app.get("/api")
def api_root() -> dict:
    return {
        "name": "NEXUS",
        "version": __version__,
        "docs": "/docs",
        "graph": {"host": settings.falkordb_host, "port": settings.falkordb_port,
                  "graph": settings.graph_name},
    }

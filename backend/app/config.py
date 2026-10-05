"""Runtime configuration for NEXUS.

All configuration is read from the environment (see ``.env.example``).
Nothing here contains secrets; the LLM key is optional and NEXUS runs in a
fully deterministic, graph-grounded mode without it.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# NEXUS/.env  (backend/app/config.py -> parents[2] is the repo root)
REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw) if raw not in (None, "") else default
    except ValueError:
        return default


class Settings:
    """Typed view over the process environment."""

    # --- FalkorDB ---------------------------------------------------------
    falkordb_host: str = os.getenv("FALKORDB_HOST", "localhost")
    falkordb_port: int = _int("FALKORDB_PORT", 6379)
    graph_name: str = os.getenv("FALKORDB_GRAPH", "nexus")

    # --- LLM (optional) ---------------------------------------------------
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    llm_api_key: str = os.getenv("LLM_API_KEY", "").strip()
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini").strip()
    llm_base_url: str = os.getenv("LLM_BASE_URL", "").strip()

    # --- Backend ----------------------------------------------------------
    backend_port: int = _int("BACKEND_PORT", 8000)
    cors_origins: list[str] = [
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if o.strip()
    ]

    @property
    def llm_enabled(self) -> bool:
        """True only when an API key is actually configured."""
        return bool(self.llm_api_key)


settings = Settings()

"""FalkorDB connection management.

A single :class:`falkordb.FalkorDB` client is reused per process. Every graph
access in NEXUS goes through :func:`get_graph` / :func:`run`, so the database
is the one and only source of truth -- there is no in-memory fallback store.
"""

from __future__ import annotations

import contextvars
from typing import Any, Iterable

from falkordb import FalkorDB

from app.config import settings

# Per-request log of executed Cypher, surfaced in the observability panel.
_query_log: contextvars.ContextVar[list[str] | None] = contextvars.ContextVar(
    "nexus_query_log", default=None
)


def start_query_log():
    return _query_log.set([])


def stop_query_log(token) -> list[str]:
    logged = _query_log.get() or []
    _query_log.reset(token)
    return logged


def current_query_log() -> list[str]:
    return list(_query_log.get() or [])


class FalkorDBUnavailable(RuntimeError):
    """Raised when the FalkorDB server cannot be reached."""


_db: FalkorDB | None = None


def get_db() -> FalkorDB:
    global _db
    if _db is None:
        _db = FalkorDB(host=settings.falkordb_host, port=settings.falkordb_port)
    return _db


def reset_db() -> None:
    """Drop the cached client (used by tests)."""
    global _db
    _db = None


def get_graph(name: str | None = None):
    """Return a graph handle by name (defaults to the configured graph)."""
    try:
        return get_db().select_graph(name or settings.graph_name)
    except Exception as exc:  # pragma: no cover - depends on live server
        raise FalkorDBUnavailable(str(exc)) from exc


def run(cypher: str, params: dict[str, Any] | None = None) -> list[list[Any]]:
    """Execute Cypher and return the raw ``result_set`` rows."""
    log = _query_log.get()
    if log is not None:
        log.append(" ".join(cypher.split()))
    try:
        result = get_graph().query(cypher, params or {})
    except Exception as exc:
        raise FalkorDBUnavailable(str(exc)) from exc
    return result.result_set or []


def run_many(statements: Iterable[tuple[str, dict[str, Any] | None]]) -> None:
    for cypher, params in statements:
        run(cypher, params)


def health() -> dict[str, Any]:
    """Ping the graph and report the configured target."""
    try:
        run("RETURN 1")
        return {
            "ok": True,
            "host": settings.falkordb_host,
            "port": settings.falkordb_port,
            "graph": settings.graph_name,
        }
    except FalkorDBUnavailable as exc:
        return {
            "ok": False,
            "host": settings.falkordb_host,
            "port": settings.falkordb_port,
            "graph": settings.graph_name,
            "error": str(exc),
        }


def stats() -> dict[str, Any]:
    """Live node/relationship counts -- never hard-coded."""
    nodes = run("MATCH (n) RETURN count(n)")[0][0]
    rels = run("MATCH ()-[r]->() RETURN count(r)")[0][0]
    by_label = {
        label: count
        for label, count in run(
            "MATCH (n) UNWIND labels(n) AS label RETURN label, count(n) "
            "ORDER BY count(n) DESC"
        )
    }
    by_rel = {
        rel: count
        for rel, count in run(
            "MATCH ()-[r]->() RETURN type(r) AS rel, count(r) ORDER BY count(r) DESC"
        )
    }
    return {
        "nodes": int(nodes),
        "relationships": int(rels),
        "node_labels": by_label,
        "relationship_types": by_rel,
    }


def clear_all() -> None:
    """Delete every node and relationship in the configured graph."""
    run("MATCH (n) DETACH DELETE n")


def delete_graph() -> None:
    get_graph().delete()

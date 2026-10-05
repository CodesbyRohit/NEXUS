"""HTTP routes.

Every endpoint reads from or writes to FalkorDB. There are no fake endpoints
and no hard-coded responses -- the numbers returned are queried live.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.agent import memory as mem
from app.agent import orchestrator as orch
from app.agent import reasoning as R
from app.config import settings
from app.graph import client, schema as S
from app.graph import seed as seeder
from app.graph import tools as T
from app.models import MemoryRequest, QueryRequest, SeedRequest

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, Any]:
    h = client.health()
    h["llm_enabled"] = settings.llm_enabled
    h["llm_provider"] = settings.llm_provider if settings.llm_enabled else None
    h["mode"] = "llm" if settings.llm_enabled else "deterministic"
    return h


@router.get("/graph/stats")
def graph_stats() -> dict[str, Any]:
    try:
        return client.stats()
    except client.FalkorDBUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/schema")
def schema() -> dict[str, Any]:
    return S.schema_document()


@router.get("/tools")
def tools() -> dict[str, Any]:
    return {
        "tools": [
            {"name": t["name"], "description": t["description"], "read_only": t["read_only"]}
            for t in T.TOOL_SPECS
        ]
    }


@router.get("/graph/overview")
def graph_overview(
    focus: str | None = Query(default=None),
    depth: int = Query(default=2, ge=1, le=3),
    limit: int = Query(default=40, ge=5, le=200),
) -> dict[str, Any]:
    try:
        if focus:
            return T.traverse_graph(focus, depth=depth, limit=limit)
        return T.graph_overview(limit=limit)
    except client.FalkorDBUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/graph/subgraph")
def graph_subgraph(ids: str = Query(..., description="Comma separated node ids")) -> dict[str, Any]:
    node_ids = [i.strip() for i in ids.split(",") if i.strip()]
    return T.subgraph(node_ids)


@router.get("/entity/{entity_id}")
def entity(entity_id: str) -> dict[str, Any]:
    node = T.get_node(entity_id)
    if node is None:
        raise HTTPException(status_code=404, detail=f"unknown entity {entity_id}")
    return {
        "node": node,
        "neighborhood": T.traverse_graph(entity_id, depth=1, limit=60),
        "history": T.get_entity_history(entity_id),
        "decisions": mem.decisions_for_entity(entity_id),
        "ownership": T.get_service_ownership(entity_id) if node["label"] == S.SERVICE else None,
        "runbooks": T.get_runbook(entity_id) if node["label"] == S.SERVICE else [],
    }


@router.get("/incidents")
def incidents(limit: int = Query(default=10, ge=1, le=50)) -> dict[str, Any]:
    ranked = R.rank_open_incidents()
    return {"count": len(ranked), "incidents": ranked[:limit]}


@router.post("/query")
def query(req: QueryRequest) -> dict[str, Any]:
    return orch.answer(req.question, req.session_id)


@router.post("/memory")
def memory(req: MemoryRequest) -> dict[str, Any]:
    result = mem.store_memory(req.text, target_id=req.target_id, session_id=req.session_id)
    return {
        "stored": result["event"],
        "target": result["target"],
        "links": result["links"],
        "signal": result["signal"],
    }


@router.get("/decisions")
def decisions(question_key: str | None = None, limit: int = Query(default=20, ge=1, le=100)):
    if question_key:
        return {"decisions": mem.decisions_for(question_key, limit=limit)}
    return {"decisions": mem.recent_decisions(limit=limit)}


@router.get("/mutations")
def mutations(limit: int = Query(default=20, ge=1, le=100)):
    return {"mutations": mem.graph_mutations(limit=limit)}


@router.post("/seed")
def seed(req: SeedRequest) -> dict[str, Any]:
    """(Re)build the synthetic dataset. Development / demo helper."""
    return seeder.seed(reset=req.reset)

"""Graph tools -- the agent's only way to learn facts.

Each function is a thin, well-typed wrapper over Cypher. The agent never
receives facts from the LLM; it receives them from these functions and the
LLM (when configured) is only allowed to *narrate* what these return.

Only tools that are really implemented are exposed (see :data:`TOOL_SPECS`).
"""

from __future__ import annotations

from typing import Any

from app.graph import client, schema as S


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _name_of(props: dict[str, Any], fallback: str) -> str:
    for key in ("name", "title", "summary", "description"):
        if props.get(key):
            return str(props[key])
    return fallback


def node_dict(label: str, node_id: str, props: dict[str, Any] | None) -> dict[str, Any]:
    props = dict(props or {})
    return {
        "id": node_id,
        "label": label,
        "name": _name_of(props, node_id),
        "props": props,
    }


def get_node(node_id: str) -> dict[str, Any] | None:
    rows = client.run(
        "MATCH (n {id: $id}) RETURN labels(n), n.id, properties(n) LIMIT 1",
        {"id": node_id},
    )
    if not rows:
        return None
    labels, nid, props = rows[0]
    return node_dict((labels or ["Unknown"])[0], nid, props)


def require_node(node_id: str) -> dict[str, Any]:
    node = get_node(node_id)
    if node is None:
        raise LookupError(f"No node with id={node_id!r} in the graph")
    return node


# ---------------------------------------------------------------------------
# Read tools
# ---------------------------------------------------------------------------

def search_graph(query: str, labels: list[str] | None = None, limit: int = 20) -> list[dict]:
    """Case-insensitive substring search over human-readable node fields."""
    q = (query or "").strip().lower()
    if not q:
        return []
    rows = client.run(
        """
        MATCH (n)
        WHERE toLower(coalesce(n.name, '')) CONTAINS $q
           OR toLower(coalesce(n.title, '')) CONTAINS $q
           OR toLower(coalesce(n.summary, '')) CONTAINS $q
           OR toLower(n.id) CONTAINS $q
        RETURN labels(n), n.id, properties(n)
        LIMIT $limit
        """,
        {"q": q, "limit": limit},
    )
    out = [
        node_dict((labels_ or ["Unknown"])[0], nid, props)
        for labels_, nid, props in rows
    ]
    if labels:
        wanted = set(labels)
        out = [n for n in out if n["label"] in wanted]
    return out


def get_entity_history(node_id: str, limit: int = 15) -> list[dict]:
    """Events, incidents and decisions directly connected to an entity."""
    rows = client.run(
        """
        MATCH (n {id: $id})-[r]-(m)
        WHERE m.kind IN ['incident', 'event', 'decision', 'action']
        RETURN type(r), labels(m), m.id,
               coalesce(m.title, m.summary, m.question, m.description, m.id) AS text,
               coalesce(m.at, m.started_at) AS at,
               coalesce(m.severity, m.status, m.kind) AS status
        ORDER BY at DESC
        LIMIT $limit
        """,
        {"id": node_id, "limit": limit},
    )
    return [
        {"rel": rel, "label": (labs or ["Unknown"])[0], "id": mid,
         "text": text, "at": at, "status": status}
        for rel, labs, mid, text, at, status in rows
    ]


def traverse_graph(
    start_id: str,
    rels: list[str] | None = None,
    direction: str = "both",
    depth: int = 2,
    limit: int = 150,
) -> dict[str, Any]:
    """Generic bounded traversal returning nodes and edges for visualisation."""
    pattern_dir = {"out": "->", "in": "<-", "both": "-"}.get(direction, "-")
    rel_expr = f":{'|'.join(rels)}" if rels else ""
    depth = max(1, min(int(depth), 4))
    cypher = (
        f"MATCH (s {{id: $id}}) "
        f"MATCH (s){_path_pattern(pattern_dir, rel_expr, depth)}(m) "
        f"RETURN DISTINCT m.id, labels(m), properties(m) LIMIT $limit"
    )
    rows = client.run(cypher, {"id": start_id, "limit": limit})
    nodes = {start_id: get_node(start_id)}
    ids = set(nodes.keys())
    for labels_, mid, props in rows:
        nodes[mid] = node_dict((labels_ or ["Unknown"])[0], mid, props)
        ids.add(mid)

    edges = edges_among(ids)
    return {"nodes": [n for n in nodes.values() if n], "edges": edges}


def _path_pattern(direction: str, rel_expr: str, depth: int) -> str:
    if direction == "out":
        return f"-[{rel_expr}*1..{depth}]->"
    if direction == "in":
        return f"<-[{rel_expr}*1..{depth}]-"
    return f"-[{rel_expr}*1..{depth}]-"


def edges_among(ids: set[str], limit: int = 400) -> list[dict]:
    if not ids:
        return []
    rows = client.run(
        """
        MATCH (a)-[r]->(b)
        WHERE a.id IN $ids AND b.id IN $ids
        RETURN a.id, type(r), b.id, properties(r)
        LIMIT $limit
        """,
        {"ids": list(ids), "limit": limit},
    )
    return [
        {"source": s, "rel": rel, "target": t, "props": dict(props or {})}
        for s, rel, t, props in rows
    ]


def find_dependencies(service_id: str, depth: int = 3) -> dict[str, Any]:
    """Everything the service depends on (downstream), with evidence."""
    depth = max(1, min(int(depth), 4))
    rows = client.run(
        f"""
        MATCH p = (s {{id: $id}})-[:DEPENDS_ON*1..{depth}]->(d)
        RETURN d.id, labels(d), properties(d), length(p) AS hops
        ORDER BY hops ASC
        LIMIT 100
        """,
        {"id": service_id},
    )
    best: dict[str, dict] = {}
    for did, labs, props, hops in rows:
        if did == service_id:
            continue
        if did not in best or hops < best[did]["hops"]:
            best[did] = {**node_dict((labs or ["Unknown"])[0], did, props), "hops": hops}
    deps = sorted(best.values(), key=lambda d: (d["hops"], d["id"]))
    return {"entity": service_id, "dependencies": deps, "count": len(deps)}


def find_dependents(service_id: str, depth: int = 3) -> dict[str, Any]:
    """Services that depend on this one (upstream blast radius)."""
    depth = max(1, min(int(depth), 4))
    rows = client.run(
        f"""
        MATCH p = (u)-[:DEPENDS_ON*1..{depth}]->(s {{id: $id}})
        WHERE u:Service
        RETURN DISTINCT u.id, properties(u), length(p) AS hops
        ORDER BY hops ASC
        LIMIT 100
        """,
        {"id": service_id},
    )
    dependents = [
        {**node_dict("Service", uid, props), "hops": hops}
        for uid, props, hops in rows
    ]
    return {"entity": service_id, "dependents": dependents, "count": len(dependents)}


def find_related_incidents(service_id: str, limit: int = 10) -> list[dict]:
    """Incidents that touched a service or anything it depends on."""
    seen: dict[str, dict] = {}
    # 1) incidents whose blast radius is the entity itself
    direct = client.run(
        """
        MATCH (i:Incident)-[:AFFECTS]->(e {id: $id})
        RETURN i.id, i.title, i.status, i.severity,
               coalesce(i.started_at, '') AS started_at
        """,
        {"id": service_id},
    )
    for iid, title, status, sev, started in direct:
        seen[iid] = {"id": iid, "title": title, "status": status,
                     "severity": sev, "started_at": started, "via": service_id}
    # 2) incidents that hit anything depending on the entity (upstream blast radius)
    upstream = client.run(
        """
        MATCH (u:Service)-[:DEPENDS_ON*1..2]->(s {id: $id})
        MATCH (i:Incident)-[:AFFECTS]->(u)
        RETURN DISTINCT i.id, i.title, i.status, i.severity,
               coalesce(i.started_at, '') AS started_at, u.id
        """,
        {"id": service_id},
    )
    for iid, title, status, sev, started, via in upstream:
        seen.setdefault(iid, {"id": iid, "title": title, "status": status,
                              "severity": sev, "started_at": started, "via": via})
    out = sorted(seen.values(), key=lambda x: x["started_at"], reverse=True)
    return out[:limit]


def find_root_causes(incident_id: str) -> dict[str, Any]:
    """Derive candidate root causes from the incident's graph neighbourhood."""
    inc = require_node(incident_id)
    affected = client.run(
        "MATCH (i:Incident {id: $id})-[:AFFECTS]->(e) RETURN e.id, labels(e), properties(e)",
        {"id": incident_id},
    )
    affected_nodes = [node_dict((l or ["Unknown"])[0], i, p) for i, l, p in affected]

    candidates: list[dict] = []
    for node in affected_nodes:
        if node["label"] != S.SERVICE:
            continue
        # Deepest dependencies (the usual suspects for cascading failures).
        deps = client.run(
            """
            MATCH p = (s {id: $id})-[:DEPENDS_ON*1..3]->(d)
            RETURN d.id, labels(d), properties(d), length(p) AS hops
            ORDER BY hops ASC
            LIMIT 60
            """,
            {"id": node["id"]},
        )
        for did, labs, props, hops in deps:
            if did == node["id"]:
                continue
            label = (labs or ["Unknown"])[0]
            # Deep dependencies and datastores are the classic root causes.
            weight = (20 - hops * 3) + (5 if label == S.DATABASE else 0)
            candidates.append({
                "id": did, "label": label, "name": _name_of(dict(props or {}), did),
                "hops": hops, "weight": weight,
                "reason": f"{node['name']} depends on {_name_of(dict(props or {}), did)} ({hops} hop(s) away)",
            })

    # Events that triggered the incident are strong root-cause signal.
    events = client.run(
        """
        MATCH (e:Event)-[:TRIGGERED]->(i:Incident {id: $id})
        RETURN e.id, e.summary, e.severity, coalesce(e.value,0), coalesce(e.unit,'')
        ORDER BY e.severity DESC LIMIT 6
        """,
        {"id": incident_id},
    )
    for eid, summary, sev, value, unit in events:
        candidates.append({
            "id": eid, "label": S.EVENT, "name": summary or eid,
            "weight": 12 if sev == "critical" else 4,
            "reason": f"triggering event ({sev}); observed value {value}{unit}",
        })

    # Merge duplicates (an entity can be reached by several paths).
    merged: dict[str, dict] = {}
    for c in candidates:
        prev = merged.get(c["id"])
        if prev is None or c["weight"] > prev["weight"]:
            merged[c["id"]] = c
    ranked = sorted(merged.values(), key=lambda c: (-c["weight"], c["id"]))
    return {"incident": inc["name"], "candidates": ranked[:8]}


def get_service_ownership(service_id: str) -> dict[str, Any]:
    team = client.run(
        "MATCH (t:Team)-[:OWNS]->(s {id: $id}) RETURN t.id, t.name, t.slack LIMIT 1",
        {"id": service_id},
    )
    oncall = client.run(
        "MATCH (p:Person)-[:ON_CALL]->(s {id: $id}) RETURN p.id, p.name, coalesce(p.email,'') LIMIT 5",
        {"id": service_id},
    )
    members = client.run(
        """
        MATCH (t:Team)-[:OWNS]->(s {id: $id})<-[:MEMBER_OF]-(p:Person)
        RETURN p.id, p.name, coalesce(p.role, '') LIMIT 20
        """,
        {"id": service_id},
    )
    return {
        "service": service_id,
        "team": ({"id": team[0][0], "name": team[0][1], "slack": team[0][2]} if team else None),
        "on_call": [{"id": r[0], "name": r[1], "email": r[2]} for r in oncall],
        "members": [{"id": r[0], "name": r[1], "role": r[2]} for r in members],
    }


def get_runbook(service_id: str) -> list[dict]:
    rows = client.run(
        """
        MATCH (s {id: $id})-[:DOCUMENTED_BY]->(r:Runbook)
        OPTIONAL MATCH (r)-[:TARGETS]->(t)
        RETURN r.id, r.title, coalesce(r.steps,0), collect(DISTINCT t.id)
        """,
        {"id": service_id},
    )
    return [
        {"id": rid, "title": title, "steps": steps, "targets": targets}
        for rid, title, steps, targets in rows
    ]


def business_impact(entity_id: str, depth: int = 2) -> dict[str, Any]:
    """Traverse to the business outcomes an entity (transitively) affects."""
    rows = client.run(
        """
        MATCH p = (s {id: $id})-[:SUPPORTS|DEPENDS_ON|IMPACTS|PART_OF*1..3]->(im:Impact)
        RETURN DISTINCT im.id, im.name, im.severity, coalesce(im.annual_exposure_usd, 0),
               length(p) AS hops
        ORDER BY hops ASC LIMIT 20
        """,
        {"id": entity_id, "depth": depth},
    )
    best: dict[str, dict] = {}
    for iid, name, sev, exp, hops in rows:
        if iid not in best or hops < best[iid]["hops"]:
            best[iid] = {"id": iid, "name": name, "severity": sev,
                         "annual_exposure_usd": exp, "hops": hops}
    impacts = sorted(best.values(), key=lambda x: (x["hops"], x["id"]))
    return {"entity": entity_id, "impacts": impacts}


def historical_precedents(incident_id: str, limit: int = 5) -> list[dict]:
    """Past incidents connected by PRECEDED/FOLLOWED/RELATED_TO or shared blast radius."""
    rows = client.run(
        """
        MATCH (i:Incident {id: $id})-[:PRECEDED|FOLLOWED|RELATED_TO]-(prev:Incident)
        RETURN DISTINCT prev.id, prev.title, prev.status, prev.severity,
               coalesce(prev.started_at, '') AS started_at
        ORDER BY started_at ASC LIMIT $limit
        """,
        {"id": incident_id, "limit": limit},
    )
    out = [
        {"id": i, "title": t, "status": s, "severity": sev, "started_at": at}
        for i, t, s, sev, at in rows
    ]
    # What those precedents caused (business impact), pulled from the graph.
    for p in out:
        caused = client.run(
            """
            MATCH (prev:Incident {id: $id})-[r:CAUSED]->(im:Impact)
            RETURN im.id, im.name, coalesce(r.amount_usd, 0), coalesce(r.note, '')
            """,
            {"id": p["id"]},
        )
        p["caused"] = [
            {"id": i, "name": n, "amount_usd": a, "note": note}
            for i, n, a, note in caused
        ]
    return out


# ---------------------------------------------------------------------------
# Overview / visualisation
# ---------------------------------------------------------------------------

def graph_overview(limit: int = 30) -> dict[str, Any]:
    """Highest-degree nodes plus the edges between them (for the UI)."""
    rows = client.run(
        """
        MATCH (n)-[r]-()
        RETURN n.id, labels(n), properties(n), count(r) AS degree
        ORDER BY degree DESC LIMIT $limit
        """,
        {"limit": limit},
    )
    nodes = [node_dict((l or ["Unknown"])[0], i, p) for i, l, p, _d in rows]
    ids = {n["id"] for n in nodes}
    return {"nodes": nodes, "edges": edges_among(ids, limit=200)}


def subgraph(node_ids: list[str]) -> dict[str, Any]:
    nodes = [n for n in (get_node(i) for i in node_ids) if n]
    ids = {n["id"] for n in nodes}
    return {"nodes": nodes, "edges": edges_among(ids)}


# ---------------------------------------------------------------------------
# Tool registry (only implemented tools are advertised to the agent)
# ---------------------------------------------------------------------------

TOOL_SPECS: list[dict[str, Any]] = [
    {"name": "search_graph", "description": "Search entities by name/title/id.",
     "read_only": True, "fn": search_graph},
    {"name": "get_node", "description": "Fetch a single entity and its properties.",
     "read_only": True, "fn": get_node},
    {"name": "get_entity_history", "description": "Events/incidents/decisions touching an entity.",
     "read_only": True, "fn": get_entity_history},
    {"name": "traverse_graph", "description": "Bounded multi-hop traversal around a node.",
     "read_only": True, "fn": traverse_graph},
    {"name": "find_dependencies", "description": "Downstream dependencies of a service.",
     "read_only": True, "fn": find_dependencies},
    {"name": "find_dependents", "description": "Upstream services that depend on a service.",
     "read_only": True, "fn": find_dependents},
    {"name": "find_related_incidents", "description": "Incidents touching a service or its deps.",
     "read_only": True, "fn": find_related_incidents},
    {"name": "find_root_causes", "description": "Graph-derived root-cause candidates.",
     "read_only": True, "fn": find_root_causes},
    {"name": "get_service_ownership", "description": "Owning team and on-call engineers.",
     "read_only": True, "fn": get_service_ownership},
    {"name": "get_runbook", "description": "Runbooks documented for a service.",
     "read_only": True, "fn": get_runbook},
    {"name": "business_impact", "description": "Business outcomes reachable from an entity.",
     "read_only": True, "fn": business_impact},
    {"name": "historical_precedents", "description": "Prior incidents linked to an incident.",
     "read_only": True, "fn": historical_precedents},
]

TOOL_NAMES = [t["name"] for t in TOOL_SPECS]

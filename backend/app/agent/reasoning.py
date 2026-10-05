"""Graph-grounded reasoning.

Facts are retrieved from FalkorDB, a transparent policy turns facts into a
priority + recommendation, and an evidence path explains *why* using the exact
edges that were traversed. No fact here is invented by a language model.
"""

from __future__ import annotations

from typing import Any

from app.graph import client, schema as S
from app.graph import tools as T

# ---------------------------------------------------------------------------
# Policy configuration (thresholds are explicit and tunable)
# ---------------------------------------------------------------------------

POLICY: dict[str, Any] = {
    "criticality_score": {"critical": 40, "high": 25, "medium": 10, "low": 3},
    "tx_score_cap": 30,
    "tx_per_10k": 1.0,          # +1 point per 10k transactions/hour (capped)
    "historical_revenue_score": 20,
    "blast_radius_score": 10,    # awarded at >= 3 dependent services
    "blast_radius_min": 3,
    "traffic_score": {"high": 20, "medium": 8},
    "traffic_high_pct": 25.0,
    "traffic_medium_pct": 10.0,
    "thresholds": {"critical": 85, "high": 65, "medium": 40},
}


def _prio_from_score(score: float) -> str:
    t = POLICY["thresholds"]
    if score >= t["critical"]:
        return "CRITICAL"
    if score >= t["high"]:
        return "HIGH"
    if score >= t["medium"]:
        return "MEDIUM"
    return "LOW"


# ---------------------------------------------------------------------------
# Fact gathering (all facts come from Cypher)
# ---------------------------------------------------------------------------

def _apis_supported_by(service_ids: list[str]) -> list[dict]:
    if not service_ids:
        return []
    rows = client.run(
        """
        MATCH (s:Service)-[:SUPPORTS]->(api:API)
        WHERE s.id IN $ids
        RETURN DISTINCT api.id, api.name, api.tx_per_hour, api.criticality, s.id
        """,
        {"ids": service_ids},
    )
    return [
        {"id": i, "label": S.API, "name": n, "tx_per_hour": tx,
         "criticality": crit, "via_service": s}
        for i, n, tx, crit, s in rows
    ]


def traffic_events() -> list[dict]:
    """All traffic-shift events plus the entity they affect (written by memory)."""
    rows = client.run(
        """
        MATCH (e:Event {kind: 'traffic_shift'})-[:AFFECTS]->(t)
        RETURN e.id, coalesce(e.value, 0), coalesce(e.unit, ''), e.summary, t.id
        ORDER BY e.at DESC
        """
    )
    return [
        {"id": eid, "value": val, "unit": unit, "summary": summary, "target": tid}
        for eid, val, unit, summary, tid in rows
    ]


def gather_incident_facts(incident_id: str) -> dict[str, Any]:
    inc = T.require_node(incident_id)
    affected = client.run(
        "MATCH (i:Incident {id: $id})-[:AFFECTS]->(e) RETURN e.id, labels(e), properties(e)",
        {"id": incident_id},
    )
    affected_nodes = [T.node_dict((l or ["Unknown"])[0], i, p) for i, l, p in affected]
    services = [n for n in affected_nodes if n["label"] == S.SERVICE]
    primary = max(services, key=lambda s: s["props"].get("tx_per_hour", 0)) if services else None

    dependencies: list[dict] = []
    dependents: list[dict] = []
    exposed_apis: list[dict] = []
    if primary:
        dependencies = T.find_dependencies(primary["id"], depth=2)["dependencies"]
        dependents = T.find_dependents(primary["id"], depth=2)["dependents"]
        exposed_apis = _apis_supported_by([primary["id"]] + [d["id"] for d in dependents])

    impacts: list[dict] = []
    for node in affected_nodes:
        impacts.extend(T.business_impact(node["id"], depth=3)["impacts"])
    for api in exposed_apis:
        impacts.extend(T.business_impact(api["id"], depth=3)["impacts"])
    dedup: dict[str, dict] = {}
    for im in impacts:
        if im["id"] not in dedup or im["hops"] < dedup[im["id"]]["hops"]:
            dedup[im["id"]] = im
    impacts = sorted(dedup.values(), key=lambda x: (-x.get("annual_exposure_usd", 0), x["id"]))

    precedents = T.historical_precedents(incident_id)
    precedent_revenue = None
    for p in precedents:
        for c in p.get("caused", []):
            if c.get("amount_usd", 0) > 0 and c["id"] == "impact-revenue":
                precedent_revenue = {"incident": p["id"], "incident_title": p["title"],
                                     "amount_usd": c["amount_usd"]}
    if precedent_revenue is None:
        # fall back to any precedent that caused financial loss
        for p in precedents:
            for c in p.get("caused", []):
                if c.get("amount_usd", 0) > 0:
                    precedent_revenue = {"incident": p["id"], "incident_title": p["title"],
                                         "amount_usd": c["amount_usd"]}
                    break
            if precedent_revenue:
                break

    blast_ids = {primary["id"]} if primary else set()
    blast_ids |= {d["id"] for d in dependents}
    blast_ids |= {a["id"] for a in exposed_apis}
    blast_ids |= {n["id"] for n in affected_nodes}
    matched_traffic = [e for e in traffic_events() if e["target"] in blast_ids]

    return {
        "incident": inc,
        "affected": affected_nodes,
        "primary_service": primary,
        "criticality": (primary or {}).get("props", {}).get("criticality"),
        "tx_per_hour": (primary or {}).get("props", {}).get("tx_per_hour", 0),
        "dependencies": dependencies,
        "dependents": dependents,
        "exposed_apis": exposed_apis,
        "impacts": impacts,
        "precedents": precedents,
        "precedent_revenue": precedent_revenue,
        "root_causes": T.find_root_causes(incident_id)["candidates"],
        "traffic_events": matched_traffic,
        "blast_radius_count": len(dependents),
    }


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

def apply_policy(facts: dict[str, Any]) -> dict[str, Any]:
    """Turn graph facts into a priority + recommendation. Fully deterministic."""
    score = 0.0
    factors: list[dict] = []

    crit = facts.get("criticality")
    if crit:
        w = POLICY["criticality_score"].get(crit, 0)
        if w:
            score += w
            factors.append({"factor": "service_criticality", "detail": f"Affected service is {crit}", "weight": w})

    tx = facts.get("tx_per_hour", 0) or 0
    tx_score = min(POLICY["tx_score_cap"], (tx / 10000.0) * POLICY["tx_per_10k"])
    if tx_score:
        score += tx_score
        factors.append({
            "factor": "transaction_volume",
            "detail": f"Affected service handles {tx:,} transactions/hour",
            "weight": round(tx_score, 1),
        })

    if facts.get("precedent_revenue"):
        w = POLICY["historical_revenue_score"]
        score += w
        pr = facts["precedent_revenue"]
        factors.append({
            "factor": "historical_precedent",
            "detail": f"{pr['incident']} involving the same dependency caused ${pr['amount_usd']:,} in revenue loss",
            "weight": w,
        })

    if facts.get("blast_radius_count", 0) >= POLICY["blast_radius_min"]:
        w = POLICY["blast_radius_score"]
        score += w
        factors.append({
            "factor": "blast_radius",
            "detail": f"{facts['blast_radius_count']} downstream services depend on the affected service",
            "weight": w,
        })

    traffic_max = 0.0
    for e in facts.get("traffic_events", []):
        if e.get("unit") == "percent":
            traffic_max = max(traffic_max, float(e.get("value") or 0))
    if traffic_max >= POLICY["traffic_high_pct"]:
        w = POLICY["traffic_score"]["high"]
        score += w
        factors.append({
            "factor": "traffic_shift",
            "detail": f"Traffic on the transaction path increased {traffic_max:g}% (graph event)",
            "weight": w,
        })
    elif traffic_max >= POLICY["traffic_medium_pct"]:
        w = POLICY["traffic_score"]["medium"]
        score += w
        factors.append({
            "factor": "traffic_shift",
            "detail": f"Traffic on the transaction path increased {traffic_max:g}% (graph event)",
            "weight": w,
        })

    priority = _prio_from_score(score)
    confidence = min(0.96, 0.62 + 0.07 * len(factors) + 0.03 * len(facts.get("precedents", [])))
    return {
        "score": round(score, 1),
        "priority": priority,
        "recommend_human_review": priority == "CRITICAL",
        "risk_factors": factors,
        "confidence": round(confidence, 2),
        "policy_version": "nexus-policy/1.0",
    }


def assess_incident(incident_id: str) -> dict[str, Any]:
    facts = gather_incident_facts(incident_id)
    decision = apply_policy(facts)
    return {"facts": facts, "decision": decision}


def open_incidents() -> list[str]:
    rows = client.run(
        "MATCH (i:Incident) WHERE i.status IN ['open', 'investigating'] RETURN i.id"
    )
    return [r[0] for r in rows]


def rank_open_incidents() -> list[dict[str, Any]]:
    """Assess every unresolved incident and rank by the policy score."""
    ranked = []
    for iid in open_incidents():
        try:
            a = assess_incident(iid)
        except LookupError:
            continue
        ranked.append({
            "id": iid,
            "title": a["facts"]["incident"]["name"],
            "status": a["facts"]["incident"]["props"].get("status"),
            "severity": a["facts"]["incident"]["props"].get("severity"),
            "service": (a["facts"]["primary_service"] or {}).get("id"),
            "service_name": (a["facts"]["primary_service"] or {}).get("name"),
            "score": a["decision"]["score"],
            "priority": a["decision"]["priority"],
            "confidence": a["decision"]["confidence"],
            "risk_factors": a["decision"]["risk_factors"],
        })
    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked


# ---------------------------------------------------------------------------
# Evidence path
# ---------------------------------------------------------------------------

def build_evidence_path(incident_id: str, facts: dict[str, Any] | None = None) -> dict[str, Any]:
    """Produce the ordered, graph-derived causal path for an incident."""
    facts = facts or gather_incident_facts(incident_id)
    inc = facts["incident"]
    hops: list[dict] = []
    nodes: dict[str, dict] = {inc["id"]: inc}
    edges: list[dict] = []

    def hop(src: dict, rel: str, dst: dict, why: str) -> None:
        hops.append({
            "from": {"id": src["id"], "label": src["label"], "name": src["name"]},
            "rel": rel,
            "to": {"id": dst["id"], "label": dst["label"], "name": dst["name"]},
            "why": why,
        })
        nodes[src["id"]] = src
        nodes[dst["id"]] = dst
        edges.append({"source": src["id"], "rel": rel, "target": dst["id"], "props": {}})

    # 1. The incident affects its targets (service / database).
    for node in facts["affected"]:
        why = "incident blast radius"
        if node["label"] == S.SERVICE:
            why = f"affected service (criticality={node['props'].get('criticality')})"
        hop(inc, S.AFFECTS, node, why)

    primary = facts["primary_service"]
    if primary:
        # 2. The affected service's critical dependencies.
        for dep in sorted(
            facts["dependencies"],
            key=lambda d: (0 if d["label"] == S.DATABASE else 1, d["hops"]),
        )[:3]:
            hop(primary, S.DEPENDS_ON, dep,
                f"{dep['label'].lower()} dependency {dep['hops']} hop(s) away")
        # 3. Blast radius: services that depend on the affected service.
        for dep in sorted(facts["dependents"], key=lambda d: d["hops"])[:3]:
            hop(dep, S.DEPENDS_ON, primary,
                f"{dep['name']} depends on the affected service (handles "
                f"{dep['props'].get('tx_per_hour', 0):,} tx/hour)")

    # 4. Exposed APIs and the business outcomes they reach.
    for api in facts["exposed_apis"][:4]:
        hop({"id": api["via_service"], "label": S.SERVICE, "name": api["via_service"]},
            S.SUPPORTS, api, "public contract on the transaction path")
        for im in facts["impacts"][:2]:
            hop(api, S.IMPACTS, {"id": im["id"], "label": S.IMPACT, "name": im["name"]},
                f"business impact (severity={im['severity']})")

    # 5. Historical precedent that caused real impact.
    for p in facts["precedents"][:3]:
        if p["id"] != inc["id"]:
            hop({"id": p["id"], "label": S.INCIDENT, "name": p["title"]},
                S.RELATED_TO, inc, f"historical precedent ({p['status']})")
        for c in p.get("caused", []):
            if c.get("amount_usd", 0) > 0:
                hop({"id": p["id"], "label": S.INCIDENT, "name": p["title"]},
                    S.CAUSED, {"id": c["id"], "label": S.IMPACT, "name": c["name"]},
                    f"caused ${c['amount_usd']:,} impact")

    # 6. Newly written traffic evidence (memory) if present.
    for e in facts.get("traffic_events", []):
        target = nodes.get(e["target"]) or T.get_node(e["target"])
        if target is None:
            continue
        hop({"id": e["id"], "label": S.EVENT, "name": e["summary"]},
            S.AFFECTS, target, f"new graph evidence: {e['value']:g}{e['unit']}")

    # De-duplicate edges for the visualiser.
    seen = set()
    unique_edges = []
    for e in edges:
        key = (e["source"], e["rel"], e["target"])
        if key not in seen:
            seen.add(key)
            unique_edges.append(e)

    return {
        "incident": {"id": inc["id"], "name": inc["name"]},
        "hops": hops,
        "nodes": list(nodes.values()),
        "edges": unique_edges,
    }


def compare_assessments(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Diff two assessments to explain what changed and why."""
    b_decision, a_decision = before["decision"], after["decision"]
    b_factor_names = {f["factor"] for f in b_decision["risk_factors"]}
    a_factor_names = {f["factor"] for f in a_decision["risk_factors"]}
    new_factors = [f for f in a_decision["risk_factors"] if f["factor"] not in b_factor_names]
    removed = [f for f in b_decision["risk_factors"] if f["factor"] not in a_factor_names]
    return {
        "changed": b_decision["priority"] != a_decision["priority"]
        or b_decision["recommend_human_review"] != a_decision["recommend_human_review"]
        or b_decision["score"] != a_decision["score"],
        "before": {"priority": b_decision["priority"], "score": b_decision["score"],
                   "recommend_human_review": b_decision["recommend_human_review"],
                   "confidence": b_decision["confidence"],
                   "risk_factors": b_decision["risk_factors"]},
        "after": {"priority": a_decision["priority"], "score": a_decision["score"],
                  "recommend_human_review": a_decision["recommend_human_review"],
                  "confidence": a_decision["confidence"],
                  "risk_factors": a_decision["risk_factors"]},
        "new_risk_factors": new_factors,
        "removed_risk_factors": removed,
        "score_delta": round(a_decision["score"] - b_decision["score"], 1),
    }

"""Persistent memory.

Anything the user tells NEXUS is written into FalkorDB as a real node with real
relationships. Because the agent's reasoning reads those relationships, a
memory write genuinely changes later answers -- the graph *is* the memory.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.graph import client, schema as S
from app.graph import tools as T


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


_PCT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent)", re.IGNORECASE)
_NUM = re.compile(r"(\d+(?:\.\d+)?)")


def parse_observation(text: str) -> dict[str, Any]:
    """Extract a numeric signal and a human topic from free text."""
    pct = _PCT.search(text or "")
    unit = "percent" if pct else None
    value: float | None = None
    if pct:
        value = float(pct.group(1))
    else:
        m = _NUM.search(text or "")
        if m:
            value = float(m.group(1))
            unit = "count"
    lowered = (text or "").lower()
    kind = "traffic_shift" if "traffic" in lowered else "metric"
    return {"value": value, "unit": unit, "kind": kind}


def resolve_target(text: str, hint: str | None = None) -> dict[str, Any] | None:
    """Find the graph entity a user sentence is most likely about."""
    if hint:
        node = T.get_node(hint)
        if node:
            return node
    words = [w for w in re.findall(r"[a-zA-Z]{3,}", text or "") if w.lower() not in
             {"the", "has", "have", "increased", "increasing", "remember", "that",
              "traffic", "today", "and", "for", "with", "please", "note", "this"}]
    best: dict[str, Any] | None = None
    best_score = -1.0
    for word in words:
        for cand in T.search_graph(word, limit=12):
            if cand["label"] not in (S.SERVICE, S.API, S.DATABASE, S.INCIDENT, S.CUSTOMER):
                continue
            props = cand["props"]
            score = 0.0
            score += 3.0 if cand["label"] in (S.SERVICE, S.API) else 1.0
            score += min(3.0, (props.get("tx_per_hour") or 0) / 60000.0)
            if word.lower() in cand["name"].lower():
                score += 2.0
            if score > best_score:
                best_score, best = score, cand
    return best


def store_memory(
    text: str,
    target_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Write a user observation into the graph as an Event with relationships."""
    signal = parse_observation(text)
    target = resolve_target(text, target_id)
    event_id = _new_id("evt-mem")
    summary = (text or "").strip() or "user observation"

    props = {
        "id": event_id,
        "kind": signal["kind"],
        "summary": summary,
        "at": _now(),
        "severity": "info",
        "source": "user_memory",
        "session": session_id or "",
    }
    if signal["value"] is not None:
        props["value"] = signal["value"]
    if signal["unit"]:
        props["unit"] = signal["unit"]

    client.run("CREATE (e:Event) SET e = $props", {"props": props})

    links: list[dict] = []
    if target:
        client.run(
            "MATCH (e:Event {id: $eid}), (t {id: $tid}) CREATE (e)-[:AFFECTS]->(t)",
            {"eid": event_id, "tid": target["id"]},
        )
        links.append({"rel": S.AFFECTS, "target": target["id"], "label": target["label"]})

        # Propagate to the API<->Service pair so the whole impact cone sees it.
        if target["label"] == S.SERVICE:
            apis = client.run(
                "MATCH (s:Service {id: $id})-[:SUPPORTS]->(a:API) RETURN a.id",
                {"id": target["id"]},
            )
            for (aid,) in apis:
                client.run(
                    "MATCH (e:Event {id: $eid}), (a:API {id: $aid}) CREATE (e)-[:AFFECTS]->(a)",
                    {"eid": event_id, "aid": aid},
                )
                links.append({"rel": S.AFFECTS, "target": aid, "label": S.API})
        elif target["label"] == S.API:
            svcs = client.run(
                "MATCH (s:Service)-[:SUPPORTS]->(a:API {id: $id}) RETURN s.id",
                {"id": target["id"]},
            )
            for (sid,) in svcs:
                client.run(
                    "MATCH (e:Event {id: $eid}), (s:Service {id: $sid}) CREATE (e)-[:AFFECTS]->(s)",
                    {"eid": event_id, "sid": sid},
                )
                links.append({"rel": S.AFFECTS, "target": sid, "label": S.SERVICE})

    return {
        "event": {"id": event_id, **props},
        "signal": signal,
        "target": target,
        "links": links,
    }


def _evidence_node(summary: str, kind: str, session_id: str | None) -> str:
    eid = _new_id("ev-mem")
    client.run(
        "CREATE (e:Evidence) SET e = $props",
        {"props": {"id": eid, "summary": summary, "kind": kind, "source": "agent",
                   "at": _now(), "session": session_id or ""}},
    )
    return eid


def record_decision(
    question: str,
    answer: str,
    confidence: float,
    session_id: str,
    priority: str | None = None,
    recommend_human_review: bool | None = None,
    question_key: str = "general",
    based_on: list[str] | None = None,
    risk_factors: list[dict] | None = None,
    traversed: list[dict] | None = None,
    actions: list[str] | None = None,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist a decision and its evidence so it can be explained later."""
    decision_id = _new_id("dec")
    props: dict[str, Any] = {
        "id": decision_id,
        "question": question,
        "question_key": question_key,
        "answer": answer,
        "confidence": float(confidence),
        "priority": priority or "",
        "recommend_human_review": bool(recommend_human_review),
        "session": session_id or "",
        "at": _now(),
        "kind": "decision",
        "policy_version": "nexus-policy/1.0",
    }
    if snapshot is not None:
        props["snapshot_json"] = json.dumps(snapshot)
    client.run("CREATE (d:Decision) SET d = $props", {"props": props})

    for ent in based_on or []:
        client.run(
            "MATCH (d:Decision {id: $did}), (e {id: $eid}) CREATE (d)-[:BASED_ON]->(e)",
            {"did": decision_id, "eid": ent},
        )
    for f in risk_factors or []:
        eid = _evidence_node(f.get("detail", f.get("factor", "risk factor")), "risk_factor", session_id)
        client.run(
            "MATCH (d:Decision {id: $did}), (e:Evidence {id: $eid}) "
            "CREATE (d)-[:SUPPORTED_BY]->(e)",
            {"did": decision_id, "eid": eid},
        )
    for hop in traversed or []:
        eid = _evidence_node(
            f"{hop.get('from',{}).get('id')} -[{hop.get('rel')}]-> {hop.get('to',{}).get('id')}",
            "traversal", session_id,
        )
        client.run(
            "MATCH (d:Decision {id: $did}) MATCH (ev:Evidence {id: $eid}) "
            "CREATE (d)-[:TRAVERSED]->(ev)",
            {"did": decision_id, "eid": eid},
        )
    for act in actions or []:
        client.run(
            "MATCH (d:Decision {id: $did}), (a:Action {id: $aid}) CREATE (d)-[:TRIGGERED]->(a)",
            {"did": decision_id, "aid": act},
        )

    return props


def create_action(
    description: str,
    target_id: str | None = None,
    decision_id: str | None = None,
    status: str = "proposed",
) -> dict[str, Any]:
    action_id = _new_id("act")
    props = {"id": action_id, "description": description, "status": status,
             "at": _now(), "kind": "action"}
    client.run("CREATE (a:Action) SET a = $props", {"props": props})
    if target_id:
        client.run(
            "MATCH (a:Action {id: $aid}), (t {id: $tid}) CREATE (a)-[:TARGETS]->(t)",
            {"aid": action_id, "tid": target_id},
        )
    if decision_id:
        client.run(
            "MATCH (d:Decision {id: $did}), (a:Action {id: $aid}) CREATE (d)-[:TRIGGERED]->(a)",
            {"did": decision_id, "aid": action_id},
        )
    return props


def _hydrate_decision(rows: list[list[Any]]) -> list[dict[str, Any]]:
    out = []
    for did, question, qkey, answer, conf, priority, review, at, session, snapshot in rows:
        item = {
            "id": did, "question": question, "question_key": qkey, "answer": answer,
            "confidence": conf, "priority": priority,
            "recommend_human_review": review, "at": at, "session": session,
        }
        if snapshot:
            try:
                item["snapshot"] = json.loads(snapshot)
            except (ValueError, TypeError):
                item["snapshot"] = None
        out.append(item)
    return out


def decisions_for(question_key: str, limit: int = 5) -> list[dict[str, Any]]:
    rows = client.run(
        """
        MATCH (d:Decision {question_key: $k})
        RETURN d.id, d.question, d.question_key, d.answer, d.confidence, d.priority,
               d.recommend_human_review, d.at, d.session, d.snapshot_json
        ORDER BY d.at DESC LIMIT $limit
        """,
        {"k": question_key, "limit": limit},
    )
    return _hydrate_decision(rows)


def recent_decisions(limit: int = 20) -> list[dict[str, Any]]:
    rows = client.run(
        """
        MATCH (d:Decision)
        RETURN d.id, d.question, d.question_key, d.answer, d.confidence, d.priority,
               d.recommend_human_review, d.at, d.session, d.snapshot_json
        ORDER BY d.at DESC LIMIT $limit
        """,
        {"limit": limit},
    )
    return _hydrate_decision(rows)


def decisions_for_entity(entity_id: str, limit: int = 10) -> list[dict[str, Any]]:
    rows = client.run(
        """
        MATCH (d:Decision)-[:BASED_ON]->(e {id: $id})
        RETURN d.id, d.question, d.question_key, d.answer, d.confidence, d.priority,
               d.recommend_human_review, d.at, d.session, d.snapshot_json
        ORDER BY d.at DESC LIMIT $limit
        """,
        {"id": entity_id, "limit": limit},
    )
    return _hydrate_decision(rows)


def graph_mutations(limit: int = 20) -> list[dict[str, Any]]:
    """Recently written Event/Decision/Action nodes (for the observability panel)."""
    rows = client.run(
        """
        MATCH (n) WHERE n.source = 'user_memory' OR n.session IS NOT NULL
          OR n.kind IN ['traffic_shift', 'metric']
        RETURN n.id, labels(n), n.summary, n.question, n.description, n.at, n.kind
        ORDER BY n.at DESC LIMIT $limit
        """,
        {"limit": limit},
    )
    return [
        {"id": i, "label": (l or ["Unknown"])[0], "text": s or q or d or i,
         "at": at, "kind": k}
        for i, l, s, q, d, at, k in rows
    ]

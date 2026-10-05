"""The primary NEXUS agent.

One orchestrating agent (no unnecessary multi-agent sprawl) with an explicit
pipeline:

    question -> intent -> graph retrieval -> relationship-aware facts
             -> graph-grounded policy -> decision -> evidence path
             -> memory write (when the user teaches something) -> trace

The graph determines *what context is retrieved* and *which decision is
appropriate*. The LLM, when configured, only narrates the retrieved facts.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from app.graph import client, schema as S
from app.graph import tools as T
from app.agent import memory as mem
from app.agent import reasoning as R
from app.agent.llm import llm

# ---------------------------------------------------------------------------
# Session state (persisted as a Session node in the graph)
# ---------------------------------------------------------------------------

def get_session(session_id: str) -> dict[str, Any]:
    rows = client.run(
        "MATCH (s:Session {id: $id}) RETURN s.last_incident, s.turns", {"id": session_id}
    )
    if rows:
        return {"id": session_id, "last_incident": rows[0][0], "turns": rows[0][1] or 0}
    client.run(
        "CREATE (s:Session) SET s = $props",
        {"props": {"id": session_id, "started_at": datetime.now(timezone.utc).isoformat(),
                   "user": "demo", "kind": "session", "turns": 0}},
    )
    return {"id": session_id, "last_incident": None, "turns": 0}


def update_session(session_id: str, last_incident: str | None, turns: int) -> None:
    client.run(
        "MATCH (s:Session {id: $id}) SET s.last_incident = $li, s.turns = $turns",
        {"id": session_id, "li": last_incident, "turns": turns},
    )


# ---------------------------------------------------------------------------
# Intent classification
# ---------------------------------------------------------------------------

_INTENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("remember", ("remember", "note that", "record that", "keep in mind", "store that",
                  "increased", "decreased", "went up", "went down", "spiked", "dropped",
                  "traffic")),
    ("compare", ("why did it change", "why did your", "what changed", "why the change",
                 "before and after", "compare", "difference between", "why did the "
                 "recommendation change", "what changed since")),
    ("reevaluate", ("re-evaluate", "reevaluate", "reassess", "re-assess", "evaluate again",
                    "run it again", "re-run", "recompute")),
    ("evidence_path", ("evidence path", "show me the evidence", "show evidence",
                       "prove it", "how did you get", "trace the path", "graph path")),
    ("root_cause", ("root cause", "what caused", "cause of", "why did it fail",
                    "what broke", "what triggered")),
    ("ownership", ("who owns", "owner", "on call", "on-call", "who is responsible",
                   "who to page", "who should we page")),
    ("next_steps", ("what should we do", "next step", "what do we do", "recommend",
                    "runbook", "remediate", "mitigate", "action plan", "fix")),
    ("blast_radius", ("what services are affected", "blast radius", "downstream",
                      "which customers", "customers at risk", "what is affected",
                      "what systems are affected", "what else")),
    ("history", ("happened before", "historical", "previous incident", "last time",
                 "history", "precedent", "seen this")),
    ("most_dangerous", ("most dangerous", "worst incident", "highest priority",
                        "most critical", "top incident", "unresolved incident",
                        "most severe", "what should we focus")),
    ("explain_why", ("why", "explain", "justify", "rationale")),
]

_NUMBER_INTENT = ("remember",)  # remember only fires with a quantity in the text


def classify(question: str) -> str:
    q = (question or "").lower()
    has_number = bool(re.search(r"\d", q))
    for intent, keywords in _INTENT_RULES:
        if any(k in q for k in keywords):
            if intent in _NUMBER_INTENT and not has_number:
                continue
            return intent
    if "incident" in q:
        return "most_dangerous"
    return "help"


def extract_incident_id(text: str) -> str | None:
    for pattern in (r"inc[-\s]?(\d{1,4})", r"#\s?(\d{1,4})", r"\bincident\s+(\d{1,4})"):
        m = re.search(pattern, text or "", re.IGNORECASE)
        if m:
            cand = f"inc-{m.group(1)}"
            if T.get_node(cand):
                return cand
    return None


def focus_incident(question: str, session_id: str) -> str:
    explicit = extract_incident_id(question)
    if explicit:
        return explicit
    session = get_session(session_id)
    if session.get("last_incident") and T.get_node(session["last_incident"]):
        return session["last_incident"]
    ranked = R.rank_open_incidents()
    return ranked[0]["id"] if ranked else "inc-142"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _graph_from_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    return {"nodes": evidence.get("nodes", []), "edges": evidence.get("edges", [])}


def _reasoning_lines(facts: dict[str, Any], decision: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    inc = facts["incident"]
    lines.append(f"Retrieved incident {inc['id']} from FalkorDB (status={inc['props'].get('status')}).")
    for node in facts["affected"]:
        lines.append(f"Traversed {inc['id']} -[AFFECTS]-> {node['id']} ({node['label']}).")
    if facts.get("primary_service"):
        ps = facts["primary_service"]
        lines.append(
            f"Affected service {ps['name']} — criticality={ps['props'].get('criticality')}, "
            f"throughput={ps['props'].get('tx_per_hour', 0):,}/hour."
        )
    if facts.get("precedent_revenue"):
        pr = facts["precedent_revenue"]
        lines.append(f"Historical precedent {pr['incident']} caused ${pr['amount_usd']:,} in revenue loss.")
    lines.append(f"Applied {decision['policy_version']}: score={decision['score']} -> priority={decision['priority']}.")
    return lines


def _narrate(question: str, fact_sheet: dict[str, Any], fallback: str) -> tuple[str, bool]:
    return llm.narrate(question, fact_sheet, fallback)


def _record(
    question: str,
    answer_text: str,
    confidence: float,
    session_id: str,
    question_key: str,
    decision: dict[str, Any] | None,
    incident_id: str | None,
    evidence: dict[str, Any] | None,
    mutations: list[dict] | None = None,
    facts: dict[str, Any] | None = None,
) -> str:
    based_on = [x for x in [incident_id] if x]
    if incident_id:
        if facts is None:
            facts = R.gather_incident_facts(incident_id)
        based_on += [n["id"] for n in facts["affected"]]
        if facts.get("primary_service"):
            based_on.append(facts["primary_service"]["id"])
    snapshot = None
    if decision and incident_id:
        snapshot = {
            "incident_id": incident_id,
            "priority": decision["priority"],
            "score": decision["score"],
            "recommend_human_review": decision["recommend_human_review"],
            "confidence": decision["confidence"],
            "risk_factors": decision["risk_factors"],
        }
    props = mem.record_decision(
        question=question,
        answer=answer_text,
        confidence=confidence,
        session_id=session_id,
        priority=decision["priority"] if decision else None,
        recommend_human_review=decision["recommend_human_review"] if decision else None,
        question_key=question_key,
        based_on=based_on,
        risk_factors=decision["risk_factors"] if decision else None,
        traversed=(evidence or {}).get("hops"),
        snapshot=snapshot,
    )
    return props["id"]


# ---------------------------------------------------------------------------
# Intent handlers
# ---------------------------------------------------------------------------

def _h_most_dangerous(question: str, session_id: str) -> dict[str, Any]:
    ranked = R.rank_open_incidents()
    if not ranked:
        return _plain("There are no unresolved incidents in the graph.", [], session_id)
    top = ranked[0]
    assessment = R.assess_incident(top["id"])
    facts, decision = assessment["facts"], assessment["decision"]
    evidence = R.build_evidence_path(top["id"], facts)

    ps = facts["primary_service"]
    pr = facts.get("precedent_revenue")
    fallback = (
        f"The most dangerous unresolved incident is {facts['incident']['name']} "
        f"({facts['incident']['props'].get('code', top['id'])}). "
        f"Priority {decision['priority']} (risk score {decision['score']}/100). "
        f"It affects {ps['name'] if ps else 'an unknown service'}"
        + (f", a {ps['props'].get('criticality')}-criticality service handling {facts['tx_per_hour']:,} transactions/hour" if ps else "")
        + f". {facts['blast_radius_count']} downstream services sit in its blast radius. "
        + (f"A previous incident on the same dependency ({pr['incident']}) caused "
           f"${pr['amount_usd']:,} in revenue loss. " if pr else "")
        + f"Human review {'is' if decision['recommend_human_review'] else 'is not'} recommended."
    )
    answer_text, used_llm = _narrate(question, {
        "incident": facts["incident"],
        "affected": facts["affected"],
        "decision": decision,
        "precedent": pr,
        "ranked_candidates": ranked[:5],
    }, fallback)

    decision_id = _record(question, answer_text, decision["confidence"], session_id,
                          "most_dangerous_incident", decision, top["id"], evidence, facts=facts)
    update_session(session_id, top["id"], get_session(session_id).get("turns", 0) + 1)

    return _response(
        intent="most_dangerous", answer=answer_text, confidence=decision["confidence"],
        used_llm=used_llm, decision=decision, facts=facts, evidence=evidence,
        reasoning=_reasoning_lines(facts, decision), session_id=session_id,
        decision_id=decision_id, ranked=ranked[:5],
    )


def _h_explain_why(question: str, session_id: str) -> dict[str, Any]:
    incident_id = focus_incident(question, session_id)
    assessment = R.assess_incident(incident_id)
    facts, decision = assessment["facts"], assessment["decision"]
    evidence = R.build_evidence_path(incident_id, facts)

    reasons = "; ".join(f["detail"] for f in decision["risk_factors"])
    path = " then ".join(
        f"{h['from']['name']} -[{h['rel']}]-> {h['to']['name']}" for h in evidence["hops"][:6]
    )
    fallback = (
        f"{facts['incident']['name']} is rated {decision['priority']} "
        f"(risk score {decision['score']}/100, confidence {decision['confidence']:.0%}). "
        f"Graph evidence: {reasons}. "
        f"Evidence path: {path}."
    )
    answer_text, used_llm = _narrate(question, {
        "incident": facts["incident"], "decision": decision,
        "evidence_hops": evidence["hops"], "root_causes": facts["root_causes"][:5],
    }, fallback)
    decision_id = _record(question, answer_text, decision["confidence"], session_id,
                          "explain_incident_priority", decision, incident_id, evidence, facts=facts)
    update_session(session_id, incident_id, get_session(session_id).get("turns", 0) + 1)
    return _response(
        intent="explain_why", answer=answer_text, confidence=decision["confidence"],
        used_llm=used_llm, decision=decision, facts=facts, evidence=evidence,
        reasoning=_reasoning_lines(facts, decision), session_id=session_id,
        decision_id=decision_id,
    )


def _h_evidence_path(question: str, session_id: str) -> dict[str, Any]:
    incident_id = focus_incident(question, session_id)
    assessment = R.assess_incident(incident_id)
    facts, decision = assessment["facts"], assessment["decision"]
    evidence = R.build_evidence_path(incident_id, facts)
    chain = "\n".join(
        f"  {h['from']['name']} --[{h['rel']}]--> {h['to']['name']}   ({h['why']})"
        for h in evidence["hops"]
    )
    fallback = (
        f"Evidence path for {facts['incident']['name']} "
        f"({len(evidence['hops'])} graph relationships):\n{chain}"
    )
    answer_text, used_llm = _narrate(question, {
        "incident": facts["incident"], "evidence_hops": evidence["hops"], "decision": decision,
    }, fallback)
    decision_id = _record(question, answer_text, decision["confidence"], session_id,
                          "evidence_path", decision, incident_id, evidence, facts=facts)
    return _response(
        intent="evidence_path", answer=answer_text, confidence=decision["confidence"],
        used_llm=used_llm, decision=decision, facts=facts, evidence=evidence,
        reasoning=[f"Traversed {len(evidence['hops'])} relationships from {incident_id}."],
        session_id=session_id, decision_id=decision_id,
    )


def _h_root_cause(question: str, session_id: str) -> dict[str, Any]:
    incident_id = focus_incident(question, session_id)
    assessment = R.assess_incident(incident_id)
    facts, decision = assessment["facts"], assessment["decision"]
    evidence = R.build_evidence_path(incident_id, facts)
    causes = facts["root_causes"]
    chain = "\n".join(f"  {i+1}. {c['id']} ({c['label']}) — {c['reason']}" for i, c in enumerate(causes[:5]))
    fallback = (
        f"Candidate root causes for {facts['incident']['name']}, ranked from graph "
        f"traversal:\n{chain}"
    )
    answer_text, used_llm = _narrate(question, {
        "incident": facts["incident"], "root_causes": causes, "decision": decision,
    }, fallback)
    decision_id = _record(question, answer_text, decision["confidence"], session_id,
                          "root_cause", decision, incident_id, evidence, facts=facts)
    return _response(
        intent="root_cause", answer=answer_text, confidence=decision["confidence"],
        used_llm=used_llm, decision=decision, facts=facts, evidence=evidence,
        reasoning=[f"Ranked {len(causes)} root-cause candidates by dependency depth and triggering events."],
        session_id=session_id, decision_id=decision_id,
    )


def _h_history(question: str, session_id: str) -> dict[str, Any]:
    incident_id = focus_incident(question, session_id)
    facts = R.gather_incident_facts(incident_id)
    precedents = facts["precedents"]
    lines = []
    for p in precedents:
        caused = ", ".join(f"{c['name']} (${c['amount_usd']:,})" if c["amount_usd"]
                           else c["name"] for c in p.get("caused", [])) or "no recorded impact"
        lines.append(f"  • {p['id']} \"{p['title']}\" — {p['status']}, {p['severity']}, caused: {caused}")
    fallback = (
        f"{facts['incident']['name']} has {len(precedents)} connected historical precedents:\n"
        + "\n".join(lines)
    )
    answer_text, used_llm = _narrate(question, {"incident": facts["incident"],
                                                "precedents": precedents}, fallback)
    evidence = R.build_evidence_path(incident_id, facts)
    decision_id = _record(question, answer_text, 0.8, session_id, "history", None, incident_id, evidence, facts=facts)
    return _response(
        intent="history", answer=answer_text, confidence=0.8, used_llm=used_llm,
        decision=None, facts=facts, evidence=evidence,
        reasoning=[f"Found {len(precedents)} precedents via PRECEDED/FOLLOWED/RELATED_TO."],
        session_id=session_id, decision_id=decision_id,
    )


def _h_blast_radius(question: str, session_id: str) -> dict[str, Any]:
    incident_id = focus_incident(question, session_id)
    facts = R.gather_incident_facts(incident_id)
    ps = facts["primary_service"]
    fallback = (
        f"{ps['name'] if ps else 'The affected service'} has {facts['blast_radius_count']} "
        f"downstream dependents: "
        + ", ".join(d["name"] for d in facts["dependents"][:8])
        + f". {len(facts['exposed_apis'])} exposed API contracts and {len(facts['impacts'])} "
        f"business impacts are reachable: "
        + ", ".join(i["name"] for i in facts["impacts"][:6]) + "."
    )
    answer_text, used_llm = _narrate(question, {
        "incident": facts["incident"], "primary_service": ps,
        "dependents": facts["dependents"], "exposed_apis": facts["exposed_apis"],
        "impacts": facts["impacts"],
    }, fallback)
    evidence = R.build_evidence_path(incident_id, facts)
    decision_id = _record(question, answer_text, 0.85, session_id, "blast_radius", None, incident_id, evidence, facts=facts)
    return _response(
        intent="blast_radius", answer=answer_text, confidence=0.85, used_llm=used_llm,
        decision=None, facts=facts, evidence=evidence,
        reasoning=[f"Traversed DEPENDS_ON upstream from {ps['id'] if ps else '?'} and SUPPORTS/IMPACTS to outcomes."],
        session_id=session_id, decision_id=decision_id,
    )


def _h_ownership(question: str, session_id: str) -> dict[str, Any]:
    incident_id = focus_incident(question, session_id)
    facts = R.gather_incident_facts(incident_id)
    ps = facts["primary_service"]
    if not ps:
        return _plain("No service is attached to this incident.", [], session_id)
    own = T.get_service_ownership(ps["id"])
    team = own.get("team") or {}
    oncall = own.get("on_call") or []
    fallback = (
        f"{ps['name']} is owned by {team.get('name', 'an unknown team')} ({team.get('slack', '')}). "
        f"On-call: " + (", ".join(f"{p['name']} <{p['email']}>" for p in oncall) or "nobody currently") + "."
    )
    answer_text, used_llm = _narrate(question, {
        "service": ps, "ownership": own, "incident": facts["incident"],
    }, fallback)
    evidence = R.build_evidence_path(incident_id, facts)
    decision_id = _record(question, answer_text, 0.9, session_id, "ownership", None, incident_id, evidence, facts=facts)
    return _response(
        intent="ownership", answer=answer_text, confidence=0.9, used_llm=used_llm,
        decision=None, facts={**facts, "ownership": own}, evidence=evidence,
        reasoning=[f"Traversed OWNS/ON_CALL from {ps['id']}."],
        session_id=session_id, decision_id=decision_id,
    )


def _h_next_steps(question: str, session_id: str) -> dict[str, Any]:
    incident_id = focus_incident(question, session_id)
    assessment = R.assess_incident(incident_id)
    facts, decision = assessment["facts"], assessment["decision"]
    evidence = R.build_evidence_path(incident_id, facts)
    ps = facts["primary_service"]
    runbooks = T.get_runbook(ps["id"]) if ps else []
    top_cause = facts["root_causes"][0] if facts["root_causes"] else None

    proposed: list[dict] = []
    if top_cause:
        proposed.append({
            "description": f"Investigate and mitigate {top_cause['name']} ({top_cause['id']})",
            "target": top_cause["id"],
        })
    if facts.get("root_causes"):
        db_causes = [c for c in facts["root_causes"] if c["label"] == S.DATABASE]
        if db_causes:
            proposed.append({
                "description": f"Raise connection limits / shed load on {db_causes[0]['name']}",
                "target": db_causes[0]["id"],
            })
    if ps:
        proposed.append({
            "description": f"Page {ps['name']} on-call and open an incident bridge",
            "target": ps["id"],
        })
    for rb in runbooks[:1]:
        proposed.append({"description": f"Follow runbook: {rb['title']}", "target": rb["id"]})

    created = []
    for p in proposed:
        created.append(mem.create_action(p["description"], target_id=p["target"]))

    steps = "\n".join(f"  {i+1}. {p['description']}" for i, p in enumerate(proposed))
    fallback = (
        f"Recommended next steps for {facts['incident']['name']} "
        f"(priority {decision['priority']}"
        + (f", human review {'recommended' if decision['recommend_human_review'] else 'not required'}" if decision else "")
        + f"):\n{steps}"
    )
    answer_text, used_llm = _narrate(question, {
        "incident": facts["incident"], "decision": decision,
        "root_causes": facts["root_causes"][:3], "runbooks": runbooks,
    }, fallback)
    decision_id = _record(question, answer_text, decision["confidence"], session_id,
                          "next_steps", decision, incident_id, evidence, facts=facts,
                          mutations=[{"type": "create_action", **a} for a in created])
    return _response(
        intent="next_steps", answer=answer_text, confidence=decision["confidence"],
        used_llm=used_llm, decision=decision, facts=facts, evidence=evidence,
        reasoning=[f"Created {len(created)} Action nodes linked by TARGETS."],
        session_id=session_id, decision_id=decision_id,
        mutations=[{"type": "create_node", "label": "Action", **a} for a in created],
    )


def _h_remember(question: str, session_id: str) -> dict[str, Any]:
    result = mem.store_memory(question, session_id=session_id)
    target = result.get("target")
    sig = result["signal"]
    fallback = (
        f"Stored in the graph: \"{question.strip()}\". "
        + (f"Linked to {target['name']} ({target['id']}, {target['label']})"
           + (f" as {sig['value']:g} {sig['unit']}" if sig["value"] is not None else "")
           + f" via {len(result['links'])} AFFECTS relationship(s). "
           if target else "No entity could be resolved, so it was stored as a standalone event. ")
        + "This new evidence is now part of the agent's context and will change subsequent assessments."
    )
    answer_text, used_llm = _narrate(question, {
        "stored_event": result["event"], "target": target, "links": result["links"],
    }, fallback)
    decision_id = _record(question, answer_text, 0.95, session_id, "remember", None,
                          None, None, mutations=result["links"])
    if target and target["label"] == S.SERVICE:
        update_session(session_id, None, get_session(session_id).get("turns", 0) + 1)
    mutations = [{"type": "create_node", "label": "Event", **result["event"]}]
    mutations += [{"type": "create_edge", "rel": l["rel"], "source": result["event"]["id"],
                   "target": l["target"], "target_label": l["label"]} for l in result["links"]]
    return _response(
        intent="remember", answer=answer_text, confidence=0.95, used_llm=used_llm,
        decision=None, facts={"stored_event": result["event"], "target": target},
        evidence=None, reasoning=[
            f"Resolved user text to graph entity {target['id']} ({target['label']})." if target
            else "Could not resolve an entity for this observation.",
            f"Created Event node {result['event']['id']} with {len(result['links'])} relationship(s).",
            "Future queries that traverse this entity will now see the new evidence.",
        ],
        session_id=session_id, decision_id=decision_id, mutations=mutations,
    )


def _h_reevaluate(question: str, session_id: str) -> dict[str, Any]:
    incident_id = focus_incident(question, session_id)
    assessment = R.assess_incident(incident_id)
    facts, decision = assessment["facts"], assessment["decision"]
    evidence = R.build_evidence_path(incident_id, facts)

    prior = [d for d in mem.decisions_for("most_dangerous_incident", limit=8)
             if d.get("snapshot")]
    before = None
    for d in prior:
        if d["snapshot"].get("incident_id") == incident_id:
            before = d["snapshot"]
            break
    comparison = R.compare_assessments({"decision": before}, assessment) if before else None

    if comparison and comparison["changed"]:
        change = (f"Re-assessment changed: {before['priority']} (score {before['score']}) "
                  f"-> {decision['priority']} (score {decision['score']}).")
    elif comparison:
        change = f"Re-assessment is unchanged at {decision['priority']} (score {decision['score']})."
    else:
        change = f"No prior assessment on record; current priority {decision['priority']}."
    new_factors = ", ".join(f["detail"] for f in (comparison or {}).get("new_risk_factors", []))
    fallback = (
        f"{change} {facts['incident']['name']} now rates {decision['priority']} "
        f"(score {decision['score']}/100, confidence {decision['confidence']:.0%}). "
        + (f"New graph risk factor(s): {new_factors}. " if new_factors else "")
        + f"Human review {'recommended' if decision['recommend_human_review'] else 'not required'}."
    )
    answer_text, used_llm = _narrate(question, {
        "incident": facts["incident"], "decision": decision,
        "comparison": comparison, "traffic_events": facts["traffic_events"],
    }, fallback)
    decision_id = _record(question, answer_text, decision["confidence"], session_id,
                          "most_dangerous_incident", decision, incident_id, evidence, facts=facts)
    update_session(session_id, incident_id, get_session(session_id).get("turns", 0) + 1)
    return _response(
        intent="reevaluate", answer=answer_text, confidence=decision["confidence"],
        used_llm=used_llm, decision=decision, facts=facts, evidence=evidence,
        reasoning=_reasoning_lines(facts, decision) + (
            [f"Diff vs prior decision: score {comparison['score_delta']:+g}, "
             f"{len(comparison['new_risk_factors'])} new risk factor(s)."] if comparison else []
        ),
        session_id=session_id, decision_id=decision_id, comparison=comparison,
    )


def _h_compare(question: str, session_id: str) -> dict[str, Any]:
    decisions = [d for d in mem.decisions_for("most_dangerous_incident", limit=8) if d.get("snapshot")]
    if len(decisions) < 2:
        # Fall back to the incident's current state vs its recorded baseline.
        incident_id = focus_incident(question, session_id)
        assessment = R.assess_incident(incident_id)
        if decisions:
            comparison = R.compare_assessments({"decision": decisions[0]["snapshot"]}, assessment)
            before, after = comparison["before"], comparison["after"]
        else:
            return _plain("There is no recorded prior decision to compare against yet.", [], session_id)
        new_factors = comparison["new_risk_factors"]
    else:
        latest, previous = decisions[0], decisions[1]
        comparison = R.compare_assessments({"decision": previous["snapshot"]},
                                           {"decision": latest["snapshot"]})
        before, after = comparison["before"], comparison["after"]
        new_factors = comparison["new_risk_factors"]

    incident_id = focus_incident(question, session_id)
    facts = R.gather_incident_facts(incident_id)
    evidence = R.build_evidence_path(incident_id, facts)
    detail = "; ".join(f["detail"] for f in new_factors) or "no new risk factors"
    fallback = (
        f"The recommendation changed from {before['priority']} (score {before['score']}) to "
        f"{after['priority']} (score {after['score']}), a delta of {comparison['score_delta']:+g}. "
        f"New graph evidence that caused the change: {detail}."
    )
    answer_text, used_llm = _narrate(question, {
        "comparison": comparison, "traffic_events": facts["traffic_events"],
        "incident": facts["incident"],
    }, fallback)
    decision_id = _record(question, answer_text, after["confidence"], session_id,
                          "compare", {"priority": after["priority"], "score": after["score"],
                                      "recommend_human_review": after["recommend_human_review"],
                                      "confidence": after["confidence"],
                                      "risk_factors": after["risk_factors"],
                                      "policy_version": "nexus-policy/1.0"},
                          incident_id, evidence, facts=facts)
    return _response(
        intent="compare", answer=answer_text, confidence=after["confidence"],
        used_llm=used_llm, decision=None, facts=facts, evidence=evidence,
        reasoning=[f"Compared decisions and found a score delta of {comparison['score_delta']:+g}.",
                   f"New risk factors: {', '.join(f['factor'] for f in new_factors) or 'none'}."],
        session_id=session_id, decision_id=decision_id, comparison=comparison,
    )


def _h_help(question: str, session_id: str) -> dict[str, Any]:
    text = (
        "I am NEXUS, a graph-native incident commander. I reason over FalkorDB and can:\n"
        "  • find the most dangerous unresolved incident\n"
        "  • explain why an incident is critical, with a full evidence path\n"
        "  • trace root causes, blast radius, ownership and business impact\n"
        "  • tell you what happened in previous incidents\n"
        "  • recommend next steps from runbooks and dependencies\n"
        "  • remember new information you give me, which changes future assessments\n\n"
        "Try: \"What is the most dangerous unresolved incident?\" then \"Why?\""
    )
    return _response(intent="help", answer=text, confidence=1.0, used_llm=False,
                     decision=None, facts={}, evidence=None, reasoning=[],
                     session_id=session_id, decision_id=None)


HANDLERS: dict[str, Callable[[str, str], dict[str, Any]]] = {
    "most_dangerous": _h_most_dangerous,
    "explain_why": _h_explain_why,
    "evidence_path": _h_evidence_path,
    "root_cause": _h_root_cause,
    "history": _h_history,
    "blast_radius": _h_blast_radius,
    "ownership": _h_ownership,
    "next_steps": _h_next_steps,
    "remember": _h_remember,
    "reevaluate": _h_reevaluate,
    "compare": _h_compare,
    "help": _h_help,
}


# ---------------------------------------------------------------------------
# Response assembly
# ---------------------------------------------------------------------------

def _plain(text: str, reasoning: list[str], session_id: str) -> dict[str, Any]:
    return _response(intent="help", answer=text, confidence=1.0, used_llm=False,
                     decision=None, facts={}, evidence=None, reasoning=reasoning,
                     session_id=session_id, decision_id=None)


def _response(
    *,
    intent: str,
    answer: str,
    confidence: float,
    used_llm: bool,
    decision: dict[str, Any] | None,
    facts: dict[str, Any],
    evidence: dict[str, Any] | None,
    reasoning: list[str],
    session_id: str,
    decision_id: str | None,
    ranked: list[dict] | None = None,
    comparison: dict[str, Any] | None = None,
    mutations: list[dict] | None = None,
) -> dict[str, Any]:
    include_facts = {k: v for k, v in facts.items() if k not in ("dependencies",)}
    graph = _graph_from_evidence(evidence) if evidence else {"nodes": [], "edges": []}
    return {
        "type": "answer",
        "intent": intent,
        "answer": answer,
        "confidence": confidence,
        "mode": "llm" if used_llm else "deterministic",
        "used_llm": used_llm,
        "decision": decision,
        "facts": include_facts,
        "evidence_path": evidence,
        "graph": graph,
        "reasoning": reasoning,
        "ranked": ranked or [],
        "comparison": comparison,
        "mutations": mutations or [],
        "decision_id": decision_id,
        "session_id": session_id,
    }


def answer(question: str, session_id: str = "default") -> dict[str, Any]:
    """Entry point: run the full pipeline and attach an observability trace."""
    token = client.start_query_log()
    try:  # noqa: SIM105 - token must be released in finally
        intent = classify(question)
        handler = HANDLERS.get(intent, _h_help)
        result = handler(question, session_id)
    except client.FalkorDBUnavailable as exc:
        result = _plain(f"FalkorDB is unavailable: {exc}", [], session_id)
        intent = "error"
    except Exception as exc:  # keep the API responsive, but be honest
        result = _plain(f"The agent could not complete this request: {exc}", [], session_id)
        intent = "error"
    finally:
        queries = client.stop_query_log(token)

    evidence = result.get("evidence_path") or {}
    result["trace"] = {
        "user_query": question,
        "intent": result.get("intent", intent),
        "graph_queries": queries,
        "query_count": len(queries),
        "retrieved_nodes": [
            {"id": n["id"], "label": n["label"], "name": n["name"]}
            for n in (evidence.get("nodes") or [])
        ],
        "retrieved_relationships": [
            {"source": e["source"], "rel": e["rel"], "target": e["target"]}
            for e in (evidence.get("edges") or [])
        ],
        "decision": result.get("decision"),
        "evidence_path": [
            f"{h['from']['id']} -[{h['rel']}]-> {h['to']['id']}" for h in (evidence.get("hops") or [])
        ],
        "graph_mutations": result.get("mutations") or [],
        "mode": result.get("mode"),
    }
    return result

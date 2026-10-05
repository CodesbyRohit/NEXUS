"""Graph-grounded reasoning: policy, causality, evidence paths."""

from __future__ import annotations

import pytest

from app.agent import reasoning as R
from app.graph import tools as T


@pytest.fixture(autouse=True)
def _clean(clean_runtime):
    yield


def test_baseline_assessment_is_high_but_not_critical():
    a = R.assess_incident("inc-142")
    decision = a["decision"]
    assert decision["priority"] == "HIGH"
    assert 65 <= decision["score"] < 85
    assert decision["recommend_human_review"] is False
    factors = {f["factor"] for f in decision["risk_factors"]}
    assert "service_criticality" in factors
    assert "historical_precedent" in factors
    assert "blast_radius" in factors
    assert "traffic_shift" not in factors


def test_policy_is_explainable_and_tunable():
    assert R.POLICY["thresholds"]["critical"] == 85
    a = R.assess_incident("inc-142")
    total = sum(f["weight"] for f in a["decision"]["risk_factors"])
    assert pytest.approx(a["decision"]["score"], abs=0.1) == total


def test_most_dangerous_incident_is_142():
    ranked = R.rank_open_incidents()
    assert ranked, "there must be unresolved incidents"
    assert ranked[0]["id"] == "inc-142"


def test_causal_reasoning_prefers_database_root_cause():
    causes = T.find_root_causes("inc-142")["candidates"]
    assert causes[0]["id"] == "db-payments"
    assert causes[0]["label"] == "Database"


def test_evidence_path_is_graph_derived():
    ep = R.build_evidence_path("inc-142")
    hops = {(h["from"]["id"], h["rel"], h["to"]["id"]) for h in ep["hops"]}
    assert ("inc-142", "AFFECTS", "svc-payments") in hops
    assert ("svc-payments", "DEPENDS_ON", "db-payments") in hops
    assert ("svc-checkout", "DEPENDS_ON", "svc-payments") in hops
    assert ("inc-91", "CAUSED", "impact-revenue") in hops
    # Every hop must correspond to a real edge in FalkorDB.
    for h in ep["hops"]:
        rows = T.client.run(
            "MATCH (a {id: $a})-[r]->(b {id: $b}) RETURN type(r)",
            {"a": h["from"]["id"], "b": h["to"]["id"]},
        )
        assert any(row[0] == h["rel"] for row in rows), f"hop {h} is not in the graph"


def test_evidence_path_edges_for_visualisation():
    ep = R.build_evidence_path("inc-142")
    assert ep["nodes"] and ep["edges"]
    node_ids = {n["id"] for n in ep["nodes"]}
    for e in ep["edges"]:
        assert e["source"] in node_ids and e["target"] in node_ids


def test_intent_classification():
    from app.agent import orchestrator as O

    assert O.classify("What is the most dangerous unresolved incident?") == "most_dangerous"
    assert O.classify("Why is Incident #142 critical?") == "explain_why"
    assert O.classify("Checkout traffic increased 34%.") == "remember"
    assert O.classify("Re-evaluate the incident.") == "reevaluate"
    assert O.classify("Why did your recommendation change?") == "compare"
    assert O.classify("Show me the evidence path") == "evidence_path"
    assert O.classify("What caused this failure?") == "root_cause"
    assert O.classify("Who owns the affected service?") == "ownership"
    assert O.classify("Re-evaluate the incident.") != "remember"

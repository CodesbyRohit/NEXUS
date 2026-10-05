"""Persistent memory and decision persistence.

The critical test here is :func:`test_new_information_changes_future_decision`:
it is the product's core claim -- new information enters the graph and the
agent's next assessment genuinely changes because of it.
"""

from __future__ import annotations

import pytest

from app.agent import memory as mem
from app.agent import orchestrator as O
from app.agent import reasoning as R
from app.graph import client
from app.graph import tools as T

SESSION = "test-memory"


@pytest.fixture(autouse=True)
def _clean(clean_runtime):
    yield


def test_store_memory_writes_real_graph_state():
    before = client.stats()["nodes"]
    result = mem.store_memory("Payments latency increased 12%.", session_id=SESSION)
    assert client.stats()["nodes"] == before + 1

    event_id = result["event"]["id"]
    assert T.get_node(event_id) is not None
    # The event must be connected, not orphaned.
    rows = client.run(
        "MATCH (e:Event {id: $id})-[:AFFECTS]->(t) RETURN t.id", {"id": event_id}
    )
    assert rows, "a stored observation must be linked to an entity"


def test_entity_resolution_for_checkout_traffic():
    result = mem.store_memory("Checkout traffic increased 34%.", session_id=SESSION)
    assert result["target"] is not None
    assert result["target"]["label"] == "Service"
    assert result["signal"]["value"] == 34.0
    assert result["signal"]["unit"] == "percent"
    assert result["signal"]["kind"] == "traffic_shift"


def test_new_information_changes_future_decision():
    """THE essential test: graph update -> changed answer."""
    baseline = R.assess_incident("inc-142")["decision"]
    assert baseline["priority"] == "HIGH"
    assert baseline["recommend_human_review"] is False

    mem.store_memory("Checkout traffic increased 34%.", session_id=SESSION)

    updated = R.assess_incident("inc-142")["decision"]
    assert updated["priority"] == "CRITICAL"
    assert updated["recommend_human_review"] is True
    assert updated["score"] > baseline["score"]
    assert any(f["factor"] == "traffic_shift" for f in updated["risk_factors"])

    # And the new evidence appears in the evidence path itself.
    ep = R.build_evidence_path("inc-142")
    assert any(h["from"]["id"].startswith("evt-mem") for h in ep["hops"])


def test_decision_persistence_and_links():
    props = mem.record_decision(
        question="Why is incident inc-142 critical?",
        answer="Because of the graph.",
        confidence=0.9,
        session_id=SESSION,
        priority="HIGH",
        recommend_human_review=False,
        question_key="unit_test_key",
        based_on=["inc-142", "svc-payments"],
        risk_factors=[{"factor": "blast_radius", "detail": "many dependents", "weight": 10}],
        traversed=[{"from": {"id": "inc-142"}, "rel": "AFFECTS", "to": {"id": "svc-payments"}}],
    )
    assert T.get_node(props["id"]) is not None

    found = mem.decisions_for("unit_test_key")
    assert found and found[0]["id"] == props["id"]

    based_on = client.run(
        "MATCH (d:Decision {id: $id})-[:BASED_ON]->(e) RETURN e.id", {"id": props["id"]}
    )
    assert {r[0] for r in based_on} == {"inc-142", "svc-payments"}
    supported = client.run(
        "MATCH (d:Decision {id: $id})-[:SUPPORTED_BY]->(e:Evidence) RETURN count(e)",
        {"id": props["id"]},
    )
    assert supported[0][0] >= 1
    traversed = client.run(
        "MATCH (d:Decision {id: $id})-[:TRAVERSED]->(e:Evidence) RETURN count(e)",
        {"id": props["id"]},
    )
    assert traversed[0][0] >= 1


def test_full_agent_flow_recommendation_changes():
    """The signature demo, exercised through the orchestrator."""
    first = O.answer("What is the most dangerous unresolved incident?", SESSION)
    assert first["intent"] == "most_dangerous"
    assert first["decision"]["priority"] == "HIGH"
    assert first["decision_id"]

    stored = O.answer("Checkout traffic increased 34%.", SESSION)
    assert stored["intent"] == "remember"
    assert stored["mutations"], "a memory write must report its graph mutations"

    second = O.answer("Re-evaluate the incident.", SESSION)
    assert second["intent"] == "reevaluate"
    assert second["decision"]["priority"] == "CRITICAL"
    assert second["comparison"]["changed"] is True
    assert second["comparison"]["score_delta"] > 0

    why = O.answer("Why did your recommendation change?", SESSION)
    assert why["intent"] == "compare"
    assert why["comparison"]["changed"] is True
    assert any(f["factor"] == "traffic_shift" for f in why["comparison"]["new_risk_factors"])


def test_observability_trace_is_populated():
    result = O.answer("Why is incident #142 critical?", SESSION)
    trace = result["trace"]
    assert trace["intent"] == "explain_why"
    assert trace["query_count"] > 0
    assert trace["graph_queries"]
    assert trace["retrieved_nodes"]
    assert trace["evidence_path"]
    assert trace["decision"]["priority"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")

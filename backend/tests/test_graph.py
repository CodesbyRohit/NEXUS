"""Graph connection, seeding, and traversal."""

from __future__ import annotations

from app.graph import client, schema as S
from app.graph import tools as T


def test_connection_health():
    h = client.health()
    assert h["ok"] is True
    assert h["graph"] == "nexus_test"


def test_seed_is_large_and_connected(seeded_graph):
    stats = client.stats()
    assert stats["nodes"] > 2000, "the demo graph must be substantial"
    assert stats["relationships"] > 5000, "relationships are the point of the product"
    # The schema vocabulary is actually present in the data.
    for label in (S.SERVICE, S.DATABASE, S.INCIDENT, S.IMPACT, S.RUNBOOK, S.PERSON):
        assert label in stats["node_labels"]
    for rel in (S.DEPENDS_ON, S.AFFECTS, S.CAUSED, S.OWNS, S.SUPPORTS, S.IMPACTS):
        assert rel in stats["relationship_types"]


def test_hero_incidents_exist():
    assert T.get_node("inc-142") is not None
    assert T.get_node("inc-91") is not None
    assert T.get_node("db-payments") is not None


def test_service_depends_on_database():
    """Regression: service->database edges must not be silently dropped."""
    deps = T.find_dependencies("svc-payments")["dependencies"]
    ids = {d["id"]: d for d in deps}
    assert "db-payments" in ids, "svc-payments must depend on db-payments"
    assert ids["db-payments"]["hops"] == 1
    assert ids["db-payments"]["label"] == S.DATABASE


def test_dependents_form_blast_radius():
    dependents = T.find_dependents("svc-payments")["dependents"]
    ids = {d["id"] for d in dependents}
    assert "svc-checkout" in ids
    assert len(ids) >= 3


def test_traverse_returns_nodes_and_edges():
    result = T.traverse_graph("inc-142", depth=2, limit=80)
    assert len(result["nodes"]) > 5
    assert len(result["edges"]) > 5
    assert all(isinstance(n["id"], str) for n in result["nodes"])


def test_relationship_traversal_precedents():
    precedents = T.historical_precedents("inc-142")
    ids = {p["id"] for p in precedents}
    assert "inc-91" in ids
    inc91 = next(p for p in precedents if p["id"] == "inc-91")
    revenue = [c for c in inc91["caused"] if c["id"] == "impact-revenue"]
    assert revenue and revenue[0]["amount_usd"] > 0


def test_search_and_history():
    assert any(n["id"] == "inc-142" for n in T.search_graph("inc-142"))
    history = T.get_entity_history("svc-payments")
    assert any(h["id"] == "inc-142" for h in history)


def test_ownership_and_runbook():
    own = T.get_service_ownership("svc-payments")
    assert own["team"]["name"] == "Payments Team"
    assert own["on_call"], "an on-call engineer must be resolvable"
    runbooks = T.get_runbook("svc-payments")
    assert any("connection pool" in r["title"].lower() for r in runbooks)

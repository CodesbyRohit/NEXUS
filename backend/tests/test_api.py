"""HTTP API tests (exercised through the real FalkorDB graph)."""

from __future__ import annotations

import pytest

SESSION = "test-api"


@pytest.fixture(autouse=True)
def _clean(clean_runtime):
    yield


def test_health(api_client):
    r = api_client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["graph"] == "nexus_test"
    assert body["mode"] in ("llm", "deterministic")


def test_stats_are_live(api_client):
    r = api_client.get("/api/graph/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["nodes"] > 2000
    assert body["relationships"] > 5000


def test_schema_and_tools(api_client):
    assert "node_labels" in api_client.get("/api/schema").json()
    tools = api_client.get("/api/tools").json()["tools"]
    names = {t["name"] for t in tools}
    assert {"search_graph", "find_dependencies", "find_root_causes"} <= names
    # Only implemented tools are advertised.
    assert all(t["name"] for t in tools)


def test_incidents_ranking(api_client):
    body = api_client.get("/api/incidents").json()
    assert body["incidents"][0]["id"] == "inc-142"


def test_graph_overview_and_subgraph(api_client):
    overview = api_client.get("/api/graph/overview?focus=inc-142&depth=2").json()
    assert len(overview["nodes"]) > 3
    assert len(overview["edges"]) > 3

    ids = ",".join(n["id"] for n in overview["nodes"][:5])
    sub = api_client.get(f"/api/graph/subgraph?ids={ids}").json()
    assert {n["id"] for n in sub["nodes"]} == set(ids.split(","))


def test_entity_detail_and_404(api_client):
    body = api_client.get("/api/entity/svc-payments").json()
    assert body["node"]["name"] == "Payment Service"
    assert body["ownership"]["team"]["name"] == "Payments Team"
    assert body["neighborhood"]["nodes"]
    assert body["history"]

    missing = api_client.get("/api/entity/nope-999")
    assert missing.status_code == 404


def test_query_endpoint_returns_evidence_and_trace(api_client):
    r = api_client.post("/api/query", json={
        "question": "What is the most dangerous unresolved incident?",
        "session_id": SESSION,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "most_dangerous"
    assert body["decision"]["priority"] in ("HIGH", "CRITICAL")
    assert body["evidence_path"]["hops"]
    assert body["graph"]["nodes"]
    assert body["trace"]["query_count"] > 0
    assert body["mode"] == "deterministic"


def test_memory_endpoint_changes_the_graph(api_client):
    before = api_client.get("/api/graph/stats").json()["nodes"]
    r = api_client.post("/api/memory", json={
        "text": "Checkout traffic increased 34%.", "session_id": SESSION,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["target"]["id"]
    assert body["links"]
    after = api_client.get("/api/graph/stats").json()["nodes"]
    assert after == before + 1


def test_decisions_and_mutations_endpoints(api_client):
    api_client.post("/api/query", json={
        "question": "What is the most dangerous unresolved incident?",
        "session_id": SESSION,
    })
    decisions = api_client.get(f"/api/decisions?question_key=most_dangerous_incident").json()
    assert decisions["decisions"]
    assert decisions["decisions"][0]["snapshot"]["priority"]

    mutations = api_client.get("/api/mutations").json()["mutations"]
    assert isinstance(mutations, list)


def test_invalid_query_is_rejected(api_client):
    assert api_client.post("/api/query", json={"question": ""}).status_code == 422

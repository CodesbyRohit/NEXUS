"""Test fixtures.

Tests run against a dedicated graph (``nexus_test``) so the demo graph is never
disturbed. The graph is seeded once per session and dropped at the end.
"""

from __future__ import annotations

import os

# Must be set before app.config is imported.
os.environ.setdefault("FALKORDB_GRAPH", "nexus_test")

import pytest  # noqa: E402

from app.config import settings  # noqa: E402
from app.graph import client  # noqa: E402
from app.graph import seed as seeder  # noqa: E402

TEST_SESSIONS = ("test", "test-flow", "test-memory", "test-api")


def _purge_runtime_writes() -> None:
    """Remove anything a test wrote, so tests stay independent."""
    try:
        client.run("MATCH (n) WHERE n.source = 'user_memory' DETACH DELETE n")
        client.run(
            "MATCH (d:Decision) WHERE d.session IN $sessions DETACH DELETE d",
            {"sessions": list(TEST_SESSIONS)},
        )
        client.run(
            "MATCH (e:Evidence) WHERE e.session IN $sessions DETACH DELETE e",
            {"sessions": list(TEST_SESSIONS)},
        )
    except Exception:
        pass


@pytest.fixture(scope="session", autouse=True)
def seeded_graph():
    assert settings.graph_name == "nexus_test", "tests must use an isolated graph"
    stats = seeder.seed(reset=True)
    assert stats["nodes"] > 2000
    yield stats
    _purge_runtime_writes()
    try:
        client.get_graph().delete()
    except Exception:
        pass


@pytest.fixture
def clean_runtime():
    _purge_runtime_writes()
    yield
    _purge_runtime_writes()


@pytest.fixture(scope="session")
def api_client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as client_:
        yield client_

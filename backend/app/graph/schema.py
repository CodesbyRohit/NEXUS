"""NEXUS graph schema.

The schema is intentionally explicit: every label and relationship used by the
agent is declared here so the agent's vocabulary and the database agree. Only
relationships that carry real context are created -- the agent traverses these
edges to answer relationship-dependent questions.
"""

from __future__ import annotations

# --- Node labels -----------------------------------------------------------
PERSON = "Person"
TEAM = "Team"
SERVICE = "Service"
SYSTEM = "System"
DATABASE = "Database"
API = "API"
INCIDENT = "Incident"
EVENT = "Event"
CUSTOMER = "Customer"
TRANSACTION = "Transaction"
DOCUMENT = "Document"
RUNBOOK = "Runbook"
DECISION = "Decision"
EVIDENCE = "Evidence"
ACTION = "Action"
QUESTION = "Question"
SESSION = "Session"
IMPACT = "Impact"  # business impact: revenue loss, failed transactions, ...

NODE_LABELS = [
    PERSON,
    TEAM,
    SERVICE,
    SYSTEM,
    DATABASE,
    API,
    INCIDENT,
    EVENT,
    CUSTOMER,
    TRANSACTION,
    DOCUMENT,
    RUNBOOK,
    DECISION,
    EVIDENCE,
    ACTION,
    QUESTION,
    SESSION,
    IMPACT,
]

# --- Relationship types ----------------------------------------------------
OWNS = "OWNS"
WORKS_ON = "WORKS_ON"
DEPENDS_ON = "DEPENDS_ON"
CALLS = "CALLS"
AFFECTS = "AFFECTS"
CAUSED = "CAUSED"
TRIGGERED = "TRIGGERED"
RELATED_TO = "RELATED_TO"
MENTIONED_IN = "MENTIONED_IN"
SUPPORTED_BY = "SUPPORTED_BY"
CONTRADICTS = "CONTRADICTS"
PRECEDED = "PRECEDED"
FOLLOWED = "FOLLOWED"
RESOLVED_BY = "RESOLVED_BY"
DECIDED_BY = "DECIDED_BY"
DERIVED_FROM = "DERIVED_FROM"
IMPACTS = "IMPACTS"
# Supporting relationships that carry genuine context:
SUPPORTS = "SUPPORTS"
MEMBER_OF = "MEMBER_OF"
ON_CALL = "ON_CALL"
DOCUMENTED_BY = "DOCUMENTED_BY"
PRODUCED = "PRODUCED"
TARGETS = "TARGETS"
BASED_ON = "BASED_ON"
TRAVERSED = "TRAVERSED"
PART_OF = "PART_OF"

RELATIONSHIP_TYPES = [
    OWNS,
    WORKS_ON,
    DEPENDS_ON,
    CALLS,
    AFFECTS,
    CAUSED,
    TRIGGERED,
    RELATED_TO,
    MENTIONED_IN,
    SUPPORTED_BY,
    CONTRADICTS,
    PRECEDED,
    FOLLOWED,
    RESOLVED_BY,
    DECIDED_BY,
    DERIVED_FROM,
    IMPACTS,
    SUPPORTS,
    MEMBER_OF,
    ON_CALL,
    DOCUMENTED_BY,
    PRODUCED,
    TARGETS,
    BASED_ON,
    TRAVERSED,
    PART_OF,
]

# Properties used to look nodes up by.
INDEXED = [
    PERSON,
    TEAM,
    SERVICE,
    SYSTEM,
    DATABASE,
    API,
    INCIDENT,
    EVENT,
    CUSTOMER,
    TRANSACTION,
    DOCUMENT,
    RUNBOOK,
    DECISION,
    EVIDENCE,
    ACTION,
    QUESTION,
    SESSION,
    IMPACT,
]

# Extra, non-id indexes that speed up common agent queries.
EXTRA_INDEXES = [
    (INCIDENT, "status"),
    (INCIDENT, "severity"),
    (EVENT, "kind"),
]


def create_indexes(graph) -> None:
    """Create id indexes for every node label (idempotent)."""
    for label in INDEXED:
        try:
            graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.id)")
        except Exception:
            # Index already exists -- FalkorDB raises; that is fine.
            pass
    for label, prop in EXTRA_INDEXES:
        try:
            graph.query(f"CREATE INDEX FOR (n:{label}) ON (n.{prop})")
        except Exception:
            pass


def schema_document() -> dict:
    """Machine-readable schema, exposed via the API for the debug panel."""
    return {
        "node_labels": NODE_LABELS,
        "relationship_types": RELATIONSHIP_TYPES,
        "indexed_labels": INDEXED,
    }

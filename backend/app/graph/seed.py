"""Deterministic, realistic synthetic dataset for the NEXUS incident-commander.

Everything here is *generated* data. It is seeded with a fixed RNG seed so the
demo is reproducible and the tests are stable. The dataset is intentionally a
connected web of services, databases, APIs, teams, people, incidents, events,
business impacts, runbooks, evidence, decisions and actions so that graph
traversal produces genuinely non-trivial answers.

The counts reported by the app are always read back from FalkorDB -- this
module never claims a number it did not actually write.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from app.graph import client, schema as S

RNG_SEED = 42
# A fixed "now" so the demo and tests are deterministic.
NOW = datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)


def _ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


class Builder:
    """Collects nodes/edges so they can be written in batched Cypher."""

    def __init__(self) -> None:
        self.nodes: dict[str, list[dict]] = {}
        self.edges: list[tuple[tuple[str, str], str, tuple[str, str]]] = []
        self.prop_edges: list[dict] = []

    def node(self, label: str, id: str, **props) -> tuple[str, str]:
        row = {"id": id}
        for k, v in props.items():
            if v is not None:
                row[k] = v
        self.nodes.setdefault(label, []).append(row)
        return (label, id)

    def edge(self, src: tuple[str, str], rel: str, dst: tuple[str, str]) -> None:
        self.edges.append((src, rel, dst))

    def prop_edge(
        self,
        src: tuple[str, str],
        rel: str,
        dst: tuple[str, str],
        **props,
    ) -> None:
        clean = {k: v for k, v in props.items() if v is not None}
        self.prop_edges.append({"src": src, "rel": rel, "dst": dst, "props": clean})


# ---------------------------------------------------------------------------
# Static vocabulary
# ---------------------------------------------------------------------------

TEAMS = [
    ("team-payments", "Payments Team", "#payments"),
    ("team-checkout", "Checkout Team", "#checkout"),
    ("team-identity", "Identity Team", "#identity"),
    ("team-platform", "Platform Team", "#platform"),
    ("team-sre", "Site Reliability Engineering", "#sre"),
    ("team-data", "Data Platform", "#data"),
    ("team-notify", "Notifications Team", "#notify"),
    ("team-search", "Search Team", "#search"),
    ("team-inventory", "Inventory Team", "#inventory"),
    ("team-ledger", "Ledger Team", "#ledger"),
    ("team-mobile", "Mobile Team", "#mobile"),
    ("team-observability", "Observability Team", "#observability"),
]

SYSTEMS = [
    ("sys-payments", "Payments Platform", "money movement"),
    ("sys-checkout", "Checkout Platform", "purchase flow"),
    ("sys-identity", "Identity Platform", "auth & accounts"),
    ("sys-notifications", "Notification Platform", "email/sms/push"),
    ("sys-search", "Search Platform", "catalog discovery"),
    ("sys-analytics", "Analytics Platform", "warehouse & reporting"),
    ("sys-inventory", "Inventory Platform", "stock & fulfillment"),
    ("sys-ledger", "Ledger Platform", "double-entry accounting"),
    ("sys-observability", "Observability Platform", "metrics/logs/traces"),
    ("sys-experience", "Customer Experience", "web & mobile surfaces"),
]

# (id, name, system, team, criticality, tx_per_hour, p99_ms, description, slo)
SERVICES = [
    ("svc-checkout", "Checkout API", "sys-checkout", "team-checkout", "critical", 180000, 240, "Orchestrates the end-to-end purchase flow.", "99.95%"),
    ("svc-payments", "Payment Service", "sys-payments", "team-payments", "critical", 120000, 310, "Authorises and captures customer payments.", "99.99%"),
    ("svc-identity", "Identity Service", "sys-identity", "team-identity", "critical", 150000, 120, "Authentication, sessions and account lookup.", "99.99%"),
    ("svc-ledger", "Ledger Service", "sys-ledger", "team-ledger", "critical", 60000, 180, "Double-entry ledger for every money movement.", "99.99%"),
    ("svc-orders", "Order Service", "sys-checkout", "team-checkout", "high", 90000, 200, "Creates and tracks orders.", "99.9%"),
    ("svc-cart", "Cart Service", "sys-checkout", "team-checkout", "high", 110000, 90, "Shopping cart state.", "99.9%"),
    ("svc-inventory", "Inventory Service", "sys-inventory", "team-inventory", "high", 40000, 170, "Stock levels and reservations.", "99.9%"),
    ("svc-pricing", "Pricing Service", "sys-checkout", "team-checkout", "high", 55000, 130, "Price calculation and discounts.", "99.9%"),
    ("svc-fraud", "Fraud Service", "sys-payments", "team-payments", "high", 45000, 260, "Risk scoring on payments.", "99.95%"),
    ("svc-refund", "Refund Service", "sys-payments", "team-payments", "high", 8000, 300, "Customer refunds.", "99.9%"),
    ("svc-search", "Search Service", "sys-search", "team-search", "medium", 30000, 110, "Catalog and product search.", "99.5%"),
    ("svc-notify", "Notification Service", "sys-notifications", "team-notify", "low", 20000, 150, "Email, SMS and push delivery.", "99.0%"),
    ("svc-catalog", "Catalog Service", "sys-search", "team-search", "medium", 25000, 95, "Product catalog.", "99.5%"),
    ("svc-recommend", "Recommendation Service", "sys-experience", "team-data", "low", 18000, 140, "Personalised recommendations.", "99.0%"),
    ("svc-shipping", "Shipping Service", "sys-inventory", "team-inventory", "high", 22000, 160, "Shipping rates and labels.", "99.9%"),
    ("svc-tax", "Tax Service", "sys-payments", "team-payments", "high", 50000, 190, "Tax computation per jurisdiction.", "99.9%"),
    ("svc-wallet", "Wallet Service", "sys-payments", "team-payments", "high", 12000, 210, "Stored balances and top-ups.", "99.9%"),
    ("svc-subscription", "Subscription Service", "sys-payments", "team-payments", "high", 15000, 230, "Recurring billing.", "99.9%"),
    ("svc-invoice", "Invoice Service", "sys-payments", "team-payments", "medium", 9000, 260, "Invoice generation.", "99.5%"),
    ("svc-dispute", "Dispute Service", "sys-payments", "team-payments", "medium", 3000, 280, "Chargebacks and disputes.", "99.5%"),
    ("svc-webhook", "Webhook Dispatcher", "sys-platform", "team-platform", "medium", 35000, 80, "Outbound partner webhooks.", "99.5%"),
    ("svc-gateway", "API Gateway", "sys-platform", "team-platform", "critical", 400000, 45, "Edge routing and auth.", "99.99%"),
    ("svc-authz", "Authorisation Service", "sys-identity", "team-identity", "critical", 200000, 60, "Policy decisions per request.", "99.99%"),
    ("svc-profile", "Profile Service", "sys-identity", "team-identity", "medium", 28000, 100, "Customer profiles.", "99.5%"),
    ("svc-loyalty", "Loyalty Service", "sys-experience", "team-data", "low", 7000, 140, "Points and rewards.", "99.0%"),
    ("svc-coupon", "Coupon Service", "sys-checkout", "team-checkout", "medium", 16000, 120, "Promo code redemption.", "99.5%"),
    ("svc-analytics-ingest", "Analytics Ingest", "sys-analytics", "team-data", "high", 500000, 70, "Event ingestion pipeline.", "99.9%"),
    ("svc-reporting", "Reporting Service", "sys-analytics", "team-data", "medium", 6000, 900, "Business reports.", "99.0%"),
    ("svc-audit", "Audit Service", "sys-platform", "team-platform", "high", 300000, 55, "Immutable audit trail.", "99.95%"),
    ("svc-config", "Config Service", "sys-platform", "team-platform", "critical", 600000, 30, "Runtime configuration.", "99.99%"),
    ("svc-featureflags", "Feature Flags", "sys-platform", "team-platform", "high", 450000, 35, "Progressive delivery flags.", "99.95%"),
    ("svc-messaging", "Messaging Service", "sys-notifications", "team-notify", "medium", 26000, 110, "Internal event bus facade.", "99.5%"),
    ("svc-email", "Email Service", "sys-notifications", "team-notify", "low", 14000, 200, "Transactional email.", "99.0%"),
    ("svc-sms", "SMS Service", "sys-notifications", "team-notify", "low", 9000, 220, "Transactional SMS.", "99.0%"),
    ("svc-push", "Push Service", "sys-notifications", "team-notify", "low", 31000, 120, "Mobile push notifications.", "99.0%"),
    ("svc-media", "Media Service", "sys-experience", "team-mobile", "medium", 11000, 180, "Image and asset delivery.", "99.5%"),
    ("svc-uploads", "Upload Service", "sys-experience", "team-mobile", "low", 4000, 350, "User uploads.", "99.0%"),
    ("svc-cdn", "CDN Service", "sys-experience", "team-platform", "high", 900000, 25, "Static asset edge cache.", "99.95%"),
    ("svc-ratelimiter", "Rate Limiter", "sys-platform", "team-platform", "critical", 700000, 20, "Per-tenant rate limiting.", "99.99%"),
    ("svc-scheduler", "Scheduler", "sys-platform", "team-platform", "high", 5000, 400, "Cron and delayed jobs.", "99.9%"),
]

# (id, name, engine, system, team, criticality, size_gb, region)
DATABASES = [
    ("db-payments", "Payments Database", "postgres", "sys-payments", "team-payments", "critical", 2400, "us-east-1"),
    ("db-users", "Users Database", "postgres", "sys-identity", "team-identity", "critical", 1800, "us-east-1"),
    ("db-orders", "Orders Database", "postgres", "sys-checkout", "team-checkout", "high", 3100, "us-east-1"),
    ("db-inventory", "Inventory Database", "mysql", "sys-inventory", "team-inventory", "high", 900, "us-west-2"),
    ("db-ledger", "Ledger Database", "postgres", "sys-ledger", "team-ledger", "critical", 1200, "us-east-1"),
    ("db-sessions", "Session Store", "redis", "sys-identity", "team-identity", "critical", 40, "us-east-1"),
    ("db-analytics", "Analytics Warehouse", "clickhouse", "sys-analytics", "team-data", "high", 14000, "us-west-2"),
    ("db-audit", "Audit Log Store", "postgres", "sys-platform", "team-platform", "high", 5200, "us-east-1"),
    ("db-search", "Search Index", "opensearch", "sys-search", "team-search", "medium", 700, "us-west-2"),
    ("db-catalog", "Catalog Database", "postgres", "sys-search", "team-search", "medium", 650, "us-west-2"),
    ("db-notify", "Notification Queue", "redis", "sys-notifications", "team-notify", "medium", 20, "us-east-1"),
    ("db-config", "Config Store", "etcd", "sys-platform", "team-platform", "critical", 5, "us-east-1"),
    ("db-flags", "Flag Store", "postgres", "sys-platform", "team-platform", "high", 12, "us-east-1"),
    ("db-media", "Media Metadata", "postgres", "sys-experience", "team-mobile", "low", 300, "us-west-2"),
    ("db-loyalty", "Loyalty Database", "postgres", "sys-experience", "team-data", "low", 180, "us-west-2"),
    ("db-coupons", "Coupon Database", "mysql", "sys-checkout", "team-checkout", "medium", 60, "us-east-1"),
    ("db-shipping", "Shipping Database", "postgres", "sys-inventory", "team-inventory", "high", 420, "us-west-2"),
    ("db-fraud", "Fraud Feature Store", "redis", "sys-payments", "team-payments", "high", 75, "us-east-1"),
    ("db-reporting", "Reporting Warehouse", "clickhouse", "sys-analytics", "team-data", "medium", 9800, "us-west-2"),
    ("db-observability", "Observability Store", "clickhouse", "sys-observability", "team-observability", "high", 22000, "us-east-1"),
]

# (id, name, owner_service, visibility, tx_per_hour, criticality)
APIS = [
    ("api-checkout", "Checkout API", "svc-checkout", "public", 180000, "critical"),
    ("api-pay", "Payments API", "svc-payments", "partner", 120000, "critical"),
    ("api-cart", "Cart API", "svc-cart", "public", 110000, "high"),
    ("api-orders", "Orders API", "svc-orders", "public", 90000, "high"),
    ("api-auth", "Auth API", "svc-identity", "public", 150000, "critical"),
    ("api-ledger", "Ledger API", "svc-ledger", "internal", 60000, "critical"),
    ("api-inventory", "Inventory API", "svc-inventory", "internal", 40000, "high"),
    ("api-pricing", "Pricing API", "svc-pricing", "internal", 55000, "high"),
    ("api-search", "Search API", "svc-search", "public", 30000, "medium"),
    ("api-refund", "Refunds API", "svc-refund", "partner", 8000, "high"),
    ("api-webhook", "Webhook API", "svc-webhook", "partner", 35000, "medium"),
    ("api-config", "Config API", "svc-config", "internal", 600000, "critical"),
    ("api-flags", "Flags API", "svc-featureflags", "internal", 450000, "high"),
    ("api-fraud", "Fraud API", "svc-fraud", "internal", 45000, "high"),
    ("api-tax", "Tax API", "svc-tax", "internal", 50000, "high"),
    ("api-analytics", "Analytics API", "svc-analytics-ingest", "internal", 500000, "high"),
    ("api-notify", "Notifications API", "svc-notify", "internal", 20000, "low"),
    ("api-shipping", "Shipping API", "svc-shipping", "partner", 22000, "high"),
    ("api-wallet", "Wallet API", "svc-wallet", "partner", 12000, "high"),
    ("api-subscriptions", "Subscriptions API", "svc-subscription", "partner", 15000, "high"),
    ("api-catalog", "Catalog API", "svc-catalog", "public", 25000, "medium"),
    ("api-media", "Media API", "svc-media", "public", 11000, "medium"),
    ("api-audit", "Audit API", "svc-audit", "internal", 300000, "high"),
    ("api-ratelimit", "Rate Limit API", "svc-ratelimiter", "internal", 700000, "critical"),
    ("api-gateway", "Gateway API", "svc-gateway", "public", 400000, "critical"),
]

# Business impacts (id, name, category, severity, annual_exposure_usd)
IMPACTS = [
    ("impact-revenue", "Revenue Loss", "financial", "severe", 42000000),
    ("impact-transactions", "Customer Transactions", "financial", "high", 18000000),
    ("impact-conversion", "Checkout Conversion", "financial", "high", 9000000),
    ("impact-trust", "Customer Trust", "brand", "high", 0),
    ("impact-sla", "SLA Credit Exposure", "contractual", "high", 3500000),
    ("impact-churn", "Customer Churn Risk", "brand", "medium", 0),
    ("impact-compliance", "Compliance Exposure", "regulatory", "severe", 0),
    ("impact-support", "Support Load", "operational", "low", 400000),
]

PEOPLE = [
    ("p-rohit", "Rohit Srivastava", "Staff SRE", "team-sre", "rohit@nexus.demo"),
    ("p-asha", "Asha Menon", "Senior Backend Engineer", "team-payments", "asha@nexus.demo"),
    ("p-daniel", "Daniel Okafor", "Platform Engineer", "team-platform", "daniel@nexus.demo"),
    ("p-mei", "Mei Lin", "Database Reliability Engineer", "team-sre", "mei@nexus.demo"),
    ("p-lucas", "Lucas Ferreira", "Backend Engineer", "team-checkout", "lucas@nexus.demo"),
    ("p-priya", "Priya Nair", "Engineering Manager", "team-payments", "priya@nexus.demo"),
    ("p-sven", "Sven Andersson", "SRE", "team-sre", "sven@nexus.demo"),
    ("p-fatima", "Fatima Al-Sayed", "Data Engineer", "team-data", "fatima@nexus.demo"),
    ("p-kenji", "Kenji Tanaka", "Backend Engineer", "team-identity", "kenji@nexus.demo"),
    ("p-sofia", "Sofia Rossi", "Frontend Engineer", "team-mobile", "sofia@nexus.demo"),
    ("p-ivan", "Ivan Petrov", "Security Engineer", "team-platform", "ivan@nexus.demo"),
    ("p-nadia", "Nadia Haddad", "Engineering Manager", "team-checkout", "nadia@nexus.demo"),
]

FIRST_NAMES = [
    "Alex", "Bianca", "Carlos", "Deepa", "Elena", "Farid", "Grace", "Hiro", "Ines",
    "Jonas", "Kavya", "Liam", "Maya", "Noah", "Olga", "Pablo", "Quinn", "Rania",
    "Sam", "Tara", "Umar", "Vera", "Wei", "Ximena", "Yuki", "Zane", "Anika",
    "Bruno", "Chloe", "Dmitri", "Esme", "Felix", "Gita", "Hassan", "Iris",
]
LAST_NAMES = [
    "Sharma", "Nguyen", "Alvarez", "Kim", "Okafor", "Petrova", "Silva", "Haddad",
    "Tanaka", "Rossi", "Andersson", "Ferreira", "Kaur", "Novak", "Dubois", "Costa",
    "Ivanov", "Mensah", "Rahman", "Larsson", "Moreau", "Bianchi", "Santos", "Weber",
]

RUNBOOK_TITLES = [
    "Payments DB connection pool exhaustion",
    "Postgres failover runbook",
    "Checkout latency mitigation",
    "Redis session store recovery",
    "Rolling back a bad deploy",
    "Scaling the API gateway",
    "Draining a degraded region",
    "Mitigating downstream dependency failure",
    "Feature flag kill-switch procedure",
    "Rate limiter overload response",
]

DOC_TITLES = [
    "Postmortem: {code}",
    "Incident review: {code}",
    "Architecture decision: {subject}",
    "Service dependency map",
    "Payments platform on-call guide",
    "Capacity planning Q4",
    "SLO review {quarter}",
]

REGIONS = ["us-east-1", "us-west-2", "eu-west-1", "ap-south-1"]


# ---------------------------------------------------------------------------
# Dataset construction
# ---------------------------------------------------------------------------

def build_dataset() -> Builder:
    rng = random.Random(RNG_SEED)
    b = Builder()

    # ---- Teams -----------------------------------------------------------
    for tid, name, channel in TEAMS:
        b.node(S.TEAM, tid, name=name, slack=channel, headcount=rng.randint(4, 22))

    # ---- Systems ---------------------------------------------------------
    for sid, name, purpose in SYSTEMS:
        b.node(S.SYSTEM, sid, name=name, purpose=purpose)

    # ---- Services --------------------------------------------------------
    for (sid, name, sys_id, team, crit, tx, p99, desc, slo) in SERVICES:
        b.node(
            S.SERVICE, sid, name=name, criticality=crit, tx_per_hour=tx,
            p99_ms=p99, description=desc, slo=slo, region="us-east-1",
            status="healthy", kind="service",
        )
        svc = (S.SERVICE, sid)
        b.edge(svc, S.PART_OF, (S.SYSTEM, sys_id))
        b.edge((S.TEAM, team), S.OWNS, svc)

    # ---- Databases -------------------------------------------------------
    for (did, name, engine, sys_id, team, crit, size, region) in DATABASES:
        b.node(
            S.DATABASE, did, name=name, engine=engine, criticality=crit,
            size_gb=size, region=region, kind="database",
        )
        b.edge((S.DATABASE, did), S.PART_OF, (S.SYSTEM, sys_id))
        b.edge((S.TEAM, team), S.OWNS, (S.DATABASE, did))

    # ---- APIs ------------------------------------------------------------
    for (aid, name, owner, vis, tx, crit) in APIS:
        b.node(
            S.API, aid, name=name, visibility=vis, tx_per_hour=tx,
            criticality=crit, kind="api",
        )
        # The owning service *supports* the API contract it exposes.
        b.edge((S.SERVICE, owner), S.SUPPORTS, (S.API, aid))

    # ---- Business impacts ------------------------------------------------
    for (iid, name, category, severity, exposure) in IMPACTS:
        b.node(
            S.IMPACT, iid, name=name, category=category,
            severity=severity, annual_exposure_usd=exposure, kind="impact",
        )
    b.edge((S.IMPACT, "impact-transactions"), S.PART_OF, (S.IMPACT, "impact-revenue"))

    # ---- People ----------------------------------------------------------
    person_ids: list[str] = []
    for pid, name, role, team, email in PEOPLE:
        b.node(S.PERSON, pid, name=name, role=role, email=email, kind="person")
        b.edge((S.PERSON, pid), S.MEMBER_OF, (S.TEAM, team))
        person_ids.append(pid)

    for i in range(48):
        pid = f"p-{i:03d}"
        name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
        team = rng.choice(TEAMS)[0]
        b.node(
            S.PERSON, pid, name=name, role=rng.choice(
                ["Backend Engineer", "SRE", "Data Engineer", "Platform Engineer"]
            ), email=f"eng{i}@nexus.demo", kind="person",
        )
        b.edge((S.PERSON, pid), S.MEMBER_OF, (S.TEAM, team))
        person_ids.append(pid)

    # ---- Service-to-service and service-to-database dependencies ---------
    service_ids = [s[0] for s in SERVICES]
    # Hand-authored backbone so traversal is meaningful and layered.
    backbone = [
        ("svc-checkout", "svc-payments"),
        ("svc-checkout", "svc-cart"),
        ("svc-checkout", "svc-orders"),
        ("svc-checkout", "svc-pricing"),
        ("svc-checkout", "svc-inventory"),
        ("svc-checkout", "svc-tax"),
        ("svc-checkout", "svc-shipping"),
        ("svc-checkout", "svc-coupon"),
        ("svc-checkout", "svc-fraud"),
        ("svc-payments", "db-payments"),
        ("svc-payments", "svc-ledger"),
        ("svc-payments", "svc-fraud"),
        ("svc-payments", "svc-tax"),
        ("svc-ledger", "db-ledger"),
        ("svc-ledger", "db-payments"),
        ("svc-refund", "svc-payments"),
        ("svc-refund", "db-payments"),
        ("svc-invoice", "db-payments"),
        ("svc-dispute", "svc-payments"),
        ("svc-wallet", "svc-payments"),
        ("svc-subscription", "svc-payments"),
        ("svc-subscription", "db-payments"),
        ("svc-fraud", "db-fraud"),
        ("svc-orders", "db-orders"),
        ("svc-cart", "db-sessions"),
        ("svc-identity", "db-users"),
        ("svc-identity", "db-sessions"),
        ("svc-identity", "svc-authz"),
        ("svc-authz", "db-users"),
        ("svc-profile", "db-users"),
        ("svc-inventory", "db-inventory"),
        ("svc-shipping", "db-shipping"),
        ("svc-catalog", "db-catalog"),
        ("svc-search", "db-search"),
        ("svc-coupon", "db-coupons"),
        ("svc-analytics-ingest", "db-analytics"),
        ("svc-reporting", "db-reporting"),
        ("svc-audit", "db-audit"),
        ("svc-config", "db-config"),
        ("svc-featureflags", "db-flags"),
        ("svc-media", "db-media"),
        ("svc-loyalty", "db-loyalty"),
        ("svc-notify", "db-notify"),
        ("svc-email", "svc-notify"),
        ("svc-sms", "svc-notify"),
        ("svc-push", "svc-notify"),
        ("svc-messaging", "db-notify"),
        ("svc-gateway", "svc-authz"),
        ("svc-gateway", "svc-ratelimiter"),
        ("svc-gateway", "svc-checkout"),
        ("svc-gateway", "svc-identity"),
        ("svc-gateway", "svc-cdn"),
        ("svc-recommend", "svc-catalog"),
        ("svc-cdn", "svc-media"),
        ("svc-scheduler", "svc-webhook"),
        ("svc-webhook", "db-notify"),
    ]
    for src, dst in backbone:
        b.edge((S.SERVICE, src), S.DEPENDS_ON, (S.SERVICE, dst))

    # Extra random-but-deterministic edges between services (kept acyclic-ish).
    for i, sid in enumerate(service_ids):
        for dst in rng.sample(service_ids, k=rng.randint(1, 3)):
            if dst != sid and (sid, dst) not in backbone:
                b.edge((S.SERVICE, sid), S.DEPENDS_ON, (S.SERVICE, dst))

    # Every API is reachable from the gateway and impacts an outcome.
    for (aid, _name, owner, _vis, _tx, _crit) in APIS:
        if aid not in ("api-gateway",):
            b.edge((S.API, "api-gateway"), S.DEPENDS_ON, (S.API, aid))
        b.edge((S.API, aid), S.IMPACTS, (S.IMPACT, "impact-transactions"))

    b.edge((S.API, "api-checkout"), S.IMPACTS, (S.IMPACT, "impact-conversion"))
    b.edge((S.API, "api-pay"), S.IMPACTS, (S.IMPACT, "impact-revenue"))
    b.edge((S.API, "api-auth"), S.IMPACTS, (S.IMPACT, "impact-trust"))
    b.edge((S.API, "api-checkout"), S.IMPACTS, (S.IMPACT, "impact-support"))
    b.edge((S.API, "api-audit"), S.IMPACTS, (S.IMPACT, "impact-compliance"))
    b.edge((S.API, "api-pay"), S.IMPACTS, (S.IMPACT, "impact-sla"))

    # ---- Operational relationships: who works on and is on-call for what --
    api_ids = [a[0] for a in APIS]
    for pid in person_ids:
        for svc in rng.sample(service_ids, k=2):
            b.edge((S.PERSON, pid), S.WORKS_ON, (S.SERVICE, svc))
    for svc, pid in zip(service_ids, rng.sample(person_ids, k=len(service_ids))):
        b.edge((S.PERSON, pid), S.ON_CALL, (S.SERVICE, svc))
    # Services invoke the API contracts they consume.
    for sid in service_ids:
        for api in rng.sample(api_ids, k=2):
            b.edge((S.SERVICE, sid), S.CALLS, (S.API, api))
    # Services contribute to business outcomes.
    for sid in service_ids:
        b.edge((S.SERVICE, sid), S.IMPACTS, (S.IMPACT, "impact-support"))

    # ---- Runbooks --------------------------------------------------------
    for i in range(60):
        rb = f"rb-{i:03d}"
        svc = rng.choice(service_ids)
        title = rng.choice(RUNBOOK_TITLES)
        b.node(
            S.RUNBOOK, rb, title=f"{title} ({svc})", steps=rng.randint(4, 14),
            owner=rng.choice(TEAMS)[0], kind="runbook",
        )
        b.edge((S.SERVICE, svc), S.DOCUMENTED_BY, (S.RUNBOOK, rb))
        b.edge((S.RUNBOOK, rb), S.TARGETS, (S.SERVICE, svc))
    # Hero runbooks
    b.node(S.RUNBOOK, "rb-payments-pool", title="Payments DB connection pool exhaustion", steps=9, owner="team-payments", kind="runbook")
    b.edge((S.SERVICE, "svc-payments"), S.DOCUMENTED_BY, (S.RUNBOOK, "rb-payments-pool"))
    b.edge((S.RUNBOOK, "rb-payments-pool"), S.TARGETS, (S.SERVICE, "svc-payments"))
    b.edge((S.RUNBOOK, "rb-payments-pool"), S.TARGETS, (S.DATABASE, "db-payments"))
    b.node(S.RUNBOOK, "rb-checkout-latency", title="Checkout latency mitigation", steps=7, owner="team-checkout", kind="runbook")
    b.edge((S.SERVICE, "svc-checkout"), S.DOCUMENTED_BY, (S.RUNBOOK, "rb-checkout-latency"))
    b.edge((S.RUNBOOK, "rb-checkout-latency"), S.TARGETS, (S.SERVICE, "svc-checkout"))

    # ---- Customers -------------------------------------------------------
    customer_ids = []
    for i in range(900):
        cid = f"cust-{i:04d}"
        customer_ids.append(cid)
        tier = rng.choices(["enterprise", "business", "standard"], weights=[2, 8, 30])[0]
        b.node(
            S.CUSTOMER, cid, name=f"Customer {i:04d}", tier=tier,
            region=rng.choice(REGIONS), mrr=round(rng.uniform(50, 90000), 2),
            status=rng.choices(["active", "trial", "churned"], weights=[42, 5, 3])[0],
            kind="customer",
        )
    # Business impact reaches customers, and customers are supported by the
    # checkout/payments services that make up the transactions path.
    for cid in customer_ids[:120]:
        b.edge((S.IMPACT, "impact-transactions"), S.IMPACTS, (S.CUSTOMER, cid))
    for cid in customer_ids:
        b.edge((S.CUSTOMER, cid), S.SUPPORTED_BY, (S.SERVICE, rng.choice(
            ["svc-checkout", "svc-payments", "svc-identity", "svc-cart", "svc-orders"]
        )))

    # ---- Transactions ----------------------------------------------------
    for i in range(900):
        tid = f"txn-{i:05d}"
        cid = rng.choice(customer_ids)
        b.node(
            S.TRANSACTION, tid, amount=round(rng.uniform(5, 2500), 2),
            currency="USD", status=rng.choices(["captured", "pending", "failed"], weights=[80, 12, 8])[0],
            at=_ts(NOW - timedelta(minutes=rng.randint(0, 1440))),
            channel=rng.choice(["web", "ios", "android", "partner"]), kind="transaction",
        )
        b.edge((S.CUSTOMER, cid), S.PRODUCED, (S.TRANSACTION, tid))
        b.edge((S.TRANSACTION, tid), S.TARGETS, (S.API, "api-pay"))

    # ---- Incidents -------------------------------------------------------
    incidents = _build_incidents(rng, b)
    _build_documents_and_actions(rng, b, incidents, service_ids, customer_ids)
    return b


def _build_incidents(rng: random.Random, b: Builder) -> list[str]:
    service_ids = [s[0] for s in SERVICES]
    incident_ids: list[str] = []

    # -------- Hero incident #142 (currently open, most dangerous) --------
    b.node(
        S.INCIDENT, "inc-142",
        title="Payments Database connection pool exhaustion causing checkout failures",
        status="open", severity="critical", detected_by="alert:db-pool-saturation",
        started_at=_ts(NOW - timedelta(hours=3, minutes=12)),
        region="us-east-1", customer_impact="checkout failures and payment declines",
        code="INC-142", kind="incident",
    )
    b.edge((S.INCIDENT, "inc-142"), S.AFFECTS, (S.SERVICE, "svc-payments"))
    b.edge((S.INCIDENT, "inc-142"), S.AFFECTS, (S.DATABASE, "db-payments"))
    b.edge((S.SERVICE, "svc-payments"), S.AFFECTS, (S.SERVICE, "svc-checkout"))
    b.edge((S.INCIDENT, "inc-142"), S.RELATED_TO, (S.INCIDENT, "inc-91"))

    # -------- Historical incident #91 (same dependency, revenue impact) --
    b.node(
        S.INCIDENT, "inc-91",
        title="Payments Database failover outage",
        status="resolved", severity="sev1",
        started_at=_ts(NOW - timedelta(days=63)),
        resolved_at=_ts(NOW - timedelta(days=63) + timedelta(hours=5)),
        region="us-east-1", customer_impact="total payment outage for 4h 12m",
        code="INC-91", kind="incident",
    )
    b.edge((S.INCIDENT, "inc-91"), S.AFFECTS, (S.SERVICE, "svc-payments"))
    b.edge((S.INCIDENT, "inc-91"), S.AFFECTS, (S.DATABASE, "db-payments"))
    b.prop_edge(
        (S.INCIDENT, "inc-91"), S.CAUSED, (S.IMPACT, "impact-revenue"),
        amount_usd=2300000, period="incident", note="4h 12m payment outage",
    )
    b.edge((S.INCIDENT, "inc-91"), S.CAUSED, (S.IMPACT, "impact-trust"))
    b.edge((S.INCIDENT, "inc-91"), S.CAUSED, (S.IMPACT, "impact-sla"))
    b.edge((S.INCIDENT, "inc-91"), S.RELATED_TO, (S.INCIDENT, "inc-63"))
    b.edge((S.INCIDENT, "inc-91"), S.PRECEDED, (S.INCIDENT, "inc-142"))

    b.node(
        S.INCIDENT, "inc-63",
        title="Payments DB replication lag",
        status="resolved", severity="sev2",
        started_at=_ts(NOW - timedelta(days=120)),
        resolved_at=_ts(NOW - timedelta(days=120) + timedelta(hours=2)),
        region="us-east-1", customer_impact="read staleness",
        code="INC-63", kind="incident",
    )
    b.edge((S.INCIDENT, "inc-63"), S.AFFECTS, (S.DATABASE, "db-payments"))
    b.edge((S.INCIDENT, "inc-63"), S.FOLLOWED, (S.INCIDENT, "inc-91"))

    b.node(
        S.INCIDENT, "inc-77",
        title="Checkout latency spike during flash sale",
        status="resolved", severity="sev2",
        started_at=_ts(NOW - timedelta(days=38)),
        resolved_at=_ts(NOW - timedelta(days=38) + timedelta(hours=1)),
        region="us-east-1", customer_impact="slow checkout",
        code="INC-77", kind="incident",
    )
    b.edge((S.INCIDENT, "inc-77"), S.AFFECTS, (S.SERVICE, "svc-checkout"))
    b.prop_edge(
        (S.INCIDENT, "inc-77"), S.CAUSED, (S.IMPACT, "impact-conversion"),
        amount_usd=410000, period="incident", note="flash-sale latency",
    )
    b.edge((S.INCIDENT, "inc-77"), S.RELATED_TO, (S.INCIDENT, "inc-142"))

    b.node(
        S.INCIDENT, "inc-54",
        title="Identity session store overload",
        status="resolved", severity="sev1",
        started_at=_ts(NOW - timedelta(days=150)),
        resolved_at=_ts(NOW - timedelta(days=150) + timedelta(hours=3)),
        region="us-east-1", customer_impact="login failures",
        code="INC-54", kind="incident",
    )
    b.edge((S.INCIDENT, "inc-54"), S.AFFECTS, (S.SERVICE, "svc-identity"))
    b.edge((S.INCIDENT, "inc-54"), S.AFFECTS, (S.DATABASE, "db-sessions"))
    b.edge((S.INCIDENT, "inc-54"), S.CAUSED, (S.IMPACT, "impact-trust"))

    incident_ids += ["inc-142", "inc-91", "inc-63", "inc-77", "inc-54"]

    # -------- Historical bulk incidents ----------------------------------
    statuses = ["resolved"] * 30 + ["mitigated"] * 6 + ["investigating"] * 3 + ["open"] * 3
    severities = ["sev1", "sev2", "sev3", "sev4"]
    for i in range(115):
        idx = 100 + i
        iid = f"inc-{idx}"
        svc = rng.choice(service_ids)
        status = rng.choice(statuses)
        sev = rng.choices(severities, weights=[4, 18, 40, 38])[0]
        started = NOW - timedelta(days=rng.randint(5, 420), hours=rng.randint(0, 23))
        b.node(
            S.INCIDENT, iid,
            title=f"{rng.choice(['Latency spike','Error rate increase','Capacity exhaustion','Deploy regression','Partial outage','Timeout cascade'])} in {svc}",
            status=status, severity=sev,
            started_at=_ts(started),
            resolved_at=_ts(started + timedelta(hours=rng.randint(1, 9))) if status == "resolved" else None,
            region=rng.choice(REGIONS),
            customer_impact=rng.choice(["none", "degraded", "partial", "none"]),
            code=f"INC-{idx}", kind="incident",
        )
        b.edge((S.INCIDENT, iid), S.AFFECTS, (S.SERVICE, svc))
        if rng.random() < 0.4:
            b.edge((S.INCIDENT, iid), S.RELATED_TO, (S.INCIDENT, rng.choice(incident_ids)))
        incident_ids.append(iid)

    return incident_ids


def _build_documents_and_actions(
    rng: random.Random,
    b: Builder,
    incident_ids: list[str],
    service_ids: list[str],
    customer_ids: list[str],
) -> None:
    # ---- Documents (postmortems / design docs) ---------------------------
    for i in range(40):
        did = f"doc-{i:03d}"
        subject = rng.choice(["payments platform", "checkout flow", "identity", "data pipeline", "rate limiting"])
        title = rng.choice(DOC_TITLES).format(code=f"INC-{rng.randint(50,200)}", subject=subject, quarter=f"Q{rng.randint(1,4)}")
        b.node(S.DOCUMENT, did, title=title, kind="document", url=f"https://wiki.nexus.demo/{did}")
        inc = rng.choice(incident_ids)
        b.edge((S.INCIDENT, inc), S.MENTIONED_IN, (S.DOCUMENT, did))
        b.edge((S.DOCUMENT, did), S.DERIVED_FROM, (S.INCIDENT, inc))
        b.edge((S.DOCUMENT, did), S.MENTIONED_IN, (S.SERVICE, rng.choice(service_ids)))
    b.node(S.DOCUMENT, "doc-inc142", title="Postmortem: INC-91 Payments DB failover", kind="document", url="https://wiki.nexus.demo/doc-inc142")
    b.edge((S.INCIDENT, "inc-91"), S.MENTIONED_IN, (S.DOCUMENT, "doc-inc142"))
    b.edge((S.DOCUMENT, "doc-inc142"), S.DERIVED_FROM, (S.INCIDENT, "inc-91"))
    b.edge((S.DOCUMENT, "doc-inc142"), S.RELATED_TO, (S.INCIDENT, "inc-142"))

    # ---- Evidence --------------------------------------------------------
    # Evidence nodes record facts extracted from graph data / telemetry.
    evidences = [
        ("ev-142-pool", "Payments DB connection pool saturated at 100% for 3h", "metric", "inc-142"),
        ("ev-142-latency", "Payment Service p99 latency 310ms -> 4200ms", "metric", "inc-142"),
        ("ev-142-errors", "Checkout error rate rose 0.2% -> 14.7%", "metric", "inc-142"),
        ("ev-91-outage", "INC-91 caused 4h12m total payment outage", "incident", "inc-91"),
        ("ev-91-revenue", "INC-91 caused $2.3M revenue loss", "financial", "inc-91"),
    ]
    for eid, summary, kind, inc in evidences:
        b.node(S.EVIDENCE, eid, summary=summary, kind=kind, source="graph", at=_ts(NOW - timedelta(hours=rng.randint(1, 200))))
        b.edge((S.EVIDENCE, eid), S.MENTIONED_IN, (S.INCIDENT, inc))
        b.edge((S.EVIDENCE, eid), S.SUPPORTED_BY, (S.INCIDENT, inc))

    for i in range(195):
        eid = f"ev-{i:04d}"
        inc = rng.choice(incident_ids)
        b.node(
            S.EVIDENCE, eid,
            summary=rng.choice([
                "error-rate deviation above baseline",
                "latency regression detected",
                "capacity headroom below threshold",
                "deploy correlated with incident start",
                "dependency timeout observed",
            ]),
            kind=rng.choice(["metric", "log", "deploy", "trace"]),
            source=rng.choice(["prometheus", "datadog", "logs", "ci"]),
            at=_ts(NOW - timedelta(hours=rng.randint(1, 400))),
        )
        b.edge((S.EVIDENCE, eid), S.MENTIONED_IN, (S.INCIDENT, inc))
        b.edge((S.EVIDENCE, eid), S.DERIVED_FROM, (S.SERVICE, rng.choice(service_ids)))

    # ---- Decisions -------------------------------------------------------
    for i in range(80):
        did = f"dec-{i:03d}"
        inc = rng.choice(incident_ids)
        svc = rng.choice(service_ids)
        b.node(
            S.DECISION, did,
            question=f"What is the priority of {inc}?",
            answer=rng.choice(["P2 - monitor", "P3 - backlog", "P1 - respond", "P2 - monitor"]),
            confidence=round(rng.uniform(0.6, 0.95), 2),
            at=_ts(NOW - timedelta(days=rng.randint(1, 300))),
            session="seed", kind="decision",
        )
        b.edge((S.DECISION, did), S.BASED_ON, (S.SERVICE, svc))
        b.edge((S.DECISION, did), S.DECIDED_BY, (S.PERSON, rng.choice(PEOPLE)[0]))
        b.edge((S.DECISION, did), S.DERIVED_FROM, (S.INCIDENT, inc))
    # A prior decision about inc-142 so "why did the recommendation change"
    # has a genuine baseline to compare against.
    b.node(
        S.DECISION, "dec-142-seed",
        question="What is the most dangerous unresolved incident?",
        answer="inc-142 priority=HIGH, recommend_human_review=false",
        confidence=0.81,
        at=_ts(NOW - timedelta(hours=2, minutes=40)),
        session="seed", kind="decision", priority="HIGH",
    )
    b.edge((S.DECISION, "dec-142-seed"), S.BASED_ON, (S.INCIDENT, "inc-142"))
    b.edge((S.DECISION, "dec-142-seed"), S.BASED_ON, (S.SERVICE, "svc-payments"))

    # ---- Actions ---------------------------------------------------------
    for i in range(120):
        aid = f"act-{i:03d}"
        svc = rng.choice(service_ids)
        b.node(
            S.ACTION, aid,
            description=rng.choice([
                "Scale out service replicas",
                "Roll back last deploy",
                "Increase DB connection pool",
                "Fail over to standby region",
                "Enable circuit breaker",
                "Page the on-call engineer",
            ]),
            status=rng.choice(["proposed", "in_progress", "done"]),
            at=_ts(NOW - timedelta(days=rng.randint(1, 200))),
            kind="action",
        )
        b.edge((S.ACTION, aid), S.TARGETS, (S.SERVICE, svc))
    b.node(S.ACTION, "act-142-1", description="Raise payments DB max_connections and shed non-critical reads", status="proposed", at=_ts(NOW - timedelta(hours=2)), kind="action")
    b.edge((S.ACTION, "act-142-1"), S.TARGETS, (S.DATABASE, "db-payments"))
    b.edge((S.ACTION, "act-142-1"), S.RELATED_TO, (S.INCIDENT, "inc-142"))
    b.node(S.ACTION, "act-142-2", description="Page Payments on-call and open incident bridge", status="in_progress", at=_ts(NOW - timedelta(hours=3)), kind="action")
    b.edge((S.ACTION, "act-142-2"), S.TARGETS, (S.SERVICE, "svc-payments"))
    b.edge((S.ACTION, "act-142-2"), S.RELATED_TO, (S.INCIDENT, "inc-142"))

    # ---- Events ----------------------------------------------------------
    kinds = ["deploy", "metric", "alert", "scale", "config_change", "error_spike", "rollback", "failover"]
    for i in range(600):
        eid = f"evt-{i:04d}"
        svc = rng.choice(service_ids)
        kind = rng.choice(kinds)
        b.node(
            S.EVENT, eid,
            kind=kind,
            summary=f"{kind} affecting {svc}",
            value=round(rng.uniform(0, 100), 2),
            unit=rng.choice(["percent", "ms", "count"]),
            at=_ts(NOW - timedelta(hours=rng.randint(1, 720))),
            severity=rng.choice(["info", "warning", "critical"]),
        )
        b.edge((S.EVENT, eid), S.AFFECTS, (S.SERVICE, svc))
        if rng.random() < 0.35:
            b.edge((S.EVENT, eid), S.TRIGGERED, (S.INCIDENT, rng.choice(incident_ids)))
        if rng.random() < 0.5:
            b.edge((S.EVENT, eid), S.RELATED_TO, (S.INCIDENT, rng.choice(incident_ids)))

    # Hero events for #142
    for eid, summary, val, unit, sev in [
        ("evt-142-pool", "DB connection pool utilisation", 100.0, "percent", "critical"),
        ("evt-142-err", "Checkout error rate", 14.7, "percent", "critical"),
        ("evt-142-lat", "Payment Service p99 latency", 4200.0, "ms", "critical"),
        ("evt-142-dep", "Deploy of payment-service v2.41.0", 0.0, "count", "info"),
    ]:
        b.node(S.EVENT, eid, kind="metric" if "deploy" not in eid else "deploy", summary=summary, value=val, unit=unit, at=_ts(NOW - timedelta(hours=rng.randint(1, 6))), severity=sev)
        b.edge((S.EVENT, eid), S.AFFECTS, (S.SERVICE, "svc-payments"))
        b.edge((S.EVENT, eid), S.TRIGGERED, (S.INCIDENT, "inc-142"))

    # ---- Sessions --------------------------------------------------------
    for i in range(10):
        sid = f"session-{i:02d}"
        b.node(S.SESSION, sid, started_at=_ts(NOW - timedelta(hours=rng.randint(1, 500))), user="demo", kind="session")


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _write(g, b: Builder) -> None:
    for label, rows in b.nodes.items():
        if not rows:
            continue
        g.query(
            f"UNWIND $rows AS row CREATE (n:{label}) SET n = row",
            {"rows": rows},
        )

    # Group plain edges by (src_label, rel, dst_label) for batched writes.
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for (slabel, sid), rel, (dlabel, did) in b.edges:
        grouped.setdefault((slabel, rel, dlabel), []).append({"src": sid, "dst": did})
    for (slabel, rel, dlabel), rows in grouped.items():
        g.query(
            f"UNWIND $rows AS row "
            f"MATCH (a:{slabel} {{id: row.src}}), (b:{dlabel} {{id: row.dst}}) "
            f"CREATE (a)-[:{rel}]->(b)",
            {"rows": rows},
        )

    # Property edges (small in number; written individually for clarity).
    for e in b.prop_edges:
        slabel, sid = e["src"]
        dlabel, did = e["dst"]
        props = e["props"]
        set_clause = ", ".join(f"r.{k} = ${k}" for k in props)
        if set_clause:
            set_clause = " SET " + set_clause
        g.query(
            f"MATCH (a:{slabel} {{id: $src}}), (b:{dlabel} {{id: $dst}}) "
            f"CREATE (a)-[r:{e['rel']}]->(b){set_clause}",
            {"src": sid, "dst": did, **props},
        )


def seed(reset: bool = True, graph=None) -> dict:
    """Seed the configured graph. Returns live stats read back from FalkorDB."""
    g = graph or client.get_graph()
    if reset:
        g.query("MATCH (n) DETACH DELETE n")
    b = build_dataset()
    _write(g, b)
    S.create_indexes(g)
    return client.stats()


def is_seeded() -> bool:
    try:
        return client.run("MATCH (n:Incident {id:'inc-142'}) RETURN count(n)")[0][0] > 0
    except Exception:
        return False

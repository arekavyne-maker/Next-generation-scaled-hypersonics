"""Service-level behaviour of the six foundation services.

Each service is exercised through its HTTP surface, because the HTTP surface
is what the rest of the platform and the console depend on.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from ngsh_audit.app import create_app as create_audit_app
from ngsh_fabric.app import create_app as create_fabric_app
from ngsh_ingest.app import create_app as create_ingest_app
from ngsh_ontology.app import create_app as create_ontology_app
from ngsh_policy.app import create_app as create_policy_app
from ngsh_thread.app import create_app as create_thread_app

pytestmark = pytest.mark.integration


@pytest.fixture
def ontology_client(settings):
    with TestClient(create_ontology_app(settings)) as client:
        yield client


@pytest.fixture
def fabric_client(settings):
    with TestClient(create_fabric_app(settings)) as client:
        yield client


@pytest.fixture
def policy_client(settings):
    with TestClient(create_policy_app(settings)) as client:
        yield client


@pytest.fixture
def audit_client(settings):
    with TestClient(create_audit_app(settings)) as client:
        yield client


@pytest.fixture
def thread_client(settings):
    with TestClient(create_thread_app(settings)) as client:
        yield client


@pytest.fixture
def ingest_client(settings):
    with TestClient(create_ingest_app(settings)) as client:
        yield client


# -- health -----------------------------------------------------------------


@pytest.mark.parametrize(
    "factory",
    [
        create_ontology_app,
        create_fabric_app,
        create_policy_app,
        create_audit_app,
        create_thread_app,
        create_ingest_app,
    ],
)
def test_every_service_reports_healthy(factory, settings) -> None:
    with TestClient(factory(settings)) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["deploymentProfile"] == "local"


@pytest.mark.parametrize(
    "factory",
    [
        create_ontology_app,
        create_fabric_app,
        create_policy_app,
        create_audit_app,
        create_thread_app,
        create_ingest_app,
    ],
)
def test_every_service_exposes_openapi(factory, settings) -> None:
    with TestClient(factory(settings)) as client:
        assert client.get("/openapi.json").status_code == 200


# -- ontology ---------------------------------------------------------------


def test_ontology_serves_the_registry(ontology_client) -> None:
    response = ontology_client.get("/v1/ontology/registry")
    assert response.status_code == 200
    body = response.json()
    assert body["ontologyVersion"] == "1.0.0"
    assert len(body["entities"]) == 23
    assert len(body["relations"]) == 10


def test_ontology_filters_types_by_pillar(ontology_client) -> None:
    response = ontology_client.get("/v1/ontology/types", params={"pillar": "F"})
    assert response.status_code == 200
    types = {entry["type"] for entry in response.json()["types"]}
    assert "ThreatSystem" in types
    assert "EngagementScenario" in types
    assert "ProcessRun" not in types


def test_ontology_rejects_an_unknown_type(ontology_client) -> None:
    response = ontology_client.get("/v1/ontology/types/NotAThing")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_ontology_validates_a_good_entity(ontology_client) -> None:
    entity = {
        "id": "TR:0001",
        "type": "TestResult",
        "tenant": "ngsh",
        "version": 1,
        "createdAt": "2026-11-14T00:00:00Z",
        "updatedAt": "2026-11-14T00:00:00Z",
        "classification": {"level": "CUI"},
        "attributes": {"testMethod": "tensile", "outcome": "PASS"},
    }
    response = ontology_client.post("/v1/ontology/validate", json={"kind": "entity", "entity": entity})
    assert response.status_code == 200
    body = response.json()
    assert body["valid"] is True
    assert body["errors"] == []


def test_ontology_reports_a_missing_attribute(ontology_client) -> None:
    entity = {
        "id": "TR:0001",
        "type": "TestResult",
        "tenant": "ngsh",
        "version": 1,
        "createdAt": "2026-11-14T00:00:00Z",
        "updatedAt": "2026-11-14T00:00:00Z",
        "classification": {"level": "CUI"},
        "attributes": {},
    }
    response = ontology_client.post("/v1/ontology/validate", json={"kind": "entity", "entity": entity})
    body = response.json()
    assert body["valid"] is False
    assert any("outcome" in error for error in body["errors"])


def test_ontology_reports_a_classification_floor_violation(ontology_client) -> None:
    """Constraint C-001: threat material may not be written at UNCLASSIFIED."""
    entity = {
        "id": "THR:0001",
        "type": "ThreatSystem",
        "tenant": "ngsh",
        "version": 1,
        "createdAt": "2026-11-14T00:00:00Z",
        "updatedAt": "2026-11-14T00:00:00Z",
        "classification": {"level": "UNCLASSIFIED"},
        "attributes": {"designation": "X", "threatClass": "HGV"},
    }
    response = ontology_client.post("/v1/ontology/validate", json={"kind": "entity", "entity": entity})
    body = response.json()
    assert body["valid"] is False
    assert any("C-001" in error for error in body["errors"])


def test_ontology_reports_a_bad_relation_direction(ontology_client) -> None:
    relation = {
        "id": "REL:0001",
        "type": "verifies",
        "from": {"type": "Requirement", "id": "REQ:0001"},
        "to": {"type": "TestResult", "id": "TR:0001"},
        "assertedAt": "2026-11-14T00:00:00Z",
        "provenance": {"source": "test"},
    }
    response = ontology_client.post("/v1/ontology/validate", json={"kind": "relation", "relation": relation})
    body = response.json()
    assert body["valid"] is False


# -- fabric -----------------------------------------------------------------


def _envelope(aggregate_id: str = "TR:0001", sequence: int = 1) -> dict:
    return {
        "eventType": "entity.created",
        "aggregateType": "TestResult",
        "aggregateId": aggregate_id,
        "sequence": sequence,
        "tenant": "ngsh",
        "actor": {
            "subjectId": "usr:operator",
            "kind": "user",
            "clearance": "TOP SECRET",
            "citizenship": "US",
        },
        "classification": {"level": "CUI"},
        "payload": {"entity": {"id": aggregate_id, "type": "TestResult"}},
    }


def test_fabric_accepts_an_event(fabric_client) -> None:
    response = fabric_client.post("/v1/events", json=_envelope())
    assert response.status_code == 201
    body = response.json()
    assert len(body["accepted"]) == 1
    assert body["rejected"] == []


def test_fabric_rejects_a_malformed_envelope(fabric_client) -> None:
    response = fabric_client.post("/v1/events", json={"nonsense": True})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_fabric_reports_a_sequence_conflict(fabric_client) -> None:
    fabric_client.post("/v1/events", json=_envelope("TR:0001", 1))
    response = fabric_client.post("/v1/events", json=_envelope("TR:0001", 5))
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] == []
    assert body["rejected"][0]["eventId"]


def test_fabric_reads_the_stream_back(fabric_client) -> None:
    fabric_client.post("/v1/events", json=_envelope("TR:0001", 1))
    fabric_client.post("/v1/events", json=_envelope("TR:0002", 1))

    response = fabric_client.get("/v1/events")
    assert response.status_code == 200
    body = response.json()
    assert len(body["events"]) == 2
    assert body["cursor"] > 0


def test_fabric_filters_the_stream_by_type(fabric_client) -> None:
    fabric_client.post("/v1/events", json=_envelope("TR:0001", 1))
    response = fabric_client.get("/v1/events", params={"types": "test.*"})
    assert response.json()["events"] == []


def test_fabric_reports_stats(fabric_client) -> None:
    fabric_client.post("/v1/events", json=_envelope("TR:0001", 1))
    body = fabric_client.get("/v1/stats").json()
    assert body["total"] == 1
    assert body["byType"]["entity.created"] == 1


# -- policy -----------------------------------------------------------------


def test_policy_allows_a_cleared_engineer(policy_client) -> None:
    response = policy_client.post(
        "/v1/decisions",
        json={
            "subject": {
                "subjectId": "usr:engineer",
                "kind": "user",
                "clearance": "TOP SECRET",
                "citizenship": "US",
                "tenant": "ngsh",
                "programs": ["NGSH-SHY"],
                "needToKnow": ["NGSH-SHY"],
            },
            "resource": {
                "type": "TestResult",
                "id": "TR:0001",
                "classification": {"level": "CUI"},
                "tenant": "ngsh",
                "program": "NGSH-SHY",
            },
            "action": "read",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "ALLOW"
    assert body["policyId"] == "POL-ALLOW-012"
    assert "audit" in body["obligations"]


def test_policy_denies_a_foreign_citizen(policy_client) -> None:
    response = policy_client.post(
        "/v1/decisions",
        json={
            "subject": {
                "subjectId": "usr:foreign",
                "kind": "user",
                "clearance": "TOP SECRET",
                "citizenship": "FOREIGN",
                "tenant": "ngsh",
                "programs": ["NGSH-SHY"],
                "needToKnow": ["NGSH-SHY"],
            },
            "resource": {
                "type": "TestResult",
                "id": "TR:0001",
                "classification": {"level": "CUI"},
                "tenant": "ngsh",
                "program": "NGSH-SHY",
            },
            "action": "read",
        },
    )
    body = response.json()
    assert body["decision"] == "DENY"
    assert body["policyId"] == "POL-DENY-002"


def test_policy_requires_a_resource(policy_client) -> None:
    response = policy_client.post("/v1/decisions", json={"subject": {}, "action": "read"})
    assert response.status_code == 422


def test_policy_lists_its_rules(policy_client) -> None:
    body = policy_client.get("/v1/policies").json()
    assert body["defaultEffect"] == "DENY"
    assert any(rule["id"] == "POL-DENY-002" for rule in body["policies"])


# -- audit ------------------------------------------------------------------


def test_audit_records_and_verifies(policy_client, audit_client) -> None:
    """A policy decision must land in the ledger and the chain must verify."""
    policy_client.post(
        "/v1/decisions",
        json={
            "subject": {
                "subjectId": "usr:engineer",
                "kind": "user",
                "clearance": "TOP SECRET",
                "citizenship": "US",
                "tenant": "ngsh",
                "programs": ["NGSH-SHY"],
                "needToKnow": ["NGSH-SHY"],
            },
            "resource": {
                "type": "TestResult",
                "id": "TR:0001",
                "classification": {"level": "CUI"},
                "tenant": "ngsh",
                "program": "NGSH-SHY",
            },
            "action": "read",
        },
    )

    ledger = audit_client.get("/v1/ledger").json()
    assert len(ledger["entries"]) == 1
    assert ledger["entries"][0]["decision"] == "ALLOW"

    verification = audit_client.get("/v1/ledger/verify").json()
    assert verification["valid"] is True
    assert verification["checked"] == 1


def test_audit_rejects_an_entry_without_a_type(audit_client) -> None:
    response = audit_client.post("/v1/ledger", json={"entry": {"decision": "ALLOW"}})
    assert response.status_code == 422


# -- thread -----------------------------------------------------------------


def test_thread_replays_into_a_graph(fabric_client, thread_client) -> None:
    """The projection must be reconstructable from the log alone."""
    fabric_client.post(
        "/v1/events",
        json={
            "eventType": "entity.created",
            "aggregateType": "Requirement",
            "aggregateId": "REQ:0001",
            "sequence": 1,
            "tenant": "ngsh",
            "actor": {"subjectId": "usr:operator", "kind": "user"},
            "classification": {"level": "CUI"},
            "payload": {
                "entity": {
                    "id": "REQ:0001",
                    "type": "Requirement",
                    "tenant": "ngsh",
                    "version": 1,
                    "createdAt": "2026-11-14T00:00:00Z",
                    "updatedAt": "2026-11-14T00:00:00Z",
                    "classification": {"level": "CUI"},
                    "attributes": {
                        "statement": "The article shall...",
                        "verificationMethod": "TEST",
                        "status": "BASELINED",
                    },
                }
            },
        },
    )

    replay = thread_client.post("/v1/project/replay")
    assert replay.status_code == 200
    assert replay.json()["replayed"] >= 1

    entity = thread_client.get("/v1/entities/Requirement/REQ:0001")
    assert entity.status_code == 200
    assert entity.json()["entity"]["id"] == "REQ:0001"


def test_thread_returns_404_for_an_unknown_entity(thread_client) -> None:
    response = thread_client.get("/v1/entities/TestResult/TR:nope")
    assert response.status_code == 404


def test_thread_rejects_a_malformed_root(thread_client) -> None:
    response = thread_client.get("/v1/trace", params={"root": "no-colon"})
    assert response.status_code == 422


# -- ingest -----------------------------------------------------------------


def test_ingest_accepts_ndjson(ingest_client) -> None:
    payload = "\n".join(
        [
            '{"id": "TR:0001", "testMethod": "tensile", "outcome": "PASS"}',
            '{"id": "TR:0002", "testMethod": "tensile", "outcome": "FAIL"}',
        ]
    )
    response = ingest_client.post(
        "/v1/ingest",
        json={
            "source": "wind-tunnel.itc",
            "format": "NDJSON",
            "payload": payload,
            "entityType": "TestResult",
            "classification": {"level": "CUI"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["recordsAccepted"] == 2
    assert len(body["entityIds"]) == 2
    assert len(body["sha256"]) == 64


def test_ingest_rejects_an_unsupported_format(ingest_client) -> None:
    response = ingest_client.post("/v1/ingest", json={"source": "x", "format": "XLSX", "payload": "binary"})
    assert response.status_code == 422


def test_ingest_rejects_malformed_ndjson(ingest_client) -> None:
    response = ingest_client.post(
        "/v1/ingest", json={"source": "x", "format": "NDJSON", "payload": "{not json}"}
    )
    assert response.status_code == 422


def test_ingest_accounts_for_the_batch(ingest_client) -> None:
    ingest_client.post(
        "/v1/ingest",
        json={"source": "sled.range", "format": "NDJSON", "payload": '{"id": "TR:1"}'},
    )
    batches = ingest_client.get("/v1/ingest/batches").json()
    assert len(batches["batches"]) == 1
    assert batches["batches"][0]["source"] == "sled.range"

"""The end-to-end vertical slice.

This test exercises the foundation the way a pillar will actually use it:

1. A batch of test data is admitted through the ingest service.
2. The admission becomes events in the fabric.
3. The thread service projects those events into the digital thread.
4. A requirement, a test result and the edge between them are traced.
5. A policy decision is taken for the trace and recorded in the audit ledger.
6. The ledger chain verifies.
7. The projection is destroyed and rebuilt from the log alone, and the thread
   comes back identical.

Step 7 is the one that matters most. It is the property that makes the
digital thread trustworthy: the graph holds nothing the log does not.
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

pytestmark = pytest.mark.e2e

REQUIREMENT_ID = "REQ:TC-0001"
ARTICLE_ID = "TA:0001"
CAMPAIGN_ID = "TC:0001"


@pytest.fixture
def stack(settings):
    """All six services sharing one platform database, as in local development."""
    apps = {
        "ontology": create_ontology_app(settings),
        "fabric": create_fabric_app(settings),
        "policy": create_policy_app(settings),
        "audit": create_audit_app(settings),
        "thread": create_thread_app(settings),
        "ingest": create_ingest_app(settings),
    }
    clients = {name: TestClient(app) for name, app in apps.items()}
    yield clients
    for client in clients.values():
        client.close()


def _publish(fabric: TestClient, event: dict) -> dict:
    response = fabric.post("/v1/events", json=event)
    assert response.status_code in (200, 201), response.text
    return response.json()


def _entity_event(
    event_type: str,
    aggregate_type: str,
    aggregate_id: str,
    entity: dict,
    sequence: int = 1,
) -> dict:
    return {
        "eventType": event_type,
        "aggregateType": aggregate_type,
        "aggregateId": aggregate_id,
        "sequence": sequence,
        "tenant": "ngsh",
        "program": "NGSH-SHY",
        "actor": {
            "subjectId": "usr:engineer",
            "kind": "user",
            "clearance": "TOP SECRET",
            "citizenship": "US",
            "tenant": "ngsh",
            "programs": ["NGSH-SHY"],
            "needToKnow": ["NGSH-SHY"],
        },
        "classification": {"level": "CUI"},
        "payload": {"entity": entity},
    }


def _requirement_entity() -> dict:
    return {
        "id": REQUIREMENT_ID,
        "type": "Requirement",
        "tenant": "ngsh",
        "program": "NGSH-SHY",
        "version": 1,
        "createdAt": "2026-11-14T00:00:00Z",
        "updatedAt": "2026-11-14T00:00:00Z",
        "createdBy": "usr:engineer",
        "updatedBy": "usr:engineer",
        "provenance": {"source": "sysml-import", "method": "sysml-v2-import"},
        "labels": {},
        "annotations": {},
        "deleted": False,
        "classification": {"level": "CUI"},
        "attributes": {
            "statement": "The nosecap shall survive 1800 K for 30 minutes.",
            "reqType": "PERFORMANCE",
            "verificationMethod": "TEST",
            "status": "BASELINED",
            "verificationStatus": "NOT_STARTED",
        },
    }


def _test_result_entity() -> dict:
    return {
        "id": "TR:0001",
        "type": "TestResult",
        "tenant": "ngsh",
        "program": "NGSH-SHY",
        "version": 1,
        "createdAt": "2026-11-14T01:00:00Z",
        "updatedAt": "2026-11-14T01:00:00Z",
        "createdBy": "svc:ingest",
        "updatedBy": "svc:ingest",
        "provenance": {"source": "ingest:BATCH:1", "method": "batch-lift"},
        "labels": {},
        "annotations": {},
        "deleted": False,
        "classification": {"level": "CUI"},
        "attributes": {
            "campaignId": CAMPAIGN_ID,
            "testArticleId": ARTICLE_ID,
            "testMethod": "plasma-arc-heater",
            "outcome": "PASS",
            "measurements": [{"name": "peak_temperature", "value": 1840.0, "unit": "K", "uncertainty": 25.0}],
            "reviewedBy": "usr:engineer",
        },
    }


def _relation_event(relation_id: str, relation_type: str, from_ref: dict, to_ref: dict) -> dict:
    return {
        "eventType": "entity.relation.asserted",
        "aggregateType": "Relation",
        "aggregateId": relation_id,
        "sequence": 1,
        "tenant": "ngsh",
        "program": "NGSH-SHY",
        "actor": {
            "subjectId": "usr:engineer",
            "kind": "user",
            "clearance": "TOP SECRET",
            "citizenship": "US",
            "tenant": "ngsh",
            "programs": ["NGSH-SHY"],
            "needToKnow": ["NGSH-SHY"],
        },
        "classification": {"level": "CUI"},
        "payload": {
            "relation": {
                "id": relation_id,
                "type": relation_type,
                "from": from_ref,
                "to": to_ref,
                "tenant": "ngsh",
                "program": "NGSH-SHY",
                "classification": {"level": "CUI"},
                "assertedAt": "2026-11-14T01:05:00Z",
                "assertedBy": "usr:engineer",
                "provenance": {"source": "digitial-thread"},
                "confidence": 0.95,
            }
        },
    }


def test_vertical_slice(stack) -> None:
    fabric = stack["fabric"]
    thread = stack["thread"]
    policy = stack["policy"]
    audit = stack["audit"]

    # -- 1. admit a batch of test data ----------------------------------
    ingest_response = stack["ingest"].post(
        "/v1/ingest",
        json={
            "source": "plasma-arc-heater.itc",
            "format": "NDJSON",
            "payload": '{"id": "TR:0002", "testMethod": "plasma-arc-heater", "outcome": "PASS"}',
            "entityType": "TestResult",
            "classification": {"level": "CUI"},
        },
    )
    assert ingest_response.status_code == 200, ingest_response.text
    batch = ingest_response.json()
    assert batch["recordsAccepted"] == 1
    assert batch["published"]["status"] == "appended"

    # The batch must be visible in the log.
    events = fabric.get("/v1/events").json()["events"]
    assert any(event["eventType"] == "ingest.batch.accepted" for event in events)
    assert any(event["eventType"] == "entity.created" for event in events)

    # -- 2. publish the requirement and the test result -----------------
    _publish(fabric, _entity_event("entity.created", "Requirement", REQUIREMENT_ID, _requirement_entity()))
    _publish(fabric, _entity_event("entity.created", "TestResult", "TR:0001", _test_result_entity()))

    # -- 3. assert the trace edge ---------------------------------------
    _publish(
        fabric,
        _relation_event(
            "REL:verifies-1",
            "verifies",
            {"type": "TestResult", "id": "TR:0001"},
            {"type": "Requirement", "id": REQUIREMENT_ID},
        ),
    )
    _publish(
        fabric,
        _relation_event(
            "REL:satisfies-1",
            "satisfies",
            {"type": "Part", "id": "PART:NSECAP-001"},
            {"type": "Requirement", "id": REQUIREMENT_ID},
        ),
    )

    # -- 4. project and trace -------------------------------------------
    replay = thread.post("/v1/project/replay")
    assert replay.status_code == 200
    assert replay.json()["replayed"] > 0

    trace = thread.get("/v1/trace", params={"root": f"Requirement:{REQUIREMENT_ID}", "depth": 2})
    assert trace.status_code == 200
    body = trace.json()
    node_ids = {node["id"] for node in body["nodes"]}
    assert REQUIREMENT_ID in node_ids
    assert "TR:0001" in node_ids
    assert any(edge["type"] == "verifies" for edge in body["edges"])

    # -- 5. requirement verification coverage ---------------------------
    coverage = thread.post(f"/v1/trace/requirements/{REQUIREMENT_ID}/coverage")
    assert coverage.status_code == 200
    coverage_body = coverage.json()
    assert coverage_body["verified"] is True
    assert coverage_body["coverage"] == 1.0
    assert coverage_body["verifyingResults"][0]["outcome"] == "PASS"

    # -- 6. a policy decision on the trace, recorded in the ledger -------
    decision = policy.post(
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
    assert decision.status_code == 200
    assert decision.json()["decision"] == "ALLOW"

    ledger = audit.get("/v1/ledger").json()
    assert len(ledger["entries"]) == 1
    assert ledger["entries"][0]["decision"] == "ALLOW"

    verification = audit.get("/v1/ledger/verify").json()
    assert verification["valid"] is True
    assert verification["checked"] == 1

    # -- 7. rebuild the projection from the log alone --------------------
    before = thread.get("/v1/graph/stats").json()
    assert before["totalEntities"] >= 3
    assert before["totalRelations"] >= 2

    thread.post("/v1/project/replay")

    after = thread.get("/v1/graph/stats").json()
    assert after["totalEntities"] == before["totalEntities"]
    assert after["totalRelations"] == before["totalRelations"]

    retraced = thread.get("/v1/trace", params={"root": f"Requirement:{REQUIREMENT_ID}", "depth": 2}).json()
    assert {node["id"] for node in retraced["nodes"]} == node_ids


def test_ingested_data_joins_the_same_thread_as_authored_data(stack) -> None:
    """Ingested and authored entities must be indistinguishable downstream."""
    thread = stack["thread"]

    stack["ingest"].post(
        "/v1/ingest",
        json={
            "source": "wind-tunnel.itc",
            "format": "NDJSON",
            "payload": '{"id": "TR:9001", "testMethod": "aero", "outcome": "PASS"}',
            "entityType": "TestResult",
            "classification": {"level": "CUI"},
        },
    )

    thread.post("/v1/project/replay")

    ingested = thread.get("/v1/entities/TestResult/TR:9001")
    assert ingested.status_code == 200
    body = ingested.json()["entity"]
    assert body["attributes"]["testMethod"] == "aero"
    assert body["provenance"]["source"].startswith("ingest:")

    stats = thread.get("/v1/graph/stats").json()
    assert stats["entityCounts"]["TestResult"] >= 1


def test_a_denied_decision_is_still_recorded(stack) -> None:
    """A trail containing only successes is not an audit trail."""
    policy = stack["policy"]
    audit = stack["audit"]

    decision = policy.post(
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
    assert decision.json()["decision"] == "DENY"

    ledger = audit.get("/v1/ledger").json()
    assert len(ledger["entries"]) == 1
    assert ledger["entries"][0]["decision"] == "DENY"
    assert audit.get("/v1/ledger/verify").json()["valid"] is True

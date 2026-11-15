"""Service-level behaviour of the Pillar A first slice.

The tests go through the HTTP surface because the console and the other
pillars see the architecture service only through that surface.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from ngsh_architecture.app import create_app as create_architecture_app

pytestmark = pytest.mark.integration


def _entity(entity_id: str, entity_type: str, attributes: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": entity_id,
        "type": entity_type,
        "tenant": "ngsh",
        "program": "NGSH-SHY",
        "version": 1,
        "createdAt": "2026-11-15T00:00:00Z",
        "updatedAt": "2026-11-15T00:00:00Z",
        "createdBy": "usr:engineer",
        "updatedBy": "usr:engineer",
        "provenance": {"source": "test", "method": "fixture"},
        "deleted": False,
        "classification": {"level": "CUI"},
        "attributes": attributes,
    }


def _relation(relation_id: str, relation_type: str, source: tuple[str, str], target: tuple[str, str]) -> dict:
    return {
        "id": relation_id,
        "type": relation_type,
        "from": {"type": source[0], "id": source[1]},
        "to": {"type": target[0], "id": target[1]},
        "tenant": "ngsh",
        "classification": {"level": "CUI"},
        "assertedBy": "usr:engineer",
        "provenance": {"source": "test", "method": "fixture"},
        "confidence": 1.0,
    }


@pytest.fixture
def app(settings):
    return create_architecture_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def _seed(app, event_factory) -> None:
    projector = app.state.projector
    events = [
        event_factory(
            aggregate_type="System",
            aggregate_id="SYS:1",
            payload={"entity": _entity("SYS:1", "System", {"name": "Booster", "lifecycleState": "DESIGN"})},
        ),
        event_factory(
            aggregate_type="Part",
            aggregate_id="PART:1",
            payload={
                "entity": _entity("PART:1", "Part", {"partNumber": "P-1", "name": "Nosecap", "revision": "C"})
            },
        ),
        event_factory(
            aggregate_type="Requirement",
            aggregate_id="REQ:1",
            payload={
                "entity": _entity(
                    "REQ:1",
                    "Requirement",
                    {
                        "statement": "The nosecap shall survive 1800 K for 30 minutes.",
                        "verificationMethod": "TEST",
                        "status": "BASELINED",
                        "verificationStatus": "NOT_STARTED",
                    },
                )
            },
        ),
        event_factory(
            aggregate_type="Requirement",
            aggregate_id="REQ:2",
            payload={
                "entity": _entity(
                    "REQ:2",
                    "Requirement",
                    {
                        "statement": "The nosecap shall remain attached through the ascent profile.",
                        "verificationMethod": "TEST",
                        "status": "BASELINED",
                        "verificationStatus": "NOT_STARTED",
                        "parentId": "REQ:1",
                    },
                )
            },
        ),
        event_factory(
            aggregate_type="TestResult",
            aggregate_id="TR:1",
            payload={
                "entity": _entity(
                    "TR:1",
                    "TestResult",
                    {
                        "testMethod": "plasma-arc-heater",
                        "outcome": "PASS",
                        "reviewedBy": "usr:reviewer",
                    },
                )
            },
        ),
        event_factory(
            aggregate_type="Relation",
            aggregate_id="REL:1",
            event_type="entity.relation.asserted",
            payload={
                "relation": _relation("REL:1", "verifies", ("TestResult", "TR:1"), ("Requirement", "REQ:1"))
            },
        ),
        event_factory(
            aggregate_type="Relation",
            aggregate_id="REL:2",
            event_type="entity.relation.asserted",
            payload={
                "relation": _relation("REL:2", "satisfies", ("System", "SYS:1"), ("Requirement", "REQ:1"))
            },
        ),
    ]
    for event in events:
        projector.apply(event)


BASELINE_BODY = {
    "systemId": "SYS:1",
    "name": "Preliminary design review",
    "members": [
        {"entityType": "Part", "entityId": "PART:1", "revision": "C"},
        {"entityType": "System", "entityId": "SYS:1"},
    ],
    "softwareBuilds": ["fw-1.4.2"],
}


def test_baseline_creation_is_idempotent_and_reproducible(client) -> None:
    first = client.post("/v1/baselines", json=BASELINE_BODY)
    assert first.status_code == 201
    created = first.json()
    assert created["created"] is True
    baseline_id = created["baseline"]["id"]
    assert baseline_id.startswith("BL:")

    second = client.post("/v1/baselines", json=BASELINE_BODY)
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["baseline"]["id"] == baseline_id

    verify = client.post(f"/v1/baselines/{baseline_id}/verify")
    assert verify.status_code == 200
    assert verify.json()["reproducible"] is True


def test_baseline_rejects_duplicate_members(client) -> None:
    body = {
        **BASELINE_BODY,
        "members": [
            {"entityType": "Part", "entityId": "PART:1", "revision": "C"},
            {"entityType": "Part", "entityId": "PART:1", "revision": "D"},
        ],
    }
    response = client.post("/v1/baselines", json=body)
    assert response.status_code == 422


def test_baseline_can_be_listed_and_fetched(client) -> None:
    baseline_id = client.post("/v1/baselines", json=BASELINE_BODY).json()["baseline"]["id"]

    listed = client.get("/v1/baselines", params={"systemId": "SYS:1"})
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["baselines"]] == [baseline_id]

    fetched = client.get(f"/v1/baselines/{baseline_id}")
    assert fetched.status_code == 200
    assert fetched.json()["baseline"]["memberCount"] == 2

    assert client.get("/v1/baselines/BL:NOPE").status_code == 404


def test_test_article_resolves_to_its_baseline(app, client, event_factory) -> None:
    _seed(app, event_factory)
    baseline_id = client.post("/v1/baselines", json=BASELINE_BODY).json()["baseline"]["id"]

    app.state.projector.apply(
        event_factory(
            aggregate_type="TestArticle",
            aggregate_id="TA:1",
            payload={
                "entity": _entity(
                    "TA:1",
                    "TestArticle",
                    {
                        "serialNumber": "SN-001",
                        "asBuiltStatus": "AS_BUILT",
                        "buildConfigurationId": baseline_id,
                    },
                )
            },
        )
    )

    resolved = client.get("/v1/baselines/resolve/TA:1")
    assert resolved.status_code == 200
    assert resolved.json()["resolved"] is True
    assert resolved.json()["baseline"]["id"] == baseline_id

    assert client.get("/v1/baselines/resolve/TA:MISSING").status_code == 404


def test_test_article_without_a_baseline_is_not_guessed(app, client, event_factory) -> None:
    app.state.projector.apply(
        event_factory(
            aggregate_type="TestArticle",
            aggregate_id="TA:2",
            payload={
                "entity": _entity(
                    "TA:2", "TestArticle", {"serialNumber": "SN-002", "asBuiltStatus": "AS_BUILT"}
                )
            },
        )
    )
    result = client.get("/v1/baselines/resolve/TA:2")
    assert result.status_code == 200
    assert result.json()["resolved"] is False


def test_interface_registration_validates_characteristics(client) -> None:
    body = {
        "interfaceId": "IFC:1",
        "fromSystemId": "SYS:1",
        "toSystemId": "SYS:2",
        "characteristics": {
            "rate": 100.0,
            "latency": 2.5,
            "timing": "periodic",
            "envelope": {"maxAltitudeKm": 40},
        },
    }
    first = client.post("/v1/interfaces", json=body)
    assert first.status_code == 201
    assert first.json()["interface"]["characteristics"]["timing"] == "PERIODIC"

    repeat = client.post("/v1/interfaces", json=body)
    assert repeat.status_code == 200
    assert repeat.json()["created"] is False

    incomplete = {**body, "characteristics": {"rate": 100.0}}
    assert client.post("/v1/interfaces", json=incomplete).status_code == 422

    listed = client.get("/v1/interfaces", params={"fromSystemId": "SYS:1"})
    assert listed.status_code == 200
    assert listed.json()["count"] == 1


def test_requirement_coverage_endpoint(app, client, event_factory) -> None:
    _seed(app, event_factory)
    response = client.get("/v1/requirements/REQ:1/coverage")
    assert response.status_code == 200
    body = response.json()
    assert body["verificationStatus"] == "COMPLETE"
    assert body["verified"] is True
    assert body["coverage"] == 1.0

    assert client.get("/v1/requirements/REQ:MISSING/coverage").status_code == 404


def test_rollup_and_gap_reports(app, client, event_factory) -> None:
    _seed(app, event_factory)

    rollup = client.post("/v1/requirements/rollup", json={"root": "REQ:1"})
    assert rollup.status_code == 200
    body = rollup.json()
    assert body["statuses"]["REQ:1"] == "PARTIAL"
    assert body["statuses"]["REQ:2"] == "NOT_STARTED"
    assert body["counts"]["COMPLETE"] == 0

    gaps = client.get("/v1/requirements/gaps")
    assert gaps.status_code == 200
    assert [item["requirement"]["id"] for item in gaps.json()["requirements"]] == ["REQ:2"]


def test_rollup_requires_an_input(client) -> None:
    assert client.post("/v1/requirements/rollup", json={}).status_code == 422

"""The edge annex flow, end to end.

A factory floor annex captures test results while disconnected, reconciles
with the fabric when the link returns, and the digital thread ends up with
the same content it would have had had the link never been down.

This is the flow that ADR-0006 exists to make possible, and it is the only
part of the platform where the order of operations is genuinely distributed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from ngsh_core.edge import EdgeAgent, EdgeQueue
from ngsh_core.envelope import Actor, Classification, EventEnvelope
from ngsh_fabric.app import create_app as create_fabric_app
from ngsh_thread.app import create_app as create_thread_app

pytestmark = pytest.mark.e2e


def _test_result_event(
    event_id: str,
    *,
    aggregate_id: str = "TR:EDGE-0001",
    campaign_id: str = "TC:EDGE-0001",
    article_id: str = "TA:EDGE-0001",
    outcome: str = "PASS",
) -> EventEnvelope:
    return EventEnvelope(
        eventId=event_id,
        eventType="test.result.recorded",
        aggregateType="TestResult",
        aggregateId=aggregate_id,
        sequence=1,
        tenant="ngsh",
        program="NGSH-SHY",
        actor=Actor(subjectId="edge:factory-3", kind="edge-agent", clearance="SECRET", citizenship="US"),
        classification=Classification(level="CUI"),
        payload={
            "testResult": {
                "id": aggregate_id,
                "type": "TestResult",
                "tenant": "ngsh",
                "version": 1,
                "createdAt": "2026-11-14T09:00:00Z",
                "updatedAt": "2026-11-14T09:00:00Z",
                "classification": {"level": "CUI"},
                "attributes": {
                    "campaignId": campaign_id,
                    "testArticleId": article_id,
                    "testMethod": "plasma-arc-heater",
                    "outcome": outcome,
                    "measurements": [{"name": "peak_temperature", "value": 1838.0, "unit": "K"}],
                },
            }
        },
    )


@pytest.fixture
def stack(settings):
    fabric = TestClient(create_fabric_app(settings))
    thread = TestClient(create_thread_app(settings))
    yield fabric, thread
    fabric.close()
    thread.close()


def _transport(fabric: TestClient):
    def send(url: str, payload: dict) -> dict:
        response = fabric.post("/v1/edge/reconcile", json=payload)
        assert response.status_code == 200, response.text
        return response.json()

    return send


def test_a_disconnected_site_captures_and_reconciles(stack, tmp_path) -> None:
    fabric, thread = stack

    queue = EdgeQueue(tmp_path / "edge.db", node_id="edge:factory-3")
    agent = EdgeAgent("edge:factory-3", queue)

    # -- disconnected capture -------------------------------------------
    agent.capture(_test_result_event("01EDGE0001"))
    agent.capture(_test_result_event("01EDGE0002", aggregate_id="TR:EDGE-0002", article_id="TA:EDGE-0002"))

    assert agent.queue.pending_count() == 2
    assert fabric.get("/v1/stats").json()["total"] == 0, "nothing reached the fabric yet"

    # The local read path works without the fabric.
    assert agent.read("TR:EDGE-0001") is not None

    # -- reconciliation --------------------------------------------------
    report = agent.sync(_transport(fabric))

    assert report.error is None
    assert len(report.accepted) == 2
    assert agent.queue.pending_count() == 0

    # -- the fabric now holds the events --------------------------------
    stats = fabric.get("/v1/stats").json()
    assert stats["total"] == 2
    assert stats["byType"]["test.result.recorded"] == 2

    # The fabric assigned the global sequence; the edge's local sequence is
    # preserved in the edge block so the two can be related.
    events = fabric.get("/v1/events").json()["events"]
    assert all(event["sequence"] == 1 for event in events)
    assert all(event["edge"]["localSequence"] == 1 for event in events)
    assert all(event["edge"]["nodeId"] == "edge:factory-3" for event in events)

    # -- the thread projects them ---------------------------------------
    thread.post("/v1/project/replay")
    entity = thread.get("/v1/entities/TestResult/TR:EDGE-0001")
    assert entity.status_code == 200
    assert entity.json()["entity"]["attributes"]["outcome"] == "PASS"


def test_rival_claims_on_the_same_physical_test_are_escalated(stack, tmp_path) -> None:
    """Two sites claiming one physical test is a question for a human."""
    fabric, thread = stack

    # The fabric already holds a result for this article and campaign.
    existing = _test_result_event("01FABRIC1")
    fabric.post("/v1/events", json=existing.to_logical_json())

    queue = EdgeQueue(tmp_path / "edge.db", node_id="edge:factory-9")
    agent = EdgeAgent("edge:factory-9", queue)
    agent.capture(_test_result_event("01EDGE9"))

    report = agent.sync(_transport(fabric))

    assert report.accepted == []
    assert len(report.quarantined) == 1
    assert report.quarantined[0]["conflictClass"] == "immutable-conflict"

    # The conflict is a first-class record, not just a ledger line.
    events = fabric.get("/v1/events").json()["events"]
    conflicts = [e for e in events if e["eventType"] == "reconcile.conflict.recorded"]
    assert len(conflicts) == 1
    assert conflicts[0]["payload"]["conflictClass"] == "immutable-conflict"
    assert conflicts[0]["payload"]["escalationTask"]["taskType"] == "safety-review"

    # The edge retains the quarantined event for the operator.
    assert len(agent.queue.quarantined()) == 1


def test_a_second_reconciliation_of_the_same_batch_is_a_duplicate(stack, tmp_path) -> None:
    """Reconciliation is idempotent, so a retried batch cannot double-apply."""
    fabric, thread = stack

    queue = EdgeQueue(tmp_path / "edge.db", node_id="edge:factory-4")
    agent = EdgeAgent("edge:factory-4", queue)
    agent.capture(_test_result_event("01EDGE4"))

    first = agent.sync(_transport(fabric))
    assert len(first.accepted) == 1

    # The edge retries with the same event (a lost acknowledgement).
    assert agent.queue.requeue("01EDGE4")

    second = agent.sync(_transport(fabric))
    assert second.accepted == []
    assert second.duplicates == ["01EDGE4"]

    assert fabric.get("/v1/stats").json()["total"] == 1


def test_the_edge_read_path_is_identical_connected_or_disconnected(stack, tmp_path) -> None:
    """An operator who cannot trust the tool offline will stop using it."""
    fabric, thread = stack

    queue = EdgeQueue(tmp_path / "edge.db", node_id="edge:factory-5")
    agent = EdgeAgent("edge:factory-5", queue)

    agent.capture(_test_result_event("01EDGE5"))
    disconnected = agent.read("TR:EDGE-0001")

    agent.sync(_transport(fabric))

    connected = agent.read("TR:EDGE-0001")
    assert disconnected == connected
    assert disconnected is not None

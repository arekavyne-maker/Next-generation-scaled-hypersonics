"""The edge annex queue and agent.

These tests cover the degraded-mode guarantees: the write path works
without the fabric, the read path is identical connected or disconnected,
nothing is lost silently, and reconciliation is deterministic.
"""

from __future__ import annotations

import pytest
from ngsh_core.edge import (
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    EdgeAgent,
    EdgeQueue,
    priority_for,
)
from ngsh_core.envelope import Actor, Classification, EventEnvelope


def _event(
    event_id: str,
    *,
    aggregate_id: str = "PART:1",
    event_type: str = "entity.updated",
    payload: dict | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        eventId=event_id,
        eventType=event_type,
        aggregateType="Part",
        aggregateId=aggregate_id,
        sequence=1,
        tenant="ngsh",
        actor=Actor(subjectId="edge:node-1", kind="edge-agent"),
        classification=Classification(level="CUI"),
        payload=payload or {},
    )


@pytest.fixture
def queue(tmp_path) -> EdgeQueue:
    return EdgeQueue(tmp_path / "edge.db")


@pytest.fixture
def agent(queue) -> EdgeAgent:
    return EdgeAgent("edge:node-1", queue)


# -- priority ---------------------------------------------------------------


def test_evidence_outranks_telemetry() -> None:
    assert priority_for("test.result.recorded") == PRIORITY_HIGH
    assert priority_for("process.run.completed") == PRIORITY_HIGH
    assert priority_for("entity.updated") == PRIORITY_NORMAL
    assert priority_for("access.decision.recorded") == PRIORITY_LOW


# -- the queue --------------------------------------------------------------


def test_capture_does_not_require_the_fabric(agent: EdgeAgent) -> None:
    entry = agent.capture(_event("01A"))

    assert entry.localSequence == 1
    assert entry.branchedFromSeq == 0
    assert agent.queue.pending_count() == 1


def test_local_sequences_are_per_aggregate(queue: EdgeQueue) -> None:
    queue.append(_event("01A", aggregate_id="PART:1"))
    queue.append(_event("01B", aggregate_id="PART:2"))
    queue.append(_event("01C", aggregate_id="PART:1"))

    sequences = {(e.aggregateId, e.eventId): e.localSequence for e in queue.pending()}
    assert sequences[("PART:1", "01A")] == 1
    assert sequences[("PART:2", "01B")] == 1
    assert sequences[("PART:1", "01C")] == 2


def test_pending_is_ordered_by_aggregate_then_local_sequence(queue: EdgeQueue) -> None:
    queue.append(_event("01A", aggregate_id="PART:2"))
    queue.append(_event("01B", aggregate_id="PART:1"))
    queue.append(_event("01C", aggregate_id="PART:2"))

    pending = queue.pending()
    assert [(e.aggregateId, e.localSequence) for e in pending] == [
        ("PART:1", 1),
        ("PART:2", 1),
        ("PART:2", 2),
    ]


def test_the_edge_stamps_its_own_sequence_onto_the_event(agent: EdgeAgent) -> None:
    entry = agent.capture(_event("01A"))
    assert entry.envelope.edge is not None
    assert entry.envelope.edge["localSequence"] == 1
    assert entry.envelope.edge["nodeId"] == "edge:node-1"


def test_the_branch_point_is_recorded_and_never_regresses(queue: EdgeQueue) -> None:
    queue.set_branch_point("PART:1", 7)
    assert queue._branch_point("PART:1") == 7  # noqa: SLF001

    queue.set_branch_point("PART:1", 3)
    assert queue._branch_point("PART:1") == 7  # noqa: SLF001


def test_acknowledged_events_leave_the_queue(queue: EdgeQueue) -> None:
    queue.append(_event("01A"))
    queue.append(_event("01B"))

    queue.acknowledge(["01A"])
    assert queue.pending_count() == 1
    assert [e.eventId for e in queue.pending()] == ["01B"]


def test_quarantined_events_are_retained_for_review(queue: EdgeQueue) -> None:
    queue.append(_event("01A"))
    queue.quarantine("01A", "immutable-conflict")

    assert queue.pending_count() == 0
    quarantined = queue.quarantined()
    assert len(quarantined) == 1
    assert quarantined[0]["quarantine_reason"] == "immutable-conflict"


# -- overflow ---------------------------------------------------------------


def test_overflow_drops_the_lowest_priority_first_and_records_it(tmp_path) -> None:
    """Silent loss is prohibited: every drop is recorded."""
    queue = EdgeQueue(tmp_path / "edge.db", capacity=2)

    queue.append(_event("01HIGH", event_type="test.result.recorded"))
    queue.append(_event("01NORMAL"))
    queue.append(_event("01LOW", event_type="access.decision.recorded"))

    dropped = queue.dropped()
    assert len(dropped) == 1
    assert dropped[0].eventId == "01LOW"
    assert "priority" in dropped[0].reason

    remaining = {e.eventId for e in queue.pending()}
    assert remaining == {"01HIGH", "01NORMAL"}


# -- the agent --------------------------------------------------------------


def test_reads_are_served_locally(agent: EdgeAgent) -> None:
    """A disconnected site operator gets an answer, not an error."""
    agent.capture(_event("01A"))

    cached = agent.read("PART:1")
    assert cached is not None
    assert cached["eventId"] == "01A"


def test_status_reports_the_link_and_the_backlog(agent: EdgeAgent) -> None:
    agent.capture(_event("01A"))
    status = agent.status()

    assert status["nodeId"] == "edge:node-1"
    assert status["connection"]["connected"] is False
    assert status["connection"]["pendingCount"] == 1


def test_sync_without_a_fabric_reports_the_failure_without_losing_anything(agent: EdgeAgent) -> None:
    agent.capture(_event("01A"))

    def failing_transport(url: str, payload: dict) -> dict:
        raise ConnectionError("fabric unreachable")

    report = agent.sync(failing_transport)

    assert report.error is not None
    assert agent.queue.pending_count() == 1, "a failed sync must not lose the queue"


def test_sync_acknowledges_accepted_events_and_quarantines_the_rest(agent: EdgeAgent) -> None:
    agent.capture(_event("01A"))
    agent.capture(_event("01B"))

    def transport(url: str, payload: dict) -> dict:
        return {
            "accepted": [{"eventId": "01A"}],
            "duplicates": [{"eventId": "01B"}],
            "quarantined": [
                {"eventId": "01C", "reason": "immutable-conflict", "conflictClass": "immutable-conflict"}
            ],
            "aggregateSequences": {"PART:1": 4},
        }

    report = agent.sync(transport)

    assert report.accepted == ["01A"]
    assert report.duplicates == ["01B"]
    assert agent.queue.pending_count() == 0
    assert agent.queue._branch_point("PART:1") == 4  # noqa: SLF001


def test_sync_consumes_the_queue_exactly_once(agent: EdgeAgent) -> None:
    """A reconciled event is not offered to the fabric again."""
    agent.capture(_event("01A"))

    def transport(url: str, payload: dict) -> dict:
        return {"accepted": [{"eventId": e["eventId"]} for e in payload["events"]], "duplicates": []}

    first = agent.sync(transport)
    assert first.accepted == ["01A"]
    assert agent.queue.pending_count() == 0

    second = agent.sync(transport)
    assert second.accepted == [], "the queue was already drained by the first sync"


def test_the_queue_survives_a_process_restart(tmp_path) -> None:
    """The queue is durable against process failure."""
    path = tmp_path / "edge.db"

    first = EdgeQueue(path)
    first.append(_event("01A"))
    first.append(_event("01B"))
    first.close()

    second = EdgeQueue(path)
    assert second.pending_count() == 2
    assert {e.eventId for e in second.pending()} == {"01A", "01B"}
    second.close()

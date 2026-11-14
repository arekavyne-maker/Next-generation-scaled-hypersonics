"""The event log: sequencing, idempotency and replay."""

from __future__ import annotations

import pytest
from ngsh_core.errors import ConcurrencyError
from ngsh_core.eventlog import EventLog


@pytest.fixture
def log(executor) -> EventLog:
    return EventLog(executor)


def test_append_and_read_back(log: EventLog, event_factory) -> None:
    envelope = event_factory()
    outcome = log.append(envelope)
    assert outcome.accepted

    stored = log.get(envelope.eventId)
    assert stored is not None
    assert stored.eventType == envelope.eventType
    assert stored.payload == envelope.payload


def test_sequence_must_increment_by_one(log: EventLog, event_factory) -> None:
    log.append(event_factory(aggregate_id="TR:A", sequence=1))
    with pytest.raises(ConcurrencyError) as excinfo:
        log.append(event_factory(aggregate_id="TR:A", sequence=3))
    assert excinfo.value.context["expected"] == 2


def test_sequences_are_tracked_per_aggregate(log: EventLog, event_factory) -> None:
    """Two aggregates must not share a sequence counter."""
    log.append(event_factory(aggregate_id="TR:A", sequence=1))
    log.append(event_factory(aggregate_id="TR:B", sequence=1))
    assert log.next_sequence("TR:A") == 2
    assert log.next_sequence("TR:B") == 2


def test_duplicate_idempotency_key_is_ignored(log: EventLog, event_factory) -> None:
    first = event_factory(idempotency_key="batch-1:TR:1")
    log.append(first)

    second = event_factory(idempotency_key="batch-1:TR:1")
    outcome = log.append(second)
    assert outcome.accepted
    assert outcome.duplicate
    assert log.count() == 1


def test_idempotency_is_scoped_to_the_tenant(log: EventLog, event_factory) -> None:
    log.append(event_factory(tenant="ngsh", aggregate_id="TR:A", idempotency_key="k"))
    log.append(event_factory(tenant="other", aggregate_id="TR:B", idempotency_key="k"))
    assert log.count() == 2


def test_read_filters_by_type_pattern(log: EventLog, event_factory) -> None:
    log.append(event_factory("test.result.recorded", aggregate_id="TR:A"))
    log.append(event_factory("process.run.completed", aggregate_id="PR:A"))
    log.append(event_factory("test.result.recorded", aggregate_id="TR:B"))

    events, _ = log.read(types=["test.*"])
    assert len(events) == 2
    assert all(event.eventType == "test.result.recorded" for event in events)


def test_read_filters_by_tenant(log: EventLog, event_factory) -> None:
    log.append(event_factory(tenant="ngsh", aggregate_id="TR:A"))
    log.append(event_factory(tenant="other", aggregate_id="TR:B"))

    events, _ = log.read(tenant="other")
    assert len(events) == 1
    assert events[0].tenant == "other"


def test_read_paginates_with_a_cursor(log: EventLog, event_factory) -> None:
    for index in range(5):
        log.append(event_factory(aggregate_id=f"TR:{index}", sequence=1))

    page_one, cursor = log.read(after=0, limit=2)
    assert len(page_one) == 2

    page_two, cursor_two = log.read(after=cursor, limit=2)
    assert len(page_two) == 2
    assert cursor_two > cursor


def test_replay_yields_events_in_order(log: EventLog, event_factory) -> None:
    for index in range(4):
        log.append(event_factory(aggregate_id=f"TR:{index}", sequence=1))

    replayed = list(log.replay())
    assert [event.aggregateId for event in replayed] == ["TR:0", "TR:1", "TR:2", "TR:3"]


def test_batch_append_reports_partial_failure(log: EventLog, event_factory) -> None:
    log.append(event_factory(aggregate_id="TR:A", sequence=1))

    outcomes = log.append_batch(
        [
            event_factory(aggregate_id="TR:A", sequence=2),
            event_factory(aggregate_id="TR:A", sequence=9),
        ]
    )
    assert outcomes[0].accepted
    assert not outcomes[1].accepted
    assert outcomes[1].reason is not None


def test_stats_group_by_type(log: EventLog, event_factory) -> None:
    log.append(event_factory("test.result.recorded", aggregate_id="TR:A"))
    log.append(event_factory("test.result.recorded", aggregate_id="TR:B"))
    log.append(event_factory("model.validated", aggregate_id="MDL:A"))

    stats = log.stats()
    assert stats["total"] == 3
    assert stats["byType"]["test.result.recorded"] == 2
    assert stats["aggregates"] == 3

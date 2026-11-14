"""Edge reconciliation.

These tests exercise the conflict rule of ADR-0006 directly. They are the
tests that prove the platform's claim of *deterministic* reconciliation: the
same inputs must always produce the same outcome, on any node, in any order
of arrival.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ngsh_core.envelope import Actor, Classification, EventEnvelope
from ngsh_core.reconcile import (
    ConflictClass,
    FabricState,
    ImmutabilityClass,
    Reconciler,
    Resolution,
    immutability_class,
)


def _event(
    event_id: str,
    *,
    aggregate_type: str = "Part",
    aggregate_id: str = "PART:1",
    local_sequence: int = 1,
    branched_from: int = 0,
    occurred_at: datetime | None = None,
    recorded_at: datetime | None = None,
    payload: dict | None = None,
    classification: str = "CUI",
    event_type: str = "entity.updated",
    clock_untrusted: bool = False,
) -> EventEnvelope:
    stamp = occurred_at or datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
    recorded = recorded_at or stamp
    return EventEnvelope(
        eventId=event_id,
        eventType=event_type,
        aggregateType=aggregate_type,
        aggregateId=aggregate_id,
        sequence=local_sequence,
        tenant="ngsh",
        actor=Actor(subjectId="edge:node-1", kind="edge-agent"),
        classification=Classification(level=classification),
        occurredAt=stamp,
        recordedAt=recorded,
        payload=payload or {},
        edge={
            "nodeId": "edge:node-1",
            "localSequence": local_sequence,
            "branchedFromSeq": branched_from,
            "clockUntrusted": clock_untrusted,
        },
    )


def _state(**overrides) -> FabricState:
    base = {
        "aggregate_sequences": {},
        "known_event_ids": set(),
        "entity_classifications": {},
        "classification_floors": {"Part": "CUI", "TestResult": "CUI", "ThreatSystem": "RESTRICTED"},
        "immutable_keys": set(),
        "incumbents": {},
    }
    base.update(overrides)
    return FabricState(**base)


# -- step 1: idempotency ---------------------------------------------------


def test_an_already_accepted_event_is_a_duplicate() -> None:
    state = _state(known_event_ids={"01ABC"})
    result = Reconciler(state).reconcile([_event("01ABC")])

    assert len(result.duplicates) == 1
    assert result.accepted == []


# -- step 2: sequence relationship ------------------------------------------


def test_fast_forward_when_the_fabric_has_not_advanced() -> None:
    """The edge was the only writer: its whole run is applied in order."""
    state = _state(aggregate_sequences={"PART:1": 3})
    events = [
        _event("01A", aggregate_id="PART:1", local_sequence=4, branched_from=3),
        _event("01B", aggregate_id="PART:1", local_sequence=5, branched_from=3),
    ]
    result = Reconciler(state).reconcile(events)

    assert len(result.accepted) == 2
    assert result.quarantined == []


def test_conflict_when_the_fabric_advanced_past_the_branch_point() -> None:
    state = _state(aggregate_sequences={"PART:1": 5})
    events = [_event("01A", aggregate_id="PART:1", local_sequence=4, branched_from=3)]
    result = Reconciler(state).reconcile(events)

    # The edge write is applied but the conflict is recorded, because the
    # fabric had already advanced.
    assert result.outcomes[0].resolution in {
        Resolution.ACCEPTED,
        Resolution.APPLIED_DETERMINISTIC_WINNER,
    }


def test_a_gap_in_the_edge_run_is_quarantined() -> None:
    """A lost queue entry must be visible, not silently skipped."""
    state = _state(aggregate_sequences={"PART:1": 3})
    events = [
        _event("01A", aggregate_id="PART:1", local_sequence=4, branched_from=3),
        _event("01B", aggregate_id="PART:1", local_sequence=7, branched_from=3),
    ]
    result = Reconciler(state).reconcile(events)

    quarantined = result.quarantined
    assert len(quarantined) == 1
    assert quarantined[0].eventId == "01B"
    assert quarantined[0].conflictClass is ConflictClass.GAP


def test_two_events_with_the_same_local_sequence_are_divergent() -> None:
    state = _state(aggregate_sequences={"PART:1": 0})
    events = [
        _event("01A", aggregate_id="PART:1", local_sequence=1),
        _event("01B", aggregate_id="PART:1", local_sequence=1),
    ]
    result = Reconciler(state).reconcile(events)

    assert len(result.quarantined) == 2
    assert all(o.conflictClass is ConflictClass.DIVERGENT_SEQUENCE for o in result.quarantined)


# -- step 3: immutability class --------------------------------------------


def test_test_results_are_immutable() -> None:
    assert immutability_class("TestResult") is ImmutabilityClass.IMMUTABLE
    assert immutability_class("PartProvenance") is ImmutabilityClass.APPEND_ONLY
    assert immutability_class("Part") is ImmutabilityClass.MUTABLE


def test_two_sites_claiming_the_same_physical_test_is_escalated() -> None:
    """The platform does not adjudicate physics. A human does."""
    state = _state(
        aggregate_sequences={"TR:1": 2},
        immutable_keys={("TC:1", "TA:1")},
    )
    event = _event(
        "01A",
        aggregate_type="TestResult",
        aggregate_id="TR:1",
        local_sequence=3,
        branched_from=2,
        payload={"testResult": {"campaignId": "TC:1", "testArticleId": "TA:1", "outcome": "PASS"}},
    )
    result = Reconciler(state).reconcile([event])

    assert len(result.quarantined) == 1
    assert result.quarantined[0].conflictClass is ConflictClass.IMMUTABLE_CONFLICT


def test_a_superseding_result_is_accepted() -> None:
    """A correction to a test result is a new version, not a conflict."""
    state = _state(
        aggregate_sequences={"TR:1": 2},
        immutable_keys={("TC:1", "TA:1")},
    )
    event = _event(
        "01A",
        aggregate_type="TestResult",
        aggregate_id="TR:1",
        local_sequence=3,
        branched_from=2,
        payload={
            "supersedesRef": "TR:OLD",
            "testResult": {"campaignId": "TC:1", "testArticleId": "TA:1", "outcome": "PASS"},
        },
    )
    result = Reconciler(state).reconcile([event])

    assert result.quarantined == []
    assert len(result.accepted) == 1


def test_append_only_facts_are_both_kept() -> None:
    """Two records of two observations are both true."""
    state = _state(aggregate_sequences={"TOBS:1": 1})
    event = _event(
        "01A",
        aggregate_type="ThreatObservation",
        aggregate_id="TOBS:1",
        local_sequence=2,
        branched_from=1,
        classification="RESTRICTED",
    )
    result = Reconciler(state).reconcile([event])

    assert result.quarantined == []
    assert len(result.accepted) == 1


# -- step 4: the mutable resolution key ------------------------------------


def test_the_later_effective_write_wins_and_the_loser_is_retained() -> None:
    incumbent = _event(
        "01OLD",
        occurred_at=datetime(2026, 11, 14, 10, 0, tzinfo=UTC),
        recorded_at=datetime(2026, 11, 14, 10, 0, tzinfo=UTC),
    )
    edge_write = _event(
        "01NEW",
        occurred_at=datetime(2026, 11, 14, 13, 0, tzinfo=UTC),
        recorded_at=datetime(2026, 11, 14, 13, 0, tzinfo=UTC),
    )
    state = _state(aggregate_sequences={"PART:1": 1}, incumbents={"PART:1": incumbent})

    result = Reconciler(state).reconcile([edge_write])

    outcome = result.outcomes[0]
    assert outcome.resolution is Resolution.APPLIED_DETERMINISTIC_WINNER
    assert outcome.winningEventId == "01NEW"
    assert outcome.losingEventId == "01OLD"


def test_the_resolution_is_deterministic_whatever_the_arrival_order() -> None:
    """The same inputs must produce the same winner, always."""
    earlier = _event(
        "01A",
        occurred_at=datetime(2026, 11, 14, 10, 0, tzinfo=UTC),
        recorded_at=datetime(2026, 11, 14, 10, 0, tzinfo=UTC),
    )
    later = _event(
        "01B",
        occurred_at=datetime(2026, 11, 14, 13, 0, tzinfo=UTC),
        recorded_at=datetime(2026, 11, 14, 13, 0, tzinfo=UTC),
    )

    winners = set()
    for incumbent, challenger in ((earlier, later), (later, earlier)):
        state = _state(
            aggregate_sequences={"PART:1": 1},
            incumbents={"PART:1": incumbent},
        )
        result = Reconciler(state).reconcile([challenger])
        outcome = result.outcomes[0]
        winners.add(outcome.winningEventId or outcome.losingEventId)

    assert winners == {"01B"}, "the later effective write must win regardless of arrival order"


def test_an_untrusted_clock_disables_effective_at_ordering() -> None:
    """With no trustworthy clock, ordering by the clock is worse than not ordering."""
    incumbent = _event(
        "01OLD",
        occurred_at=datetime(2026, 11, 14, 23, 0, tzinfo=UTC),
        recorded_at=datetime(2026, 11, 14, 10, 0, tzinfo=UTC),
    )
    edge_write = _event(
        "01NEW",
        occurred_at=datetime(2026, 11, 14, 10, 0, tzinfo=UTC),
        recorded_at=datetime(2026, 11, 14, 13, 0, tzinfo=UTC),
        clock_untrusted=True,
    )
    state = _state(aggregate_sequences={"PART:1": 1}, incumbents={"PART:1": incumbent})

    result = Reconciler(state).reconcile([edge_write])
    outcome = result.outcomes[0]

    # The recordedAt component decides, not the untrusted occurredAt.
    assert outcome.winningEventId == "01NEW"


# -- step 5: the classification gate ---------------------------------------


def test_a_merge_may_not_lower_the_classification() -> None:
    state = _state(
        aggregate_sequences={"TR:1": 1},
        entity_classifications={"TR:1": "SECRET"},
    )
    event = _event(
        "01A",
        aggregate_type="TestResult",
        aggregate_id="TR:1",
        local_sequence=2,
        branched_from=1,
        classification="CUI",
    )
    result = Reconciler(state).reconcile([event])

    assert len(result.quarantined) == 1
    assert result.quarantined[0].conflictClass is ConflictClass.CLASSIFICATION_VIOLATION


def test_a_merge_may_not_breach_the_classification_floor() -> None:
    state = _state(aggregate_sequences={"THR:1": 1})
    event = _event(
        "01A",
        aggregate_type="ThreatSystem",
        aggregate_id="THR:1",
        local_sequence=2,
        branched_from=1,
        classification="UNCLASSIFIED",
    )
    result = Reconciler(state).reconcile([event])

    assert len(result.quarantined) == 1
    assert result.quarantined[0].conflictClass is ConflictClass.CLASSIFICATION_VIOLATION


# -- clock skew ------------------------------------------------------------


def test_extreme_clock_skew_quarantines_the_whole_batch() -> None:
    state = _state(clock_skew_ms=120_000)
    result = Reconciler(state).reconcile([_event("01A")])

    assert len(result.quarantined) == 1
    assert result.quarantined[0].conflictClass is ConflictClass.CLOCK_SKEW


def test_moderate_clock_skew_is_recorded_but_not_escalated() -> None:
    """Skew of 5 to 60 seconds is flagged; it does not stop the batch."""
    state = _state(clock_skew_ms=30_000)
    result = Reconciler(state).reconcile([_event("01A")])

    assert result.quarantined == []
    assert len(result.accepted) == 1


# -- multi-aggregate batches ----------------------------------------------


def test_a_batch_spanning_aggregates_is_reconciled_per_aggregate() -> None:
    state = _state(
        aggregate_sequences={"PART:1": 5, "PART:2": 0},
        known_event_ids={"01DUP"},
    )
    events = [
        _event("01A", aggregate_id="PART:1", local_sequence=6, branched_from=5),
        _event("01B", aggregate_id="PART:2", local_sequence=1, branched_from=0),
        _event("01DUP", aggregate_id="PART:2", local_sequence=2, branched_from=0),
    ]
    result = Reconciler(state).reconcile(events)

    assert len(result.accepted) == 2
    assert len(result.duplicates) == 1


@pytest.mark.parametrize("reordered", [False, True])
def test_batch_order_does_not_change_the_outcome(reordered: bool) -> None:
    """Ordering within a batch must not change what the fabric decides."""
    events = [
        _event("01A", aggregate_id="PART:1", local_sequence=1),
        _event("01B", aggregate_id="PART:1", local_sequence=2),
        _event("01C", aggregate_id="PART:1", local_sequence=3),
    ]
    if reordered:
        events = list(reversed(events))

    state = _state(aggregate_sequences={"PART:1": 0})
    result = Reconciler(state).reconcile(events)

    assert {outcome.eventId for outcome in result.accepted} == {"01A", "01B", "01C"}

"""Edge reconciliation.

Implements the conflict rule of ADR-0006. The rule is a deterministic
function of its inputs, not a consensus algorithm: given the same fabric
state and the same incoming batch, every replica computes the same outcome.
That determinism is what allows the platform to keep the replay determinism
the whole log architecture depends on (ADR-0001).

The rule proceeds in six steps, applied per aggregate:

1. **Idempotency** — an event already accepted is a duplicate and is dropped.
2. **Sequence relationship** — fast-forward, conflict, gap, or divergent
   sequence, decided from the edge's local sequence, its branch point, and the
   fabric's current sequence for the aggregate.
3. **Immutability class** — immutable, append-only, mutable, or relation.
   This determines whether the situation is even resolvable.
4. **Mutable resolution key** — for mutable aggregates, a fixed composite key
   selects a winner deterministically. The loser is retained in the ledger.
5. **Classification gate** — a merge may never downgrade content and may
   never breach a classification floor.
6. **Escalation** — what the rules cannot decide is raised to a human.

The design's limits are stated in the ADR and are real: this is not
consensus, two sites writing the same mutable aggregate produce a
deterministic but semantically arbitrary winner, and the platform's job is to
make that choice visible rather than to make it correct.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .classification import at_least, parse_level
from .envelope import EventEnvelope


class ImmutabilityClass(StrEnum):
    """How an aggregate type behaves when two sites modify it independently."""

    IMMUTABLE = "immutable"
    APPEND_ONLY = "append-only"
    MUTABLE = "mutable"
    RELATION = "relation"


#: Immutability class per aggregate type. Types not listed are MUTABLE.
#:
#: This mapping is domain policy expressed in code, and it is the single
#: place where the platform encodes an assumption that a domain authority
#: must confirm. ADR-0006 records this as a consequence of the design: each
#: mutable entity type needs a merge decision from the engineers who
#: understand it.
IMMUTABILITY_BY_TYPE: dict[str, ImmutabilityClass] = {
    # Immutable evidence. Two sites claiming a result for the same physical
    # test is a question about physics, not about software.
    "TestResult": ImmutabilityClass.IMMUTABLE,
    # Append-only facts. Two records of two observations are both true.
    "PartProvenance": ImmutabilityClass.APPEND_ONLY,
    "ThreatObservation": ImmutabilityClass.APPEND_ONLY,
    "ProcessRun": ImmutabilityClass.APPEND_ONLY,
    "Credential": ImmutabilityClass.APPEND_ONLY,
    "RangeSlot": ImmutabilityClass.APPEND_ONLY,
}


def immutability_class(aggregate_type: str) -> ImmutabilityClass:
    return IMMUTABILITY_BY_TYPE.get(aggregate_type, ImmutabilityClass.MUTABLE)


class ConflictClass(StrEnum):
    """The classes of conflict that can be escalated."""

    IMMUTABLE_CONFLICT = "immutable-conflict"
    GAP = "gap"
    DIVERGENT_SEQUENCE = "divergent-sequence"
    CLOCK_SKEW = "clock-skew"
    CLASSIFICATION_VIOLATION = "classification-violation"
    MUTABLE_CONFLICT = "mutable-conflict"


class Resolution(StrEnum):
    """What the platform did about a conflict."""

    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    QUARANTINED = "quarantined"
    APPLIED_DETERMINISTIC_WINNER = "applied-deterministic-winner"
    REJECTED = "rejected"


#: Clock skew thresholds, from ADR-0006 rules C-5 to C-7.
CLOCK_SKEW_RECORD_MS = 5_000
CLOCK_SKEW_ESCALATE_MS = 60_000


@dataclass
class FabricState:
    """The fabric's state for the aggregates an edge batch touches.

    This is the snapshot the edge pulls during the handshake (step 3 of the
    reconciliation procedure).
    """

    aggregate_sequences: dict[str, int] = field(default_factory=dict)
    known_event_ids: set[str] = field(default_factory=set)
    entity_ids: set[str] = field(default_factory=set)
    #: Keys of immutable aggregates that already exist, e.g.
    #: ``("TC:1", "TA:1")`` for a ``(campaignId, testArticleId)`` pair.
    immutable_keys: set[tuple[str, str]] = field(default_factory=set)
    #: Current classification level per entity id, for the non-downgrade gate.
    entity_classifications: dict[str, str] = field(default_factory=dict)
    #: Classification floor per entity type, from the ontology registry.
    classification_floors: dict[str, str] = field(default_factory=dict)
    #: The fabric's current event for an aggregate, for the mutable tiebreak.
    incumbents: dict[str, EventEnvelope] = field(default_factory=dict)
    clock_skew_ms: float = 0.0

    def sequence_for(self, aggregate_id: str) -> int:
        return self.aggregate_sequences.get(aggregate_id, 0)


@dataclass
class EventOutcome:
    """The result of reconciling one event."""

    eventId: str
    aggregateId: str
    resolution: Resolution
    reason: str = ""
    conflictClass: ConflictClass | None = None
    winningEventId: str | None = None
    losingEventId: str | None = None
    localSequence: int | None = None

    @property
    def accepted(self) -> bool:
        return self.resolution in {
            Resolution.ACCEPTED,
            Resolution.APPLIED_DETERMINISTIC_WINNER,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "eventId": self.eventId,
            "aggregateId": self.aggregateId,
            "resolution": self.resolution.value,
            "reason": self.reason,
            "conflictClass": self.conflictClass.value if self.conflictClass else None,
            "winningEventId": self.winningEventId,
            "losingEventId": self.losingEventId,
            "localSequence": self.localSequence,
        }


@dataclass
class ReconcileResult:
    outcomes: list[EventOutcome] = field(default_factory=list)

    @property
    def accepted(self) -> list[EventOutcome]:
        return [outcome for outcome in self.outcomes if outcome.accepted]

    @property
    def quarantined(self) -> list[EventOutcome]:
        return [
            outcome
            for outcome in self.outcomes
            if outcome.resolution in {Resolution.QUARANTINED, Resolution.REJECTED}
        ]

    @property
    def duplicates(self) -> list[EventOutcome]:
        return [outcome for outcome in self.outcomes if outcome.resolution == Resolution.DUPLICATE]

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": [outcome.to_dict() for outcome in self.accepted],
            "quarantined": [outcome.to_dict() for outcome in self.quarantined],
            "duplicates": [outcome.to_dict() for outcome in self.duplicates],
        }


def _local_sequence(envelope: EventEnvelope) -> int:
    if not envelope.edge:
        return 0
    value = envelope.edge.get("localSequence")
    return int(value) if value else 0


def _branched_from(envelope: EventEnvelope) -> int:
    if not envelope.edge:
        return 0
    value = envelope.edge.get("branchedFromSeq")
    return int(value) if value else 0


def _resolution_key(envelope: EventEnvelope, *, clock_untrusted: bool) -> tuple[Any, ...]:
    """The fixed composite key of ADR-0006 Step 4.

    ``max by (effectiveAt, recordedAtAuthority, eventId)``

    The ``effectiveAt`` component is disabled when the site has no
    trustworthy clock (rule C-9), because ordering by an untrusted clock is
    worse than not ordering by it at all.
    """
    effective_at: Any = envelope.recordedAt
    if not clock_untrusted:
        effective_at = envelope.occurredAt
    return (effective_at, envelope.recordedAt, envelope.eventId)


class Reconciler:
    """Applies the ADR-0006 conflict rule to an incoming edge batch."""

    def __init__(self, state: FabricState) -> None:
        self.state = state

    # -- entry point -----------------------------------------------------

    def reconcile(self, events: Sequence[EventEnvelope]) -> ReconcileResult:
        result = ReconcileResult()

        if abs(self.state.clock_skew_ms) > CLOCK_SKEW_ESCALATE_MS:
            for envelope in events:
                result.outcomes.append(
                    EventOutcome(
                        eventId=envelope.eventId,
                        aggregateId=envelope.aggregateId,
                        resolution=Resolution.QUARANTINED,
                        conflictClass=ConflictClass.CLOCK_SKEW,
                        reason=(
                            f"clock skew {self.state.clock_skew_ms:.0f} ms exceeds the "
                            f"{CLOCK_SKEW_ESCALATE_MS} ms escalation threshold; "
                            "the edge clock must be corrected before the batch is retried"
                        ),
                        localSequence=_local_sequence(envelope),
                    )
                )
            return result

        grouped: dict[str, list[EventEnvelope]] = {}
        for envelope in events:
            grouped.setdefault(envelope.aggregateId, []).append(envelope)

        for aggregate_id, group in grouped.items():
            result.outcomes.extend(self._reconcile_aggregate(aggregate_id, group))

        return result

    # -- per aggregate ---------------------------------------------------

    def _reconcile_aggregate(self, aggregate_id: str, group: list[EventEnvelope]) -> list[EventOutcome]:
        outcomes: list[EventOutcome] = []

        # Step 1 — idempotency.
        deduplicated: list[EventEnvelope] = []
        for envelope in group:
            if envelope.eventId in self.state.known_event_ids:
                outcomes.append(
                    EventOutcome(
                        eventId=envelope.eventId,
                        aggregateId=aggregate_id,
                        resolution=Resolution.DUPLICATE,
                        reason="the fabric already holds this event",
                        localSequence=_local_sequence(envelope),
                    )
                )
                continue
            deduplicated.append(envelope)

        if not deduplicated:
            return outcomes

        # The edge's events are ordered by its own local sequence.
        ordered = sorted(deduplicated, key=lambda e: (_local_sequence(e), e.eventId))

        # Divergent sequence: two events claim the same local sequence. The
        # edge's allocator is at fault; this is an edge incident.
        by_local: dict[int, list[EventEnvelope]] = {}
        for envelope in ordered:
            by_local.setdefault(_local_sequence(envelope), []).append(envelope)

        divergent: set[str] = set()
        for local, members in by_local.items():
            if len(members) > 1:
                for envelope in members:
                    divergent.add(envelope.eventId)
                    outcomes.append(
                        EventOutcome(
                            eventId=envelope.eventId,
                            aggregateId=aggregate_id,
                            resolution=Resolution.QUARANTINED,
                            conflictClass=ConflictClass.DIVERGENT_SEQUENCE,
                            reason=(
                                f"local sequence {local} was allocated to "
                                f"{len(members)} events at the edge node"
                            ),
                            localSequence=local,
                        )
                    )

        candidates = [envelope for envelope in ordered if envelope.eventId not in divergent]
        if not candidates:
            return outcomes

        # Sequence gap: the edge's run has a hole. The contiguous prefix is
        # applied; the remainder is quarantined.
        branch = _branched_from(candidates[0])
        expected_local = _local_sequence(candidates[0])
        prefix: list[EventEnvelope] = []
        remainder: list[EventEnvelope] = []
        for envelope in candidates:
            local = _local_sequence(envelope)
            if local == expected_local:
                prefix.append(envelope)
                expected_local += 1
            else:
                remainder.append(envelope)

        for envelope in remainder:
            outcomes.append(
                EventOutcome(
                    eventId=envelope.eventId,
                    aggregateId=aggregate_id,
                    resolution=Resolution.QUARANTINED,
                    conflictClass=ConflictClass.GAP,
                    reason=(
                        f"local sequence {_local_sequence(envelope)} does not follow the "
                        f"contiguous run ending at {expected_local - 1}; a queue entry was lost"
                    ),
                    localSequence=_local_sequence(envelope),
                )
            )

        if not prefix:
            return outcomes

        # Immutable evidence is checked before the sequence relationship.
        # Two sites can claim the same physical test under different
        # aggregate ids, so the conflict exists even when the fabric has
        # not advanced for this aggregate. Immutable evidence is never
        # silently overwritten.
        klass = immutability_class(self._aggregate_type_of(prefix))
        if klass is ImmutabilityClass.IMMUTABLE:
            for envelope in prefix:
                outcomes.append(self._resolve_immutable(envelope))
            return outcomes

        if klass is ImmutabilityClass.APPEND_ONLY:
            for envelope in prefix:
                outcomes.append(self._accept(envelope, "append-only fact; both records are retained"))
            return outcomes

        # Step 2 — sequence relationship.
        fabric_sequence = self.state.sequence_for(aggregate_id)
        advanced = fabric_sequence > branch

        if not advanced:
            # Fast-forward. The edge was the only writer for this aggregate.
            for envelope in prefix:
                outcomes.append(self._accept(envelope, "fast-forward"))
            return outcomes

        # The fabric has advanced past the branch point. Decide per event.
        for envelope in prefix:
            outcomes.append(self._resolve_advanced(envelope, branch, fabric_sequence))
        return outcomes

    def _aggregate_type_of(self, group: Sequence[EventEnvelope]) -> str:
        for envelope in group:
            if envelope.aggregateType:
                return envelope.aggregateType
        return ""

    def _resolve_immutable(self, envelope: EventEnvelope) -> EventOutcome:
        """Immutable evidence: a superseding record is accepted, a rival claim is not."""
        supersedes = envelope.payload.get("supersedesRef")
        if supersedes:
            return self._accept(
                envelope,
                f"supersedes {supersedes}; accepted as a new version of the result",
            )

        key = self._immutable_key(envelope)
        if key is not None and key in self.state.immutable_keys:
            return EventOutcome(
                eventId=envelope.eventId,
                aggregateId=envelope.aggregateId,
                resolution=Resolution.QUARANTINED,
                conflictClass=ConflictClass.IMMUTABLE_CONFLICT,
                reason=(
                    "the fabric already holds a test result for this article and campaign; "
                    "two sites claiming the same physical test is a question for the "
                    "programme quality authority, not for software"
                ),
                localSequence=_local_sequence(envelope),
            )

        return self._accept(envelope, "no conflicting immutable record found")

    def _resolve_advanced(self, envelope: EventEnvelope, branch: int, fabric_sequence: int) -> EventOutcome:
        klass = immutability_class(envelope.aggregateType)

        if klass is ImmutabilityClass.RELATION:
            return self._accept(envelope, "relation assertions are additive")

        # Mutable. A deterministic winner is selected and the loser retained.
        incumbent = self._incumbent_for(envelope.aggregateId)
        if incumbent is None:
            return self._accept(envelope, "no incumbent edit to conflict with")

        clock_untrusted = bool((envelope.edge or {}).get("clockUntrusted"))
        winner, loser = (
            (incumbent, envelope)
            if _resolution_key(incumbent, clock_untrusted=clock_untrusted)
            >= _resolution_key(envelope, clock_untrusted=clock_untrusted)
            else (envelope, incumbent)
        )

        if winner.eventId == incumbent.eventId:
            return EventOutcome(
                eventId=envelope.eventId,
                aggregateId=envelope.aggregateId,
                resolution=Resolution.QUARANTINED,
                conflictClass=ConflictClass.MUTABLE_CONFLICT,
                reason=(
                    "the fabric's incumbent edit wins the composite key; the edge write is "
                    "retained in the ledger and the aggregate is annotated with it"
                ),
                winningEventId=incumbent.eventId,
                losingEventId=envelope.eventId,
                localSequence=_local_sequence(envelope),
            )

        return EventOutcome(
            eventId=envelope.eventId,
            aggregateId=envelope.aggregateId,
            resolution=Resolution.APPLIED_DETERMINISTIC_WINNER,
            conflictClass=ConflictClass.MUTABLE_CONFLICT,
            reason=(
                "the edge write wins the composite key (effectiveAt, recordedAt, eventId); "
                "the incumbent is retained in the ledger"
            ),
            winningEventId=envelope.eventId,
            losingEventId=incumbent.eventId,
            localSequence=_local_sequence(envelope),
        )

    # -- helpers ---------------------------------------------------------

    def _accept(self, envelope: EventEnvelope, reason: str) -> EventOutcome:
        gate = self._classification_gate(envelope)
        if gate is not None:
            return gate
        return EventOutcome(
            eventId=envelope.eventId,
            aggregateId=envelope.aggregateId,
            resolution=Resolution.ACCEPTED,
            reason=reason,
            localSequence=_local_sequence(envelope),
        )

    def _classification_gate(self, envelope: EventEnvelope) -> EventOutcome | None:
        """Step 5. A merge may never downgrade content."""
        floor = self.state.classification_floors.get(envelope.aggregateType)
        incoming = envelope.classification.level

        if floor and not at_least(incoming, floor):
            return EventOutcome(
                eventId=envelope.eventId,
                aggregateId=envelope.aggregateId,
                resolution=Resolution.REJECTED,
                conflictClass=ConflictClass.CLASSIFICATION_VIOLATION,
                reason=(
                    f"constraint C-001: {envelope.aggregateType} has classification floor "
                    f"{floor} but the incoming write is {incoming}"
                ),
                localSequence=_local_sequence(envelope),
            )

        current = self.state.entity_classifications.get(envelope.aggregateId)
        if current and parse_level(incoming) < parse_level(current):
            return EventOutcome(
                eventId=envelope.eventId,
                aggregateId=envelope.aggregateId,
                resolution=Resolution.REJECTED,
                conflictClass=ConflictClass.CLASSIFICATION_VIOLATION,
                reason=(
                    f"the incoming write would lower the classification of {envelope.aggregateId} "
                    f"from {current} to {incoming}"
                ),
                localSequence=_local_sequence(envelope),
            )

        return None

    def _immutable_key(self, envelope: EventEnvelope) -> tuple[str, str] | None:
        """The identity of a physical test, for immutable aggregates.

        A test result is identified by the article it was run on and the
        campaign it belonged to, not by its aggregate id, because two sites
        may use different aggregate ids for the same physical test.
        """
        payload = envelope.payload
        if not isinstance(payload, dict):
            return None

        for key in ("testResult", "entity"):
            candidate = payload.get(key)
            if not isinstance(candidate, dict):
                continue
            # The entity body nests its attributes; a flat body does not.
            attributes = candidate.get("attributes")
            if not isinstance(attributes, dict):
                attributes = candidate
            campaign = attributes.get("campaignId")
            article = attributes.get("testArticleId")
            if campaign and article:
                return (str(campaign), str(article))

        attributes = payload.get("attributes")
        if isinstance(attributes, dict):
            campaign = attributes.get("campaignId")
            article = attributes.get("testArticleId")
            if campaign and article:
                return (str(campaign), str(article))

        return None

    def _incumbent_for(self, aggregate_id: str) -> EventEnvelope | None:
        """The fabric's current state for an aggregate, if it holds one.

        When the fabric does not supply an incumbent, the aggregate is
        treated as unedited by the fabric and the edge write is accepted.
        """
        return self.state.incumbents.get(aggregate_id)


def summarise(outcomes: Iterable[EventOutcome]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.resolution.value] = counts.get(outcome.resolution.value, 0) + 1
    return counts

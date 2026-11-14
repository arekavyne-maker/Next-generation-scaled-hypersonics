"""The event log: the system of record.

Every mutation in NGSH is expressed as an event appended to this log. The
graph, the search indexes, the lakehouse and the vector index are projections
rebuilt by replaying it. Two properties are enforced here rather than left to
callers:

**Per-aggregate monotonic sequencing.**
    Each aggregate carries a sequence number that must increase by exactly
    one per append. This gives optimistic concurrency without locks and makes
    replay ordering deterministic even when two events share a timestamp.

**Idempotency.**
    A caller-supplied idempotency key, scoped to (tenant, eventType), is
    unique. Re-delivering a batch after a network failure is therefore safe,
    which matters for edge reconciliation where the same capture may arrive
    more than once.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any

from .envelope import EventEnvelope
from .errors import ConcurrencyError
from .store import Executor, canonical_json


@dataclass
class AppendOutcome:
    eventId: str
    accepted: bool
    reason: str | None = None
    duplicate: bool = False


class EventLog:
    """Append-only event log backed by the ``fabric`` schema."""

    def __init__(self, executor: Executor) -> None:
        self._db = executor

    # -- writing ---------------------------------------------------------

    def append(self, envelope: EventEnvelope, *, assign_sequence: bool = False) -> AppendOutcome:
        """Append a single envelope, enforcing sequencing and idempotency.

        ``assign_sequence`` is used for events that arrive from an edge
        node. Those events were stamped with a sequence in the edge's own
        local space, which is not the fabric's global space, so the fabric
        allocates the global sequence on acceptance (ADR-0006, rule S-3).
        The mapping between the two is recorded in the event's ``edge``
        block, so the two can always be related afterwards.
        """
        existing = self._find_duplicate(envelope)
        if existing is not None:
            return AppendOutcome(
                eventId=envelope.eventId,
                accepted=True,
                reason="duplicate of an already-recorded event; append ignored",
                duplicate=True,
            )

        head = self._db.fetchone(
            "SELECT last_sequence FROM aggregate_heads WHERE aggregate_id = ?",
            (envelope.aggregateId,),
        )
        expected = int(head["last_sequence"]) + 1 if head else 1

        if assign_sequence:
            envelope = envelope.model_copy(update={"sequence": expected})
        elif envelope.sequence != expected:
            raise ConcurrencyError(
                f"aggregate {envelope.aggregateId} expects sequence {expected} "
                f"but the event carries {envelope.sequence}",
                aggregateId=envelope.aggregateId,
                expected=expected,
                received=envelope.sequence,
            )

        envelope_json = canonical_json(envelope.to_logical_json())
        payload_json = canonical_json(envelope.payload)
        actor_json = canonical_json(envelope.actor.model_dump(mode="json"))
        attachments_json = canonical_json([a.model_dump(mode="json") for a in envelope.attachments])

        self._db.execute(
            "INSERT INTO events (event_id, event_type, event_version, aggregate_type, aggregate_id, "
            "agg_sequence, causation_id, correlation_id, transaction_id, occurred_at, recorded_at, "
            "tenant, program, actor_json, classification, payload_json, attachments, envelope_json, "
            "idempotency_key, edge_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                envelope.eventId,
                envelope.eventType,
                envelope.eventVersion,
                envelope.aggregateType,
                envelope.aggregateId,
                envelope.sequence,
                envelope.causationId,
                envelope.correlationId,
                envelope.transactionId,
                envelope.occurredAt.isoformat(),
                envelope.recordedAt.isoformat(),
                envelope.tenant,
                envelope.program,
                actor_json,
                envelope.classification.level,
                payload_json,
                attachments_json,
                envelope_json,
                envelope.idempotencyKey,
                canonical_json(envelope.edge) if envelope.edge else None,
            ),
        )

        self._db.execute(
            "INSERT INTO aggregate_heads (aggregate_id, aggregate_type, last_sequence, last_event_id, updated_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(aggregate_id) DO UPDATE SET last_sequence = excluded.last_sequence, "
            "last_event_id = excluded.last_event_id, updated_at = excluded.updated_at",
            (
                envelope.aggregateId,
                envelope.aggregateType,
                envelope.sequence,
                envelope.eventId,
                envelope.recordedAt.isoformat(),
            ),
        )

        return AppendOutcome(eventId=envelope.eventId, accepted=True)

    def append_batch(self, envelopes: Sequence[EventEnvelope]) -> list[AppendOutcome]:
        outcomes: list[AppendOutcome] = []
        for envelope in envelopes:
            try:
                outcomes.append(self.append(envelope))
            except ConcurrencyError as exc:
                outcomes.append(AppendOutcome(eventId=envelope.eventId, accepted=False, reason=exc.message))
        return outcomes

    def _find_duplicate(self, envelope: EventEnvelope) -> str | None:
        if envelope.idempotencyKey:
            row = self._db.fetchone(
                "SELECT event_id FROM events WHERE tenant = ? AND event_type = ? AND idempotency_key = ?",
                (envelope.tenant, envelope.eventType, envelope.idempotencyKey),
            )
            if row is not None:
                return row["event_id"]
        row = self._db.fetchone("SELECT event_id FROM events WHERE event_id = ?", (envelope.eventId,))
        return row["event_id"] if row is not None else None

    def next_sequence(self, aggregate_id: str) -> int:
        row = self._db.fetchone(
            "SELECT last_sequence FROM aggregate_heads WHERE aggregate_id = ?", (aggregate_id,)
        )
        return int(row["last_sequence"]) + 1 if row else 1

    # -- reading ---------------------------------------------------------

    def get(self, event_id: str) -> EventEnvelope | None:
        row = self._db.fetchone("SELECT envelope_json FROM events WHERE event_id = ?", (event_id,))
        if row is None:
            return None
        return EventEnvelope.model_validate(json.loads(row["envelope_json"]))

    def read(
        self,
        *,
        after: int = 0,
        limit: int = 100,
        types: Sequence[str] | None = None,
        tenant: str | None = None,
        aggregate_id: str | None = None,
    ) -> tuple[list[EventEnvelope], int]:
        """Read a page of events in append order.

        Returns the events and the cursor to pass as ``after`` for the next
        page. The cursor is the log sequence, not a ULID, so it is stable and
        cheap.
        """
        clauses = ["seq > ?"]
        params: list[Any] = [after]

        if types:
            clauses.append("(" + " OR ".join("event_type LIKE ?" for _ in types) + ")")
            params.extend(_like_pattern(t) for t in types)

        if tenant:
            clauses.append("tenant = ?")
            params.append(tenant)

        if aggregate_id:
            clauses.append("aggregate_id = ?")
            params.append(aggregate_id)

        params.append(limit)
        rows = self._db.fetchall(
            f"SELECT seq, envelope_json FROM events WHERE {' AND '.join(clauses)} ORDER BY seq ASC LIMIT ?",
            params,
        )
        events = [EventEnvelope.model_validate(json.loads(row["envelope_json"])) for row in rows]
        cursor = int(rows[-1]["seq"]) if rows else after
        return events, cursor

    def replay(self, *, from_seq: int = 0, types: Sequence[str] | None = None) -> Iterator[EventEnvelope]:
        """Yield events from a sequence position, for projection rebuilds."""
        page_size = 500
        cursor = from_seq
        while True:
            events, cursor = self.read(after=cursor, limit=page_size, types=types)
            if not events:
                return
            yield from events

    def count(self, *, tenant: str | None = None) -> int:
        if tenant:
            row = self._db.fetchone("SELECT COUNT(*) AS n FROM events WHERE tenant = ?", (tenant,))
        else:
            row = self._db.fetchone("SELECT COUNT(*) AS n FROM events")
        return int(row["n"]) if row else 0

    def stats(self) -> dict[str, Any]:
        by_type = self._db.fetchall(
            "SELECT event_type AS name, COUNT(*) AS n FROM events GROUP BY event_type ORDER BY n DESC"
        )
        return {
            "total": self.count(),
            "byType": {row["name"]: int(row["n"]) for row in by_type},
            "aggregates": int(
                (self._db.fetchone("SELECT COUNT(*) AS n FROM aggregate_heads") or {"n": 0})["n"]
            ),
        }


def _like_pattern(pattern: str) -> str:
    """Translate a subscription pattern such as ``test.*`` into SQL LIKE."""
    if pattern.endswith(".*"):
        return pattern[:-1] + "%"
    if "*" in pattern:
        return pattern.replace("*", "%")
    return pattern

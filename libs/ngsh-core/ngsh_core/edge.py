"""The edge annex agent.

An edge node is a factory floor, a test range, or an air-gapped analysis
node. It runs the platform's write path while the central fabric is
unreachable, and reconciles when the link returns.

The behaviour is specified in ADR-0006. The properties this module exists to
guarantee:

* **Reads do not depend on the fabric.** The edge serves reads from a local
  projection cache. A site operator gets the same answer whether or not the
  link is up, because an operator who cannot trust the tool offline will
  stop using it.
* **Nothing is lost silently.** The queue is bounded, but every overflow
  drop is recorded and surfaced to the operator.
* **Reconciliation is deterministic.** The same queue and the same fabric
  state always produce the same outcome, on every node.
* **The edge never guesses about physics.** Immutable evidence that conflicts
  is escalated to a human rather than resolved by a rule.

The queue is durable against process failure through SQLite's write-ahead
log. It is not durable against media loss; replicating the queue to a second
local appliance is a site configuration option, not a platform default
(ADR-0006, N-5).
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .envelope import EventEnvelope, utcnow
from .ids import new_ulid
from .store import canonical_json

#: Queue priorities, highest first. Used to decide what survives an
#: overflow. The ordering is domain policy: the ADR records that the
#: overflow policy must be agreed with the programme, not chosen by the
#: platform team.
PRIORITY_HIGH = 30
PRIORITY_NORMAL = 20
PRIORITY_LOW = 10

#: Event types that carry evidence about a physical test. These are the
#: highest priority because losing one is losing a test.
HIGH_PRIORITY_EVENT_TYPES = {"test.result.recorded", "process.run.completed"}

#: Event types that are operationally cheap to regenerate.
LOW_PRIORITY_EVENT_TYPES = {"access.decision.recorded"}


def priority_for(event_type: str) -> int:
    if event_type in HIGH_PRIORITY_EVENT_TYPES:
        return PRIORITY_HIGH
    if event_type in LOW_PRIORITY_EVENT_TYPES:
        return PRIORITY_LOW
    return PRIORITY_NORMAL


@dataclass
class QueueEntry:
    """One queued event with its edge-local sequence."""

    localSequence: int
    aggregateId: str
    eventId: str
    eventType: str
    priority: int
    capturedAt: str
    branchedFromSeq: int
    envelope: EventEnvelope

    def to_dict(self) -> dict[str, Any]:
        return {
            "localSequence": self.localSequence,
            "aggregateId": self.aggregateId,
            "eventId": self.eventId,
            "eventType": self.eventType,
            "priority": self.priority,
            "capturedAt": self.capturedAt,
            "branchedFromSeq": self.branchedFromSeq,
            "envelope": self.envelope.to_logical_json(),
        }


@dataclass
class DroppedEntry:
    """An event discarded by queue overflow.

    Silent loss is prohibited (ADR-0006). Every drop is recorded, counted
    and surfaced to the operator.
    """

    eventId: str
    aggregateId: str
    eventType: str
    priority: int
    capturedAt: str
    droppedAt: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "eventId": self.eventId,
            "aggregateId": self.aggregateId,
            "eventType": self.eventType,
            "priority": self.priority,
            "capturedAt": self.capturedAt,
            "droppedAt": self.droppedAt,
            "reason": self.reason,
        }


class EdgeQueue:
    """Durable, bounded, store-and-forward queue of pending events.

    The queue is local to the edge node and holds its own sequence space per
    aggregate, independent of the fabric's global sequence space (ADR-0006,
    rule S-1).
    """

    def __init__(self, path: Path | str, *, capacity: int = 10_000, node_id: str = "edge:unknown") -> None:
        self.node_id = node_id
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._capacity = capacity
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._bootstrap()

    def _bootstrap(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS edge_queue (
                local_sequence   INTEGER PRIMARY KEY AUTOINCREMENT,
                aggregate_id     TEXT NOT NULL,
                event_id         TEXT NOT NULL UNIQUE,
                event_type       TEXT NOT NULL,
                priority         INTEGER NOT NULL,
                captured_at      TEXT NOT NULL,
                branched_from_seq INTEGER NOT NULL DEFAULT 0,
                aggregate_local_seq INTEGER NOT NULL,
                envelope_json    TEXT NOT NULL,
                acknowledged     INTEGER NOT NULL DEFAULT 0,
                quarantined      INTEGER NOT NULL DEFAULT 0,
                quarantine_reason TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_edge_queue_pending
                ON edge_queue (acknowledged, quarantined, aggregate_id, aggregate_local_seq);
            CREATE TABLE IF NOT EXISTS edge_local_sequence (
                aggregate_id TEXT PRIMARY KEY,
                last_local_seq INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS edge_branch (
                aggregate_id TEXT PRIMARY KEY,
                last_known_fabric_seq INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS edge_drops (
                event_id TEXT PRIMARY KEY,
                body_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS edge_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        self._conn.commit()

    # -- writing ---------------------------------------------------------

    def append(self, envelope: EventEnvelope) -> QueueEntry:
        """Queue an event, allocating its edge-local sequence."""
        with self._lock:
            aggregate_local_seq = self._next_aggregate_sequence(envelope.aggregateId)
            branched_from = self._branch_point(envelope.aggregateId)
            captured_at = utcnow().isoformat()

            edge_block = dict(envelope.edge or {})
            edge_block.update(
                {
                    "nodeId": self.node_id,
                    "capturedAt": captured_at,
                    "localSequence": aggregate_local_seq,
                    "branchedFromSeq": branched_from,
                }
            )
            stamped = envelope.model_copy(update={"edge": edge_block})

            entry = QueueEntry(
                localSequence=aggregate_local_seq,
                aggregateId=envelope.aggregateId,
                eventId=envelope.eventId,
                eventType=envelope.eventType,
                priority=priority_for(envelope.eventType),
                capturedAt=captured_at,
                branchedFromSeq=branched_from,
                envelope=stamped,
            )

            self._conn.execute(
                "INSERT INTO edge_queue (aggregate_id, event_id, event_type, priority, captured_at, "
                "branched_from_seq, aggregate_local_seq, envelope_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry.aggregateId,
                    entry.eventId,
                    entry.eventType,
                    entry.priority,
                    entry.capturedAt,
                    entry.branchedFromSeq,
                    entry.localSequence,
                    canonical_json(stamped.to_logical_json()),
                ),
            )
            self._conn.execute(
                "INSERT INTO edge_local_sequence (aggregate_id, last_local_seq) VALUES (?, ?) "
                "ON CONFLICT(aggregate_id) DO UPDATE SET last_local_seq = excluded.last_local_seq",
                (envelope.aggregateId, aggregate_local_seq),
            )
            self._conn.commit()

            self._enforce_capacity()
            return entry

    def _next_aggregate_sequence(self, aggregate_id: str) -> int:
        row = self._conn.execute(
            "SELECT last_local_seq FROM edge_local_sequence WHERE aggregate_id = ?", (aggregate_id,)
        ).fetchone()
        return int(row["last_local_seq"]) + 1 if row else 1

    def _branch_point(self, aggregate_id: str) -> int:
        row = self._conn.execute(
            "SELECT last_known_fabric_seq FROM edge_branch WHERE aggregate_id = ?", (aggregate_id,)
        ).fetchone()
        return int(row["last_known_fabric_seq"]) if row else 0

    def set_branch_point(self, aggregate_id: str, fabric_sequence: int) -> None:
        """Record the fabric sequence the edge last saw for an aggregate."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO edge_branch (aggregate_id, last_known_fabric_seq) VALUES (?, ?) "
                "ON CONFLICT(aggregate_id) DO UPDATE SET "
                "last_known_fabric_seq = MAX(last_known_fabric_seq, excluded.last_known_fabric_seq)",
                (aggregate_id, fabric_sequence),
            )
            self._conn.commit()

    def _enforce_capacity(self) -> None:
        """Drop the lowest-priority, oldest entries when over capacity.

        Ties on priority are broken by age, so a burst of low-priority
        telemetry cannot evict the high-priority evidence queued alongside it.
        """
        while self.pending_count() > self._capacity:
            row = self._conn.execute(
                "SELECT local_sequence, aggregate_id, event_id, event_type, priority, captured_at "
                "FROM edge_queue WHERE acknowledged = 0 AND quarantined = 0 "
                "ORDER BY priority ASC, captured_at ASC, local_sequence ASC LIMIT 1"
            ).fetchone()
            if row is None:
                return
            dropped = DroppedEntry(
                eventId=row["event_id"],
                aggregateId=row["aggregate_id"],
                eventType=row["event_type"],
                priority=int(row["priority"]),
                capturedAt=row["captured_at"],
                droppedAt=utcnow().isoformat(),
                reason=(
                    f"queue capacity {self._capacity} exceeded; dropped by the declared "
                    "priority-then-age policy"
                ),
            )
            self._conn.execute("DELETE FROM edge_queue WHERE local_sequence = ?", (row["local_sequence"],))
            self._conn.execute(
                "INSERT OR REPLACE INTO edge_drops (event_id, body_json) VALUES (?, ?)",
                (dropped.eventId, canonical_json(dropped.to_dict())),
            )
            self._conn.commit()

    # -- reading ---------------------------------------------------------

    def pending(self, *, limit: int = 500) -> list[QueueEntry]:
        """Pending events, ordered by aggregate and local sequence.

        The ordering is what makes the push deterministic: the fabric sees
        the edge's events in the edge's own sequence order, per aggregate.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT envelope_json, aggregate_local_seq, aggregate_id, event_id, event_type, "
                "priority, captured_at, branched_from_seq FROM edge_queue "
                "WHERE acknowledged = 0 AND quarantined = 0 "
                "ORDER BY aggregate_id ASC, aggregate_local_seq ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            QueueEntry(
                localSequence=int(row["aggregate_local_seq"]),
                aggregateId=row["aggregate_id"],
                eventId=row["event_id"],
                eventType=row["event_type"],
                priority=int(row["priority"]),
                capturedAt=row["captured_at"],
                branchedFromSeq=int(row["branched_from_seq"]),
                envelope=EventEnvelope.model_validate(json.loads(row["envelope_json"])),
            )
            for row in rows
        ]

    def pending_count(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM edge_queue WHERE acknowledged = 0 AND quarantined = 0"
        ).fetchone()
        return int(row["n"]) if row else 0

    def dropped(self) -> list[DroppedEntry]:
        """Every event the queue has discarded. Silent loss is prohibited."""
        with self._lock:
            rows = self._conn.execute("SELECT body_json FROM edge_drops ORDER BY event_id").fetchall()
        return [DroppedEntry(**json.loads(row["body_json"])) for row in rows]

    def acknowledge(self, event_ids: Sequence[str]) -> int:
        """Remove acknowledged events from the queue."""
        if not event_ids:
            return 0
        with self._lock:
            placeholders = ",".join("?" for _ in event_ids)
            cursor = self._conn.execute(
                f"UPDATE edge_queue SET acknowledged = 1 WHERE event_id IN ({placeholders})",
                list(event_ids),
            )
            self._conn.commit()
            return cursor.rowcount

    def requeue(self, event_id: str) -> bool:
        """Offer an event to the fabric again.

        Used when an acknowledgement is lost in transit: the edge cannot
        know whether the fabric applied the event, so it retries. The
        fabric's idempotency makes the retry safe.
        """
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE edge_queue SET acknowledged = 0, quarantined = 0 WHERE event_id = ?",
                (event_id,),
            )
            self._conn.commit()
            return cursor.rowcount > 0

    def quarantine(self, event_id: str, reason: str) -> None:
        """Retain an event the fabric could not decide, for operator review."""
        with self._lock:
            self._conn.execute(
                "UPDATE edge_queue SET quarantined = 1, quarantine_reason = ? WHERE event_id = ?",
                (reason, event_id),
            )
            self._conn.commit()

    def quarantined(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT event_id, aggregate_id, event_type, quarantine_reason FROM edge_queue "
                "WHERE quarantined = 1 ORDER BY local_sequence"
            ).fetchall()
        return [dict(row) for row in rows]

    def aggregates(self) -> dict[str, int]:
        """The edge's local high-water mark per aggregate."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT aggregate_id, MAX(aggregate_local_seq) AS seq FROM edge_queue GROUP BY aggregate_id"
            ).fetchall()
        return {row["aggregate_id"]: int(row["seq"]) for row in rows}

    def close(self) -> None:
        with self._lock:
            self._conn.close()


@dataclass
class ConnectionState:
    """What the local console shows about the link to the fabric."""

    connected: bool = False
    lastSyncAt: str | None = None
    lastAttemptAt: str | None = None
    lastError: str | None = None
    pendingCount: int = 0
    quarantinedCount: int = 0
    droppedCount: int = 0
    clockSkewMs: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "lastSyncAt": self.lastSyncAt,
            "lastAttemptAt": self.lastAttemptAt,
            "lastError": self.lastError,
            "pendingCount": self.pendingCount,
            "quarantinedCount": self.quarantinedCount,
            "droppedCount": self.droppedCount,
            "clockSkewMs": self.clockSkewMs,
        }


@dataclass
class SyncReport:
    """The outcome of one reconciliation attempt."""

    attempted: bool = False
    accepted: list[str] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)
    quarantined: list[dict[str, Any]] = field(default_factory=list)
    rejected: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    clockSkewMs: float | None = None
    syncedAt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "accepted": list(self.accepted),
            "duplicates": list(self.duplicates),
            "quarantined": list(self.quarantined),
            "rejected": list(self.rejected),
            "error": self.error,
            "clockSkewMs": self.clockSkewMs,
            "syncedAt": self.syncedAt,
        }


class EdgeAgent:
    """The edge node's capture and reconciliation agent.

    The agent owns a queue and a local projection cache. It never requires
    the fabric to be reachable in order to accept a write or serve a read.
    """

    def __init__(
        self,
        node_id: str,
        queue: EdgeQueue,
        *,
        fabric_url: str = "",
        capacity: int = 10_000,
        clock_untrusted: bool = False,
    ) -> None:
        self.node_id = node_id
        self.queue = queue
        # The queue stamps the node id onto every event it holds, so a queue
        # and its agent always agree on which node captured the write.
        self.queue.node_id = node_id
        self.fabric_url = fabric_url
        self.capacity = capacity
        self.clock_untrusted = clock_untrusted
        self.state = ConnectionState()
        self._cache: dict[str, dict[str, Any]] = {}

    # -- degraded mode ---------------------------------------------------

    def capture(self, envelope: EventEnvelope) -> QueueEntry:
        """Capture an event locally. Never contacts the fabric."""
        entry = self.queue.append(envelope)
        self._cache[envelope.aggregateId] = envelope.to_logical_json()
        self.state.pendingCount = self.queue.pending_count()
        return entry

    def read(self, aggregate_id: str) -> dict[str, Any] | None:
        """Read from the local cache. Identical connected or disconnected."""
        return self._cache.get(aggregate_id)

    def status(self) -> dict[str, Any]:
        self.state.pendingCount = self.queue.pending_count()
        self.state.quarantinedCount = len(self.queue.quarantined())
        self.state.droppedCount = len(self.queue.dropped())
        return {
            "nodeId": self.node_id,
            "capacity": self.capacity,
            "clockUntrusted": self.clock_untrusted,
            "connection": self.state.to_dict(),
            "aggregates": self.queue.aggregates(),
        }

    # -- reconciliation --------------------------------------------------

    def sync(self, transport: Callable[[str, dict[str, Any]], dict[str, Any]]) -> SyncReport:
        """Attempt one reconciliation cycle.

        The transport is injected so that the same logic is exercised by the
        unit tests, by the local demonstration, and by the HTTP client
        without the reconciliation rules having any knowledge of HTTP.
        """
        report = SyncReport(attempted=True, syncedAt=utcnow().isoformat())
        self.state.lastAttemptAt = report.syncedAt

        pending = self.queue.pending()
        if not pending:
            self.state.connected = True
            return report

        payload = {
            "nodeId": self.node_id,
            "clockUntrusted": self.clock_untrusted,
            "aggregates": self.queue.aggregates(),
            "events": [entry.envelope.to_logical_json() for entry in pending],
        }

        try:
            response = transport(self.fabric_url, payload)
        except Exception as exc:
            self.state.connected = False
            self.state.lastError = f"{type(exc).__name__}: {exc}"
            report.error = self.state.lastError
            return report

        self.state.connected = True
        self.state.lastError = None
        self.state.lastSyncAt = report.syncedAt

        accepted = [entry["eventId"] for entry in response.get("accepted", [])]
        duplicates = [entry["eventId"] for entry in response.get("duplicates", [])]
        quarantined = response.get("quarantined", [])
        rejected = response.get("rejected", [])
        clock_skew = response.get("clockSkewMs")

        report.accepted = accepted
        report.duplicates = duplicates
        report.quarantined = quarantined
        report.rejected = rejected
        report.clockSkewMs = clock_skew
        self.state.clockSkewMs = clock_skew

        self.queue.acknowledge(accepted + duplicates)
        for entry in quarantined:
            self.queue.quarantine(entry["eventId"], entry.get("reason", "quarantined by the fabric"))

        # The fabric's high-water mark becomes the edge's new branch point.
        for aggregate_id, sequence in (response.get("aggregateSequences") or {}).items():
            self.queue.set_branch_point(aggregate_id, int(sequence))

        self.state.pendingCount = self.queue.pending_count()
        return report

    def dropped(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self.queue.dropped()]


def http_transport(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Transport that pushes a batch to the fabric over HTTP.

    Kept separate from :class:`EdgeAgent` so that the reconciliation rules
    stay independent of the network.
    """
    import urllib.request

    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/edge/reconcile",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
    )
    request.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def build_agent(
    node_id: str,
    queue_path: Path | str,
    *,
    fabric_url: str = "",
    capacity: int = 10_000,
    clock_untrusted: bool = False,
) -> EdgeAgent:
    queue = EdgeQueue(queue_path, capacity=capacity, node_id=node_id)
    return EdgeAgent(
        node_id,
        queue,
        fabric_url=fabric_url,
        capacity=capacity,
        clock_untrusted=clock_untrusted,
    )


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def new_batch_id() -> str:
    return f"EDGE:{new_ulid()}"

"""Storage layer.

The foundation stores are accessed through a small executor interface so that
the same repositories run against SQLite (local development, edge annex, CI)
and PostgreSQL (accredited cloud enclave, on-prem IL6 node) without change.
Only two dialects are in play and the difference is limited to placeholder
style and a handful of DDL statements, both handled here.

Schema layout, mirroring ``deploy/compose/postgres/init.sql``:

``fabric``
    The append-only event log. Never updated, never deleted.
``audit``
    The hash-chained ledger. Append-only, verified on demand.
``graph``
    Materialised projection of the digital thread.
``ontology``
    Entity snapshots written by the ontology service.
``ingest``
    Batch accounting for bulk ingestion.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Protocol

from .errors import ConflictError

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS events (
        seq            INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id       TEXT NOT NULL UNIQUE,
        event_type     TEXT NOT NULL,
        event_version  INTEGER NOT NULL,
        aggregate_type TEXT NOT NULL,
        aggregate_id   TEXT NOT NULL,
        agg_sequence   INTEGER NOT NULL,
        causation_id   TEXT,
        correlation_id TEXT,
        transaction_id TEXT,
        occurred_at    TEXT NOT NULL,
        recorded_at    TEXT NOT NULL,
        tenant         TEXT NOT NULL,
        program        TEXT,
        actor_json     TEXT NOT NULL,
        classification TEXT NOT NULL,
        payload_json   TEXT NOT NULL,
        attachments    TEXT NOT NULL,
        envelope_json  TEXT NOT NULL,
        idempotency_key TEXT,
        edge_json      TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_events_aggregate ON events (aggregate_id, agg_sequence)",
    "CREATE INDEX IF NOT EXISTS idx_events_type ON events (event_type)",
    "CREATE INDEX IF NOT EXISTS idx_events_tenant ON events (tenant, seq)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_idem ON events (tenant, event_type, idempotency_key) WHERE idempotency_key IS NOT NULL",
    """
    CREATE TABLE IF NOT EXISTS aggregate_heads (
        aggregate_id   TEXT PRIMARY KEY,
        aggregate_type TEXT NOT NULL,
        last_sequence  INTEGER NOT NULL,
        last_event_id  TEXT NOT NULL,
        updated_at     TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ledger (
        seq        INTEGER PRIMARY KEY AUTOINCREMENT,
        hash       TEXT NOT NULL UNIQUE,
        prev_hash  TEXT NOT NULL,
        timestamp  TEXT NOT NULL,
        event_type TEXT NOT NULL,
        entry_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS entities (
        id             TEXT PRIMARY KEY,
        type           TEXT NOT NULL,
        tenant         TEXT NOT NULL,
        program        TEXT,
        version        INTEGER NOT NULL,
        classification TEXT NOT NULL,
        body_json      TEXT NOT NULL,
        updated_at     TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_entities_type ON entities (type, tenant)",
    """
    CREATE TABLE IF NOT EXISTS relations (
        id             TEXT PRIMARY KEY,
        type           TEXT NOT NULL,
        from_type      TEXT NOT NULL,
        from_id        TEXT NOT NULL,
        to_type        TEXT NOT NULL,
        to_id          TEXT NOT NULL,
        tenant         TEXT,
        classification TEXT NOT NULL,
        asserted_at    TEXT NOT NULL,
        retracted_at   TEXT,
        body_json      TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_relations_from ON relations (from_type, from_id)",
    "CREATE INDEX IF NOT EXISTS idx_relations_to ON relations (to_type, to_id)",
    """
    CREATE TABLE IF NOT EXISTS ingest_batches (
        batch_id      TEXT PRIMARY KEY,
        source        TEXT NOT NULL,
        format        TEXT NOT NULL,
        classification TEXT NOT NULL,
        records_accepted INTEGER NOT NULL,
        records_rejected INTEGER NOT NULL,
        bytes_accepted   INTEGER NOT NULL,
        sha256        TEXT,
        object_uri    TEXT,
        entity_ids    TEXT NOT NULL,
        created_at    TEXT NOT NULL,
        body_json     TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS projections (
        name       TEXT PRIMARY KEY,
        cursor_seq INTEGER NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
)


class Executor(Protocol):
    """Minimal SQL executor shared by the SQLite and PostgreSQL backends."""

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None: ...

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]: ...

    def fetchone(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None: ...

    def insert_returning_id(self, sql: str, params: Sequence[Any] = ()) -> int: ...


class SqliteExecutor:
    """SQLite-backed executor.

    SQLite is the default because it lets the whole foundation run on a
    developer laptop, in CI, and on an edge annex with no external service
    dependency. The write-ahead log and ``busy_timeout`` keep concurrent
    appends safe.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = str(path)
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._lock = threading.RLock()

    def _write(self, sql: str, params: Sequence[Any]) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            return cursor

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        self._write(sql, params)

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            cursor = self._conn.execute(sql, tuple(params))
            return [dict(row) for row in cursor.fetchall()]

    def fetchone(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        with self._lock:
            cursor = self._conn.execute(sql, tuple(params))
            row = cursor.fetchone()
            return dict(row) if row is not None else None

    def insert_returning_id(self, sql: str, params: Sequence[Any] = ()) -> int:
        cursor = self._write(sql, params)
        return int(cursor.lastrowid or 0)

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def open_database(dsn: str) -> Executor:
    """Open the configured database and ensure the schema exists."""
    if dsn.startswith("sqlite:///"):
        raw = dsn[len("sqlite:///") :]
        executor: Executor = SqliteExecutor(raw or ":memory:")
    elif dsn.startswith("sqlite://"):
        executor = SqliteExecutor(":memory:")
    else:
        raise NotImplementedError(
            f"DSN {dsn!r} requires the PostgreSQL backend. The PostgreSQL executor "
            "is introduced in Increment 0.4; until then use the sqlite DSN."
        )
    for statement in SCHEMA_STATEMENTS:
        executor.execute(statement)
    return executor


def canonical_json(value: Any) -> str:
    """Deterministic JSON encoding used for hashing and identity comparison.

    Keys are sorted, separators are tight, and non-ASCII is preserved so that
    a hash computed on one node matches one computed on another.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def loads(value: str | bytes | None, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def chunks(items: Iterable[Any], size: int) -> Iterable[list[Any]]:
    """Batch an iterable into fixed-size lists."""
    batch: list[Any] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def ensure_unique(connection: sqlite3.Connection, message: str) -> None:
    """Raise a domain conflict error on a uniqueness violation."""
    try:
        connection.execute("SELECT 1")
    except sqlite3.IntegrityError as exc:  # pragma: no cover - defensive
        raise ConflictError(message) from exc

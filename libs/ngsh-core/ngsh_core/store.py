"""Storage layer.

The foundation stores are accessed through a small executor interface so that
the same repositories run against SQLite (local development, edge annex, CI)
and PostgreSQL (accredited cloud enclave, on-prem IL6 node) without change.

Two dialects are in play, and the differences are deliberately narrow:

* **Placeholders.** The repositories write ``?``; the PostgreSQL executor
  rewrites them to ``%s``. The rewrite is safe because no SQL text in the
  platform contains a literal ``%`` — LIKE patterns are always passed as
  parameters, never interpolated — and the executor asserts this rather
  than assuming it.
* **Schema.** The DDL differs in exactly one construct: SQLite's
  ``INTEGER PRIMARY KEY AUTOINCREMENT`` is PostgreSQL's ``SERIAL PRIMARY
  KEY``. Everything else — the partial unique index, the upsert clauses, the
  ``COALESCE`` aggregates — is in the portable subset of both.

The result is that the same image runs unchanged on a developer laptop and
in an accredited enclave, which is the property ADR-0003 requires and which
the deployment layer assumes.

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
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class Dialect:
    """The differences between two SQL dialects."""

    name: str = "sqlite"
    #: The column definition used for an auto-incrementing primary key.
    serial_pk: str = "INTEGER PRIMARY KEY AUTOINCREMENT"

    def translate(self, sql: str) -> str:
        """Rewrite a statement for this dialect."""
        return sql


@dataclass(frozen=True)
class SqliteDialect(Dialect):
    name: str = "sqlite"
    serial_pk: str = "INTEGER PRIMARY KEY AUTOINCREMENT"

    def translate(self, sql: str) -> str:
        return sql


@dataclass(frozen=True)
class PostgresDialect(Dialect):
    name: str = "postgresql"
    serial_pk: str = "SERIAL PRIMARY KEY"

    def translate(self, sql: str) -> str:
        """Rewrite SQLite placeholders as PostgreSQL placeholders.

        The repositories write ``?`` everywhere. PostgreSQL's parameter
        marker is ``%s``. The rewrite is a plain substitution because the
        platform's SQL text contains no literal ``%``; a LIKE pattern is
        always a parameter. The check below turns that assumption into an
        error rather than a silent corruption.
        """
        if "%" in sql:
            raise ValueError(
                "SQL text contains a literal '%', which is ambiguous when "
                "translating placeholders for PostgreSQL. Pass the pattern as "
                "a parameter instead."
            )
        return sql.replace("?", "%s")


SQLITE_DIALECT = SqliteDialect()
POSTGRES_DIALECT = PostgresDialect()


def schema_statements(dialect: Dialect) -> tuple[str, ...]:
    """The platform schema for a dialect."""
    pk = dialect.serial_pk
    return (
        f"""
        CREATE TABLE IF NOT EXISTS events (
            seq            {pk},
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
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_events_idem "
        "ON events (tenant, event_type, idempotency_key) WHERE idempotency_key IS NOT NULL",
        """
        CREATE TABLE IF NOT EXISTS aggregate_heads (
            aggregate_id   TEXT PRIMARY KEY,
            aggregate_type TEXT NOT NULL,
            last_sequence  INTEGER NOT NULL,
            last_event_id  TEXT NOT NULL,
            updated_at     TEXT NOT NULL
        )
        """,
        f"""
        CREATE TABLE IF NOT EXISTS ledger (
            seq        {pk},
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

    dialect: Dialect

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None: ...

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]: ...

    def fetchone(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None: ...

    def insert_returning_id(self, sql: str, params: Sequence[Any] = ()) -> int: ...

    def close(self) -> None: ...

    @property
    def rowcount(self) -> int:
        """Rows affected by the most recent statement."""
        return 0


class SqliteExecutor:
    """SQLite-backed executor.

    SQLite is the default because it lets the whole foundation run on a
    developer laptop, in CI, and on an edge annex with no external service
    dependency. The write-ahead log and ``busy_timeout`` keep concurrent
    appends safe.
    """

    dialect = SQLITE_DIALECT

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
        self._rowcount = 0

    def _write(self, sql: str, params: Sequence[Any]) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._conn.execute(sql, tuple(params))
            self._conn.commit()
            self._rowcount = cursor.rowcount
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

    @property
    def rowcount(self) -> int:
        return self._rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()


class PostgresExecutor:
    """PostgreSQL-backed executor.

    This is the backend used in the accredited cloud enclave and on the
    on-prem IL6 node. It speaks the same repository interface as the SQLite
    executor, so nothing above the storage layer changes.

    The driver is psycopg 3, with psycopg2 accepted as a fallback. Both are
    imported lazily so that a deployment which only ever uses SQLite does
    not carry the dependency.
    """

    dialect = POSTGRES_DIALECT

    def __init__(self, dsn: str) -> None:
        self._lock = threading.RLock()
        self._rowcount = 0
        self._conn, self._backend = _connect_postgres(dsn)
        self._conn.autocommit = True

    def _run(self, sql: str, params: Sequence[Any], *, fetch: str = "none"):
        statement = self.dialect.translate(sql)
        with self._lock, self._conn.cursor() as cursor:
            cursor.execute(statement, tuple(params))
            if fetch == "all":
                rows = cursor.fetchall()
                return [self._row_to_dict(row) for row in rows]
            if fetch == "one":
                row = cursor.fetchone()
                return self._row_to_dict(row) if row is not None else None
            return None

    @staticmethod
    def _row_to_dict(row: Any) -> dict[str, Any]:
        if row is None:
            return {}
        if isinstance(row, dict):
            return dict(row)
        description = getattr(row, "_fields", None)
        if description is None:
            return dict(row)
        return dict(zip(description, row, strict=False))

    def execute(self, sql: str, params: Sequence[Any] = ()) -> None:
        self._run(sql, params)

    def fetchall(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        return self._run(sql, params, fetch="all") or []

    def fetchone(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        return self._run(sql, params, fetch="one")

    def insert_returning_id(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Insert a row and return the generated key.

        The caller appends ``RETURNING id`` so that the key comes back in
        the same statement rather than in a second round trip. The
        identifier column is named ``seq`` in the platform schema.
        """
        statement = self.dialect.translate(sql.rstrip().rstrip(";") + " RETURNING seq")
        with self._lock, self._conn.cursor() as cursor:
            cursor.execute(statement, tuple(params))
            row = cursor.fetchone()
            self._rowcount = cursor.rowcount
            if row is None:
                return 0
            value = self._row_to_dict(row).get("seq")
            return int(value) if value is not None else 0

    @property
    def rowcount(self) -> int:
        return self._rowcount

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _connect_postgres(dsn: str) -> tuple[Any, str]:
    """Open a PostgreSQL connection using whichever driver is installed."""
    try:
        import psycopg  # type: ignore[import-not-found]

        return psycopg.connect(dsn), "psycopg3"
    except ImportError:
        pass
    try:
        import psycopg2  # type: ignore[import-not-found]

        return psycopg2.connect(dsn), "psycopg2"
    except ImportError as exc:
        raise RuntimeError(
            "the PostgreSQL backend needs a driver: install 'psycopg[binary]' "
            "or 'psycopg2-binary'. A SQLite deployment does not need either."
        ) from exc


def open_database(dsn: str) -> Executor:
    """Open the configured database and ensure the schema exists."""
    if dsn.startswith("sqlite:///"):
        raw = dsn[len("sqlite:///") :]
        executor: Executor = SqliteExecutor(raw or ":memory:")
    elif dsn.startswith("sqlite://"):
        executor = SqliteExecutor(":memory:")
    elif dsn.startswith("postgresql://") or dsn.startswith("postgres://"):
        executor = PostgresExecutor(dsn)
    else:
        raise ValueError(f"unsupported DSN {dsn!r}: use a sqlite:// or postgresql:// URL")

    for statement in schema_statements(executor.dialect):
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

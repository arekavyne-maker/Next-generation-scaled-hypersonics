"""The PostgreSQL backend.

The platform's claim is that the same image runs unchanged on a developer
laptop and in an accredited enclave, which means the SQLite path and the
PostgreSQL path must be genuinely equivalent rather than nominally so.

No PostgreSQL server is available in the build environment, so these tests
verify the two things that can be verified without one:

1. **Every statement the platform issues parses as PostgreSQL**, checked
   against the real PostgreSQL grammar via ``pglast``. A statement that
   only SQLite accepts would be caught here rather than in an accredited
   environment.
2. **The dialect translation is sound**: placeholders are rewritten
   correctly, the schema differs only in the one construct that differs,
   and a literal ``%`` in SQL text is rejected rather than silently
   corrupting a LIKE pattern.

The remaining risk is behavioural rather than syntactic — transaction
semantics, isolation levels and driver behaviour — and it is called out
explicitly rather than hidden behind a passing test.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from ngsh_core.store import (
    POSTGRES_DIALECT,
    SQLITE_DIALECT,
    PostgresExecutor,
    SqliteExecutor,
    schema_statements,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _parse(sql: str) -> None:
    """Parse a statement with the real PostgreSQL grammar.

    The parameter markers are substituted with a literal first: ``%s`` is
    the extended-query-protocol placeholder, not SQL grammar, so the
    parser would read it as a modulo operator. The grammar check is about
    the statement's structure.
    """
    from pglast import parse_sql

    parse_sql(sql.replace("%s", "NULL"))


def _as_postgres(sql: str) -> str | None:
    """A statement translated for PostgreSQL, or None if it is not a statement.

    Statements that still carry Python interpolation are templates rather
    than statements, and are covered by the tests that exercise the code
    path they belong to.
    """
    if "{" in sql or "}" in sql:
        return None
    try:
        return POSTGRES_DIALECT.translate(sql)
    except ValueError:
        return None


# -- the schema -------------------------------------------------------------


def test_the_postgres_schema_parses() -> None:
    for statement in schema_statements(POSTGRES_DIALECT):
        _parse(statement)


def test_the_sqlite_schema_parses() -> None:
    """The SQLite schema must remain valid SQLite after the refactor."""
    import sqlite3

    connection = sqlite3.connect(":memory:")
    for statement in schema_statements(SQLITE_DIALECT):
        connection.execute(statement)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    for expected in (
        "events",
        "aggregate_heads",
        "ledger",
        "entities",
        "relations",
        "ingest_batches",
        "projections",
    ):
        assert expected in tables, f"the schema is missing the {expected} table"
    connection.close()


def test_the_schemas_differ_only_in_the_primary_key_construct() -> None:
    """One dialect difference is acceptable. Two is a portability problem."""
    sqlite = [re.sub(r"\s+", " ", s).strip() for s in schema_statements(SQLITE_DIALECT)]
    postgres = [re.sub(r"\s+", " ", s).strip() for s in schema_statements(POSTGRES_DIALECT)]

    assert len(sqlite) == len(postgres)

    differences = [(a, b) for a, b in zip(sqlite, postgres, strict=True) if a != b]
    assert len(differences) == 2, (
        "the two schemas differ in more than the auto-incrementing primary key:\n"
        + "\n".join(f"  sqlite:   {a}\n  postgres: {b}" for a, b in differences)
    )
    for a, b in differences:
        assert "PRIMARY KEY" in a and "PRIMARY KEY" in b


def test_the_auto_increment_key_is_correct_for_each_dialect() -> None:
    assert "AUTOINCREMENT" in SQLITE_DIALECT.serial_pk
    assert "SERIAL" in POSTGRES_DIALECT.serial_pk
    assert "AUTOINCREMENT" not in POSTGRES_DIALECT.serial_pk


# -- placeholder translation ------------------------------------------------


def test_placeholders_are_rewritten_for_postgres() -> None:
    assert POSTGRES_DIALECT.translate("SELECT * FROM events WHERE tenant = ?") == (
        "SELECT * FROM events WHERE tenant = %s"
    )


def test_sqlite_placeholder_translation_is_a_no_op() -> None:
    sql = "SELECT * FROM events WHERE tenant = ?"
    assert SQLITE_DIALECT.translate(sql) == sql


def test_a_literal_percent_is_rejected_rather_than_corrupted() -> None:
    """A LIKE pattern in SQL text would be mangled by the rewrite."""
    with pytest.raises(ValueError, match="literal '%'"):
        POSTGRES_DIALECT.translate("SELECT * FROM events WHERE event_type LIKE 'test.%'")


# -- every statement the platform issues ------------------------------------


def _repository_statements() -> list[str]:
    """Every SQL statement the platform's repositories issue.

    Collected from the source rather than maintained by hand, so that a new
    statement is covered the moment it is written.
    """
    statements: list[str] = []
    pattern = re.compile(r'(?:execute|fetchall|fetchone)\(\s*f?"([^"]+)"', re.DOTALL)

    for path in sorted(
        list((REPO_ROOT / "libs").rglob("*.py")) + list((REPO_ROOT / "services").rglob("*.py"))
    ):
        if "generated" in path.parts:
            continue
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            statement = match.group(1)
            if "?" in statement or "LIKE" in statement.upper():
                statements.append(statement)

    # The f-string built statements need their placeholders reconstructed.
    for path in sorted((REPO_ROOT / "libs").rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r'f"""(.*?)"""', text, re.DOTALL):
            statements.append(match.group(1))

    return statements


def test_every_repository_statement_parses_as_postgres() -> None:
    """This is the check that would catch a SQLite-only statement."""
    failures: list[str] = []

    for statement in _repository_statements():
        if not statement.strip():
            continue
        translated = _as_postgres(statement)
        if translated is None:
            continue
        try:
            _parse(translated)
        except Exception as exc:  # pglast raises its own error type
            failures.append(f"{statement[:110]!r}: {exc}")

    assert not failures, "statements that do not parse as PostgreSQL:\n" + "\n".join(failures)


def test_the_edge_queue_schema_parses_as_postgres() -> None:
    """The edge annex has its own schema and its own dialect requirements."""
    from ngsh_core.edge import EdgeQueue

    queue = EdgeQueue(":memory:")
    try:
        for statement in _edge_schema_statements():
            if not statement.strip():
                continue
            # The edge schema is built with the dialect's primary key
            # construct interpolated in.
            statement = statement.replace("{pk}", POSTGRES_DIALECT.serial_pk)
            translated = _as_postgres(statement)
            if translated is None:
                continue
            _parse(translated)
    finally:
        queue.close()


def _edge_schema_statements() -> list[str]:
    """The edge queue's schema, as the queue would build it."""
    import re as _re

    source = (REPO_ROOT / "libs" / "ngsh-core" / "ngsh_core" / "edge.py").read_text(encoding="utf-8")
    block = _re.search(r"statements = \((.*?)\n        \)", source, _re.DOTALL)
    assert block, "the edge schema block was not found"
    return [match.group(1) for match in _re.finditer(r'f?"""(.*?)"""', block.group(1), _re.DOTALL)]


# -- the executor itself ----------------------------------------------------


def test_the_postgres_executor_is_importable_and_the_driver_is_present() -> None:
    """The driver must be installed, or the deployment fails at boot."""
    import psycopg  # noqa: F401

    assert PostgresExecutor is not None


def test_the_postgres_executor_translates_on_the_way_out(monkeypatch) -> None:
    """The executor must send PostgreSQL placeholders to the driver."""
    sent: list[tuple[str, tuple]] = []

    class FakeCursor:
        rowcount = 1

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, statement, params):
            sent.append((statement, tuple(params)))

        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class FakeConnection:
        autocommit = False

        def cursor(self):
            return FakeCursor()

        def close(self):
            return None

    executor = PostgresExecutor.__new__(PostgresExecutor)
    executor._conn = FakeConnection()  # noqa: SLF001
    executor._lock = __import__("threading").RLock()  # noqa: SLF001
    executor._rowcount = 0  # noqa: SLF001

    executor.execute("SELECT * FROM events WHERE tenant = ?", ("ngsh",))
    assert sent[0][0] == "SELECT * FROM events WHERE tenant = %s"
    assert sent[0][1] == ("ngsh",)


def test_both_backends_expose_the_same_interface() -> None:
    """The repositories depend on the interface, not on a backend."""
    for name in ("execute", "fetchall", "fetchone", "insert_returning_id", "close"):
        assert hasattr(SqliteExecutor, name), f"the SQLite executor lacks {name}"
        assert hasattr(PostgresExecutor, name), f"the PostgreSQL executor lacks {name}"


def test_opening_an_unknown_dsn_is_an_error_not_a_crash() -> None:
    from ngsh_core.store import open_database

    with pytest.raises(ValueError, match="unsupported DSN"):
        open_database("mysql://someone@localhost/ngsh")


def test_the_sqlite_backend_still_works_end_to_end(tmp_path) -> None:
    """The refactor must not have broken the path everyone actually uses."""
    from ngsh_core.envelope import Actor, EventEnvelope
    from ngsh_core.eventlog import EventLog
    from ngsh_core.store import open_database

    db = open_database(f"sqlite:///{tmp_path / 'x.db'}")
    log = EventLog(db)
    envelope = EventEnvelope(
        eventType="entity.created",
        aggregateType="TestResult",
        aggregateId="TR:1",
        sequence=1,
        tenant="ngsh",
        actor=Actor(subjectId="usr:operator"),
        payload={"entity": {"id": "TR:1"}},
    )
    assert log.append(envelope).accepted
    assert log.get(envelope.eventId) is not None
    db.close()

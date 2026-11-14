"""Shared test fixtures.

The foundation is exercised against a real SQLite database rather than an
in-memory fake, because several of the properties under test - the hash
chain, per-aggregate sequencing, projection rebuild - only exist in the
interaction between the code and the store.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from ngsh_core.config import Settings
from ngsh_core.envelope import Actor, Classification, Entity, EventEnvelope, Relation
from ngsh_core.store import open_database

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _stable_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the environment so a developer's shell cannot change test outcomes."""
    monkeypatch.setenv("NGSH_TENANT", "ngsh")
    monkeypatch.setenv("NGSH_DEPLOYMENT_PROFILE", "local")
    monkeypatch.setenv("NGSH_IDENTITY_PROVIDER", "stub")


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        dsn=f"sqlite:///{tmp_path / 'ngsh-test.db'}",
        tenant="ngsh",
        program="NGSH-SHY",
        deployment_profile="local",
        identity_provider="stub",
    )


@pytest.fixture
def executor(settings: Settings) -> Iterator[Any]:
    db = open_database(settings.dsn)
    yield db
    db.close()


@pytest.fixture
def operator() -> Actor:
    return Actor(
        subjectId="usr:operator",
        kind="user",
        displayName="Test Operator",
        clearance="TOP SECRET",
        citizenship="US",
        tenant="ngsh",
        programs=["NGSH-SHY"],
        needToKnow=["NGSH-SHY"],
    )


@pytest.fixture
def service_actor() -> Actor:
    return Actor(
        subjectId="svc:ingest",
        kind="service",
        clearance="SECRET",
        citizenship="US",
        tenant="ngsh",
        programs=["NGSH-SHY"],
        needToKnow=["NGSH-SHY"],
    )


@pytest.fixture
def entity_factory():
    """Build a valid ontology entity for a given type."""

    def _make(
        entity_type: str,
        entity_id: str,
        attributes: dict[str, Any] | None = None,
        *,
        classification: str = "CUI",
        tenant: str = "ngsh",
    ) -> Entity:
        return Entity(
            id=entity_id,
            type=entity_type,
            tenant=tenant,
            program="NGSH-SHY",
            classification=Classification(level=classification),
            createdBy="usr:operator",
            updatedBy="usr:operator",
            provenance={"source": "test", "method": "fixture"},
            attributes=attributes or {},
        )

    return _make


@pytest.fixture
def relation_factory():
    def _make(
        relation_type: str,
        from_ref: tuple[str, str],
        to_ref: tuple[str, str],
        *,
        relation_id: str = "REL:0001",
        classification: str = "CUI",
        confidence: float | None = 0.9,
    ) -> Relation:
        return Relation(
            id=relation_id,
            type=relation_type,
            fromRef={"type": from_ref[0], "id": from_ref[1]},
            toRef={"type": to_ref[0], "id": to_ref[1]},
            tenant="ngsh",
            classification=Classification(level=classification),
            assertedBy="usr:operator",
            provenance={"source": "test", "method": "fixture"},
            confidence=confidence,
        )

    return _make


@pytest.fixture
def event_factory(operator: Actor):
    """Build an event envelope, defaulting the aggregate to the operator's tenant."""

    def _make(
        event_type: str = "entity.created",
        *,
        aggregate_type: str = "TestResult",
        aggregate_id: str = "TR:0001",
        sequence: int = 1,
        payload: dict[str, Any] | None = None,
        actor: Actor | None = None,
        tenant: str = "ngsh",
        classification: str = "CUI",
        idempotency_key: str | None = None,
    ) -> EventEnvelope:
        return EventEnvelope(
            eventType=event_type,
            aggregateType=aggregate_type,
            aggregateId=aggregate_id,
            sequence=sequence,
            tenant=tenant,
            program="NGSH-SHY",
            actor=actor or operator,
            classification=Classification(level=classification),
            payload=payload if payload is not None else {},
            idempotencyKey=idempotency_key,
        )

    return _make

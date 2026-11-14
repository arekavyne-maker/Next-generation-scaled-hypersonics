"""Event envelope models.

These mirror ``contracts/events/event-envelope.schema.json`` exactly. The
contract file is the source of truth; this module is the Python binding of it
and is validated against the contract in CI (``tests/integration/test_contracts.py``)
so the two can never drift silently.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .classification import ClassificationLevel, parse_level
from .ids import new_ulid


def utcnow() -> datetime:
    return datetime.now(UTC)


class Actor(BaseModel):
    """Who or what performed an action."""

    model_config = ConfigDict(extra="forbid")

    subjectId: str
    kind: str = "service"
    displayName: str | None = None
    clearance: str | None = None
    citizenship: str | None = None
    tenant: str | None = None
    programs: list[str] = Field(default_factory=list)
    needToKnow: list[str] = Field(default_factory=list)
    org: str | None = None

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        allowed = {"user", "service", "device", "edge-agent", "anonymous"}
        if value not in allowed:
            raise ValueError(f"actor.kind must be one of {sorted(allowed)}")
        return value


class Classification(BaseModel):
    """Handling caveats carried by every record."""

    model_config = ConfigDict(extra="forbid")

    level: str = "UNCLASSIFIED"
    caveats: list[str] = Field(default_factory=list)
    origins: list[str] = Field(default_factory=list)
    derivedFromClassified: bool = False

    @field_validator("level")
    @classmethod
    def _known_level(cls, value: str) -> str:
        parse_level(value)  # raises nothing; normalises unknown to RESTRICTED
        return value.strip().upper()

    @property
    def rank(self) -> ClassificationLevel:
        return parse_level(self.level)

    @property
    def partition(self) -> str:
        from .classification import partition_key

        return partition_key(self.level)


class Attachment(BaseModel):
    """Pointer to a large artifact in the object store."""

    model_config = ConfigDict(extra="forbid")

    uri: str
    sha256: str
    sizeBytes: int | None = None
    mediaType: str | None = None
    classification: Classification | None = None
    encrypted: bool = True
    retentionUntil: datetime | None = None


class EventEnvelope(BaseModel):
    """Envelope written to the NGSH event log."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    eventId: str = Field(default_factory=new_ulid)
    eventType: str
    eventVersion: int = 1
    aggregateType: str
    aggregateId: str
    sequence: int = Field(ge=1)
    causationId: str | None = None
    correlationId: str | None = None
    transactionId: str | None = None
    occurredAt: datetime = Field(default_factory=utcnow)
    recordedAt: datetime = Field(default_factory=utcnow)
    tenant: str
    program: str | None = None
    actor: Actor
    classification: Classification = Field(default_factory=Classification)
    payload: dict[str, Any] = Field(default_factory=dict)
    attachments: list[Attachment] = Field(default_factory=list)
    idempotencyKey: str | None = None
    schemaRef: str | None = None
    edge: dict[str, Any] | None = None

    @field_validator("eventType")
    @classmethod
    def _event_type_shape(cls, value: str) -> str:
        parts = value.split(".")
        if len(parts) < 2 or not all(part and part[0].isalpha() for part in parts):
            raise ValueError("eventType must be dot-delimited, e.g. 'test.result.recorded'")
        return value

    @field_validator("occurredAt", "recordedAt")
    @classmethod
    def _tz_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def to_logical_json(self) -> dict[str, Any]:
        """JSON-safe representation with datetimes as RFC 3339 strings."""
        return self.model_dump(mode="json")


class Entity(BaseModel):
    """An entity in the shared ontology.

    The header is the common part; ``attributes`` holds the type-specific body
    and is validated against the type's JSON Schema by the ontology service.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    type: str
    tenant: str
    program: str | None = None
    version: int = Field(default=1, ge=1)
    classification: Classification = Field(default_factory=Classification)
    createdAt: datetime = Field(default_factory=utcnow)
    updatedAt: datetime = Field(default_factory=utcnow)
    createdBy: str | None = None
    updatedBy: str | None = None
    provenance: dict[str, Any] | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    deleted: bool = False
    attributes: dict[str, Any] = Field(default_factory=dict)


class Relation(BaseModel):
    """An edge in the digital thread."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    type: str
    fromRef: dict[str, str] = Field(alias="from")
    toRef: dict[str, str] = Field(alias="to")
    tenant: str | None = None
    program: str | None = None
    classification: Classification = Field(default_factory=Classification)
    assertedAt: datetime = Field(default_factory=utcnow)
    assertedBy: str | None = None
    provenance: dict[str, Any] | None = None
    retractedAt: datetime | None = None
    retractedBy: str | None = None
    retractionReason: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    weight: float | None = None
    confidence: float | None = None


class EventBatch(BaseModel):
    """A batch of envelopes accepted in one transaction."""

    model_config = ConfigDict(extra="forbid")

    events: list[EventEnvelope] = Field(default_factory=list)


class Rejection(BaseModel):
    eventId: str
    reason: str
    detail: str | None = None

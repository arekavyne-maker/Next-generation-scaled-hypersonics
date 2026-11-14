"""Error types raised by the NGSH foundation.

Error classes carry an HTTP status and a stable machine-readable code so that
services can translate domain failures into API responses without leaking
implementation detail, and so that clients can branch on ``code`` rather than
on message text.
"""

from __future__ import annotations

from typing import Any


class NGSHError(Exception):
    """Base class for all NGSH domain errors."""

    status_code = 500
    code = "ngsh_internal_error"

    def __init__(self, message: str, **context: Any) -> None:
        super().__init__(message)
        self.message = message
        self.context = context

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "context": self.context,
            }
        }


class ValidationError(NGSHError):
    """A payload violated the ontology, an event contract, or a constraint."""

    status_code = 422
    code = "validation_error"


class NotFoundError(NGSHError):
    """A requested entity, event or ledger entry does not exist."""

    status_code = 404
    code = "not_found"


class ConflictError(NGSHError):
    """A write conflicted with the current state, e.g. a stale aggregate version."""

    status_code = 409
    code = "conflict"


class ConcurrencyError(ConflictError):
    """An append used an aggregate sequence that was not the expected next one."""

    code = "concurrency_conflict"


class AuthorizationError(NGSHError):
    """A policy decision denied the requested action."""

    status_code = 403
    code = "authorization_denied"


class AuthenticationError(NGSHError):
    """The caller could not be identified."""

    status_code = 401
    code = "authentication_required"


class LedgerIntegrityError(NGSHError):
    """The audit ledger hash chain did not verify."""

    status_code = 500
    code = "ledger_integrity_failure"


class OntologyError(NGSHError):
    """The ontology registry or a contract file could not be loaded."""

    status_code = 500
    code = "ontology_unavailable"

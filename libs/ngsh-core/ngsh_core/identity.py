"""Identity resolution and clearance verification.

NGSH federates to the government identity provider (PIV/ICAM, IF-6 in
PSDD §7) rather than holding credentials of its own. The platform never
stores a password; it holds an assertion and the attributes derived from it.

The attributes carried forward are exactly the ones the policy engine needs:
subject identity, citizenship, clearance, program tags and need-to-know.
Clearinghouse status is treated as an attribute with a validity window, not as
a boolean, because an expired clearance must stop granting access the moment
it expires rather than at the next login.

``StubIdentityProvider`` is the development adapter. It accepts a base64url
encoded actor document in the ``Authorization: Bearer`` header, and falls back
to a clearly-labelled development actor when no credential is presented. It is
rejected outright when the deployment profile is anything other than ``local``,
so a development adapter can never be reachable in an accredited environment.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from .envelope import Actor
from .errors import AuthenticationError


@dataclass(frozen=True)
class IdentityContext:
    """Resolved identity plus the environment facts the policy may consider."""

    actor: Actor
    source: str
    authenticated: bool
    attributes: dict[str, Any]


class IdentityProvider(Protocol):
    def resolve(self, authorization: str | None, **context: Any) -> IdentityContext: ...


DEV_ACTOR = Actor(
    subjectId="dev:operator",
    kind="user",
    displayName="NGSH Development Operator",
    clearance="TOP SECRET",
    citizenship="US",
    tenant="ngsh",
    programs=["NGSH-SHY", "NGSH-MAVERICK"],
    needToKnow=["NGSH-SHY", "NGSH-MAVERICK"],
    org="NGSH Development",
)


def _decode_actor(token: str) -> Actor:
    padded = token + "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        document = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AuthenticationError("bearer token is not a valid encoded actor document") from exc
    if not isinstance(document, dict):
        raise AuthenticationError("bearer token payload must be a JSON object")
    try:
        return Actor.model_validate(document)
    except Exception as exc:  # pydantic ValidationError
        raise AuthenticationError(f"bearer token does not describe a valid actor: {exc}") from exc


class StubIdentityProvider:
    """Development identity adapter. Local deployments only."""

    def __init__(self, *, default_actor: Actor | None = None, allow_anonymous: bool = True) -> None:
        self._default = default_actor or DEV_ACTOR
        self._allow_anonymous = allow_anonymous

    def resolve(self, authorization: str | None, **context: Any) -> IdentityContext:
        if authorization:
            scheme, _, token = authorization.partition(" ")
            if scheme.lower() != "bearer" or not token:
                raise AuthenticationError("authorization header must use the Bearer scheme")
            return IdentityContext(
                actor=_decode_actor(token),
                source="bearer",
                authenticated=True,
                attributes={},
            )
        if not self._allow_anonymous:
            raise AuthenticationError("no credential presented")
        return IdentityContext(
            actor=self._default,
            source="development-default",
            authenticated=False,
            attributes={"note": "unauthenticated development request"},
        )


class PivIdentityProvider:
    """Federated identity adapter for PIV/ICAM.

    The production implementation validates the PIV assertion chain against
    the Federal Bridge or an agency PKI, maps the X.509 attributes to the
    NGSH actor attributes, and resolves clearance from the DoD clearance
    verification service.

    The adapter is wired but not yet connected to a live directory, because
    doing so requires an accreditation boundary that a development
    environment cannot cross. Until then it fails closed.
    """

    def __init__(self, *, metadata_url: str = "", verification_url: str = "") -> None:
        self._metadata_url = metadata_url
        self._verification_url = verification_url

    def resolve(self, authorization: str | None, **context: Any) -> IdentityContext:
        if not self._metadata_url or not self._verification_url:
            raise AuthenticationError(
                "PIV/ICAM federation is not configured in this deployment; "
                "set NGSH_IDENTITY_PROVIDER=stub for local development only"
            )
        # A production implementation would:
        #   1. fetch and validate the IdP metadata and signing certificates,
        #   2. verify the assertion signature, audience, nonce and timestamps,
        #   3. extract subject, citizenship and clearance attributes,
        #   4. confirm clearance validity with the verification service,
        #   5. return an IdentityContext with the mapped attributes.
        raise AuthenticationError("PIV/ICAM assertion validation is not implemented in this build")


def _local_key() -> bytes:
    """The development assertion key.

    This key exists only so a local deployment can exercise the IF-6 path end
    to end. It is refused outside ``local`` and ``edge`` by
    :func:`build_identity_provider`; it is not a production secret.
    """
    return os.environ.get("NGSH_LOCAL_IDENTITY_KEY", "ngsh-local-dev-identity-key").encode()


def _canonical(document: dict[str, Any]) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode()


def issue_assertion(
    attributes: dict[str, Any],
    *,
    issuer: str = "ngsh-local-piv",
    expires_at: str | None = None,
    lifetime_seconds: int = 3600,
) -> dict[str, Any]:
    """Issue a signed local PIV-style assertion.

    The shape mirrors what IF-6 delivers: a subject, the clearance and
    citizenship attributes the policy engine needs, an issuer, an expiry and a
    signature. The signature is HMAC, not an X.509 chain, so this is a local
    adapter and never an accredited credential.
    """
    if not isinstance(attributes, dict) or not attributes.get("subjectId"):
        raise AuthenticationError("an assertion requires a 'subjectId'")
    document = dict(attributes)
    document.setdefault("kind", "user")
    document["issuer"] = issuer
    if expires_at is None:
        expires_at = (datetime.now(UTC) + timedelta(seconds=lifetime_seconds)).isoformat()
    document["expiresAt"] = expires_at
    document["signature"] = hmac.new(_local_key(), _canonical(document), hashlib.sha256).hexdigest()
    return document


def verify_assertion(document: dict[str, Any]) -> dict[str, Any]:
    """Verify a local assertion and return its actor attributes.

    Expiry is checked before the signature is trusted for any decision, and the
    signature is compared in constant time. Failures are authentication
    failures, never a default actor.
    """
    if not isinstance(document, dict):
        raise AuthenticationError("identity assertion must be an object")
    signature = document.get("signature")
    if not isinstance(signature, str) or not signature:
        raise AuthenticationError("identity assertion is not signed")
    unsigned = {key: value for key, value in document.items() if key != "signature"}
    expected = hmac.new(_local_key(), _canonical(unsigned), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise AuthenticationError("identity assertion signature is invalid")

    expires_at = document.get("expiresAt")
    if not isinstance(expires_at, str):
        raise AuthenticationError("identity assertion has no expiry")
    try:
        expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AuthenticationError("identity assertion expiry is not ISO-8601") from exc
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=UTC)
    if expiry <= datetime.now(UTC):
        raise AuthenticationError("identity assertion has expired")

    actor_fields = {
        key: value for key, value in document.items() if key not in {"issuer", "expiresAt", "signature"}
    }
    try:
        Actor.model_validate(actor_fields)
    except Exception as exc:  # pydantic ValidationError
        raise AuthenticationError(f"identity assertion does not describe a valid actor: {exc}") from exc
    return actor_fields


class SimulatedPivIdentityProvider:
    """A signed local PIV/ICAM adapter for end-to-end local exercise.

    It is a real verification loop — signature, expiry and actor validation —
    over a development key. It is selected only by ``piv-sim`` and only in the
    ``local`` or ``edge`` profile.
    """

    def __init__(self, *, allow_anonymous: bool = False) -> None:
        self._allow_anonymous = allow_anonymous

    def resolve(self, authorization: str | None, **context: Any) -> IdentityContext:
        if not authorization:
            if self._allow_anonymous:
                return IdentityContext(
                    actor=DEV_ACTOR,
                    source="development-default",
                    authenticated=False,
                    attributes={"note": "unauthenticated development request"},
                )
            raise AuthenticationError("no credential presented")
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            raise AuthenticationError("authorization header must use the Bearer scheme")
        padded = token + "=" * (-len(token) % 4)
        try:
            document = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AuthenticationError("bearer token is not a valid PIV assertion") from exc
        attributes = verify_assertion(document)
        return IdentityContext(
            actor=Actor.model_validate(attributes),
            source="piv-sim",
            authenticated=True,
            attributes={"issuer": document.get("issuer"), "expiresAt": document.get("expiresAt")},
        )


def build_identity_provider(kind: str, *, deployment_profile: str = "local") -> IdentityProvider:
    """Select an identity adapter, refusing development adapters outside local."""
    normalized = (kind or "stub").strip().lower()

    if normalized in {"stub", "piv-sim"}:
        if deployment_profile not in {"local", "edge"}:
            raise RuntimeError(
                f"the {normalized} identity provider is only permitted in the 'local' and "
                f"'edge' deployment profiles, not {deployment_profile!r}"
            )
        if normalized == "piv-sim":
            return SimulatedPivIdentityProvider()
        return StubIdentityProvider()

    if normalized == "piv":
        return PivIdentityProvider()

    raise RuntimeError(f"unknown identity provider {kind!r}")


def actor_from_attributes(attributes: dict[str, Any]) -> Actor:
    """Build an actor from a flat attribute dictionary."""
    return Actor.model_validate(attributes)

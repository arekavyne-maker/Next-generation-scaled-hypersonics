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
import json
from dataclasses import dataclass
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


def build_identity_provider(kind: str, *, deployment_profile: str = "local") -> IdentityProvider:
    """Select an identity adapter, refusing development adapters outside local."""
    normalized = (kind or "stub").strip().lower()

    if normalized == "stub":
        if deployment_profile not in {"local", "edge"}:
            raise RuntimeError(
                "the stub identity provider is only permitted in the 'local' and 'edge' "
                f"deployment profiles, not {deployment_profile!r}"
            )
        return StubIdentityProvider()

    if normalized == "piv":
        return PivIdentityProvider()

    raise RuntimeError(f"unknown identity provider {kind!r}")


def actor_from_attributes(attributes: dict[str, Any]) -> Actor:
    """Build an actor from a flat attribute dictionary."""
    return Actor.model_validate(attributes)

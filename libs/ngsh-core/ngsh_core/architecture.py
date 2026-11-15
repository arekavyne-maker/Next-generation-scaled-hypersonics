"""Pillar A domain logic: configuration baselines, interfaces and traceability.

This module holds the parts of Pillar A that have to be *provable* rather than
merely implemented:

* a configuration baseline is content-addressed, so the same inputs produce
  the same baseline identifier on any machine, in any language, at any time;
* interface characteristics are checked as a set, because an interface that
  declares a rate but not a timing model is not an interface;
* requirement verification status is a pure function of the evidence
  attached to it, so the same evidence produces the same status regardless of
  the order in which the evidence arrived.

The functions here are deliberately free of storage and HTTP concerns. The
architecture service binds them to the store and the transport; the thread
projection reuses the traceability rules so that two services cannot disagree
about whether a requirement is verified.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from .errors import ValidationError
from .ontology import OntologyRegistry

#: Version of the baseline identifier derivation. Changing how a baseline id
#: is computed is a contract-breaking change, so it is versioned explicitly
#: and travels with every baseline record.
BASELINE_ID_VERSION = "1"

#: The four characteristics WP-1.1 requires on an interface. Each one answers
#: a different question and none substitutes for another: rate and latency are
#: budgets, timing is the synchronisation model, and envelope is the operating
#: range within which the budgets hold.
REQUIRED_INTERFACE_CHARACTERISTICS = ("rate", "latency", "timing", "envelope")

TIMING_MODELS = {"SYNCHRONOUS", "ASYNCHRONOUS", "PERIODIC", "EVENT"}

#: Entity types whose baseline membership is meaningless without a revision.
REVISIONED_TYPES = {"Part", "Variant", "Interface", "Material", "ProcessPlan"}

#: The ontology's verification status vocabulary. Pillar A does not invent a
#: parallel one; an assessor should see the same words in the API and in the
#: registry.
VERIFICATION_STATUSES = ("NOT_STARTED", "IN_PROGRESS", "PARTIAL", "COMPLETE", "NOT_APPLICABLE")

#: Test outcomes that count as satisfying evidence. ``PASS`` alone is not
#: enough: the result must also have been reviewed by a named human, which is
#: what ``reviewedBy`` records (see docs/architecture/02-ontology-model.md).
SATISFYING_OUTCOME = "PASS"

#: Outcomes that do not satisfy a requirement and therefore raise a review
#: item rather than silently passing.
REVIEW_OUTCOMES = {"MARGINAL": "marginal_outcome", "INCONCLUSIVE": "inconclusive_outcome"}

INTERFACE_CHARACTERISTIC_ERRORS = {
    "rate": "must be a positive number",
    "latency": "must be a number greater than or equal to zero",
    "timing": f"must be one of {sorted(TIMING_MODELS)}",
    "envelope": "must be a non-empty object naming the operating range",
}


# ---------------------------------------------------------------------------
# Configuration baselines
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BaselineMember:
    """One pinned element of a configuration baseline."""

    entityType: str
    entityId: str
    revision: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"entityType": self.entityType, "entityId": self.entityId, "revision": self.revision}

    def sort_key(self) -> tuple[str, str]:
        return (self.entityType, self.entityId)


@dataclass(frozen=True)
class Baseline:
    """A content-addressed configuration baseline."""

    id: str
    digest: str
    systemId: str
    name: str
    members: tuple[BaselineMember, ...]
    softwareBuilds: tuple[str, ...]
    createdBy: str
    createdAt: str
    idVersion: str = BASELINE_ID_VERSION
    notes: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "digest": self.digest,
            "idVersion": self.idVersion,
            "systemId": self.systemId,
            "name": self.name,
            "members": [member.to_dict() for member in self.members],
            "memberCount": len(self.members),
            "softwareBuilds": list(self.softwareBuilds),
            "createdBy": self.createdBy,
            "createdAt": self.createdAt,
            "notes": self.notes,
        }


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def normalise_members(
    raw_members: Any,
    *,
    registry: OntologyRegistry | None = None,
) -> tuple[BaselineMember, ...]:
    """Validate members and return them in canonical order.

    Two members for the same entity are rejected rather than merged: a
    baseline that pinning two revisions of one part is ambiguous, and an
    ambiguous baseline is worse than no baseline.
    """
    if not isinstance(raw_members, list) or not raw_members:
        raise ValidationError("a baseline must pin at least one member")

    members: dict[tuple[str, str], BaselineMember] = {}
    for index, raw in enumerate(raw_members):
        if not isinstance(raw, dict):
            raise ValidationError(f"member at index {index} must be an object")
        entity_type = raw.get("entityType")
        entity_id = raw.get("entityId")
        revision = raw.get("revision")

        if not isinstance(entity_type, str) or not entity_type:
            raise ValidationError(f"member at index {index} is missing 'entityType'")
        if not isinstance(entity_id, str) or not entity_id:
            raise ValidationError(f"member at index {index} is missing 'entityId'")

        spec = registry.entity_type(entity_type) if registry is not None else None
        if registry is not None and spec is None:
            raise ValidationError(f"member at index {index} names unknown entity type {entity_type!r}")
        if spec is not None and not entity_id.startswith(f"{spec.idPrefix}:"):
            raise ValidationError(
                f"member at index {index} has id {entity_id!r} which does not carry the "
                f"{spec.idPrefix}: prefix required for {entity_type}"
            )
        if entity_type in REVISIONED_TYPES and not isinstance(revision, str):
            raise ValidationError(
                f"member at index {index} ({entity_id}) must pin a 'revision' for entity type {entity_type}"
            )
        if revision is not None and not isinstance(revision, str):
            raise ValidationError(f"member at index {index} has a non-string 'revision'")

        key = (entity_type, entity_id)
        if key in members:
            raise ValidationError(f"duplicate baseline member {entity_type}:{entity_id}")
        members[key] = BaselineMember(entityType=entity_type, entityId=entity_id, revision=revision)

    return tuple(sorted(members.values(), key=BaselineMember.sort_key))


def baseline_digest(system_id: str, members: tuple[BaselineMember, ...]) -> str:
    """The canonical digest of a baseline's pinned content.

    The digest covers the system and the pinned members only. A baseline's
    *name* is a label, not content: renaming a baseline must not change the
    configuration it identifies.
    """
    payload = {
        "idVersion": BASELINE_ID_VERSION,
        "systemId": system_id,
        "members": [member.to_dict() for member in members],
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def baseline_id(digest: str) -> str:
    """The identifier derived from a digest.

    26 hex characters is 104 bits, comfortably beyond collision risk for the
    number of baselines a programme can create, and short enough to read out
    in a review.
    """
    return f"BL:{digest[:26].upper()}"


def create_baseline(
    *,
    system_id: Any,
    name: Any,
    raw_members: Any,
    software_builds: Any = None,
    created_by: str,
    created_at: str,
    notes: str | None = None,
    registry: OntologyRegistry | None = None,
) -> Baseline:
    """Validate the inputs and build the baseline record.

    Determinism is the point: no clock, no random salt and no database
    sequence enters the identifier, so replaying the same request always
    yields the same id.
    """
    if not isinstance(system_id, str) or not system_id.startswith("SYS:"):
        raise ValidationError("'systemId' must be a System id of the form 'SYS:...'")
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("'name' is required")

    members = normalise_members(raw_members, registry=registry)

    builds: list[str] = []
    if software_builds is not None:
        if not isinstance(software_builds, list) or not all(
            isinstance(build, str) and build for build in software_builds
        ):
            raise ValidationError("'softwareBuilds' must be a list of non-empty strings")
        builds = sorted(set(software_builds))

    digest = baseline_digest(system_id, members)
    return Baseline(
        id=baseline_id(digest),
        digest=digest,
        systemId=system_id,
        name=name.strip(),
        members=members,
        softwareBuilds=tuple(builds),
        createdBy=created_by,
        createdAt=created_at,
        notes=notes,
    )


def verify_baseline(baseline: Baseline) -> dict[str, Any]:
    """Recompute a stored baseline's identity from its content."""
    digest = baseline_digest(baseline.systemId, baseline.members)
    recomputed = baseline_id(digest)
    return {
        "baselineId": baseline.id,
        "recomputedId": recomputed,
        "recomputedDigest": digest,
        "reproducible": recomputed == baseline.id and digest == baseline.digest,
    }


# ---------------------------------------------------------------------------
# Interfaces
# ---------------------------------------------------------------------------


def validate_interface(
    *,
    from_system_id: Any,
    to_system_id: Any,
    characteristics: Any,
) -> dict[str, Any]:
    """Validate an interface's endpoints and characteristics.

    Returns the normalised characteristics. The interface itself is an
    ontology entity (``Interface``) and is written through the normal entity
    path; this function is the gate that decides whether its characteristics
    are complete enough to be registered at all.
    """
    if not isinstance(from_system_id, str) or not from_system_id.startswith("SYS:"):
        raise ValidationError("'fromSystemId' must be a System id of the form 'SYS:...'")
    if not isinstance(to_system_id, str) or not to_system_id.startswith("SYS:"):
        raise ValidationError("'toSystemId' must be a System id of the form 'SYS:...'")
    if from_system_id == to_system_id:
        raise ValidationError("an interface must connect two distinct systems")
    if not isinstance(characteristics, dict):
        raise ValidationError("'characteristics' must be an object")

    problems: list[str] = []
    for key in REQUIRED_INTERFACE_CHARACTERISTICS:
        if key not in characteristics:
            problems.append(f"characteristics.{key} is required: {INTERFACE_CHARACTERISTIC_ERRORS[key]}")

    rate = characteristics.get("rate")
    if "rate" in characteristics and (
        not isinstance(rate, int | float) or isinstance(rate, bool) or rate <= 0
    ):
        problems.append(f"characteristics.rate {INTERFACE_CHARACTERISTIC_ERRORS['rate']}")

    latency = characteristics.get("latency")
    if "latency" in characteristics and (
        not isinstance(latency, int | float) or isinstance(latency, bool) or latency < 0
    ):
        problems.append(f"characteristics.latency {INTERFACE_CHARACTERISTIC_ERRORS['latency']}")

    timing = characteristics.get("timing")
    if "timing" in characteristics and (not isinstance(timing, str) or timing.upper() not in TIMING_MODELS):
        problems.append(f"characteristics.timing {INTERFACE_CHARACTERISTIC_ERRORS['timing']}")

    envelope = characteristics.get("envelope")
    if "envelope" in characteristics and (not isinstance(envelope, dict) or not envelope):
        problems.append(f"characteristics.envelope {INTERFACE_CHARACTERISTIC_ERRORS['envelope']}")

    if problems:
        raise ValidationError("interface characteristics are incomplete", detail=problems)

    normalised = dict(characteristics)
    normalised["timing"] = str(timing).upper()
    return normalised


def interface_digest(
    *,
    from_system_id: str,
    to_system_id: str,
    characteristics: dict[str, Any],
) -> str:
    """A content digest for an interface definition.

    Two interface revisions that differ in any characteristic produce
    different digests, which is what lets a baseline pin an ICD revision
    rather than an ICD label.
    """
    payload = {
        "fromSystemId": from_system_id,
        "toSystemId": to_system_id,
        "characteristics": characteristics,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Requirement traceability
# ---------------------------------------------------------------------------


@dataclass
class EvidenceAssessment:
    """The outcome of reading one requirement's verification evidence."""

    status: str
    verified: bool
    coverage: float
    satisfying: list[dict[str, Any]] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)
    reviewItems: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verificationStatus": self.status,
            "verified": self.verified,
            "coverage": self.coverage,
            "satisfyingResults": self.satisfying,
            "failedResults": self.failed,
            "reviewItems": self.reviewItems,
            "reviewRequired": bool(self.reviewItems),
            "gaps": self.gaps,
        }


def _result_summary(result: dict[str, Any]) -> dict[str, Any]:
    attributes = result.get("attributes") or {}
    return {
        "id": result.get("id"),
        "outcome": attributes.get("outcome"),
        "testMethod": attributes.get("testMethod"),
        "reviewedBy": attributes.get("reviewedBy"),
    }


def assess_evidence(results: list[dict[str, Any]]) -> EvidenceAssessment:
    """Compute verification status from test results.

    The rule, in order:

    * no evidence means ``NOT_STARTED`` and a gap item - a requirement with
      nothing behind it must be visible, not counted as in progress;
    * a ``PASS`` without ``reviewedBy`` is *not* satisfying evidence, because
      an unreviewed pass is a claim rather than a verification;
    * ``MARGINAL`` and ``INCONCLUSIVE`` raise review items and never satisfy;
    * the requirement is ``COMPLETE`` only when there is at least one
      satisfying result and nothing outstanding at all. A failure or a review
      item leaves it ``PARTIAL``.
    """
    satisfying: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    unknown: list[str] = []
    gaps: list[str] = []

    for result in results:
        summary = _result_summary(result)
        outcome = summary["outcome"]
        if outcome == SATISFYING_OUTCOME:
            if summary["reviewedBy"]:
                satisfying.append(summary)
            else:
                review.append({**summary, "reason": "unreviewed_pass"})
        elif outcome == "FAIL":
            failed.append(summary)
        elif outcome in REVIEW_OUTCOMES:
            review.append({**summary, "reason": REVIEW_OUTCOMES[outcome]})
        elif outcome == "NOT_RUN":
            review.append({**summary, "reason": "not_run"})
        else:
            unknown.append(str(summary["id"]))
            review.append({**summary, "reason": "unknown_outcome"})

    if unknown:
        gaps.append(
            "verification evidence carries an outcome outside the contract: " + ", ".join(sorted(unknown))
        )
    if not results:
        gaps.append("no verification evidence has been recorded against this requirement")
    if failed:
        gaps.append(f"{len(failed)} verification result(s) failed")

    if not results:
        status = "NOT_STARTED"
    elif satisfying and not failed and not review:
        status = "COMPLETE"
    elif satisfying or review:
        status = "PARTIAL"
    else:
        status = "IN_PROGRESS"

    return EvidenceAssessment(
        status=status,
        verified=status == "COMPLETE",
        coverage=round(len(satisfying) / len(results), 4) if results else 0.0,
        satisfying=satisfying,
        failed=failed,
        reviewItems=review,
        gaps=gaps,
    )


def requirement_coverage(
    requirement: dict[str, Any] | None,
    results: list[dict[str, Any]],
    *,
    allocated_to: list[dict[str, Any]] | None = None,
    dangling: list[str] | None = None,
    requirement_id: str | None = None,
) -> dict[str, Any]:
    """The full coverage report for one requirement.

    ``allocated_to`` and ``dangling`` come from the caller because they are
    graph facts, not evidence facts: the projection owns the edges, this
    module owns the rule that turns evidence into a status.
    """
    assessment = assess_evidence(results)
    allocated = allocated_to or []
    gaps = list(assessment.gaps)

    if dangling:
        gaps.append(
            "verification evidence references test results that are not in the thread: "
            + ", ".join(sorted(dangling))
        )
    if not allocated:
        gaps.append("no design element has been allocated to this requirement")

    return {
        "requirement": requirement or {"id": requirement_id, "type": "Requirement"},
        "verifyingResults": [_result_summary(result) for result in results],
        "allocatedTo": allocated,
        **assessment.to_dict(),
        "gaps": gaps,
    }


def aggregate_status(own_status: str, child_statuses: list[str]) -> str:
    """Roll a parent requirement's status up from its children.

    A parent is ``COMPLETE`` only when it and every child are complete. A
    mixture of complete and incomplete work is ``PARTIAL`` whether the mix is
    at this level or below it; a tree that has not started anywhere is
    ``NOT_STARTED`` rather than in progress by accident of existing.
    """
    statuses = [own_status, *child_statuses]
    if all(status == "COMPLETE" for status in statuses):
        return "COMPLETE"
    if all(status == "NOT_STARTED" for status in statuses):
        return "NOT_STARTED"
    if any(status in {"PARTIAL", "COMPLETE"} for status in statuses):
        return "PARTIAL"
    return "IN_PROGRESS"


def rollup_tree(
    coverage: dict[str, dict[str, Any]],
    parents: dict[str, str | None],
) -> dict[str, Any]:
    """Roll a requirement set up the ``parentId`` hierarchy.

    The traversal is post-order and deterministic (children evaluated in
    sorted id order), so the same tree always produces the same report. A
    parent that is missing from ``coverage`` is reported as an orphan rather
    than silently absorbing its children's status.
    """
    children: dict[str, list[str]] = {}
    roots: list[str] = []
    for requirement_id, parent_id in sorted(parents.items()):
        if parent_id and parent_id in parents:
            children.setdefault(parent_id, []).append(requirement_id)
        else:
            roots.append(requirement_id)

    resolved: dict[str, str] = {}
    visits: set[str] = set()
    cycles: set[str] = set()

    def resolve(requirement_id: str) -> str:
        if requirement_id in resolved:
            return resolved[requirement_id]
        if requirement_id in visits:
            cycles.add(requirement_id)
            return coverage.get(requirement_id, {}).get("verificationStatus", "NOT_STARTED")
        visits.add(requirement_id)
        own = coverage.get(requirement_id, {}).get("verificationStatus", "NOT_STARTED")
        child_statuses = [resolve(child) for child in sorted(children.get(requirement_id, []))]
        status = aggregate_status(own, child_statuses)
        resolved[requirement_id] = status
        visits.discard(requirement_id)
        return status

    for requirement_id in sorted(parents):
        resolve(requirement_id)

    counts = {status: 0 for status in VERIFICATION_STATUSES}
    review_items = 0
    for requirement_id in sorted(parents):
        report = coverage.get(requirement_id)
        if report is None:
            continue
        counts[resolved.get(requirement_id, "NOT_STARTED")] += 1
        review_items += len(report.get("reviewItems", []))

    total = sum(counts.values())
    return {
        "statuses": {requirement_id: resolved[requirement_id] for requirement_id in sorted(resolved)},
        "counts": counts,
        "total": total,
        "coverage": round(counts["COMPLETE"] / total, 4) if total else 0.0,
        "reviewItemCount": review_items,
        "orphans": sorted(requirement_id for requirement_id in parents if requirement_id not in coverage),
        "cycles": sorted(cycles),
    }

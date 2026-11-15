"""Pillar E capabilities: training, curriculum replication and sanitised extracts.

Three capabilities share one rule: a partner never receives more than the
programme intended to release.

* **E-1 digital-twin training** - a scenario is valid only when it references
  live thread entities; a completion is retrievable and maps to the skill it
  exercised;
* **E-2 replicable curriculum** - a courseware package is content-addressed,
  versioned, and carries the guard version and reviewer that cleared it;
* **E-5 industry-academia sandbox** - an extract carries a manifest naming its
  source ids, transformation rules, guard version and reviewer, and a
  RESTRICTED record is blocked before anything leaves the boundary.

The functions are pure. The workforce service supplies live entity ids, stores
the content-addressed artefacts and anchors the manifests in the audit ledger.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from .classification import ClassificationLevel, parse_level
from .errors import ValidationError

#: Version of the curriculum package and extract manifest derivations.
CURRICULUM_ID_VERSION = "1"
EXTRACT_MANIFEST_VERSION = "1"

#: Tokens that mark a reference or a scenario as demonstration material. A
#: training environment built on placeholders teaches the wrong system.
PLACEHOLDER_PATTERN = re.compile(
    r"\b(placeholder|todo|tbd|dummy|lorem|foobar|example-only|sample-only)\b",
    re.IGNORECASE,
)

#: The classification at and above which nothing may enter a partner extract.
EXTRACT_BLOCK_LEVEL = ClassificationLevel.RESTRICTED

#: The fields every extract manifest must carry (E-5 acceptance criterion 1).
EXTRACT_MANIFEST_FIELDS = (
    "sourceIds",
    "transformationRules",
    "guardVersion",
    "reviewer",
)


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _is_placeholder(value: str) -> bool:
    return bool(PLACEHOLDER_PATTERN.search(value))


# ---------------------------------------------------------------------------
# E-1: digital-twin training
# ---------------------------------------------------------------------------


def validate_training_scenario(
    scenario: dict[str, Any],
    *,
    live_references: set[tuple[str, str]],
) -> dict[str, Any]:
    """Check that a training scenario is built on the real digital thread.

    A scenario is valid when every reference resolves to a live entity and no
    reference or title carries a placeholder marker. The coverage figure is
    reported per scenario so the programme can see the share of scenarios that
    meet the 90% live-reference criterion without a separate query.
    """
    name = scenario.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("'name' is required")

    references = scenario.get("references")
    if not isinstance(references, list) or not references:
        raise ValidationError("a training scenario must reference at least one thread entity")

    resolved: list[dict[str, Any]] = []
    placeholders: list[str] = []
    unresolved: list[dict[str, Any]] = []
    live_count = 0

    for index, reference in enumerate(references):
        if not isinstance(reference, dict):
            raise ValidationError(f"reference at index {index} must be an object")
        entity_type = reference.get("type")
        entity_id = reference.get("id")
        if not isinstance(entity_type, str) or not entity_type:
            raise ValidationError(f"reference at index {index} is missing 'type'")
        if not isinstance(entity_id, str) or not entity_id:
            raise ValidationError(f"reference at index {index} is missing 'id'")

        if _is_placeholder(entity_type) or _is_placeholder(entity_id):
            placeholders.append(f"{entity_type}:{entity_id}")
            resolved.append({"type": entity_type, "id": entity_id, "live": False})
            continue

        live = (entity_type, entity_id) in live_references
        if live:
            live_count += 1
        else:
            unresolved.append({"type": entity_type, "id": entity_id})
        resolved.append({"type": entity_type, "id": entity_id, "live": live})

    placeholder_title = _is_placeholder(name)
    total = len(resolved)
    coverage = round(live_count / total, 4) if total else 0.0
    gaps: list[str] = []
    if unresolved:
        gaps.append(
            "references that do not resolve to a live entity: "
            + ", ".join(f"{item['type']}:{item['id']}" for item in unresolved)
        )
    if placeholders:
        gaps.append("placeholder references: " + ", ".join(sorted(placeholders)))
    if placeholder_title:
        gaps.append("the scenario title carries a placeholder marker")
    if not live_count:
        gaps.append("no live entity is referenced")

    return {
        "name": name.strip(),
        "references": resolved,
        "liveReferenceCount": live_count,
        "referenceCount": total,
        "referenceCoverage": coverage,
        "placeholders": sorted(placeholders),
        "unresolved": unresolved,
        "valid": not gaps,
        "meetsCoverageTarget": coverage >= 0.90,
        "gaps": gaps,
    }


def training_completion(
    *,
    person_id: str,
    scenario_id: str,
    skill_id: str,
    score: float,
    passed: bool,
    completed_at: str,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    """A completion record that resolves to the skill it exercised."""
    if not isinstance(person_id, str) or not person_id.startswith("PER:"):
        raise ValidationError("'personId' must be a Person id of the form 'PER:...'")
    if not isinstance(scenario_id, str) or not scenario_id:
        raise ValidationError("'scenarioId' is required")
    if not isinstance(skill_id, str) or not skill_id.startswith("SKL:"):
        raise ValidationError("'skillId' must be a Skill id of the form 'SKL:...'")
    if not isinstance(score, int | float) or isinstance(score, bool) or score < 0:
        raise ValidationError("'score' must be a non-negative number")
    if not isinstance(passed, bool):
        raise ValidationError("'passed' must be a boolean")
    if not isinstance(completed_at, str) or not completed_at:
        raise ValidationError("'completedAt' is required")

    digest = _digest(
        {
            "personId": person_id,
            "scenarioId": scenario_id,
            "skillId": skill_id,
            "completedAt": completed_at,
        }
    )
    return {
        "completionId": f"TRAIN:{digest[:16].upper()}",
        "personId": person_id,
        "scenarioId": scenario_id,
        "score": float(score),
        "passed": passed,
        "completedAt": completed_at,
        "evidenceRefs": sorted({str(item) for item in evidence_refs or []}),
        "skillId": skill_id,
        "mapsToSkill": skill_id,
        "credentialEligible": bool(passed),
    }


def training_coverage(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    """The share of training scenarios built on live thread entities."""
    valid = [scenario for scenario in scenarios if scenario.get("valid") is True]
    live = [scenario for scenario in scenarios if int(scenario.get("liveReferenceCount") or 0) > 0]
    placeholders = [
        scenario.get("scenarioId") or scenario.get("name")
        for scenario in scenarios
        if scenario.get("placeholders")
    ]
    total = len(scenarios)
    return {
        "scenarioCount": total,
        "validCount": len(valid),
        "liveReferenceShare": round(len(live) / total, 4) if total else 0.0,
        "placeholderScenarios": placeholders,
        "meetsLiveReferenceTarget": bool(total) and len(live) / total >= 0.90,
        "meetsZeroPlaceholderTarget": not placeholders,
    }


# ---------------------------------------------------------------------------
# E-2: curriculum packaging
# ---------------------------------------------------------------------------


def curriculum_package(
    *,
    title: str,
    version: str,
    modules: list[dict[str, Any]],
    source_records: list[dict[str, Any]],
    guard_version: str,
    reviewer: str,
    supersedes: str | None = None,
) -> dict[str, Any]:
    """Build a content-addressed courseware package manifest.

    The package is refused if any source record is RESTRICTED or above. That
    check is the automated guard E-2 acceptance criterion 5 requires: a package
    cannot contain content derived from a classified record, and the refusal
    names the offending source.
    """
    if not isinstance(title, str) or not title.strip():
        raise ValidationError("'title' is required")
    if not isinstance(version, str) or not version.strip():
        raise ValidationError("'version' is required")
    if not isinstance(modules, list) or not modules:
        raise ValidationError("a package must contain at least one module")
    if not isinstance(guard_version, str) or not guard_version.strip():
        raise ValidationError("'guardVersion' is required")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValidationError("'reviewer' is required: a package must name the human who cleared it")

    blocked = [
        str(record.get("id"))
        for record in source_records
        if parse_level(record.get("classification")) >= EXTRACT_BLOCK_LEVEL
    ]
    if blocked:
        raise ValidationError(
            "the package contains content derived from a RESTRICTED record",
            detail=sorted(blocked),
        )

    module_ids = [str(module.get("moduleId") or module.get("id")) for module in modules]
    if any(not module_id or module_id == "None" for module_id in module_ids):
        raise ValidationError("every module must carry a 'moduleId'")

    source_ids = sorted({str(record.get("id")) for record in source_records})
    manifest = {
        "idVersion": CURRICULUM_ID_VERSION,
        "title": title.strip(),
        "version": version.strip(),
        "moduleIds": module_ids,
        "moduleCount": len(module_ids),
        "sourceIds": source_ids,
        "guardVersion": guard_version.strip(),
        "reviewer": reviewer.strip(),
        "releaseClassification": "UNCLASSIFIED",
        "supersedes": supersedes,
    }
    digest = _digest(manifest)
    return {
        **manifest,
        "packageId": f"PKG:{digest[:26].upper()}",
        "contentDigest": digest,
        "contentAddressed": True,
        "update": {
            "mode": "HOT_SWAP",
            "requiresPartnerRebuild": False,
            "instruction": "deploy the new manifest under the existing package line",
        },
        "lmsConnector": {"protocol": "LTI-1.3", "manifestVersion": CURRICULUM_ID_VERSION},
    }


def verify_package(manifest: dict[str, Any]) -> dict[str, Any]:
    """Recompute a package's content address from its stored manifest."""
    body = {
        key: manifest.get(key)
        for key in (
            "idVersion",
            "title",
            "version",
            "moduleIds",
            "moduleCount",
            "sourceIds",
            "guardVersion",
            "reviewer",
            "releaseClassification",
            "supersedes",
        )
    }
    digest = _digest(body)
    return {
        "packageId": manifest.get("packageId"),
        "recomputedId": f"PKG:{digest[:26].upper()}",
        "recomputedDigest": digest,
        "reproducible": digest == manifest.get("contentDigest"),
        "contentAddressed": True,
    }


# ---------------------------------------------------------------------------
# E-5: sanitised extracts
# ---------------------------------------------------------------------------


def sanitised_extract(
    *,
    view: str,
    records: list[dict[str, Any]],
    transformations: list[str],
    guard_version: str,
    reviewer: str,
    previous_anchor: str | None = None,
) -> dict[str, Any]:
    """Build an extract manifest, or block the release.

    The blocked path returns a complete record of the attempt rather than
    raising: the caller anchors that record in the audit ledger, which is what
    makes "a seeded attempt was blocked and recorded" true rather than merely
    logged by the web server.
    """
    if not isinstance(view, str) or not view.strip():
        raise ValidationError("'view' is required")
    if not isinstance(records, list) or not records:
        raise ValidationError("an extract must name at least one source record")
    if not isinstance(transformations, list) or not all(
        isinstance(item, str) and item for item in transformations
    ):
        raise ValidationError("'transformations' must be a list of non-empty rule identifiers")
    if not isinstance(guard_version, str) or not guard_version.strip():
        raise ValidationError("'guardVersion' is required")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValidationError("'reviewer' is required: an extract must name the reviewing human")

    blocked: list[dict[str, Any]] = []
    for record in records:
        record_id = record.get("id")
        if not isinstance(record_id, str) or not record_id:
            raise ValidationError("each extract record must carry an 'id'")
        level = parse_level(record.get("classification"))
        if level >= EXTRACT_BLOCK_LEVEL:
            blocked.append(
                {
                    "id": record_id,
                    "type": record.get("type"),
                    "classification": level.label,
                }
            )

    if blocked:
        return {
            "released": False,
            "blocked": blocked,
            "blockedCount": len(blocked),
            "recorded": True,
            "view": view.strip(),
            "guardVersion": guard_version.strip(),
            "reviewer": reviewer.strip(),
            "reason": "a RESTRICTED or above record is not eligible for partner release",
            "manifest": None,
        }

    source_ids = sorted({str(record["id"]) for record in records})
    body = {
        "idVersion": EXTRACT_MANIFEST_VERSION,
        "view": view.strip(),
        "sourceIds": source_ids,
        "transformationRules": sorted({item.strip() for item in transformations}),
        "guardVersion": guard_version.strip(),
        "reviewer": reviewer.strip(),
        "releaseClassification": "UNCLASSIFIED",
    }
    digest = _digest(body)
    previous = previous_anchor or "GENESIS"
    anchor = hashlib.sha256(f"{previous}:{digest}".encode()).hexdigest()
    manifest = {
        **body,
        "manifestId": f"EXT:{digest[:26].upper()}",
        "manifestDigest": digest,
        "ledgerAnchor": anchor,
        "previousAnchor": previous_anchor,
        "recordCount": len(source_ids),
        "complete": all(body.get(field) for field in EXTRACT_MANIFEST_FIELDS),
    }
    return {
        "released": True,
        "blocked": [],
        "blockedCount": 0,
        "recorded": True,
        "view": view.strip(),
        "manifest": manifest,
    }


def verify_extract_manifest(
    manifest: dict[str, Any],
    *,
    previous_anchor: str | None = None,
) -> dict[str, Any]:
    """Recompute an extract manifest digest and its ledger anchor."""
    body = {
        "idVersion": manifest.get("idVersion"),
        "view": manifest.get("view"),
        "sourceIds": manifest.get("sourceIds"),
        "transformationRules": manifest.get("transformationRules"),
        "guardVersion": manifest.get("guardVersion"),
        "reviewer": manifest.get("reviewer"),
        "releaseClassification": manifest.get("releaseClassification"),
    }
    digest = _digest(body)
    previous = previous_anchor or "GENESIS"
    anchor = hashlib.sha256(f"{previous}:{digest}".encode()).hexdigest()
    return {
        "manifestId": manifest.get("manifestId"),
        "recomputedDigest": digest,
        "recomputedAnchor": anchor,
        "reproducible": digest == manifest.get("manifestDigest"),
        "anchored": anchor == manifest.get("ledgerAnchor"),
        "complete": all(body.get(field) for field in EXTRACT_MANIFEST_FIELDS),
    }

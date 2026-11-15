"""Pillar A capabilities that make the architecture generative.

Increment 5's Pillar A is not about storing more diagrams. It is about three
things a programme can *prove*:

* **A-2 modularity engine** - a family of variants generated deterministically
  from one common core, with a complete bill of materials each, and a library
  rule that refuses a variant which is not a legal member of the family;
* **A-4 technology insertion planner** - a TRL/SRL candidate mapped against
  real production slots, with the maturity disagreement and the slot conflict
  named before anything is inserted;
* **A-5 digital engineering** - an ICD generated from the registered interface
  characteristics (not typed separately) and a catalogue of pre-integrated
  reference architectures.

Everything here is a pure function of its inputs. The same core produces the
same variant identifiers, the same ICD digest and the same insertion finding on
any machine, which is what makes a review of a generated artefact meaningful.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .architecture import interface_digest
from .errors import ValidationError
from .testlab import find_slot_conflicts

#: Versions of the derivations. A change is a contract change.
CORE_ID_VERSION = "1"
VARIANT_ID_VERSION = "1"
ICD_ID_VERSION = "1"
REFERENCE_ARCHITECTURE_VERSION = "1"

TRL_LABELS = tuple(f"TRL_{level}" for level in range(1, 10))
SRL_LABELS = tuple(f"SRL_{level}" for level in range(1, 10))

#: The three pre-integrated DoN reference architectures A-5 requires. They are
#: templates, not programme facts: a programme instantiates one and the
#: instantiation is what lives in the thread.
REFERENCE_ARCHITECTURES: tuple[dict[str, Any], ...] = (
    {
        "id": "RA:HBTSS-AEGIS",
        "name": "HBTSS tracking layer into Aegis cueing",
        "sponsor": "DoN / MDA",
        "systemTypes": ["SPACE_SENSOR", "SHIPBOARD_COMBAT_SYSTEM", "INTERCEPTOR"],
        "interfaceCount": 4,
        "description": "Hypersonic tracking custody handed to Aegis for engagement.",
    },
    {
        "id": "RA:GPI-TERMINAL",
        "name": "GPI terminal defence against a glide vehicle",
        "sponsor": "DoN / MDA",
        "systemTypes": ["SHIPBOARD_RADAR", "INTERCEPTOR", "FIRE_CONTROL"],
        "interfaceCount": 5,
        "description": "Terminal-phase intercept using shipboard radar and GPI.",
    },
    {
        "id": "RA:HGV-TRACK-REL",
        "name": "Relocatable HGV tracking and custody relay",
        "sponsor": "DoN",
        "systemTypes": ["GROUND_RADAR", "RELAY", "C2"],
        "interfaceCount": 3,
        "description": "Relocatable custody relay for a contested tracking layer.",
    },
)

REFERENCE_ARCHITECTURE_REQUIRED = ("id", "name", "sponsor", "systemTypes", "interfaceCount")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# A-2: family-of-systems generation
# ---------------------------------------------------------------------------


def normalise_core(core_members: Any) -> tuple[dict[str, Any], ...]:
    """Validate and canonically order a common-core bill of materials.

    Every core member pins a revision. A member without a revision is not a
    pinned element, and a family generated from an unpinned core would produce
    variants that look identical and behave differently.
    """
    if not isinstance(core_members, list) or not core_members:
        raise ValidationError("a common core must contain at least one member")

    seen: dict[tuple[str, str], dict[str, Any]] = {}
    for index, raw in enumerate(core_members):
        if not isinstance(raw, dict):
            raise ValidationError(f"core member at index {index} must be an object")
        entity_type = raw.get("entityType")
        entity_id = raw.get("entityId")
        revision = raw.get("revision")
        if not isinstance(entity_type, str) or not entity_type:
            raise ValidationError(f"core member at index {index} is missing 'entityType'")
        if not isinstance(entity_id, str) or not entity_id:
            raise ValidationError(f"core member at index {index} is missing 'entityId'")
        if not isinstance(revision, str) or not revision:
            raise ValidationError(
                f"core member at index {index} ({entity_id}) must pin a 'revision'"
            )
        key = (entity_type, entity_id)
        if key in seen:
            raise ValidationError(f"duplicate core member {entity_type}:{entity_id}")
        seen[key] = {
            "entityType": entity_type,
            "entityId": entity_id,
            "revision": revision,
        }
    return tuple(sorted(seen.values(), key=lambda item: (item["entityType"], item["entityId"])))


def core_content_id(family_id: str, core_members: tuple[dict[str, Any], ...]) -> tuple[str, str]:
    """The content address of a common core: ``(coreId, digest)``."""
    payload = {
        "idVersion": CORE_ID_VERSION,
        "familyId": family_id,
        "members": list(core_members),
    }
    digest = _digest(payload)
    return f"CORE:{digest[:26].upper()}", digest


def library_violations(
    members: list[dict[str, Any]],
    rules: dict[str, Any] | None,
) -> list[str]:
    """Check a bill of materials against the family's library rules.

    The rules are intentionally declarative: allowed entity types, members that
    every variant must carry, members no variant may carry, and a size cap.
    A violation is returned, never repaired, because a generator that silently
    fixes an illegal variant hides the architecture error it was meant to catch.
    """
    if not rules:
        return []
    problems: list[str] = []
    ids = {member["entityId"] for member in members}
    types = {member["entityType"] for member in members}

    allowed = rules.get("allowedEntityTypes")
    if isinstance(allowed, list):
        illegal = sorted(types - {str(item) for item in allowed})
        if illegal:
            problems.append("entity types outside the library: " + ", ".join(illegal))

    for required in rules.get("requiredEntityIds") or []:
        if str(required) not in ids:
            problems.append(f"required library member {required} is missing")

    for forbidden in rules.get("forbiddenEntityIds") or []:
        if str(forbidden) in ids:
            problems.append(f"member {forbidden} is forbidden by the library")

    maximum = rules.get("maxMembers")
    if isinstance(maximum, int) and len(members) > maximum:
        problems.append(f"bill of materials has {len(members)} members, above the cap of {maximum}")

    return problems


def generate_variants(
    *,
    family_id: Any,
    core_members: Any,
    variant_specs: Any,
    library_rules: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a family of variants from one common core.

    A variant spec may add members, remove members, override revisions and
    declare its distinguishing characteristics. The generated variant entity
    carries the complete bill of materials, the ``familyId`` and the content
    address of the core it came from, so a core defect is traceable to every
    variant that inherited it.

    Illegal variants are *refused* and reported alongside the legal ones rather
    than aborting the batch: a programme needs to see which of its twenty
    variants broke the library, not merely that one did.
    """
    if not isinstance(family_id, str) or not family_id.strip():
        raise ValidationError("'familyId' is required")
    if not isinstance(variant_specs, list) or not variant_specs:
        raise ValidationError("'variantSpecs' must be a non-empty list")

    core = normalise_core(core_members)
    core_id, core_digest = core_content_id(family_id.strip(), core)

    core_problems = library_violations(list(core), library_rules)
    if core_problems:
        raise ValidationError("the common core violates the library", detail=core_problems)

    variants: list[dict[str, Any]] = []
    refused: list[dict[str, Any]] = []
    designations: set[str] = set()

    for index, spec in enumerate(variant_specs):
        if not isinstance(spec, dict):
            raise ValidationError(f"variant spec at index {index} must be an object")
        designation = spec.get("variantId") or spec.get("designation")
        if not isinstance(designation, str) or not designation.strip():
            raise ValidationError(f"variant spec at index {index} is missing a designation")
        designation = designation.strip()
        if designation in designations:
            raise ValidationError(f"duplicate variant designation {designation!r}")
        designations.add(designation)

        system_id = spec.get("systemId")
        if not isinstance(system_id, str) or not system_id.startswith("SYS:"):
            raise ValidationError(
                f"variant {designation!r} must name a 'systemId' of the form 'SYS:...'"
            )

        overrides = spec.get("overrides") or {}
        if not isinstance(overrides, dict):
            raise ValidationError(f"variant {designation!r} has a non-object 'overrides'")

        members: dict[tuple[str, str], dict[str, Any]] = {
            (member["entityType"], member["entityId"]): dict(member) for member in core
        }
        additions = spec.get("additions") or []
        if not isinstance(additions, list):
            raise ValidationError(f"variant {designation!r} has a non-list 'additions'")
        for addition in additions:
            if not isinstance(addition, dict):
                raise ValidationError(f"variant {designation!r} has a non-object addition")
            entity_type = addition.get("entityType")
            entity_id = addition.get("entityId")
            revision = addition.get("revision")
            if not all(isinstance(value, str) and value for value in (entity_type, entity_id, revision)):
                raise ValidationError(
                    f"variant {designation!r} has an addition without entityType, entityId and revision"
                )
            members[(entity_type, entity_id)] = {
                "entityType": entity_type,
                "entityId": entity_id,
                "revision": revision,
            }

        for entity_id, revision in overrides.items():
            key = next((key for key in members if key[1] == entity_id), None)
            if key is None:
                raise ValidationError(
                    f"variant {designation!r} overrides unknown member {entity_id!r}"
                )
            if not isinstance(revision, str) or not revision:
                raise ValidationError(
                    f"variant {designation!r} overrides {entity_id!r} with a non-string revision"
                )
            members[key] = {**members[key], "revision": revision}

        for removal in spec.get("removals") or []:
            key = next((key for key in members if key[1] == str(removal)), None)
            if key is None:
                raise ValidationError(
                    f"variant {designation!r} removes unknown member {removal!r}"
                )
            del members[key]

        bom = sorted(members.values(), key=lambda item: (item["entityType"], item["entityId"]))
        problems = library_violations(bom, library_rules)
        if problems:
            refused.append({"variantId": designation, "reasons": problems})
            continue

        digest = _digest(
            {
                "idVersion": VARIANT_ID_VERSION,
                "familyId": family_id.strip(),
                "designation": designation,
                "members": bom,
            }
        )
        variants.append(
            {
                "id": f"VAR:{digest[:26].upper()}",
                "systemId": system_id,
                "variantId": designation,
                "familyId": family_id.strip(),
                "configurationVersion": spec.get("configurationVersion") or "1",
                "distinguishingCharacteristics": sorted(
                    {str(item) for item in spec.get("distinguishingCharacteristics") or []}
                ),
                "coreId": core_id,
                "coreDigest": core_digest,
                "billOfMaterials": bom,
                "billOfMaterialsDigest": _digest(bom),
                "memberCount": len(bom),
                "licensable": True,
                "configurable": True,
            }
        )

    variants.sort(key=lambda item: item["variantId"])
    refused.sort(key=lambda item: item["variantId"])
    return {
        "familyId": family_id.strip(),
        "coreId": core_id,
        "coreDigest": core_digest,
        "idVersion": VARIANT_ID_VERSION,
        "variants": variants,
        "refused": refused,
        "generatedCount": len(variants),
        "refusedCount": len(refused),
        "reproducible": True,
    }


def propagate_core_error(
    *,
    finding: dict[str, Any],
    variants: list[dict[str, Any]],
) -> dict[str, Any]:
    """Show which variants inherited a core defect.

    This is the detection half of A-2's second acceptance criterion: a defect
    in the core is not one finding, it is one finding per generated variant,
    and the report names each affected variant id.
    """
    entity_id = finding.get("entityId")
    if not isinstance(entity_id, str) or not entity_id:
        raise ValidationError("a core finding must name the 'entityId' it concerns")

    affected = [
        variant["variantId"]
        for variant in variants
        if any(member["entityId"] == entity_id for member in variant.get("billOfMaterials") or [])
    ]
    return {
        "finding": finding,
        "detectedIn": affected,
        "detectedInAll": bool(variants) and len(affected) == len(variants),
        "variantCount": len(variants),
    }


# ---------------------------------------------------------------------------
# A-4: technology insertion planning
# ---------------------------------------------------------------------------


def _maturity_for(level: int) -> str:
    if not 1 <= level <= 9:
        raise ValidationError("TRL and SRL must be between 1 and 9")
    return f"TRL_{level}"


def assess_insertion(
    *,
    candidate: dict[str, Any],
    subsystems: list[dict[str, Any]],
    slots: list[dict[str, Any]],
    existing_insertions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Assess a technology insertion against maturity and production slots.

    Three findings decide the outcome:

    * the candidate's TRL must agree with the subsystem's recorded maturity,
      because a planner that accepts a newer claim than the ontology holds is
      planning against a fiction;
    * every required production slot must be free in the requested window;
    * a candidate below the programme's minimum TRL/SRL is not insertable,
      however attractive its impact.

    The impact is reported in both cost and schedule, and the traceable change
    names the configuration artefact the insertion would produce.
    """
    name = candidate.get("name")
    if not isinstance(name, str) or not name:
        raise ValidationError("the insertion candidate must carry a 'name'")

    trl = candidate.get("trl")
    srl = candidate.get("srl")
    if not isinstance(trl, int) or isinstance(trl, bool) or not 1 <= trl <= 9:
        raise ValidationError("'trl' must be an integer between 1 and 9")
    if not isinstance(srl, int) or isinstance(srl, bool) or not 1 <= srl <= 9:
        raise ValidationError("'srl' must be an integer between 1 and 9")

    subsystem_id = candidate.get("subsystemId")
    if not isinstance(subsystem_id, str) or not subsystem_id:
        raise ValidationError("the insertion candidate must name a 'subsystemId'")

    subsystem = next((row for row in subsystems if row.get("id") == subsystem_id), None)
    if subsystem is None:
        raise ValidationError(f"subsystem {subsystem_id!r} is not in the architecture")

    expected_maturity = _maturity_for(trl)
    recorded_maturity = str(subsystem.get("maturity") or "")
    findings: list[dict[str, Any]] = []
    if recorded_maturity and recorded_maturity != expected_maturity:
        findings.append(
            {
                "kind": "maturity_mismatch",
                "severity": "ERROR",
                "message": (
                    f"the candidate claims {expected_maturity} but subsystem {subsystem_id} "
                    f"records {recorded_maturity}"
                ),
            }
        )

    minimum_trl = candidate.get("minimumTrl")
    if isinstance(minimum_trl, int) and trl < minimum_trl:
        findings.append(
            {
                "kind": "below_programme_floor",
                "severity": "ERROR",
                "message": f"TRL {trl} is below the programme floor of TRL {minimum_trl}",
            }
        )

    window = candidate.get("window")
    conflicts: list[dict[str, Any]] = []
    if isinstance(window, dict):
        conflicts = find_slot_conflicts(window, [*slots, *(existing_insertions or [])])
        if conflicts:
            findings.append(
                {
                    "kind": "slot_conflict",
                    "severity": "ERROR",
                    "message": "the requested production window is already committed",
                    "conflicts": conflicts,
                }
            )

    required_slots = [str(item) for item in candidate.get("requiredSlotIds") or []]
    known_slots = {
        str(slot.get("slotId") or slot.get("id"))
        for slot in [*slots, *(existing_insertions or [])]
    }
    unknown = sorted(set(required_slots) - known_slots)
    if unknown:
        findings.append(
            {
                "kind": "unknown_slot",
                "severity": "ERROR",
                "message": "the candidate names production slots that do not exist: "
                + ", ".join(unknown),
            }
        )

    blocking = [finding for finding in findings if finding["severity"] == "ERROR"]
    traceable_change = {
        "kind": "VARIANT",
        "subsystemId": subsystem_id,
        "technologyId": candidate.get("technologyId"),
        "proposedRevision": candidate.get("proposedRevision") or f"{trl}.0",
        "description": f"insert {name} into {subsystem_id}",
    }
    return {
        "candidate": {
            "name": name,
            "technologyId": candidate.get("technologyId"),
            "trl": trl,
            "srl": srl,
            "maturity": expected_maturity,
            "subsystemId": subsystem_id,
        },
        "recordedMaturity": recorded_maturity or None,
        "insertable": not blocking,
        "findings": findings,
        "slotConflicts": conflicts,
        "impact": {
            "costDelta": candidate.get("costDelta", 0),
            "scheduleImpactDays": candidate.get("scheduleImpactDays", 0),
            "rateImpactUnitsPerDay": candidate.get("rateImpactUnitsPerDay", 0),
        },
        "traceableChange": traceable_change,
        "reproducible": True,
    }


# ---------------------------------------------------------------------------
# A-5: ICD generation and the reference-architecture catalogue
# ---------------------------------------------------------------------------


def generate_icd(
    *,
    interface: dict[str, Any],
    from_system: dict[str, Any],
    to_system: dict[str, Any],
) -> dict[str, Any]:
    """Generate an interface control document from the registered interface.

    The ICD is derived, never authored: every characteristic in it comes from
    the interface record that a baseline pins. That is the property A-5 asks
    for - an ICD that cannot drift from the interface it describes without the
    digest changing.
    """
    characteristics = interface.get("characteristics")
    if not isinstance(characteristics, dict) or not characteristics:
        raise ValidationError("the interface must carry characteristics before an ICD can be generated")
    from_system_id = interface.get("fromSystemId")
    to_system_id = interface.get("toSystemId")
    if from_system.get("id") != from_system_id:
        raise ValidationError("the 'from' system does not match the interface's fromSystemId")
    if to_system.get("id") != to_system_id:
        raise ValidationError("the 'to' system does not match the interface's toSystemId")

    digest = interface.get("digest") or interface_digest(
        from_system_id=from_system_id,
        to_system_id=to_system_id,
        characteristics=characteristics,
    )
    envelope = characteristics.get("envelope") or {}
    from_name = (from_system.get("attributes") or {}).get("name") or from_system_id
    to_name = (to_system.get("attributes") or {}).get("name") or to_system_id

    sections = [
        {
            "id": "1",
            "title": "Scope",
            "body": f"This ICD governs the interface between {from_name} and {to_name}.",
        },
        {
            "id": "2",
            "title": "Endpoints",
            "body": (
                f"Provider: {from_name} ({from_system_id}); "
                f"Consumer: {to_name} ({to_system_id})."
            ),
        },
        {
            "id": "3",
            "title": "Rate",
            "body": f"The interface carries {characteristics.get('rate')} units per second.",
        },
        {
            "id": "4",
            "title": "Latency",
            "body": f"End-to-end latency shall not exceed {characteristics.get('latency')} ms.",
        },
        {
            "id": "5",
            "title": "Timing",
            "body": f"The timing model is {characteristics.get('timing')}.",
        },
        {
            "id": "6",
            "title": "Envelope",
            "body": "The interface is valid within "
            + ", ".join(f"{key}={value}" for key, value in sorted(envelope.items()))
            + ".",
        },
    ]
    return {
        "icdId": f"ICD:{digest[:26].upper()}",
        "idVersion": ICD_ID_VERSION,
        "interfaceId": interface.get("interfaceId"),
        "interfaceDigest": digest,
        "fromSystemId": from_system_id,
        "toSystemId": to_system_id,
        "title": f"ICD {from_name} to {to_name}",
        "sections": sections,
        "characteristics": characteristics,
        "conformant": True,
    }


def verify_icd(
    *,
    icd: dict[str, Any],
    interface: dict[str, Any],
    from_system: dict[str, Any] | None,
    to_system: dict[str, Any] | None,
) -> dict[str, Any]:
    """Check a generated ICD against the interface and the systems it names."""
    problems: list[str] = []
    if from_system is None:
        problems.append(f"the provider system {icd.get('fromSystemId')} does not exist")
    if to_system is None:
        problems.append(f"the consumer system {icd.get('toSystemId')} does not exist")

    digest = interface.get("digest") or interface_digest(
        from_system_id=interface.get("fromSystemId"),
        to_system_id=interface.get("toSystemId"),
        characteristics=interface.get("characteristics") or {},
    )
    if icd.get("interfaceDigest") != digest:
        problems.append("the ICD was generated from a different interface revision")
    if icd.get("characteristics") != interface.get("characteristics"):
        problems.append("the ICD characteristics differ from the registered interface")
    if icd.get("fromSystemId") != interface.get("fromSystemId"):
        problems.append("the ICD provider differs from the interface provider")
    if icd.get("toSystemId") != interface.get("toSystemId"):
        problems.append("the ICD consumer differs from the interface consumer")

    return {
        "icdId": icd.get("icdId"),
        "interfaceDigest": digest,
        "conformant": not problems,
        "problems": problems,
    }


def catalogue_report(
    architectures: list[dict[str, Any]] | None = None,
    *,
    minimum: int = 3,
) -> dict[str, Any]:
    """Validate a reference-architecture catalogue.

    A catalogue entry is usable only when it names its sponsor, its system
    types and its interface count. An entry that is a slide title is reported
    as incomplete rather than counted toward the minimum.
    """
    entries = [dict(item) for item in (architectures if architectures is not None else REFERENCE_ARCHITECTURES)]
    valid: list[dict[str, Any]] = []
    incomplete: list[dict[str, Any]] = []
    for entry in entries:
        missing = [
            field
            for field in REFERENCE_ARCHITECTURE_REQUIRED
            if entry.get(field) in (None, "", [], {})
        ]
        if missing:
            incomplete.append({"id": entry.get("id"), "missing": missing})
        else:
            valid.append(entry)

    identifiers = [str(entry.get("id")) for entry in entries if entry.get("id")]
    duplicates = sorted({identifier for identifier in identifiers if identifiers.count(identifier) > 1})
    return {
        "idVersion": REFERENCE_ARCHITECTURE_VERSION,
        "entries": entries,
        "valid": valid,
        "incomplete": incomplete,
        "duplicateIds": duplicates,
        "count": len(valid),
        "sufficient": len(valid) >= minimum and not duplicates,
        "minimum": minimum,
    }

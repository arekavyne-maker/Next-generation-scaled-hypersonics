"""Pillar A generative rules: variants, insertion, ICDs and the catalogue."""

from __future__ import annotations

import pytest
from ngsh_core.architecture import interface_digest
from ngsh_core.errors import ValidationError
from ngsh_core.modularity import (
    REFERENCE_ARCHITECTURES,
    assess_insertion,
    catalogue_report,
    core_content_id,
    generate_icd,
    generate_variants,
    normalise_core,
    propagate_core_error,
    verify_icd,
)

CORE = [
    {"entityType": "Part", "entityId": "PART:CORE-A", "revision": "A"},
    {"entityType": "Part", "entityId": "PART:CORE-B", "revision": "B"},
]


def test_core_members_are_canonically_ordered_and_need_revisions():
    core = normalise_core(list(reversed(CORE)))
    assert [member["entityId"] for member in core] == ["PART:CORE-A", "PART:CORE-B"]
    with pytest.raises(ValidationError):
        normalise_core([{"entityType": "Part", "entityId": "PART:1"}])


def test_core_content_id_is_the_same_for_the_same_core():
    core = normalise_core(CORE)
    assert core_content_id("FAM:1", core) == core_content_id("FAM:1", core)


def test_variants_are_generated_deterministically_with_a_complete_bom():
    body = {
        "family_id": "FAM:1",
        "core_members": CORE,
        "variant_specs": [
            {
                "variantId": "BLK-1",
                "systemId": "SYS:1",
                "additions": [{"entityType": "Part", "entityId": "PART:NOSE", "revision": "A"}],
                "distinguishingCharacteristics": ["short nose"],
            },
            {
                "variantId": "BLK-2",
                "systemId": "SYS:2",
                "overrides": {"PART:CORE-A": "C"},
            },
        ],
    }
    first = generate_variants(**body)
    second = generate_variants(**body)
    assert first["generatedCount"] == 2
    assert [item["id"] for item in first["variants"]] == [item["id"] for item in second["variants"]]
    assert first["variants"][0]["memberCount"] == 3
    assert first["variants"][0]["coreId"].startswith("CORE:")
    assert first["variants"][0]["billOfMaterialsDigest"]


def test_an_illegal_variant_is_refused_and_reported_alongside_the_legal_ones():
    result = generate_variants(
        family_id="FAM:1",
        core_members=CORE,
        variant_specs=[
            {"variantId": "LEGAL", "systemId": "SYS:1"},
            {
                "variantId": "ILLEGAL",
                "systemId": "SYS:2",
                "additions": [{"entityType": "Supplier", "entityId": "SUP:1", "revision": "A"}],
            },
        ],
        library_rules={"allowedEntityTypes": ["Part"]},
    )
    assert result["generatedCount"] == 1
    assert result["refusedCount"] == 1
    assert result["refused"][0]["variantId"] == "ILLEGAL"
    assert any("outside the library" in reason for reason in result["refused"][0]["reasons"])


def test_a_core_defect_is_detected_in_every_variant_that_carries_it():
    result = generate_variants(
        family_id="FAM:1",
        core_members=CORE,
        variant_specs=[
            {"variantId": "BLK-1", "systemId": "SYS:1"},
            {"variantId": "BLK-2", "systemId": "SYS:2"},
        ],
    )
    report = propagate_core_error(
        finding={"entityId": "PART:CORE-A", "kind": "material"},
        variants=result["variants"],
    )
    assert report["detectedInAll"] is True
    assert sorted(report["detectedIn"]) == ["BLK-1", "BLK-2"]


def test_insertion_requires_the_recorded_maturity_to_match_the_claim():
    report = assess_insertion(
        candidate={
            "name": "new TPS",
            "technologyId": "TECH:1",
            "subsystemId": "SUB:TPS",
            "trl": 7,
            "srl": 6,
        },
        subsystems=[{"id": "SUB:TPS", "maturity": "TRL_5"}],
        slots=[],
    )
    assert report["insertable"] is False
    assert any(finding["kind"] == "maturity_mismatch" for finding in report["findings"])
    assert report["traceableChange"]["kind"] == "VARIANT"


def test_insertion_is_blocked_by_a_committed_production_slot():
    report = assess_insertion(
        candidate={
            "name": "new TPS",
            "subsystemId": "SUB:TPS",
            "trl": 7,
            "srl": 6,
            "window": {
                "slotId": "RS:NEW",
                "facilityId": "FAC:1",
                "start": "2026-01-01T00:00:00+00:00",
                "end": "2026-01-10T00:00:00+00:00",
            },
        },
        subsystems=[{"id": "SUB:TPS", "maturity": "TRL_7"}],
        slots=[
            {
                "slotId": "RS:EXISTING",
                "facilityId": "FAC:1",
                "start": "2026-01-05T00:00:00+00:00",
                "end": "2026-01-15T00:00:00+00:00",
            }
        ],
    )
    assert report["insertable"] is False
    assert report["slotConflicts"]


def _interface() -> dict:
    characteristics = {
        "rate": 1000,
        "latency": 20,
        "timing": "deterministic",
        "envelope": {"range": 500},
    }
    return {
        "interfaceId": "IF:1",
        "fromSystemId": "SYS:1",
        "toSystemId": "SYS:2",
        "characteristics": characteristics,
        "digest": interface_digest(
            from_system_id="SYS:1",
            to_system_id="SYS:2",
            characteristics=characteristics,
        ),
    }


def test_an_icd_is_derived_from_the_registered_interface_and_verifies():
    interface = _interface()
    from_system = {"id": "SYS:1", "attributes": {"name": "HBTSS"}}
    to_system = {"id": "SYS:2", "attributes": {"name": "Aegis"}}
    icd = generate_icd(interface=interface, from_system=from_system, to_system=to_system)
    assert icd["icdId"].startswith("ICD:")
    assert icd["interfaceDigest"] == interface["digest"]
    verification = verify_icd(
        icd=icd, interface=interface, from_system=from_system, to_system=to_system
    )
    assert verification["conformant"] is True


def test_an_icd_cannot_drift_from_the_interface_revision():
    interface = _interface()
    from_system = {"id": "SYS:1", "attributes": {"name": "HBTSS"}}
    to_system = {"id": "SYS:2", "attributes": {"name": "Aegis"}}
    icd = generate_icd(interface=interface, from_system=from_system, to_system=to_system)
    changed = {**interface, "characteristics": {**interface["characteristics"], "latency": 30}}
    verification = verify_icd(
        icd=icd, interface=changed, from_system=from_system, to_system=to_system
    )
    assert verification["conformant"] is False


def test_the_reference_catalogue_has_the_three_required_architectures():
    report = catalogue_report(list(REFERENCE_ARCHITECTURES))
    assert report["sufficient"] is True
    assert report["count"] >= 3
    assert report["incomplete"] == []


def test_an_incomplete_catalogue_entry_is_not_counted():
    report = catalogue_report(
        [{"id": "RA:X", "name": "slide", "sponsor": "", "systemTypes": [], "interfaceCount": 0}]
    )
    assert report["count"] == 0
    assert report["sufficient"] is False
    assert report["incomplete"][0]["id"] == "RA:X"

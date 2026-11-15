"""Pillar E rules: live-thread training, reusable curriculum, safe extracts."""

from __future__ import annotations

import pytest
from ngsh_core.errors import ValidationError
from ngsh_core.training import (
    curriculum_package,
    sanitised_extract,
    training_completion,
    training_coverage,
    validate_training_scenario,
    verify_extract_manifest,
    verify_package,
)

LIVE = {("Part", "PART:1"), ("Variant", "VAR:1")}


def test_a_scenario_built_on_live_entities_is_valid():
    report = validate_training_scenario(
        {
            "name": "CMC cell walkthrough",
            "references": [
                {"type": "Part", "id": "PART:1"},
                {"type": "Variant", "id": "VAR:1"},
            ],
        },
        live_references=LIVE,
    )
    assert report["valid"] is True
    assert report["referenceCoverage"] == 1.0
    assert report["meetsCoverageTarget"] is True


def test_a_placeholder_reference_is_named_and_refused():
    report = validate_training_scenario(
        {
            "name": "training on placeholder-part",
            "references": [{"type": "Part", "id": "PART:1"}, {"type": "Part", "id": "dummy"}],
        },
        live_references=LIVE,
    )
    assert report["valid"] is False
    assert report["placeholders"] == ["Part:dummy"]


def test_a_scenario_with_no_references_is_refused_at_the_door():
    with pytest.raises(ValidationError):
        validate_training_scenario({"name": "empty", "references": []}, live_references=LIVE)


def test_training_coverage_reports_the_live_share_and_placeholders():
    report = training_coverage(
        [
            {
                "valid": True,
                "liveReferenceCount": 2,
                "scenarioId": "TSC:1",
                "placeholders": [],
            },
            {
                "valid": False,
                "liveReferenceCount": 0,
                "scenarioId": "TSC:2",
                "placeholders": ["Part:dummy"],
            },
        ]
    )
    assert report["liveReferenceShare"] == 0.5
    assert report["meetsLiveReferenceTarget"] is False
    assert report["placeholderScenarios"] == ["TSC:2"]


def test_a_completion_maps_to_the_skill_it_exercised():
    completion = training_completion(
        person_id="PER:1",
        scenario_id="TSC:1",
        skill_id="SKL:1",
        score=92.5,
        passed=True,
        completed_at="2026-02-01T00:00:00+00:00",
    )
    assert completion["mapsToSkill"] == "SKL:1"
    assert completion["credentialEligible"] is True
    assert completion["completionId"].startswith("TRAIN:")


def _package(**overrides):
    body = {
        "title": "CMC fundamentals",
        "version": "1.0.0",
        "modules": [{"moduleId": "MOD:1"}, {"moduleId": "MOD:2"}],
        "source_records": [{"id": "PART:1", "classification": "UNCLASSIFIED"}],
        "guard_version": "2026.1",
        "reviewer": "usr:professor",
    }
    body.update(overrides)
    return curriculum_package(**body)


def test_a_curriculum_package_is_content_addressed_and_verifies():
    package = _package()
    assert package["packageId"].startswith("PKG:")
    assert verify_package(package)["reproducible"] is True


def test_a_package_derived_from_a_restricted_record_is_refused():
    with pytest.raises(ValidationError) as excinfo:
        _package(source_records=[{"id": "PART:1", "classification": "RESTRICTED"}])
    assert "RESTRICTED" in excinfo.value.message


def test_an_extract_releases_only_when_no_record_is_restricted():
    outcome = sanitised_extract(
        view="academic",
        records=[
            {"id": "PART:1", "type": "Part", "classification": "UNCLASSIFIED"},
            {"id": "PART:2", "type": "Part", "classification": "CUI"},
        ],
        transformations=["strip-cost", "coarsen-tolerance"],
        guard_version="2026.1",
        reviewer="usr:security",
    )
    assert outcome["released"] is True
    manifest = outcome["manifest"]
    assert manifest["complete"] is True
    verification = verify_extract_manifest(manifest, previous_anchor=None)
    assert verification["reproducible"] is True
    assert verification["anchored"] is True


def test_a_restricted_record_blocks_the_extract_and_the_attempt_is_recorded():
    outcome = sanitised_extract(
        view="academic",
        records=[{"id": "PART:9", "type": "Part", "classification": "RESTRICTED"}],
        transformations=["strip-cost"],
        guard_version="2026.1",
        reviewer="usr:security",
    )
    assert outcome["released"] is False
    assert outcome["recorded"] is True
    assert outcome["blocked"][0]["id"] == "PART:9"

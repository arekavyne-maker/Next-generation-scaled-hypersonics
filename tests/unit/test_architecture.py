"""Unit tests for the Pillar A domain rules.

These are the properties the increment is assessed on: reproducible baseline
identity, complete interface characteristics, and verification status that is
a pure function of the evidence.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ngsh_core.architecture import (
    aggregate_status,
    assess_evidence,
    baseline_digest,
    baseline_id,
    create_baseline,
    interface_digest,
    normalise_members,
    requirement_coverage,
    rollup_tree,
    validate_interface,
    verify_baseline,
)
from ngsh_core.errors import ValidationError
from ngsh_core.ontology import OntologyLoader

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def registry():
    return OntologyLoader(REPO_ROOT / "contracts").load()


def _member(entity_type: str, entity_id: str, revision: str | None = None) -> dict:
    return {"entityType": entity_type, "entityId": entity_id, "revision": revision}


def _baseline(registry, members=None, name="Baseline A", builds=None):
    return create_baseline(
        system_id="SYS:01J8ZSYS",
        name=name,
        raw_members=members
        or [
            _member("Part", "PART:01J8ZPART1", "C"),
            _member("Part", "PART:01J8ZPART2", "A"),
        ],
        software_builds=builds or ["fw-1.4.2"],
        created_by="usr:engineer",
        created_at="2026-11-15T00:00:00Z",
        registry=registry,
    )


def _result(outcome: str, *, reviewed_by: str | None = "usr:reviewer", result_id: str = "TR:1") -> dict:
    attributes = {"outcome": outcome, "testMethod": "plasma-arc-heater"}
    if reviewed_by:
        attributes["reviewedBy"] = reviewed_by
    return {"id": result_id, "type": "TestResult", "attributes": attributes}


# -- baselines ---------------------------------------------------------------


def test_baseline_id_is_deterministic_across_member_order(registry) -> None:
    forward = _baseline(
        registry,
        members=[
            _member("Part", "PART:01J8ZPART1", "C"),
            _member("Part", "PART:01J8ZPART2", "A"),
        ],
    )
    reverse = _baseline(
        registry,
        members=[
            _member("Part", "PART:01J8ZPART2", "A"),
            _member("Part", "PART:01J8ZPART1", "C"),
        ],
    )
    assert forward.id == reverse.id
    assert forward.digest == reverse.digest


def test_baseline_id_ignores_the_label(registry) -> None:
    first = _baseline(registry, name="Preliminary design review")
    second = _baseline(registry, name="Renamed after the review")
    assert first.id == second.id


def test_baseline_id_changes_when_content_changes(registry) -> None:
    first = _baseline(registry)
    second = _baseline(
        registry,
        members=[
            _member("Part", "PART:01J8ZPART1", "D"),
            _member("Part", "PART:01J8ZPART2", "A"),
        ],
    )
    assert first.id != second.id


def test_baseline_is_reproducible_from_its_own_record(registry) -> None:
    baseline = _baseline(registry)
    assert verify_baseline(baseline)["reproducible"] is True


def test_duplicate_member_is_rejected(registry) -> None:
    with pytest.raises(ValidationError):
        normalise_members(
            [
                _member("Part", "PART:01J8ZPART1", "C"),
                _member("Part", "PART:01J8ZPART1", "D"),
            ],
            registry=registry,
        )


def test_unknown_entity_type_is_rejected(registry) -> None:
    with pytest.raises(ValidationError):
        normalise_members([_member("Widget", "PART:1", "A")], registry=registry)


def test_revisioned_type_requires_a_revision(registry) -> None:
    with pytest.raises(ValidationError):
        normalise_members([_member("Part", "PART:01J8ZPART1")], registry=registry)


def test_member_id_must_match_its_type_prefix(registry) -> None:
    with pytest.raises(ValidationError):
        normalise_members([_member("Part", "SYS:01J8ZPART1", "A")], registry=registry)


def test_baseline_requires_a_system_id(registry) -> None:
    with pytest.raises(ValidationError):
        create_baseline(
            system_id="not-a-system",
            name="x",
            raw_members=[_member("Part", "PART:1", "A")],
            created_by="usr:engineer",
            created_at="2026-11-15T00:00:00Z",
            registry=registry,
        )


def test_baseline_id_shape() -> None:
    ident = baseline_id(baseline_digest("SYS:1", normalise_members([_member("Part", "PART:1", "A")])))
    assert ident.startswith("BL:")
    assert len(ident) == len("BL:") + 26


# -- interfaces --------------------------------------------------------------


VALID_CHARACTERISTICS = {
    "rate": 100.0,
    "latency": 2.5,
    "timing": "periodic",
    "envelope": {"minAltitudeKm": 0, "maxAltitudeKm": 40},
}


def test_interface_accepts_and_normalises_valid_characteristics() -> None:
    normalised = validate_interface(
        from_system_id="SYS:1",
        to_system_id="SYS:2",
        characteristics=VALID_CHARACTERISTICS,
    )
    assert normalised["timing"] == "PERIODIC"


@pytest.mark.parametrize("missing", ["rate", "latency", "timing", "envelope"])
def test_interface_requires_every_characteristic(missing: str) -> None:
    characteristics = {key: value for key, value in VALID_CHARACTERISTICS.items() if key != missing}
    with pytest.raises(ValidationError):
        validate_interface(from_system_id="SYS:1", to_system_id="SYS:2", characteristics=characteristics)


@pytest.mark.parametrize(
    "overrides",
    [
        {"rate": 0},
        {"rate": -1},
        {"latency": -0.1},
        {"timing": "sometimes"},
        {"envelope": {}},
    ],
)
def test_interface_rejects_bad_characteristic_values(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        validate_interface(
            from_system_id="SYS:1",
            to_system_id="SYS:2",
            characteristics={**VALID_CHARACTERISTICS, **overrides},
        )


def test_interface_must_connect_distinct_systems() -> None:
    with pytest.raises(ValidationError):
        validate_interface(
            from_system_id="SYS:1", to_system_id="SYS:1", characteristics=VALID_CHARACTERISTICS
        )


def test_interface_digest_tracks_characteristic_changes() -> None:
    first = interface_digest(
        from_system_id="SYS:1", to_system_id="SYS:2", characteristics=VALID_CHARACTERISTICS
    )
    second = interface_digest(
        from_system_id="SYS:1",
        to_system_id="SYS:2",
        characteristics={**VALID_CHARACTERISTICS, "latency": 3.0},
    )
    assert first != second


# -- verification status -----------------------------------------------------


def test_no_evidence_is_not_started_and_gapped() -> None:
    assessment = assess_evidence([])
    assert assessment.status == "NOT_STARTED"
    assert assessment.verified is False
    assert assessment.gaps


def test_reviewed_pass_verifies() -> None:
    assessment = assess_evidence([_result("PASS")])
    assert assessment.status == "COMPLETE"
    assert assessment.verified is True
    assert assessment.coverage == 1.0
    assert not assessment.reviewItems


def test_unreviewed_pass_does_not_verify() -> None:
    assessment = assess_evidence([_result("PASS", reviewed_by=None)])
    assert assessment.verified is False
    assert assessment.status == "PARTIAL"
    assert assessment.reviewItems[0]["reason"] == "unreviewed_pass"


def test_marginal_raises_a_review_item_and_does_not_satisfy() -> None:
    assessment = assess_evidence([_result("MARGINAL")])
    assert assessment.verified is False
    assert assessment.status == "PARTIAL"
    assert assessment.reviewItems[0]["reason"] == "marginal_outcome"
    assert assessment.coverage == 0.0


def test_inconclusive_raises_a_review_item() -> None:
    assessment = assess_evidence([_result("INCONCLUSIVE")])
    assert assessment.verified is False
    assert assessment.reviewItems[0]["reason"] == "inconclusive_outcome"


def test_not_run_does_not_satisfy() -> None:
    assessment = assess_evidence([_result("NOT_RUN")])
    assert assessment.verified is False
    assert assessment.reviewItems[0]["reason"] == "not_run"


def test_failure_blocks_verification_even_with_a_pass() -> None:
    assessment = assess_evidence([_result("PASS", result_id="TR:1"), _result("FAIL", result_id="TR:2")])
    assert assessment.verified is False
    assert assessment.status == "PARTIAL"
    assert assessment.coverage == 0.5
    assert any("failed" in gap for gap in assessment.gaps)


def test_coverage_reports_the_satisfying_ratio() -> None:
    assessment = assess_evidence(
        [
            _result("PASS", result_id="TR:1"),
            _result("FAIL", result_id="TR:2"),
            _result("PASS", result_id="TR:3"),
        ]
    )
    assert assessment.coverage == pytest.approx(0.6667)


def test_coverage_is_order_independent() -> None:
    forward = assess_evidence([_result("PASS", result_id="TR:1"), _result("MARGINAL", result_id="TR:2")])
    reverse = assess_evidence([_result("MARGINAL", result_id="TR:2"), _result("PASS", result_id="TR:1")])
    assert forward.to_dict() == reverse.to_dict()


def test_unknown_outcome_is_a_gap_not_a_pass() -> None:
    assessment = assess_evidence([_result("SPLENDID")])
    assert assessment.verified is False
    assert any("outside the contract" in gap for gap in assessment.gaps)


def test_requirement_report_names_missing_allocation() -> None:
    report = requirement_coverage(
        {"id": "REQ:1", "type": "Requirement"},
        [_result("PASS")],
        allocated_to=[],
        requirement_id="REQ:1",
    )
    assert any("allocated" in gap for gap in report["gaps"])
    assert report["verified"] is True


# -- rollup ------------------------------------------------------------------


def test_parent_needs_every_child_complete() -> None:
    assert aggregate_status("COMPLETE", ["COMPLETE", "COMPLETE"]) == "COMPLETE"
    assert aggregate_status("COMPLETE", ["COMPLETE", "PARTIAL"]) == "PARTIAL"
    assert aggregate_status("NOT_STARTED", ["NOT_STARTED"]) == "NOT_STARTED"
    assert aggregate_status("IN_PROGRESS", ["NOT_STARTED"]) == "IN_PROGRESS"


def test_rollup_tree_derives_status_and_counts() -> None:
    coverage = {
        "REQ:1": {"verificationStatus": "COMPLETE", "reviewItems": []},
        "REQ:2": {"verificationStatus": "COMPLETE", "reviewItems": []},
        "REQ:3": {"verificationStatus": "PARTIAL", "reviewItems": [{"reason": "marginal_outcome"}]},
    }
    parents = {"REQ:1": None, "REQ:2": "REQ:1", "REQ:3": "REQ:2"}

    report = rollup_tree(coverage, parents)
    assert report["statuses"] == {"REQ:1": "PARTIAL", "REQ:2": "PARTIAL", "REQ:3": "PARTIAL"}
    assert report["counts"]["PARTIAL"] == 3
    assert report["reviewItemCount"] == 1
    assert report["coverage"] == 0.0
    assert report["cycles"] == []


def test_rollup_tree_is_deterministic() -> None:
    coverage = {f"REQ:{index}": {"verificationStatus": "COMPLETE", "reviewItems": []} for index in range(6)}
    parents = {
        "REQ:0": None,
        "REQ:1": "REQ:0",
        "REQ:2": "REQ:1",
        "REQ:3": "REQ:1",
        "REQ:4": "REQ:2",
        "REQ:5": "REQ:3",
    }
    first = rollup_tree(coverage, parents)
    second = rollup_tree(dict(reversed(list(coverage.items()))), dict(reversed(list(parents.items()))))
    assert first["statuses"] == second["statuses"]
    assert first["counts"] == second["counts"]


def test_rollup_reports_orphans_rather_than_absorbing_them() -> None:
    coverage = {"REQ:1": {"verificationStatus": "COMPLETE", "reviewItems": []}}
    parents = {"REQ:1": None, "REQ:2": "REQ:1"}
    report = rollup_tree(coverage, parents)
    assert report["orphans"] == ["REQ:2"]


def test_rollup_reports_a_cycle() -> None:
    coverage = {
        "REQ:1": {"verificationStatus": "COMPLETE", "reviewItems": []},
        "REQ:2": {"verificationStatus": "COMPLETE", "reviewItems": []},
    }
    parents = {"REQ:1": "REQ:2", "REQ:2": "REQ:1"}
    report = rollup_tree(coverage, parents)
    assert report["cycles"]

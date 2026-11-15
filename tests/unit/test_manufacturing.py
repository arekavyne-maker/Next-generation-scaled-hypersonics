"""Rules of the manufacturing pillar: traveller, drift, genealogy and rate."""

from __future__ import annotations

import pytest
from ngsh_core.errors import ValidationError
from ngsh_core.manufacturing import (
    assemble_genealogy,
    build_traveller,
    detect_drift,
    simulate_rate,
)

PLAN = {
    "id": "PP:1",
    "revision": "C",
    "operations": [
        {"operationId": "OP1", "sequence": 1, "name": "Layup", "requiredSkillIds": ["SKL:1"]},
        {"operationId": "OP2", "sequence": 2, "name": "Cure"},
        {"operationId": "OP3", "sequence": 3, "name": "Machine"},
    ],
}


def _run(operation_id: str, disposition: str = "COMPLETE", **overrides):
    run = {
        "runId": f"PR:{operation_id}",
        "operationId": operation_id,
        "disposition": disposition,
        "measuredParameters": {},
    }
    run.update(overrides)
    return run


def test_traveller_starts_at_the_first_operation_when_nothing_has_run():
    traveller = build_traveller(PLAN, [])
    assert traveller["nextOperation"] == "OP1"
    assert [row["status"] for row in traveller["operations"]] == ["PENDING", "BLOCKED", "BLOCKED"]
    assert not traveller["complete"]


def test_traveller_advances_only_after_the_predecessor_completes():
    traveller = build_traveller(PLAN, [_run("OP1")])
    assert traveller["nextOperation"] == "OP2"
    assert traveller["operations"][0]["status"] == "COMPLETE"


def test_traveller_marks_a_rework_run_nonconforming_and_names_it():
    traveller = build_traveller(PLAN, [_run("OP1", disposition="REWORK", nonconformanceId="NC:1")])
    assert traveller["operations"][0]["status"] == "NONCONFORMING"
    assert traveller["nonconformances"][0]["nonconformanceId"] == "NC:1"
    assert not traveller["complete"]


def test_traveller_requires_at_least_one_operation():
    with pytest.raises(ValidationError):
        build_traveller({"id": "PP:1", "operations": []}, [])


def test_drift_flags_a_parameter_beyond_three_sigma():
    reference = [{"measuredParameters": {"temp": value}} for value in (179.0, 180.0, 181.0, 180.5, 179.5)]
    report = detect_drift(reference, {"measuredParameters": {"temp": 400.0}})
    assert report["status"] == "DRIFT"
    assert report["quarantine"] is True
    assert report["drivers"][0]["parameter"] == "temp"


def test_drift_does_not_flag_a_normal_run():
    reference = [{"measuredParameters": {"temp": value}} for value in (179.0, 180.0, 181.0, 180.5, 179.5)]
    assert detect_drift(reference, {"measuredParameters": {"temp": 180.2}})["status"] == "OK"


def test_drift_flags_any_departure_when_the_reference_has_no_variation():
    reference = [{"measuredParameters": {"pressure": 10.0}} for _ in range(4)]
    report = detect_drift(reference, {"measuredParameters": {"pressure": 10.5}})
    assert report["drivers"][0]["reason"] == "baseline_deviation"


def test_drift_is_not_claimed_without_enough_reference_runs():
    reference = [{"measuredParameters": {"temp": 180.0}} for _ in range(2)]
    report = detect_drift(reference, {"measuredParameters": {"temp": 400.0}})
    assert report["status"] == "INSUFFICIENT_REFERENCE"
    assert report["quarantine"] is False


def test_genealogy_names_a_missing_hop_instead_of_skipping_it():
    provenance = {
        "materialIds": ["MAT:1"],
        "processRunIds": ["PR:1"],
        "chainOfCustody": [
            {"type": "Material", "id": "MAT:1"},
            {"type": "ProcessRun", "id": "PR:404"},
        ],
    }
    report = assemble_genealogy(
        "PART:1",
        provenance,
        known_runs={"PR:1"},
        known_materials={"MAT:1"},
        known_parts={"PART:1"},
    )
    assert not report["complete"]
    assert any("PR:404" in gap for gap in report["gaps"])


def test_genealogy_understands_the_contract_chain_of_custody_shape():
    provenance = {
        "materialIds": ["MAT:1"],
        "processRunIds": ["PR:1"],
        "chainOfCustody": [
            {
                "fromNodeId": "MAT:1",
                "toNodeId": "PART:1",
                "transferredAt": "2026-11-01T00:00:00+00:00",
                "transferType": "RECEIPT",
            },
            {
                "fromNodeId": "PART:1",
                "toNodeId": "PART:404",
                "transferredAt": "2026-11-02T00:00:00+00:00",
                "transferType": "TRANSFER",
            },
        ],
    }
    report = assemble_genealogy(
        "PART:1",
        provenance,
        known_runs={"PR:1"},
        known_materials={"MAT:1"},
        known_parts={"PART:1"},
    )
    assert [hop["sequence"] for hop in report["hops"]] == [1, 2]
    assert report["hops"][0]["present"] is True
    assert report["hops"][1]["present"] is False
    assert not report["complete"]
    assert any("PART:404" in gap for gap in report["gaps"])


def test_genealogy_reports_absence_of_provenance_as_a_gap():
    report = assemble_genealogy("PART:1", None, known_runs=set(), known_materials=set(), known_parts=set())
    assert not report["complete"]
    assert report["gaps"]


def test_rate_model_names_the_binding_constraint():
    facility = {"id": "FAC:1", "surgeCapacity": {"unitsPerHour": 4, "shiftsPerDay": 2}}
    report = simulate_rate(facility, units=10_000, horizon_days=30)
    assert report["meetsDemand"] is False
    assert report["constraints"][0]["constraint"] == "facility_capacity"
    assert report["daysRequired"] is not None


def test_rate_model_meets_a_modest_demand():
    facility = {"id": "FAC:1", "surgeCapacity": {"unitsPerHour": 10, "shiftsPerDay": 3}}
    report = simulate_rate(facility, units=100, horizon_days=30)
    assert report["meetsDemand"] is True
    assert report["constraints"] == []
    assert len(report["rateCurve"]) == 30


def test_rate_model_requires_a_declared_capacity():
    with pytest.raises(ValidationError):
        simulate_rate({"id": "FAC:1"}, units=10)


def test_rate_model_rejects_non_positive_units():
    facility = {"id": "FAC:1", "surgeCapacity": {"unitsPerHour": 4}}
    with pytest.raises(ValidationError):
        simulate_rate(facility, units=0)

"""Pillars C and G extended rules: range capacity, scheduling, fidelity drift."""

from __future__ import annotations

import pytest
from ngsh_core.errors import ValidationError
from ngsh_core.testlab import apply_drift, fidelity_registry, optimise_schedule, range_capacity

RANGES = [
    {
        "facilityId": "FAC:R1",
        "name": "R1",
        "capacityPerPeriod": 4,
        "telemetryCoverage": {"overall": 0.95},
        "accreditations": ["CUI"],
        "capabilities": ["TELEMETRY"],
        "classificationCeiling": "CUI",
    },
    {
        "facilityId": "FAC:R2",
        "name": "R2",
        "capacityPerPeriod": 2,
        "telemetryCoverage": {"overall": 0.92},
        "accreditations": ["CUI", "SECRET"],
        "capabilities": ["TELEMETRY", "OPTICS"],
        "classificationCeiling": "SECRET",
    },
]


def test_range_capacity_reports_utilisation_coverage_and_conflicts():
    report = range_capacity(
        ranges=RANGES,
        slots=[
            {
                "id": "RS:1",
                "facilityId": "FAC:R1",
                "start": "2026-01-01T00:00:00+00:00",
                "end": "2026-01-05T00:00:00+00:00",
                "status": "CONFIRMED",
            },
            {
                "id": "RS:2",
                "facilityId": "FAC:R1",
                "start": "2026-01-04T00:00:00+00:00",
                "end": "2026-01-08T00:00:00+00:00",
                "status": "CONFIRMED",
            },
        ],
    )
    assert report["rangeCount"] == 2
    assert report["multiRange"] is True
    r1 = next(row for row in report["ranges"] if row["rangeId"] == "FAC:R1")
    assert r1["booked"] == 2
    assert r1["conflicts"]
    assert r1["feasible"] is False
    assert report["feasible"] is False


def test_range_capacity_requires_a_declared_capacity():
    with pytest.raises(ValidationError):
        range_capacity(ranges=[{"facilityId": "FAC:X"}], slots=[])


def test_scheduling_assigns_by_priority_and_reports_unscheduled_demand():
    report = optimise_schedule(
        demands=[
            {"demandId": "DEM:1", "priority": 9, "durationDays": 2},
            {"demandId": "DEM:2", "priority": 1, "durationDays": 1},
            {"demandId": "DEM:3", "priority": 5, "durationDays": 1, "requiredAccreditations": ["SECRET"]},
        ],
        ranges=RANGES,
    )
    assignments = {row["demandId"]: row for row in report["assignments"]}
    assert assignments["DEM:1"]["rangeId"] == "FAC:R1"
    assert assignments["DEM:3"]["rangeId"] == "FAC:R2"
    assert report["reproducible"] is True
    assert "DEM:2" in assignments


def test_scheduling_refuses_a_demand_no_range_can_satisfy():
    report = optimise_schedule(
        demands=[
            {"demandId": "DEM:X", "priority": 1, "durationDays": 1, "requiredAccreditations": ["TS_SCI"]}
        ],
        ranges=RANGES,
    )
    assert report["assignments"] == []
    assert report["unscheduled"][0]["demandId"] == "DEM:X"


def test_scheduling_with_a_baseline_reports_improvement():
    report = optimise_schedule(
        demands=[{"demandId": "DEM:1", "priority": 10, "durationDays": 1}],
        ranges=RANGES,
        baseline={"assignments": [{"demandId": "DEM:1", "completionDay": 20}]},
    )
    assert report["baselineObjective"] is not None
    assert report["improvementPct"] is not None


def _model(**overrides) -> dict:
    body = {
        "id": "MDL:1",
        "name": "aero model",
        "modelType": "AERODYNAMIC",
        "modelVersion": "3.0",
        "fidelity": {
            "overall": 0.9,
            "applicabilityEnvelope": {"mach": {"min": 4, "max": 12}},
        },
        "provenance": {"source": "wind tunnel"},
        "validationHistory": [{"campaignId": "TC:1", "fidelityDelta": 0.05}],
        "approvedForUse": True,
        "lastApprovedAt": "2026-01-01T00:00:00+00:00",
    }
    body.update(overrides)
    return body


def test_fidelity_registry_passes_a_complete_card_and_flags_an_aged_approval():
    report = fidelity_registry(models=[_model()], as_of="2026-02-01T00:00:00+00:00")
    assert report["summary"]["releaseGatePassed"] is True
    assert report["summary"]["modelCount"] == 1
    assert report["models"][0]["modelCard"]["complete"] is True
    assert report["summary"]["approvalQueueCount"] == 0


def test_an_incomplete_model_card_fails_the_release_gate():
    report = fidelity_registry(
        models=[_model(provenance=None, validationHistory=None)],
        as_of="2026-02-01T00:00:00+00:00",
    )
    assert report["summary"]["releaseGatePassed"] is False
    assert set(report["models"][0]["modelCard"]["missing"]) == {
        "provenance",
        "validationHistory",
    }


def test_a_drift_breach_withdraws_approval_and_names_dependents():
    report = fidelity_registry(
        models=[_model(drift={"metric": "rmse", "value": 0.12}, dependents=["ESC:1"])],
        as_of="2026-02-01T00:00:00+00:00",
    )
    assert report["summary"]["driftBreaches"] == 1
    assert report["summary"]["withdrawnApprovals"] == 1
    assert report["notifications"][0]["notify"] == ["ESC:1"]


def test_apply_drift_returns_the_document_to_write_back():
    report = apply_drift(_model(), drift_metric="rmse", drift_value=0.09)
    assert report["breach"] is True
    assert report["approvalWithdrawn"] is True
    assert report["model"]["approvedForUse"] is False
    assert report["model"]["drift"]["threshold"] == 0.05

"""Pillar H rules: verified surge, measured reconstitution, honest cost."""

from __future__ import annotations

import pytest
from ngsh_core.errors import ValidationError
from ngsh_core.industrial import (
    affordability_trace,
    estimate_quality,
    reconstitution_assessment,
    surge_readiness,
    unit_cost_curve,
)

FACILITY = {
    "id": "FAC:1",
    "surgeCapacity": {"unitsPerHour": 4, "shiftsPerDay": 2},
}


def test_surge_is_unverified_without_an_owner_and_a_twin_run():
    report = surge_readiness(
        facility=FACILITY,
        suppliers=[{"id": "SUP:1", "riskScore": 0.1, "leadTimeDays": 10}],
        demand_units=100,
        horizon_days=90,
    )
    assert report["verified"] is False
    assert report["confidenceInterval"]["high"] >= report["confidenceInterval"]["low"]
    assert any("twin run" in gap for gap in report["gaps"])
    assert any("owner" in gap for gap in report["gaps"])


def test_surge_is_verified_with_evidence_and_names_its_bottleneck():
    report = surge_readiness(
        facility=FACILITY,
        suppliers=[
            {"id": "SUP:1", "riskScore": 0.1, "leadTimeDays": 10},
            {"id": "SUP:2", "riskScore": 0.2, "leadTimeDays": 90},
        ],
        demand_units=100,
        horizon_days=120,
        twin_run_id="RUN:1",
        owner="usr:programme",
    )
    assert report["verified"] is True
    assert report["evidence"]["bottleneckSupplier"]["supplierId"] == "SUP:2"
    assert report["evidence"]["digest"]


def test_surge_rejects_a_confidence_level_it_cannot_report():
    with pytest.raises(ValidationError):
        surge_readiness(
            facility=FACILITY,
            suppliers=[],
            demand_units=10,
            confidence_level=0.87,
        )


def test_estimate_quality_flags_a_parametric_estimate_presented_as_actual():
    check = estimate_quality(
        {"estimateId": "CE:1", "amount": 10.0, "basis": "PARAMETRIC", "confidence": 0.6, "presentedAs": "ACTUAL"}
    )
    assert check["qualityOk"] is False
    assert any("basis_misrepresentation" in item for item in check["violations"])


def test_affordability_trace_attaches_cost_to_the_allocated_element():
    report = affordability_trace(
        requirement_ids=["REQ:1", "REQ:2"],
        satisfies_edges=[
            {"from": {"type": "Part", "id": "PART:1"}, "to": {"type": "Requirement", "id": "REQ:1"}},
        ],
        cost_estimates=[
            {"subjectId": "PART:1", "amount": 1200.0, "basis": "ACTUAL", "confidence": 0.95},
        ],
        quantity=10,
    )
    rows = {row["requirementId"]: row for row in report["requirements"]}
    assert rows["REQ:1"]["traced"] is True
    assert rows["REQ:1"]["amount"] == 1200.0
    assert rows["REQ:2"]["traced"] is False
    assert report["summary"]["untracedCount"] == 1
    assert report["summary"]["unitCostAtQuantity"] == 120.0


def test_unit_cost_curve_recovers_a_ninety_percent_learning_rate():
    curve = unit_cost_curve(
        points=[
            {"rate": 10, "unitCost": 100.0},
            {"rate": 20, "unitCost": 90.0},
            {"rate": 40, "unitCost": 81.0},
            {"rate": 80, "unitCost": 72.9},
        ],
        quantity=160,
    )
    assert curve["learningRate"] == pytest.approx(0.9, abs=0.01)
    assert curve["rSquared"] == pytest.approx(1.0, abs=1e-6)
    assert curve["error"] is None


def test_reconstitution_reports_no_measured_time_without_an_exercise():
    report = reconstitution_assessment(
        critical_node={"id": "PART:1"},
        candidates=[{"supplierId": "SUP:2", "leadTimeDays": 30, "riskScore": 0.2}],
        owner="usr:supply",
    )
    assert report["measured"] is False
    assert report["timeToReconstituteDays"] is None
    assert report["playbook"]["leadTimeSumDays"] == 30
    assert any("tabletop" in gap for gap in report["gaps"])


def test_reconstitution_reports_the_measured_exercise_time_and_escalation():
    report = reconstitution_assessment(
        critical_node={"id": "PART:1"},
        candidates=[{"supplierId": "SUP:2", "leadTimeDays": 30, "riskScore": 0.2}],
        exercise={
            "completedAt": "2026-01-05T00:00:00+00:00",
            "measuredTimeToReconstituteDays": 41.5,
            "conductedBy": "usr:range",
            "failureMode": "second source not qualified",
            "escalateTo": "usr:programme",
        },
        owner="usr:supply",
    )
    assert report["measured"] is True
    assert report["timeToReconstituteDays"] == 41.5
    assert report["escalation"]["escalateTo"] == "usr:programme"

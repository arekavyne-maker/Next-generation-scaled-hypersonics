"""Rules of the supply pillar: C-007 exposure, surge and reconstitution."""

from __future__ import annotations

import pytest
from ngsh_core.errors import ValidationError
from ngsh_core.supply import reconstitution_playbook, single_source_risks, surge_plan

CRITICAL_SINGLE_SOURCE = {
    "id": "PART:1",
    "partNumber": "P-1",
    "criticality": "CRITICAL",
    "isSingleSource": True,
}


def test_c007_flags_a_critical_single_source_part_with_no_path():
    findings = single_source_risks([CRITICAL_SINGLE_SOURCE], reconstitutes_targets=set())
    assert len(findings) == 1
    assert findings[0]["constraint"] == "C-007"
    assert findings[0]["severity"] == "WARNING"


def test_c007_is_satisfied_by_a_reconstitutes_path():
    findings = single_source_risks([CRITICAL_SINGLE_SOURCE], reconstitutes_targets={"PART:1"})
    assert findings == []


def test_c007_does_not_flag_a_part_that_is_not_critical():
    part = dict(CRITICAL_SINGLE_SOURCE, criticality="ROUTINE")
    assert single_source_risks([part], reconstitutes_targets=set()) == []


def test_c007_does_not_flag_a_multi_sourced_part():
    part = dict(CRITICAL_SINGLE_SOURCE, isSingleSource=False)
    assert single_source_risks([part], reconstitutes_targets=set()) == []


def _facility() -> dict:
    return {"id": "FAC:1", "surgeCapacity": {"unitsPerHour": 4, "shiftsPerDay": 2}}


def test_surge_names_the_longest_lead_time_as_the_bottleneck():
    report = surge_plan(
        facility=_facility(),
        suppliers=[
            {"id": "SUP:1", "riskScore": 0.2, "leadTimeDays": 30},
            {"id": "SUP:2", "riskScore": 0.1, "leadTimeDays": 90},
        ],
        demand_units=100,
        horizon_days=120,
    )
    assert report["bottleneckSupplier"]["supplierId"] == "SUP:2"
    assert report["criticalDelayDays"] == 90
    assert report["supplierCount"] == 2


def test_surge_reduces_capacity_by_supplier_risk():
    low_risk = surge_plan(
        facility=_facility(),
        suppliers=[{"id": "SUP:1", "riskScore": 0.0, "leadTimeDays": 0}],
        demand_units=100,
        horizon_days=90,
    )
    high_risk = surge_plan(
        facility=_facility(),
        suppliers=[{"id": "SUP:1", "riskScore": 1.0, "leadTimeDays": 0}],
        demand_units=100,
        horizon_days=90,
    )
    assert high_risk["riskFactor"] < low_risk["riskFactor"]
    assert high_risk["achievableUnits"] < low_risk["achievableUnits"]


def test_surge_rejects_a_non_positive_demand():
    with pytest.raises(ValidationError):
        surge_plan(facility=_facility(), suppliers=[], demand_units=0)


def test_surge_requires_a_declared_capacity():
    with pytest.raises(ValidationError):
        surge_plan(facility={"id": "FAC:1"}, suppliers=[], demand_units=10)


def test_reconstitution_ranks_by_lead_time_then_risk():
    report = reconstitution_playbook(
        CRITICAL_SINGLE_SOURCE,
        [
            {"supplierId": "SUP:slow", "leadTimeDays": 120, "riskScore": 0.1},
            {"supplierId": "SUP:fast", "leadTimeDays": 30, "riskScore": 0.4},
        ],
    )
    assert report["feasible"] is True
    assert report["steps"][0]["target"] == "SUP:fast"
    assert report["steps"][1]["cumulativeDays"] == 150
    assert report["coverageDays"] == 150


def test_reconstitution_without_alternatives_is_not_feasible():
    report = reconstitution_playbook(CRITICAL_SINGLE_SOURCE, [])
    assert report["feasible"] is False
    assert report["gaps"]

"""Pillar B domain logic: traveller, genealogy, process drift and rate.

The manufacturing pillar is assessed on whether a lot can be traced from
material to test result and whether drift is caught before a part is scrapped.
Both are properties of *rules*, not of screens, so they live here as pure
functions:

* a traveller is built from the process plan revision, not typed from scratch,
  and an operation cannot start before its predecessor is complete;
* genealogy is a chain, and a broken link is named rather than skipped;
* drift is a measured departure from the process's own history, and a flagged
  run is quarantined for a human rather than auto-dispositioned;
* the rate model is an explicit, inspectable surrogate - not a black box - so
  that a planner can see which constraint produced the number.
"""

from __future__ import annotations

import math
from statistics import mean, pstdev
from typing import Any

from .errors import ValidationError

DRIFT_SIGMA_LIMIT = 3.0
MIN_REFERENCE_RUNS = 3


def build_traveller(
    plan: dict[str, Any],
    runs: list[dict[str, Any]],
    *,
    operator_authorised: bool | None = None,
) -> dict[str, Any]:
    """Build a traveller from a ``ProcessPlan`` revision and its runs.

    ``plan`` is the entity's attribute block; ``runs`` are ``ProcessRun``
    attribute blocks already recorded against it. An operation is complete
    when a run for it has a disposition other than ``REWORK``; the next
    operation cannot start until every earlier one is complete.
    """
    operations = plan.get("operations")
    if not isinstance(operations, list) or not operations:
        raise ValidationError("a process plan must declare at least one operation")

    ordered = sorted(
        enumerate(operations),
        key=lambda pair: (pair[1].get("sequence", pair[0] + 1), pair[1].get("opId", pair[0])),
    )
    runs_by_operation: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        operations_ref = run.get("opId") or run.get("operationId") or run.get("operation")
        if operations_ref:
            runs_by_operation.setdefault(str(operations_ref), []).append(run)

    rows: list[dict[str, Any]] = []
    blocked = False
    next_operation: str | None = None
    nonconformances: list[dict[str, Any]] = []

    for index, operation in ordered:
        operation_id = str(operation.get("opId") or operation.get("operationId") or f"OP-{index + 1}")
        operation_runs = runs_by_operation.get(operation_id, [])
        dispositions = [str(run.get("disposition") or "PENDING").upper() for run in operation_runs]
        if any(disposition in {"REWORK", "SCRAP"} for disposition in dispositions):
            status = "NONCONFORMING"
        elif operation_runs and all(disposition in {"COMPLETE", "ACCEPTED"} for disposition in dispositions):
            status = "COMPLETE"
        elif operation_runs:
            status = "IN_PROGRESS"
        else:
            status = "BLOCKED" if blocked else "PENDING"
            blocked = True

        if next_operation is None and status != "COMPLETE":
            next_operation = operation_id
            blocked = True

        for run in operation_runs:
            if str(run.get("disposition") or "").upper() in {"REWORK", "SCRAP"}:
                nonconformances.append(
                    {
                        "operationId": operation_id,
                        "runId": run.get("runId"),
                        "disposition": str(run.get("disposition")).upper(),
                        "nonconformanceId": run.get("nonconformanceId"),
                    }
                )

        rows.append(
            {
                "operationId": operation_id,
                "sequence": operation.get("sequence", index + 1),
                "name": operation.get("name"),
                "requiredSkillIds": operation.get("requiredSkillIds") or [],
                "status": status,
                "runIds": [run.get("runId") for run in operation_runs if run.get("runId")],
                "operatorAuthorised": operator_authorised,
            }
        )

    return {
        "processPlanId": plan.get("id"),
        "planRevision": plan.get("revision"),
        "operations": rows,
        "nextOperation": next_operation,
        "complete": all(row["status"] == "COMPLETE" for row in rows),
        "nonconformances": nonconformances,
    }


def detect_drift(
    reference_runs: list[dict[str, Any]],
    candidate: dict[str, Any],
    *,
    sigma_limit: float = DRIFT_SIGMA_LIMIT,
    min_reference: int = MIN_REFERENCE_RUNS,
) -> dict[str, Any]:
    """Compare one run's measured parameters with the process history.

    Parameters are compared one at a time, using the reference mean and
    standard deviation. A parameter with no variation in the reference is
    only flagged when the candidate differs from it at all, which is reported
    as ``baseline_deviation`` because a z-score is undefined there.
    """
    parameters = candidate.get("measuredParameters")
    if not isinstance(parameters, dict) or not parameters:
        raise ValidationError("a candidate run must carry measuredParameters")

    history: dict[str, list[float]] = {}
    for run in reference_runs:
        for name, value in (run.get("measuredParameters") or {}).items():
            if isinstance(value, int | float) and not isinstance(value, bool):
                history.setdefault(name, []).append(float(value))

    drivers: list[dict[str, Any]] = []
    for name, value in sorted(parameters.items()):
        if not isinstance(value, int | float) or isinstance(value, bool):
            continue
        samples = history.get(name, [])
        if len(samples) < min_reference:
            continue
        reference_mean = mean(samples)
        reference_sigma = pstdev(samples)
        if reference_sigma == 0:
            if float(value) != reference_mean:
                drivers.append(
                    {
                        "parameter": name,
                        "reason": "baseline_deviation",
                        "value": float(value),
                        "referenceMean": reference_mean,
                    }
                )
            continue
        z_score = (float(value) - reference_mean) / reference_sigma
        if abs(z_score) > sigma_limit:
            drivers.append(
                {
                    "parameter": name,
                    "reason": "sigma_exceeded",
                    "value": float(value),
                    "referenceMean": round(reference_mean, 6),
                    "referenceSigma": round(reference_sigma, 6),
                    "zScore": round(z_score, 3),
                }
            )

    comparable = [name for name in parameters if len(history.get(name, [])) >= min_reference]
    if not comparable:
        return {
            "status": "INSUFFICIENT_REFERENCE",
            "drivers": [],
            "quarantine": False,
            "reason": f"fewer than {min_reference} reference runs carry a comparable parameter",
        }
    return {
        "status": "DRIFT" if drivers else "OK",
        "drivers": drivers,
        "quarantine": bool(drivers),
        "sigmaLimit": sigma_limit,
        "referenceRuns": len(reference_runs),
    }


def assemble_genealogy(
    part_id: str,
    provenance: dict[str, Any] | None,
    *,
    known_runs: set[str],
    known_materials: set[str],
    known_parts: set[str],
) -> dict[str, Any]:
    """Return the chain of custody for a part, with every gap named.

    The chain comes from ``PartProvenance.chainOfCustody``. The function does
    not invent missing hops: a hop whose referenced run, lot or sub-part is
    absent is reported as a gap, because an unbroken chain with an invented
    link is worse than a broken chain that is visible.
    """
    if provenance is None:
        return {
            "partId": part_id,
            "complete": False,
            "hops": [],
            "gaps": ["no PartProvenance record exists for this part"],
        }

    chain = provenance.get("chainOfCustody") or []
    if not isinstance(chain, list):
        raise ValidationError("chainOfCustody must be a list")

    hops: list[dict[str, Any]] = []
    gaps: list[str] = []
    for index, hop in enumerate(chain):
        reference_type = str(hop.get("type") or hop.get("entityType") or "").upper()
        reference_id = str(hop.get("id") or hop.get("entityId") or "")
        exists = True
        if reference_type in {"PROCESSRUN", "PROCESS_RUN", "PR"}:
            exists = reference_id in known_runs
        elif reference_type in {"MATERIAL", "MAT"}:
            exists = reference_id in known_materials
        elif reference_type in {"PART"}:
            exists = reference_id in known_parts
        if not reference_id:
            gaps.append(f"hop {index} names no entity")
            exists = False
        elif not exists:
            gaps.append(f"{reference_type or 'unknown type'} {reference_id} is referenced but not present")
        hops.append({"sequence": index + 1, "type": reference_type, "id": reference_id, "present": exists})

    return {
        "partId": part_id,
        "materialIds": provenance.get("materialIds") or [],
        "processRunIds": provenance.get("processRunIds") or [],
        "hops": hops,
        "complete": not gaps,
        "gaps": gaps,
    }


def simulate_rate(
    facility: dict[str, Any],
    *,
    units: int,
    horizon_days: int = 90,
    shifts: int | None = None,
    hours_per_shift: float = 8.0,
    efficiency: float = 0.85,
    setup_days: int = 1,
    unit_cost: float | None = None,
) -> dict[str, Any]:
    """A discrete rate model with an inspectable constraint.

    The model is deliberately small: capacity comes from the facility's
    declared ``surgeCapacity``, degraded by shift pattern and efficiency, and
    the answer names the binding constraint so a planner can argue with it.
    """
    if units <= 0:
        raise ValidationError("'units' must be positive")
    capacity = facility.get("surgeCapacity") or {}
    units_per_hour = capacity.get("unitsPerHour")
    if not isinstance(units_per_hour, int | float) or units_per_hour <= 0:
        raise ValidationError("the facility must declare surgeCapacity.unitsPerHour")

    shifts_per_day = shifts or int(capacity.get("shiftsPerDay") or 2)
    daily_capacity = float(units_per_hour) * hours_per_shift * shifts_per_day * efficiency
    usable_days = max(horizon_days - setup_days, 0)
    achievable = daily_capacity * usable_days
    days_required = math.ceil(units / daily_capacity) + setup_days if daily_capacity else None

    curve: list[dict[str, Any]] = []
    cumulative = 0.0
    for day in range(1, min(horizon_days, 180) + 1):
        if day > setup_days:
            cumulative = min(float(units), cumulative + daily_capacity)
        curve.append({"day": day, "cumulativeUnits": round(cumulative, 1)})

    constraints: list[dict[str, Any]] = []
    if achievable < units:
        constraints.append(
            {
                "constraint": "facility_capacity",
                "detail": f"{achievable:.0f} units achievable in {horizon_days} days at "
                f"{daily_capacity:.1f} units/day",
            }
        )

    return {
        "facilityId": facility.get("id"),
        "dailyCapacity": round(daily_capacity, 2),
        "horizonDays": horizon_days,
        "setupDays": setup_days,
        "requestedUnits": units,
        "achievableUnits": round(achievable, 1),
        "daysRequired": days_required,
        "meetsDemand": achievable >= units,
        "constraints": constraints,
        "rateCurve": curve,
        "costPerUnit": unit_cost,
        "totalCost": round(unit_cost * units, 2) if unit_cost is not None else None,
        "assumptions": {
            "hoursPerShift": hours_per_shift,
            "shiftsPerDay": shifts_per_day,
            "efficiency": efficiency,
        },
    }

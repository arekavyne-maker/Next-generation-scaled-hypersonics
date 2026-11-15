"""Pillar D domain logic: supply risk, surge and reconstitution.

The supply pillar's question is not "who supplies this part?" but "what
happens to the programme when this supplier stops?". The functions here make
that question explicit:

* C-007 becomes a computed program risk: a critical, single-source part with
  no reconstitution path is flagged, not silently tolerated;
* surge is computed from the declared capacity and the declared lead times,
  with the binding supplier named;
* a reconstitution playbook is an ordered set of actions with lead times and
  a coverage figure, not a paragraph of intent.
"""

from __future__ import annotations

from typing import Any

from .errors import ValidationError


def single_source_risks(
    parts: list[dict[str, Any]],
    *,
    reconstitutes_targets: set[str],
) -> list[dict[str, Any]]:
    """C-007: critical single-source parts without a reconstitution path.

    A part is at risk when it is ``CRITICAL`` and ``isSingleSource`` and no
    ``reconstitutes`` edge points at it. The finding is a WARNING, because the
    constraint is a program obligation, not a data error.
    """
    findings: list[dict[str, Any]] = []
    for part in parts:
        if str(part.get("criticality") or "").upper() != "CRITICAL":
            continue
        if part.get("isSingleSource") is not True:
            continue
        part_id = part.get("id")
        if part_id in reconstitutes_targets:
            continue
        findings.append(
            {
                "constraint": "C-007",
                "severity": "WARNING",
                "partId": part_id,
                "partNumber": part.get("partNumber"),
                "finding": "critical single-source part has no reconstitutes path and must be "
                "carried as a program risk",
            }
        )
    return findings


def surge_plan(
    *,
    facility: dict[str, Any],
    suppliers: list[dict[str, Any]],
    demand_units: int,
    horizon_days: int = 90,
) -> dict[str, Any]:
    """Achievable production rate under supply constraints.

    Capacity is the facility's declared surge capacity degraded by the
    supply base's risk, and delayed by the longest lead time in the chain.
    Naming the bottleneck is the point: a number without its constraint is
    not planable.
    """
    if demand_units <= 0:
        raise ValidationError("'demandUnits' must be positive")
    capacity = facility.get("surgeCapacity") or {}
    units_per_hour = capacity.get("unitsPerHour")
    if not isinstance(units_per_hour, int | float) or units_per_hour <= 0:
        raise ValidationError("the facility must declare surgeCapacity.unitsPerHour")

    shifts = int(capacity.get("shiftsPerDay") or 2)
    daily_capacity = float(units_per_hour) * 8.0 * shifts * 0.85

    risks = [float(supplier.get("riskScore") or 0.0) for supplier in suppliers]
    average_risk = sum(risks) / len(risks) if risks else 0.0
    risk_factor = max(0.0, 1.0 - 0.5 * average_risk)

    lead_times = [int(supplier.get("leadTimeDays") or 0) for supplier in suppliers]
    critical_delay = max(lead_times) if lead_times else 0
    bottleneck = (
        max(suppliers, key=lambda s: (int(s.get("leadTimeDays") or 0), -float(s.get("riskScore") or 0)))
        if suppliers
        else None
    )

    usable_days = max(horizon_days - critical_delay, 0)
    achievable = daily_capacity * usable_days * risk_factor

    return {
        "facilityId": facility.get("id"),
        "demandUnits": demand_units,
        "horizonDays": horizon_days,
        "dailyCapacity": round(daily_capacity, 2),
        "riskFactor": round(risk_factor, 3),
        "criticalDelayDays": critical_delay,
        "achievableUnits": round(achievable, 1),
        "meetsDemand": achievable >= demand_units,
        "bottleneckSupplier": (
            {"supplierId": bottleneck.get("id"), "leadTimeDays": bottleneck.get("leadTimeDays")}
            if bottleneck
            else None
        ),
        "supplierCount": len(suppliers),
    }


def reconstitution_playbook(
    part: dict[str, Any],
    alternatives: list[dict[str, Any]],
) -> dict[str, Any]:
    """An ordered reconstitution plan for a critical single-source part.

    Alternatives are ranked by lead time and then by risk, because the fastest
    credible route is the one a programme will actually take under pressure.
    """
    part_id = part.get("id")
    if not alternatives:
        return {
            "partId": part_id,
            "feasible": False,
            "steps": [],
            "gaps": ["no alternative source, process or design route has been identified"],
        }

    ranked = sorted(
        alternatives,
        key=lambda item: (int(item.get("leadTimeDays") or 10**6), float(item.get("riskScore") or 1.0)),
    )
    steps = []
    cumulative_days = 0
    for index, alternative in enumerate(ranked, start=1):
        cumulative_days += int(alternative.get("leadTimeDays") or 0)
        steps.append(
            {
                "step": index,
                "action": alternative.get("action") or "qualify alternative source",
                "target": alternative.get("supplierId") or alternative.get("facilityId"),
                "leadTimeDays": int(alternative.get("leadTimeDays") or 0),
                "cumulativeDays": cumulative_days,
                "riskScore": alternative.get("riskScore"),
            }
        )

    return {
        "partId": part_id,
        "feasible": True,
        "steps": steps,
        "coverageDays": cumulative_days,
        "residualRisk": ranked[0].get("riskScore"),
    }

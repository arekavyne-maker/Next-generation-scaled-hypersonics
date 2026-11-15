"""Pillar H domain logic: surge readiness, reconstitution and affordability.

Pillar H answers the three questions a programme office asks continuously rather
than once per budget cycle:

* **H-1 surge readiness** - what rate can the industrial base actually reach,
  with a confidence interval, a named owner and a traceable twin run behind it;
* **H-2 reconstitution** - what is the measured time to restore a lost critical
  node, and who is escalated to when the playbook fails;
* **H-3 affordability** - which requirements trace through their design
  elements to a cost, what the unit cost is at a production rate, and whether a
  cost estimate is being presented as something it is not.

The rules are pure functions. Nothing here reads a clock, a random source or a
database, so the same evidence produces the same report on any machine and a
reviewer can recompute it by hand.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any

from .errors import ValidationError
from .supply import surge_plan

#: Version of the surge evidence digest. A change to how the digest is derived
#: is a contract change and must be visible in every report.
SURGE_EVIDENCE_VERSION = "1"

#: Two-sided normal quantiles for the confidence interval. A probability that
#: is not in this table is not silently approximated: the caller is refused.
NORMAL_QUANTILES = {
    0.80: 1.2816,
    0.90: 1.6449,
    0.95: 1.9600,
    0.99: 2.5758,
}

#: Cost bases that are estimates rather than measurements. Presenting one of
#: these as an actual is the specific misrepresentation H-3 exists to prevent.
ESTIMATE_BASES = {"QUOTE", "ANALOG", "PARAMETRIC", "LEARNED_CURVE"}
MEASURED_BASES = {"ACTUAL"}
COST_BASES = ESTIMATE_BASES | MEASURED_BASES


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _number(value: Any, *, field_name: str, minimum: float | None = None) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValidationError(f"{field_name} must be a number")
    if minimum is not None and value < minimum:
        raise ValidationError(f"{field_name} must be greater than or equal to {minimum}")
    return float(value)


# ---------------------------------------------------------------------------
# H-1: surge readiness
# ---------------------------------------------------------------------------


def surge_readiness(
    *,
    facility: dict[str, Any],
    suppliers: list[dict[str, Any]],
    demand_units: int,
    horizon_days: int = 90,
    confidence_level: float = 0.90,
    twin_run_id: str | None = None,
    owner: str | None = None,
) -> dict[str, Any]:
    """A verified surge figure, not a single optimistic number.

    The point estimate comes from the same capacity and lead-time model the
    supply pillar uses, so the two pillars cannot disagree about achievable
    output. What this function adds is the uncertainty: supplier risk is
    translated into a relative standard deviation and reported as a two-sided
    interval, because a surge rate quoted without its spread is a guess with a
    decimal point.

    ``verified`` is deliberately strict. A figure without a confidence
    interval, a named owner and the twin run that produced it is *reported*
    but not *verified*, and the gap is named rather than hidden.
    """
    if not isinstance(demand_units, int) or demand_units <= 0:
        raise ValidationError("'demandUnits' must be a positive integer")
    if not isinstance(horizon_days, int) or horizon_days <= 0:
        raise ValidationError("'horizonDays' must be a positive integer")
    if confidence_level not in NORMAL_QUANTILES:
        raise ValidationError(f"'confidenceLevel' must be one of {sorted(NORMAL_QUANTILES)}")

    base = surge_plan(
        facility=facility,
        suppliers=suppliers,
        demand_units=demand_units,
        horizon_days=horizon_days,
    )

    risks = [max(0.0, min(1.0, float(supplier.get("riskScore") or 0.0))) for supplier in suppliers]
    average_risk = sum(risks) / len(risks) if risks else 0.0
    usable_days = max(horizon_days - int(base["criticalDelayDays"]), 0)
    usable_fraction = usable_days / horizon_days

    # The spread is driven by supplier risk and shrinks as the supplier count
    # grows. It is a stated model, not a measured variance, and the report says
    # so in ``intervalMethod``.
    relative_sigma = (0.05 + 0.25 * average_risk) / math.sqrt(max(1, len(suppliers)))
    z = NORMAL_QUANTILES[confidence_level]
    half_width = z * base["achievableUnits"] * relative_sigma * math.sqrt(max(usable_fraction, 0.0))

    achievable = float(base["achievableUnits"])
    interval = {
        "level": confidence_level,
        "low": round(max(0.0, achievable - half_width), 1),
        "high": round(achievable + half_width, 1),
        "halfWidth": round(half_width, 1),
    }

    daily_rate = base["dailyCapacity"] * base["riskFactor"]
    evidence = {
        "idVersion": SURGE_EVIDENCE_VERSION,
        "facilityId": facility.get("id"),
        "supplierIds": sorted(str(supplier.get("id")) for supplier in suppliers),
        "demandUnits": demand_units,
        "horizonDays": horizon_days,
        "twinRunId": twin_run_id,
        "facilityCapacity": facility.get("surgeCapacity"),
    }
    evidence_digest = _digest(evidence)

    gaps: list[str] = []
    if not twin_run_id:
        gaps.append("the figure is not traceable to a twin run")
    if not owner:
        gaps.append("the figure has no named owner")
    if not suppliers:
        gaps.append("no supplier evidence was supplied, so the risk factor is an assumption")
    if not base["meetsDemand"]:
        gaps.append(f"achievable output {base['achievableUnits']:.1f} is below demand {demand_units}")

    return {
        "facilityId": facility.get("id"),
        "demandUnits": demand_units,
        "horizonDays": horizon_days,
        "surgeRatePerDay": round(daily_rate, 2),
        "achievableUnits": round(achievable, 1),
        "meetsDemand": base["meetsDemand"],
        "confidenceInterval": interval,
        "confidenceLevel": confidence_level,
        "intervalMethod": "supplier-risk-normal-approximation",
        "owner": owner,
        "status": ("READY" if base["meetsDemand"] else "SHORTFALL"),
        "verified": bool(twin_run_id and owner and suppliers),
        "evidence": {
            **evidence,
            "digest": evidence_digest,
            "bottleneckSupplier": base["bottleneckSupplier"],
            "riskFactor": base["riskFactor"],
            "criticalDelayDays": base["criticalDelayDays"],
        },
        "gaps": gaps,
    }


# ---------------------------------------------------------------------------
# H-3: affordability engineering
# ---------------------------------------------------------------------------


def estimate_quality(estimate: dict[str, Any]) -> dict[str, Any]:
    """Quality control for one cost estimate.

    Two things are checked: that the estimate carries its basis and confidence
    at all, and that the basis it is *presented* as matches the basis it was
    *derived* as. A parametric estimate shown as an actual is a misstatement of
    precision, and it is reported as a violation rather than a warning.
    """
    violations: list[str] = []
    basis = str(estimate.get("basis") or "").upper()
    presented = str(estimate.get("presentedAs") or basis).upper()
    confidence = estimate.get("confidence")
    amount = estimate.get("amount")

    if not basis:
        violations.append("missing_basis")
    elif basis not in COST_BASES:
        violations.append(f"unknown_basis:{basis}")
    if not isinstance(confidence, int | float) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
        violations.append("missing_or_invalid_confidence")
    if not isinstance(amount, int | float) or isinstance(amount, bool) or amount < 0:
        violations.append("missing_or_invalid_amount")
    if presented and basis and presented != basis:
        violations.append(f"basis_misrepresentation:{basis}_presented_as_{presented}")

    return {
        "estimateId": estimate.get("estimateId") or estimate.get("id"),
        "basis": basis or None,
        "presentedAs": presented or None,
        "confidence": confidence,
        "measured": basis in MEASURED_BASES,
        "qualityOk": not violations,
        "violations": violations,
    }


def affordability_trace(
    *,
    requirement_ids: list[str],
    satisfies_edges: list[dict[str, Any]],
    cost_estimates: list[dict[str, Any]],
    quantity: int | None = None,
) -> dict[str, Any]:
    """Trace requirements through allocated design elements to cost.

    The trace follows ``satisfies`` edges from a design element to a
    requirement, then attaches every cost estimate carried by that element.
    Requirements whose elements carry no estimate are reported as untraced;
    they are never filled in with an average, because an average is the one
    number that belongs to no requirement.
    """
    if not isinstance(requirement_ids, list) or not all(isinstance(item, str) for item in requirement_ids):
        raise ValidationError("'requirementIds' must be a list of requirement ids")
    if quantity is not None and (not isinstance(quantity, int) or quantity <= 0):
        raise ValidationError("'quantity' must be a positive integer")

    allocations: dict[str, set[tuple[str, str]]] = {}
    for edge in satisfies_edges:
        if edge.get("retractedAt"):
            continue
        target = edge.get("to") or {}
        source = edge.get("from") or {}
        if target.get("type") != "Requirement" or not target.get("id"):
            continue
        allocations.setdefault(str(target["id"]), set()).add(
            (str(source.get("type") or ""), str(source.get("id") or ""))
        )

    estimates_by_subject: dict[str, list[dict[str, Any]]] = {}
    quality: list[dict[str, Any]] = []
    for estimate in cost_estimates:
        subject_id = estimate.get("subjectId")
        if not isinstance(subject_id, str) or not subject_id:
            raise ValidationError("each cost estimate must name a 'subjectId'")
        estimates_by_subject.setdefault(subject_id, []).append(estimate)
        quality.append(estimate_quality(estimate))

    rows: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    for requirement_id in sorted(set(requirement_ids)):
        elements = sorted(allocations.get(requirement_id, set()))
        attached: list[dict[str, Any]] = []
        for element_type, element_id in elements:
            for estimate in estimates_by_subject.get(element_id, []):
                attached.append({**estimate, "subjectType": element_type, "subjectId": element_id})

        for estimate in attached:
            check = estimate_quality(estimate)
            if not check["qualityOk"]:
                violations.append({"requirementId": requirement_id, **check})

        amount = sum(
            float(estimate["amount"])
            for estimate in attached
            if isinstance(estimate.get("amount"), int | float)
        )
        confidences = [
            float(estimate["confidence"])
            for estimate in attached
            if isinstance(estimate.get("confidence"), int | float)
        ]
        rows.append(
            {
                "requirementId": requirement_id,
                "allocatedTo": [{"type": kind, "id": element_id} for kind, element_id in elements],
                "estimates": attached,
                "traced": bool(attached),
                "amount": round(amount, 2),
                "currency": (attached[0].get("currency") if attached else "USD"),
                "basis": sorted({str(item.get("basis")).upper() for item in attached if item.get("basis")}),
                "minimumConfidence": round(min(confidences), 4) if confidences else None,
            }
        )

    traced = [row for row in rows if row["traced"]]
    total = sum(row["amount"] for row in traced)
    return {
        "quantity": quantity,
        "requirements": rows,
        "summary": {
            "requirementCount": len(rows),
            "tracedCount": len(traced),
            "untracedCount": len(rows) - len(traced),
            "traceCoverage": round(len(traced) / len(rows), 4) if rows else 0.0,
            "tracedAmount": round(total, 2),
            "unitCostAtQuantity": round(total / quantity, 2) if quantity and total else None,
            "qualityViolationCount": len(violations),
            "missing": [row["requirementId"] for row in rows if not row["traced"]],
        },
        "qualityViolations": violations,
        "allEstimatesMeasured": bool(traced)
        and all(
            str(estimate.get("basis") or "").upper() in MEASURED_BASES
            for row in traced
            for estimate in row["estimates"]
        ),
    }


def unit_cost_curve(
    *,
    points: list[dict[str, Any]],
    quantity: int,
    actual_unit_cost: float | None = None,
) -> dict[str, Any]:
    """Fit a log-log learning curve and predict unit cost at a rate.

    A learning curve is the honest model for unit cost against rate: doubling
    the quantity reduces unit cost by a roughly constant percentage. The fit is
    ordinary least squares on ``log(unitCost)`` against ``log(rate)``, so it is
    reproducible and its inputs are inspectable.

    The prediction error is reported only when an actual is supplied. When it
    is not, the error is ``None`` rather than zero - an unmeasured error is not
    a perfect one.
    """
    if not isinstance(quantity, int) or quantity <= 0:
        raise ValidationError("'quantity' must be a positive integer")
    samples: list[tuple[float, float]] = []
    for point in points:
        rate = point.get("rate")
        cost = point.get("unitCost")
        if not isinstance(rate, int | float) or isinstance(rate, bool) or rate <= 0:
            raise ValidationError("each rate-curve point must carry a positive 'rate'")
        if not isinstance(cost, int | float) or isinstance(cost, bool) or cost <= 0:
            raise ValidationError("each rate-curve point must carry a positive 'unitCost'")
        samples.append((float(rate), float(cost)))

    if len(samples) < 2:
        raise ValidationError("at least two rate-curve points are required to fit a curve")

    xs = [math.log(rate) for rate, _ in samples]
    ys = [math.log(cost) for _, cost in samples]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / denominator
    intercept = mean_y - slope * mean_x
    predicted = math.exp(intercept + slope * math.log(quantity))

    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys, strict=True)]
    ss_res = sum(residual**2 for residual in residuals)
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot else 1.0

    error = None
    error_pct = None
    if actual_unit_cost is not None:
        error = predicted - float(actual_unit_cost)
        error_pct = (error / float(actual_unit_cost)) * 100 if actual_unit_cost else None

    return {
        "quantity": quantity,
        "predictedUnitCost": round(predicted, 2),
        "slope": round(slope, 6),
        "learningRate": round(2**slope, 4),
        "intercept": round(intercept, 6),
        "rSquared": round(r_squared, 6),
        "pointCount": len(samples),
        "actualUnitCost": actual_unit_cost,
        "error": round(error, 2) if error is not None else None,
        "errorPct": round(error_pct, 3) if error_pct is not None else None,
        "fittedFrom": [{"rate": rate, "unitCost": cost} for rate, cost in samples],
    }


# ---------------------------------------------------------------------------
# H-2: reconstitution planning
# ---------------------------------------------------------------------------


def reconstitution_assessment(
    *,
    critical_node: dict[str, Any],
    candidates: list[dict[str, Any]],
    exercise: dict[str, Any] | None = None,
    owner: str | None = None,
) -> dict[str, Any]:
    """A reconstitution playbook with a *measured* time, not an estimate.

    The playbook ranks candidates by lead time and then risk, exactly as the
    supply pillar does, and names the dependencies each candidate carries. The
    time-to-reconstitute is taken only from a completed tabletop exercise; when
    no exercise exists the metric is ``None`` and the gap is named. Reporting a
    lead-time sum as a measured time would be the precise substitution this
    capability is meant to prevent.
    """
    node_id = critical_node.get("id")
    if not isinstance(node_id, str) or not node_id:
        raise ValidationError("'criticalNode' must carry an id")

    ranked = sorted(
        candidates,
        key=lambda item: (
            int(item.get("leadTimeDays") if item.get("leadTimeDays") is not None else 10**6),
            float(item.get("riskScore") if item.get("riskScore") is not None else 1.0),
        ),
    )
    steps: list[dict[str, Any]] = []
    cumulative = 0
    for index, candidate in enumerate(ranked, start=1):
        lead = int(candidate.get("leadTimeDays") or 0)
        cumulative += lead
        steps.append(
            {
                "step": index,
                "action": candidate.get("action") or "qualify alternative source",
                "target": candidate.get("supplierId") or candidate.get("facilityId"),
                "leadTimeDays": lead,
                "cumulativeDays": cumulative,
                "dependencies": sorted(str(item) for item in candidate.get("dependencies") or []),
                "riskScore": candidate.get("riskScore"),
            }
        )

    measured_days: float | None = None
    measured = False
    if exercise:
        measured_at = exercise.get("completedAt")
        value = exercise.get("measuredTimeToReconstituteDays")
        if measured_at and isinstance(value, int | float) and not isinstance(value, bool) and value >= 0:
            measured = True
            measured_days = float(value)

    gaps: list[str] = []
    if not candidates:
        gaps.append("no alternative source, process or design route has been identified")
    if not measured:
        gaps.append(
            "no completed tabletop exercise supplies a measured time-to-reconstitute; "
            "the lead-time sum is an estimate and is not reported as the metric"
        )
    if not owner:
        gaps.append("the playbook has no named owner")

    escalation = None
    if exercise and exercise.get("failureMode"):
        escalation = {
            "failureMode": exercise["failureMode"],
            "reason": "the tabletop exercise reproduced the playbook's failure mode",
            "escalateTo": exercise.get("escalateTo") or owner or "programme office",
            "raisedAt": exercise.get("completedAt"),
            "severity": "HIGH",
        }

    return {
        "criticalNode": {"id": node_id, "type": critical_node.get("type") or "Part"},
        "playbook": {
            "steps": steps,
            "leadTimeSumDays": cumulative,
            "residualRisk": ranked[0].get("riskScore") if ranked else None,
            "candidateCount": len(ranked),
            "dependencies": sorted(
                {str(item) for candidate in ranked for item in candidate.get("dependencies") or []}
            ),
        },
        "timeToReconstituteDays": measured_days,
        "measured": measured,
        "measuredBy": exercise.get("conductedBy") if measured else None,
        "measuredAt": exercise.get("completedAt") if measured else None,
        "owner": owner,
        "escalation": escalation,
        "feasible": bool(ranked),
        "gaps": gaps,
    }

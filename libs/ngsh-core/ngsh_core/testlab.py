"""Pillar C domain logic: test integrity, anomaly surfacing and the twin loop.

The properties Pillar C is assessed on are all about refusing to accept a
number without its context:

* a ``TestResult`` without a configuration snapshot is rejected at write
  (Increment 2, I2-2), because a result that cannot name its build is not
  evidence of anything;
* an anomaly is surfaced against the result's own limits and, when history is
  available, against the campaign's variation - and it is surfaced, not acted
  on: disposition stays with a human;
* model validation is produced *from* the test result, so the twin loop has a
  causation chain rather than a manual reconciliation;
* a range slot is booked only when it does not overlap another booking.
"""

from __future__ import annotations

from datetime import UTC, datetime
from statistics import mean, pstdev
from typing import Any

from .classification import parse_level
from .errors import ValidationError

REQUIRED_CONFIGURATION_KEYS = ("variantId", "baselineId")
ANOMALY_SIGMA_LIMIT = 3.0


def _as_datetime(value: Any, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValidationError(f"{field_name} is not an ISO-8601 timestamp: {value!r}") from exc
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    raise ValidationError(f"{field_name} is required and must be an ISO-8601 timestamp")


def validate_result(result: dict[str, Any]) -> list[str]:
    """The write-time gate for a test result.

    Returns the list of reasons the result may not be admitted. An empty list
    means it carries enough configuration context to be evidence.
    """
    errors: list[str] = []
    if not isinstance(result.get("testMethod"), str) or not result["testMethod"]:
        errors.append("testMethod is required")
    if result.get("outcome") not in {"PASS", "FAIL", "MARGINAL", "INCONCLUSIVE", "NOT_RUN"}:
        errors.append("outcome must be one of PASS, FAIL, MARGINAL, INCONCLUSIVE, NOT_RUN")

    snapshot = result.get("configurationSnapshot")
    if not isinstance(snapshot, dict) or not snapshot:
        errors.append(
            "configurationSnapshot is required: a result without its build configuration is not evidence"
        )
    else:
        missing = [key for key in REQUIRED_CONFIGURATION_KEYS if not snapshot.get(key)]
        if missing:
            errors.append("configurationSnapshot is missing " + ", ".join(missing))
        if not snapshot.get("baselineId") and not snapshot.get("softwareBuild"):
            errors.append("configurationSnapshot must name a baselineId or a softwareBuild")
    return errors


def surface_anomalies(
    result: dict[str, Any],
    *,
    reference_results: list[dict[str, Any]] | None = None,
    sigma_limit: float = ANOMALY_SIGMA_LIMIT,
) -> dict[str, Any]:
    """Surface limit breaches and departures from the campaign's own history."""
    anomalies: list[dict[str, Any]] = []
    limits = result.get("limits") or {}

    for measurement in result.get("measurements") or []:
        name = measurement.get("name")
        value = measurement.get("value")
        if not isinstance(value, int | float) or isinstance(value, bool):
            continue

        rule = limits.get(name) if isinstance(limits, dict) else None
        if isinstance(rule, dict):
            minimum = rule.get("min")
            maximum = rule.get("max")
            if isinstance(minimum, int | float) and value < minimum:
                anomalies.append(
                    {"measurement": name, "kind": "below_limit", "value": value, "limit": minimum}
                )
            if isinstance(maximum, int | float) and value > maximum:
                anomalies.append(
                    {"measurement": name, "kind": "above_limit", "value": value, "limit": maximum}
                )
            if measurement.get("unit") is None:
                anomalies.append({"measurement": name, "kind": "missing_unit", "value": value})

    history: dict[str, list[float]] = {}
    for reference in reference_results or []:
        for measurement in reference.get("measurements") or []:
            name = measurement.get("name")
            value = measurement.get("value")
            if isinstance(name, str) and isinstance(value, int | float) and not isinstance(value, bool):
                history.setdefault(name, []).append(float(value))

    for measurement in result.get("measurements") or []:
        name = measurement.get("name")
        value = measurement.get("value")
        samples = history.get(name or "", [])
        if not isinstance(value, int | float) or len(samples) < 3:
            continue
        sigma = pstdev(samples)
        if sigma == 0:
            continue
        z_score = (float(value) - mean(samples)) / sigma
        if abs(z_score) > sigma_limit:
            anomalies.append(
                {
                    "measurement": name,
                    "kind": "trend_departure",
                    "value": float(value),
                    "campaignMean": round(mean(samples), 6),
                    "zScore": round(z_score, 3),
                }
            )

    return {
        "testResultId": result.get("id"),
        "anomalies": anomalies,
        "hasAnomalies": bool(anomalies),
        "sigmaLimit": sigma_limit,
    }


def curate_campaign(campaign: dict[str, Any], results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarise a campaign into a dataset that can be reused."""
    counts = {outcome: 0 for outcome in ("PASS", "FAIL", "MARGINAL", "INCONCLUSIVE", "NOT_RUN")}
    datasets: list[str] = []
    anomalies = 0
    for result in results:
        outcome = result.get("outcome")
        if outcome in counts:
            counts[outcome] += 1
        datasets.extend(result.get("dataSetUris") or [])
        anomalies += len(result.get("anomalyFlags") or [])

    total = sum(counts.values())
    return {
        "campaignId": campaign.get("id") or campaign.get("campaignId"),
        "results": total,
        "outcomes": counts,
        "passRate": round(counts["PASS"] / total, 4) if total else None,
        "datasetUris": sorted(set(datasets)),
        "anomalyCount": anomalies,
        "configurationSnapshots": sum(
            1 for result in results if isinstance(result.get("configurationSnapshot"), dict)
        ),
        "curated": total > 0
        and all(
            isinstance(result.get("configurationSnapshot"), dict) and result["configurationSnapshot"]
            for result in results
        ),
    }


def twin_validation(
    result: dict[str, Any],
    model: dict[str, Any],
    *,
    prior_fidelity: float | None = None,
) -> dict[str, Any]:
    """Produce the ``model.validated`` fact from a test result.

    C-004 is enforced here as well as at use: a model that is not approved
    for use, or that has no fidelity score, cannot be validated by evidence.
    """
    if model.get("approvedForUse") is not True:
        raise ValidationError("C-004: the model is not approved for use and cannot be validated")
    fidelity = model.get("fidelity") or {}
    # The contract's FidelityScore names its headline figure ``overall``;
    # ``components`` carries the per-dimension detail.
    base = prior_fidelity if prior_fidelity is not None else fidelity.get("overall")
    if not isinstance(base, int | float):
        raise ValidationError("C-004: the model has no fidelity score to update")

    outcome = result.get("outcome")
    delta = {"PASS": 0.02, "MARGINAL": -0.02, "FAIL": -0.10, "INCONCLUSIVE": 0.0, "NOT_RUN": 0.0}.get(
        str(outcome), 0.0
    )
    updated = min(1.0, max(0.0, float(base) + delta))
    return {
        "modelId": model.get("id"),
        "modelVersion": model.get("modelVersion"),
        "validatedByTestResultId": result.get("id"),
        "evidenceTestResultIds": [result.get("id")],
        "outcome": outcome,
        "priorFidelity": float(base),
        "fidelity": round(updated, 4),
        "fidelityDelta": round(updated - float(base), 4),
        "applicabilityEnvelope": fidelity.get("applicabilityEnvelope"),
    }


def find_slot_conflicts(
    candidate: dict[str, Any],
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Overlapping bookings for the same facility."""
    start = _as_datetime(candidate.get("start"), field_name="start")
    end = _as_datetime(candidate.get("end"), field_name="end")
    if end <= start:
        raise ValidationError("a range slot must end after it starts")

    conflicts: list[dict[str, Any]] = []
    for slot in existing:
        if slot.get("facilityId") != candidate.get("facilityId"):
            continue
        if str(slot.get("status") or "").upper() in {"CANCELLED", "RELEASED", "USED"}:
            continue
        other_start = _as_datetime(slot.get("start"), field_name="start")
        other_end = _as_datetime(slot.get("end"), field_name="end")
        if start < other_end and other_start < end:
            conflicts.append(
                {
                    "slotId": slot.get("id") or slot.get("slotId"),
                    "start": other_start.isoformat(),
                    "end": other_end.isoformat(),
                    "campaignId": slot.get("campaignId"),
                }
            )
    return conflicts


# ---------------------------------------------------------------------------
# G-2: campaign digital twin and range scheduling
# ---------------------------------------------------------------------------

_ACTIVE_SLOT_STATES = {"CONFIRMED", "PLANNED", "BOOKED", "IN_PROGRESS"}


def _slot_is_active(slot: dict[str, Any]) -> bool:
    return str(slot.get("status") or "CONFIRMED").upper() in _ACTIVE_SLOT_STATES


def range_capacity(
    *,
    ranges: list[dict[str, Any]],
    slots: list[dict[str, Any]],
    required_telemetry_coverage: float = 0.90,
) -> dict[str, Any]:
    """Model capacity, coverage and conflicts across the range enterprise.

    Each range reports its declared period capacity, its committed slots, its
    utilisation, its telemetry coverage and its instrumentation and target
    availability. A range is feasible only when it has capacity left, no
    overlapping bookings and enough telemetry coverage for the campaign.

    Two ranges are not assumed: the report states how many it actually modelled
    so that a single-range deployment is visible rather than implied.
    """
    if not isinstance(ranges, list) or not ranges:
        raise ValidationError("at least one range is required")
    if not 0 <= required_telemetry_coverage <= 1:
        raise ValidationError("'requiredTelemetryCoverage' must be between 0 and 1")

    entries: list[dict[str, Any]] = []
    total_capacity = 0
    total_booked = 0
    for row in ranges:
        range_id = row.get("facilityId") or row.get("id")
        if not isinstance(range_id, str) or not range_id:
            raise ValidationError("every range must carry an id")
        capacity = row.get("capacityPerPeriod")
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
            raise ValidationError(f"range {range_id} must declare a positive capacityPerPeriod")

        range_slots = [
            slot for slot in slots if (slot.get("facilityId") == range_id) and _slot_is_active(slot)
        ]
        conflicts: list[dict[str, Any]] = []
        for index, slot in enumerate(range_slots):
            other = range_slots[:index] + range_slots[index + 1 :]
            for conflict in find_slot_conflicts(slot, other):
                marker = (slot.get("id") or slot.get("slotId"), conflict.get("slotId"))
                if marker not in {(item["slotId"], item["conflictsWith"]) for item in conflicts}:
                    conflicts.append(
                        {
                            "slotId": marker[0],
                            "conflictsWith": conflict.get("slotId"),
                            "campaignId": slot.get("campaignId"),
                        }
                    )

        telemetry = row.get("telemetryCoverage")
        if isinstance(telemetry, dict):
            telemetry = telemetry.get("overall")
        if not isinstance(telemetry, int | float):
            values = [
                (slot.get("telemetryCoverage") or {}).get("overall")
                for slot in range_slots
                if isinstance(slot.get("telemetryCoverage"), dict)
            ]
            values = [float(value) for value in values if isinstance(value, int | float)]
            telemetry = sum(values) / len(values) if values else None

        booked = len(range_slots)
        total_capacity += capacity
        total_booked += booked
        utilisation = round(booked / capacity, 4)
        feasible = (
            utilisation <= 1.0
            and not conflicts
            and (not isinstance(telemetry, int | float) or telemetry >= required_telemetry_coverage)
        )
        findings: list[str] = []
        if utilisation > 1.0:
            findings.append(f"range {range_id} is over-committed at {utilisation:.2f} utilisation")
        if conflicts:
            findings.append(f"range {range_id} has {len(conflicts)} overlapping booking(s)")
        if isinstance(telemetry, int | float) and telemetry < required_telemetry_coverage:
            findings.append(
                f"range {range_id} telemetry coverage {telemetry:.2f} is below the "
                f"{required_telemetry_coverage:.2f} requirement"
            )

        entries.append(
            {
                "rangeId": range_id,
                "name": row.get("name") or range_id,
                "capacityPerPeriod": capacity,
                "booked": booked,
                "utilisation": utilisation,
                "remaining": max(capacity - booked, 0),
                "telemetryCoverage": telemetry,
                "instrumentation": sorted({str(item) for item in row.get("instrumentation") or []}),
                "targetsAvailable": row.get("targetsAvailable"),
                "accreditations": sorted(str(item) for item in row.get("accreditations") or []),
                "classificationCeiling": row.get("classificationCeiling"),
                "conflicts": conflicts,
                "findings": findings,
                "feasible": feasible,
            }
        )

    return {
        "ranges": entries,
        "rangeCount": len(entries),
        "multiRange": len(entries) >= 2,
        "requiredTelemetryCoverage": required_telemetry_coverage,
        "summary": {
            "totalCapacity": total_capacity,
            "totalBooked": total_booked,
            "utilisation": round(total_booked / total_capacity, 4) if total_capacity else None,
            "feasibleRanges": sum(1 for entry in entries if entry["feasible"]),
            "conflictCount": sum(len(entry["conflicts"]) for entry in entries),
        },
        "feasible": all(entry["feasible"] for entry in entries),
        "reproducible": True,
    }


def _eligible_range(demand: dict[str, Any], range_row: dict[str, Any]) -> tuple[bool, str | None]:
    ceiling = range_row.get("classificationCeiling")
    if ceiling and parse_level(demand.get("classification")) > parse_level(ceiling):
        return False, "classification exceeds the range accreditation"
    accreditations = {str(item) for item in range_row.get("accreditations") or []}
    required = {str(item) for item in demand.get("requiredAccreditations") or []}
    if required and not required.issubset(accreditations):
        missing = ", ".join(sorted(required - accreditations))
        return False, f"range lacks accreditation: {missing}"
    capabilities = {str(item) for item in range_row.get("capabilities") or []}
    required_capabilities = {str(item) for item in demand.get("requiredCapabilities") or []}
    if required_capabilities and not required_capabilities.issubset(capabilities):
        missing = ", ".join(sorted(required_capabilities - capabilities))
        return False, f"range lacks capability: {missing}"
    return True, None


def optimise_schedule(
    *,
    demands: list[dict[str, Any]],
    ranges: list[dict[str, Any]],
    baseline: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assign campaigns to ranges under capacity and accreditation constraints.

    The optimiser is a deterministic greedy assignment ordered by priority,
    then target date, then demand id. That is intentionally simple: a schedule
    a programme cannot explain is a schedule it will not trust. Every assignment
    and every refusal carries its reason, and the same inputs always produce the
    same schedule, so a scheduling decision is reproducible from its objective.
    """
    if not isinstance(demands, list):
        raise ValidationError("'demands' must be a list")
    if not isinstance(ranges, list) or not ranges:
        raise ValidationError("at least one range is required")

    range_state: dict[str, dict[str, Any]] = {}
    for row in ranges:
        range_id = row.get("facilityId") or row.get("id")
        if not isinstance(range_id, str) or not range_id:
            raise ValidationError("every range must carry an id")
        capacity = row.get("capacityPerPeriod")
        if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
            raise ValidationError(f"range {range_id} must declare a positive capacityPerPeriod")
        range_state[range_id] = {
            **row,
            "rangeId": range_id,
            "capacityPerPeriod": capacity,
            "used": int(row.get("booked") or 0),
            "nextDay": 1,
        }

    ordered = sorted(
        demands,
        key=lambda item: (
            -int(item.get("priority") or 0),
            str(item.get("targetDate") or "9999-12-31"),
            str(item.get("demandId") or item.get("id") or ""),
        ),
    )

    assignments: list[dict[str, Any]] = []
    infeasible: list[dict[str, Any]] = []
    for demand in ordered:
        demand_id = demand.get("demandId") or demand.get("id")
        if not demand_id:
            raise ValidationError("every demand must carry a demandId")
        duration = demand.get("durationDays", 1)
        if not isinstance(duration, int) or isinstance(duration, bool) or duration <= 0:
            raise ValidationError(f"demand {demand_id} must carry a positive durationDays")

        candidates: list[tuple[float, str]] = []
        refused: list[str] = []
        for range_id, row in sorted(range_state.items()):
            eligible, reason = _eligible_range(demand, row)
            if not eligible:
                refused.append(f"{range_id}: {reason}")
                continue
            if row["used"] >= row["capacityPerPeriod"]:
                refused.append(f"{range_id}: no capacity left in the period")
                continue
            utilisation = row["used"] / row["capacityPerPeriod"]
            candidates.append((utilisation, range_id))

        if not candidates:
            infeasible.append(
                {
                    "demandId": demand_id,
                    "reasons": refused or ["no eligible range"],
                }
            )
            continue

        _, chosen_id = min(candidates)
        chosen = range_state[chosen_id]
        completion_day = chosen["nextDay"] + duration - 1
        chosen["used"] += 1
        chosen["nextDay"] = completion_day + 1
        assignments.append(
            {
                "demandId": demand_id,
                "rangeId": chosen_id,
                "startDay": completion_day - duration + 1,
                "completionDay": completion_day,
                "durationDays": duration,
                "priority": int(demand.get("priority") or 0),
                "classification": demand.get("classification"),
            }
        )

    objective = round(
        sum(assignment["priority"] / (1 + assignment["completionDay"]) for assignment in assignments) * 100,
        4,
    )

    baseline_objective = _baseline_objective(baseline, ordered, assignments)
    improvement = None
    if baseline_objective:
        improvement = round((objective - baseline_objective) / baseline_objective * 100, 3)

    return {
        "assignments": assignments,
        "unscheduled": infeasible,
        "objective": objective,
        "baselineObjective": baseline_objective,
        "improvementPct": improvement,
        "constraintsRespected": not any(
            str(assignment.get("classification") or "") for assignment in assignments
        )
        or all(
            _eligible_range(
                {"classification": assignment.get("classification")},
                range_state[assignment["rangeId"]],
            )[0]
            for assignment in assignments
        ),
        "reproducible": True,
    }


def _baseline_objective(
    baseline: dict[str, Any] | None,
    demands: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
) -> float | None:
    """A comparable historical baseline objective.

    When a baseline schedule is supplied its objective is recomputed from the
    same formula as the optimiser's, so the improvement is a like-for-like
    comparison rather than two different measures.
    """
    if not baseline:
        return None
    if isinstance(baseline.get("objective"), int | float):
        return round(float(baseline["objective"]), 4)
    rows = baseline.get("assignments")
    if not isinstance(rows, list):
        return None
    priorities = {
        str(item.get("demandId") or item.get("id")): int(item.get("priority") or 0) for item in demands
    }
    total = 0.0
    for row in rows:
        demand_id = str(row.get("demandId"))
        completion = row.get("completionDay")
        if not isinstance(completion, int):
            continue
        total += priorities.get(demand_id, 0) / (1 + completion)
    if assignments and not rows:
        return None
    return round(total * 100, 4)


# ---------------------------------------------------------------------------
# G-4: fidelity registry and model governance
# ---------------------------------------------------------------------------

#: Fields a complete model card must carry (G-4 acceptance criterion 2).
MODEL_CARD_REQUIRED_FIELDS = ("provenance", "validationHistory", "applicabilityEnvelope")

#: Default drift suspend thresholds by model type. A type not listed uses the
#: ``default`` entry; an unlisted type with no default is not silently exempt.
DEFAULT_DRIFT_THRESHOLDS: dict[str, float] = {
    "AERODYNAMIC": 0.05,
    "THERMAL": 0.05,
    "PLASMA": 0.08,
    "STRUCTURAL": 0.05,
    "default": 0.05,
}


def fidelity_registry(
    *,
    models: list[dict[str, Any]],
    as_of: Any,
    approval_age_limit_days: int = 180,
    drift_thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """The model index with card completeness, approval ageing and drift.

    A model without provenance, validation history or an applicability envelope
    fails the release gate. An unapproved model is visible in an aged queue
    rather than absent from the report. A drift breach at or above the suspend
    threshold withdraws approval and names the dependents that must be told.
    """
    when = _as_datetime(as_of, field_name="asOf")
    if not isinstance(approval_age_limit_days, int) or approval_age_limit_days <= 0:
        raise ValidationError("'approvalAgeLimitDays' must be a positive integer")
    thresholds = {**DEFAULT_DRIFT_THRESHOLDS, **(drift_thresholds or {})}

    entries: list[dict[str, Any]] = []
    approval_queue: list[dict[str, Any]] = []
    notifications: list[dict[str, Any]] = []

    for model in models:
        model_id = model.get("id")
        if not model_id:
            raise ValidationError("every model must carry an id")
        model_type = str(model.get("modelType") or "UNKNOWN")
        fidelity = model.get("fidelity") or {}
        facts = {
            "provenance": model.get("provenance"),
            "validationHistory": model.get("validationHistory")
            or (model.get("annotations") or {}).get("validationHistory")
            or fidelity.get("evidenceRefs"),
            "applicabilityEnvelope": fidelity.get("applicabilityEnvelope")
            or model.get("applicabilityEnvelope"),
        }
        missing = [field for field in MODEL_CARD_REQUIRED_FIELDS if not facts[field]]
        approved = model.get("approvedForUse") is True

        approved_at = model.get("lastApprovedAt") or model.get("createdAt")
        age_days = None
        if approved_at:
            age_days = max(0, (when - _as_datetime(approved_at, field_name="lastApprovedAt")).days)

        drift = model.get("drift") or {}
        drift_value = drift.get("value")
        threshold = float(thresholds.get(model_type, thresholds.get("default", 0.05)))
        drift_breach = isinstance(drift_value, int | float) and float(drift_value) >= threshold
        effective_approval = approved and not drift_breach

        if not approved or age_days is None or (age_days > approval_age_limit_days):
            approval_queue.append(
                {
                    "modelId": model_id,
                    "modelType": model_type,
                    "approved": approved,
                    "ageDays": age_days,
                    "overdue": bool(age_days is None or age_days > approval_age_limit_days),
                    "state": (
                        "DRIFT_WITHDRAWN"
                        if drift_breach
                        else ("APPROVED" if effective_approval else "UNAPPROVED")
                    ),
                }
            )

        if drift_breach:
            notifications.append(
                {
                    "modelId": model_id,
                    "modelType": model_type,
                    "event": "approval_withdrawn",
                    "driftMetric": drift.get("metric"),
                    "driftValue": drift_value,
                    "threshold": threshold,
                    "notify": sorted(str(item) for item in model.get("dependents") or []),
                }
            )

        entries.append(
            {
                "modelId": model_id,
                "name": model.get("name"),
                "modelType": model_type,
                "modelVersion": model.get("modelVersion"),
                "fidelity": fidelity.get("overall"),
                "approvedForUse": approved,
                "effectiveApproval": effective_approval,
                "modelCard": {
                    "complete": not missing,
                    "missing": missing,
                    "required": list(MODEL_CARD_REQUIRED_FIELDS),
                },
                "approvalAgeDays": age_days,
                "drift": {
                    "metric": drift.get("metric"),
                    "value": drift_value,
                    "threshold": threshold,
                    "breach": drift_breach,
                },
            }
        )

    entries.sort(key=lambda item: str(item["modelId"]))
    return {
        "asOf": when.isoformat(),
        "models": entries,
        "approvalQueue": sorted(approval_queue, key=lambda item: str(item["modelId"])),
        "notifications": notifications,
        "thresholds": thresholds,
        "summary": {
            "modelCount": len(entries),
            "cardComplete": sum(1 for entry in entries if entry["modelCard"]["complete"]),
            "releaseGatePassed": all(entry["modelCard"]["complete"] for entry in entries),
            "approvalQueueCount": len(approval_queue),
            "overdueCount": sum(1 for item in approval_queue if item["overdue"]),
            "driftBreaches": sum(1 for entry in entries if entry["drift"]["breach"]),
            "withdrawnApprovals": sum(
                1 for entry in entries if entry["approvedForUse"] and not entry["effectiveApproval"]
            ),
        },
    }


def apply_drift(
    model: dict[str, Any],
    *,
    drift_metric: str,
    drift_value: float,
    drift_thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Apply a drift observation and decide whether approval is withdrawn.

    The returned model is the document to write back; this function does not
    write. Keeping the decision pure lets the service publish the withdrawal as
    an event, so the governance act is in the log rather than in a dashboard.
    """
    if not isinstance(drift_metric, str) or not drift_metric:
        raise ValidationError("'driftMetric' is required")
    if not isinstance(drift_value, int | float) or isinstance(drift_value, bool):
        raise ValidationError("'driftValue' must be a number")

    thresholds = {**DEFAULT_DRIFT_THRESHOLDS, **(drift_thresholds or {})}
    model_type = str(model.get("modelType") or "UNKNOWN")
    threshold = float(thresholds.get(model_type, thresholds.get("default", 0.05)))
    breach = float(drift_value) >= threshold
    updated = {
        **model,
        "drift": {
            "metric": drift_metric,
            "value": float(drift_value),
            "threshold": threshold,
            "breach": breach,
        },
    }
    if breach:
        updated["approvedForUse"] = False
    return {
        "model": updated,
        "breach": breach,
        "threshold": threshold,
        "approvalWithdrawn": breach and model.get("approvedForUse") is True,
        "dependents": sorted(str(item) for item in model.get("dependents") or []),
    }

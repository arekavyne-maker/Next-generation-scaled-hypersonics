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
                anomalies.append({"measurement": name, "kind": "below_limit", "value": value, "limit": minimum})
            if isinstance(maximum, int | float) and value > maximum:
                anomalies.append({"measurement": name, "kind": "above_limit", "value": value, "limit": maximum})
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
        "curated": total > 0 and all(
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

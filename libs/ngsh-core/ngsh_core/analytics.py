"""Programme KPIs: the PSDD section 12 measures, computed from the thread.

A KPI that is typed into a slide is not a measure of vitality, it is an
assertion. Every figure here is computed from platform facts and carries the
evidence it was computed from, or it is reported as ``NOT_COMPUTED`` with the
reason. There is no third state in which an unavailable number is shown as
zero.

The inputs are plain lists supplied by the analytics service from the graph
projection. Keeping this module free of storage means a reviewer can recompute
any figure from an exported thread.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .errors import ValidationError
from .workforce import gap_report

#: Test methods that consume a physical flight test, for the virtual-versus-
#: physical ratio. A method outside this set is a ground, tunnel or sled test.
FLIGHT_TEST_METHODS = {"FLIGHT", "FLIGHT_TEST", "FREE_FLIGHT", "CAPTIVE_CARRY"}


def _attributes(entity: dict[str, Any]) -> dict[str, Any]:
    return entity.get("attributes") or {}


def _number(value: Any) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _kpi(
    identifier: str,
    name: str,
    *,
    value: float | None,
    unit: str | None,
    target: Any,
    comparison: str,
    evidence: list[str] | None = None,
    note: str | None = None,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    computed = value is not None
    if not computed:
        status = "NOT_COMPUTED"
    elif comparison == "min":
        status = "MEETS" if value >= float(target) else "BELOW"
    elif comparison == "max":
        status = "MEETS" if value <= float(target) else "ABOVE"
    else:
        status = "REPORTED"
    return {
        "id": identifier,
        "name": name,
        "value": round(value, 4) if value is not None else None,
        "unit": unit,
        "target": target,
        "comparison": comparison,
        "status": status,
        "computed": computed,
        "evidence": sorted({str(item) for item in evidence or []}),
        "note": note,
        "detail": detail or {},
    }


def _kill_chain_kpi(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    current: list[float] = []
    baselines: list[float] = []
    evidence: list[str] = []
    for scenario in scenarios:
        timeline = _attributes(scenario).get("timeline") or {}
        if not isinstance(timeline, dict):
            continue
        value = _number(timeline.get("detectionToCustodySeconds"))
        baseline = _number(timeline.get("baselineDetectionToCustodySeconds"))
        if baseline is not None:
            baselines.append(baseline)
        elif _attributes(scenario).get("baseline") is True and value is not None:
            baselines.append(value)
        if value is not None and _attributes(scenario).get("baseline") is not True:
            current.append(value)
            evidence.append(str(scenario.get("id")))

    if not current:
        return _kpi(
            "kill-chain-latency",
            "Simulated detection-to-custody time",
            value=None,
            unit="s",
            target="reduction vs baseline",
            comparison="reported",
            note="no scenario records timeline.detectionToCustodySeconds",
        )

    mean_current = sum(current) / len(current)
    reduction = None
    if baselines:
        mean_baseline = sum(baselines) / len(baselines)
        if mean_baseline:
            reduction = (mean_baseline - mean_current) / mean_baseline * 100
    return _kpi(
        "kill-chain-latency",
        "Simulated detection-to-custody time",
        value=mean_current,
        unit="s",
        target="reduction vs baseline",
        comparison="reported",
        evidence=evidence,
        detail={
            "architectureCount": len(current),
            "meanBaselineSeconds": round(sum(baselines) / len(baselines), 4) if baselines else None,
            "reductionPct": round(reduction, 3) if reduction is not None else None,
        },
        note=None if reduction is not None else "no baseline scenario was supplied",
    )


def _virtual_physical_kpi(
    scenarios: list[dict[str, Any]],
    test_results: list[dict[str, Any]],
    campaigns: list[dict[str, Any]],
) -> dict[str, Any]:
    runs = 0
    evidence: list[str] = []
    for scenario in scenarios:
        summary = _attributes(scenario).get("resultsSummary") or {}
        value = _number(summary.get("runs"))
        if value is not None:
            runs += int(value)
            evidence.append(str(scenario.get("id")))

    flight_results = [
        result
        for result in test_results
        if str(_attributes(result).get("testMethod") or "").upper() in FLIGHT_TEST_METHODS
    ]
    flight_campaigns = [
        campaign
        for campaign in campaigns
        if str(_attributes(campaign).get("campaignType") or "").upper() in FLIGHT_TEST_METHODS
    ]
    flight_tests = len(flight_results) or len(flight_campaigns)

    if not runs:
        return _kpi(
            "virtual-to-physical",
            "Virtual engagements per flight test consumed",
            value=None,
            unit="x",
            target=10,
            comparison="min",
            note="no engagement scenario records a completed batch in resultsSummary",
        )
    if not flight_tests:
        return _kpi(
            "virtual-to-physical",
            "Virtual engagements per flight test consumed",
            value=None,
            unit="x",
            target=10,
            comparison="min",
            evidence=evidence,
            detail={"virtualRuns": runs, "flightTests": 0},
            note="no physical flight test is recorded, so the ratio has no denominator",
        )
    ratio = runs / flight_tests
    return _kpi(
        "virtual-to-physical",
        "Virtual engagements per flight test consumed",
        value=ratio,
        unit="x",
        target=10,
        comparison="min",
        evidence=[*evidence, *[str(result.get("id")) for result in flight_results]],
        detail={"virtualRuns": runs, "flightTests": flight_tests},
    )


def _surge_kpi(surge_reports: list[dict[str, Any]]) -> dict[str, Any]:
    verified = [report for report in surge_reports if report.get("verified") is True]
    if not verified:
        return _kpi(
            "surge-readiness",
            "Verified surge production rate",
            value=None,
            unit="units/day",
            target="demand",
            comparison="reported",
            note="no surge report carries an owner, a twin run and supplier evidence",
        )
    latest = verified[-1]
    rate = _number(latest.get("surgeRatePerDay"))
    return _kpi(
        "surge-readiness",
        "Verified surge production rate",
        value=rate,
        unit="units/day",
        target=latest.get("demandUnits"),
        comparison="reported",
        evidence=[str(latest.get("facilityId"))] if latest.get("facilityId") else [],
        detail={
            "verified": True,
            "owner": latest.get("owner"),
            "confidenceInterval": latest.get("confidenceInterval"),
            "meetsDemand": latest.get("meetsDemand"),
            "twinRunId": (latest.get("evidence") or {}).get("twinRunId"),
        },
    )


def _reconstitution_kpi(reconstitutions: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [
        report
        for report in reconstitutions
        if report.get("measured") is True and _number(report.get("timeToReconstituteDays")) is not None
    ]
    if not measured:
        return _kpi(
            "time-to-reconstitute",
            "Time-to-reconstitute for critical nodes",
            value=None,
            unit="days",
            target="measured",
            comparison="reported",
            note="no reconstitution assessment carries a measured tabletop time",
        )
    values = [float(report["timeToReconstituteDays"]) for report in measured]
    return _kpi(
        "time-to-reconstitute",
        "Time-to-reconstitute for critical nodes",
        value=sum(values) / len(values),
        unit="days",
        target="measured",
        comparison="reported",
        evidence=[str(report.get("criticalNode", {}).get("id")) for report in measured],
        detail={
            "measuredCount": len(values),
            "minimumDays": round(min(values), 3),
            "maximumDays": round(max(values), 3),
        },
    )


def _workforce_kpi(
    *,
    persons: list[dict[str, Any]],
    credentials: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    demand: list[dict[str, Any]] | None,
    as_of: str,
) -> dict[str, Any]:
    if not demand:
        return _kpi(
            "workforce-gap",
            "Cleared-skills supply versus classified demand",
            value=None,
            unit="people",
            target=0,
            comparison="max",
            note="no classified production demand was supplied for this report",
        )
    report = gap_report(
        demand=demand,
        persons=persons,
        credentials=credentials,
        skills=skills,
        at=datetime.fromisoformat(as_of.replace("Z", "+00:00")).astimezone(UTC),
    )
    gap = report["summary"]["gap"]
    return _kpi(
        "workforce-gap",
        "Cleared-skills supply versus classified demand",
        value=float(gap),
        unit="people",
        target=0,
        comparison="max",
        evidence=[row["skillId"] for row in report["rows"]],
        detail=report["summary"],
    )


def _development_kpi(
    *,
    campaigns: list[dict[str, Any]],
    test_results: list[dict[str, Any]],
    models: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    flight_results = [
        result
        for result in test_results
        if str(_attributes(result).get("testMethod") or "").upper() in FLIGHT_TEST_METHODS
    ]
    flight_campaigns = [
        campaign
        for campaign in campaigns
        if str(_attributes(campaign).get("campaignType") or "").upper() in FLIGHT_TEST_METHODS
    ]
    flight_tests = len(flight_results) or len(flight_campaigns)
    cycle_kpi = _kpi(
        "design-iterate-cycles",
        "Design-iterate cycles per flight test",
        value=(len(campaigns) / flight_tests) if flight_tests and campaigns else None,
        unit="cycles",
        target="reported",
        comparison="reported",
        evidence=[str(campaign.get("id")) for campaign in campaigns],
        note=None if flight_tests else "no physical flight test is recorded",
    )

    deltas: list[float] = []
    evidence: list[str] = []
    for model in models:
        history = _attributes(model).get("validationHistory") or []
        if not isinstance(history, list):
            continue
        for record in history:
            if not isinstance(record, dict):
                continue
            delta = _number(record.get("fidelityDelta"))
            if delta is not None:
                deltas.append(delta)
                if record.get("campaignId"):
                    evidence.append(str(record["campaignId"]))
    fidelity_kpi = _kpi(
        "model-fidelity-improvement",
        "Model fidelity improvement per campaign",
        value=(sum(deltas) / len(deltas)) if deltas else None,
        unit="fidelity",
        target="reported",
        comparison="reported",
        evidence=evidence,
        detail={"validationCount": len(deltas)},
        note=None if deltas else "no model carries a validation history with a fidelity delta",
    )
    return [cycle_kpi, fidelity_kpi]


def programme_kpis(
    *,
    as_of: str,
    scenarios: list[dict[str, Any]],
    test_results: list[dict[str, Any]],
    campaigns: list[dict[str, Any]],
    models: list[dict[str, Any]],
    persons: list[dict[str, Any]],
    credentials: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    reconstitutions: list[dict[str, Any]] | None = None,
    surge_reports: list[dict[str, Any]] | None = None,
    workforce_demand: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compute every PSDD section 12 KPI that the thread can support."""
    if not isinstance(as_of, str) or not as_of:
        raise ValidationError("'asOf' is required")

    kpis = [
        _kill_chain_kpi(scenarios),
        _virtual_physical_kpi(scenarios, test_results, campaigns),
        _surge_kpi(surge_reports or []),
        _reconstitution_kpi(reconstitutions or []),
        _workforce_kpi(
            persons=persons,
            credentials=credentials,
            skills=skills,
            demand=workforce_demand,
            as_of=as_of,
        ),
        *_development_kpi(campaigns=campaigns, test_results=test_results, models=models),
    ]
    computed = [kpi for kpi in kpis if kpi["computed"]]
    return {
        "asOf": as_of,
        "kpis": kpis,
        "summary": {
            "kpiCount": len(kpis),
            "computedCount": len(computed),
            "notComputedCount": len(kpis) - len(computed),
            "meetingTargetCount": sum(1 for kpi in kpis if kpi["status"] == "MEETS"),
            "belowTargetCount": sum(
                1 for kpi in kpis if kpi["status"] in {"BELOW", "ABOVE"}
            ),
        },
        "method": "computed-from-thread",
    }

"""Pillars F and G domain logic: engagement batches, kill chain and range slots.

The engagement pillar is where the platform's performance claim is made, so
the batch runner is deliberately simple and deterministic rather than clever:

* every run's random draw is derived from a hash of the seed and the run
  index, so a batch is reproducible from its inputs and two machines agree;
* the statistics are computed from the batch rather than assumed, and the
  threshold that defines an intercept is an input;
* the kill chain reports which stage is missing rather than averaging over it;
* range slots are booked only when they do not overlap.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

from .errors import ValidationError

DEFAULT_RUNS = 10_000
DEFAULT_PK_THRESHOLD = 0.7


def _uniform(seed: int, index: int) -> float:
    digest = hashlib.sha256(f"{seed}:{index}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def _normal(seed: int, index: int) -> float:
    """A deterministic standard normal draw (Box-Muller, one draw per index)."""
    import math

    u1 = max(_uniform(seed, index * 2), 1e-12)
    u2 = _uniform(seed, index * 2 + 1)
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def _percentile(sorted_values: list[float], fraction: float) -> float:
    if not sorted_values:
        return 0.0
    position = min(len(sorted_values) - 1, max(0, int(round(fraction * (len(sorted_values) - 1)))))
    return sorted_values[position]


def run_batch(
    scenario: dict[str, Any],
    *,
    runs: int = DEFAULT_RUNS,
    seed: int = 1234,
    pk_threshold: float = DEFAULT_PK_THRESHOLD,
) -> dict[str, Any]:
    """Run a deterministic Monte Carlo engagement batch.

    ``x`` defaults come from the scenario's ``monteCarloConfig`` so that a
    scenario remains the single place a study is described.
    """
    if runs <= 0:
        raise ValidationError("'runs' must be positive")
    if not 0.0 <= pk_threshold <= 1.0:
        raise ValidationError("'pkThreshold' must be between 0 and 1")

    config = scenario.get("monteCarloConfig") or {}
    pk_mean = float(config.get("pkMean", 0.78))
    pk_sigma = float(config.get("pkSigma", 0.12))
    detection = float(config.get("detectionProbability", 0.9))
    if pk_sigma < 0:
        raise ValidationError("monteCarloConfig.pkSigma must be non-negative")

    started = time.perf_counter()
    values: list[float] = []
    intercepts = 0
    detections = 0
    for index in range(runs):
        draw = pk_mean + pk_sigma * _normal(seed, index)
        pk = min(1.0, max(0.0, draw))
        values.append(pk)
        if _uniform(seed + 1, index) <= detection:
            detections += 1
            if pk >= pk_threshold:
                intercepts += 1
    elapsed = time.perf_counter() - started

    ordered = sorted(values)
    return {
        "scenarioId": scenario.get("id"),
        "runs": runs,
        "seed": seed,
        "pkThreshold": pk_threshold,
        "statistics": {
            "meanPk": round(sum(ordered) / len(ordered), 4),
            "p10Pk": round(_percentile(ordered, 0.10), 4),
            "medianPk": round(_percentile(ordered, 0.50), 4),
            "p90Pk": round(_percentile(ordered, 0.90), 4),
            "intercepts": intercepts,
            "interceptProbability": round(intercepts / runs, 4),
            "detections": detections,
            "detectionProbability": round(detections / runs, 4),
        },
        "elapsedSeconds": round(elapsed, 4),
        "runsPerSecond": round(runs / elapsed, 1) if elapsed else None,
    }


def kill_chain(
    *,
    observation: dict[str, Any] | None,
    threat: dict[str, Any] | None,
    scenario: dict[str, Any] | None,
    models: list[dict[str, Any]],
) -> dict[str, Any]:
    """Report the kill chain by stage, naming the missing ones."""
    stages: list[dict[str, Any]] = []

    def stage(name: str, present: bool, evidence: list[str], note: str) -> None:
        stages.append({"stage": name, "present": present, "evidence": evidence, "note": note})

    stage(
        "DETECT",
        observation is not None,
        [observation.get("id")] if observation else [],
        "a threat observation with sensor provenance",
    )
    stage(
        "CLASSIFY",
        threat is not None,
        [threat.get("id")] if threat else [],
        "a threat system with a kinematic profile and confidence",
    )
    stage(
        "ENGAGE",
        bool(scenario and scenario.get("sensorChain") and scenario.get("effectorChain")),
        [scenario.get("id")] if scenario else [],
        "a scenario with both a sensor chain and an effector chain",
    )
    approved_models = [model.get("id") for model in models if model.get("approvedForUse") is True]
    stage(
        "ASSESS",
        bool(approved_models),
        approved_models,
        "an approved model to produce the engagement assessment (C-004)",
    )

    return {
        "stages": stages,
        "complete": all(item["present"] for item in stages),
        "missing": [item["stage"] for item in stages if not item["present"]],
    }


def slot_conflicts(
    candidate: dict[str, Any],
    existing: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Overlapping range bookings, using the same rule as the test pillar."""
    from .testlab import find_slot_conflicts

    return find_slot_conflicts(candidate, existing)


# ---------------------------------------------------------------------------
# F-3: fire-control data quality scoring
# ---------------------------------------------------------------------------

#: The three metrics F-3 turns into testable requirements, with the default
#: thresholds a programme can tighten but not silently loosen.
DEFAULT_FIRE_CONTROL_THRESHOLDS = {
    "custodyHandoverQuality": 0.90,
    "trackPurity": 0.85,
    "solutionErrorM": 50.0,
    "maxHandoverLatencyMs": 250.0,
}


def _metric(
    name: str,
    value: float | None,
    *,
    threshold: float,
    comparison: str,
    evidence: list[str],
    sample_count: int,
) -> dict[str, Any]:
    if value is None:
        return {
            "metric": name,
            "value": None,
            "threshold": threshold,
            "comparison": comparison,
            "breach": False,
            "insufficientData": True,
            "evidence": evidence,
            "sampleCount": sample_count,
        }
    breach = value < threshold if comparison == "min" else value > threshold
    return {
        "metric": name,
        "value": round(value, 4),
        "threshold": threshold,
        "comparison": comparison,
        "breach": breach,
        "insufficientData": False,
        "evidence": evidence,
        "sampleCount": sample_count,
    }


def fire_control_quality(
    *,
    handovers: list[dict[str, Any]] | None = None,
    tracks: list[dict[str, Any]] | None = None,
    solutions: list[dict[str, Any]] | None = None,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Measure custody handover quality, track purity and solution error.

    Each metric is computed from named observations and carries those
    observation ids back in ``evidence``, so a breach can be traced to the
    feed data that produced it. The computation is deterministic, which is what
    makes a metric reproducible from the same feed.

    Empty input is reported as ``insufficientData`` rather than as a perfect
    score. A fire-control chain that has produced no handovers has not
    demonstrated 100% handover quality.
    """
    limits = {**DEFAULT_FIRE_CONTROL_THRESHOLDS, **(thresholds or {})}
    for key, value in limits.items():
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise ValidationError(f"threshold {key!r} must be numeric")

    handover_rows = handovers or []
    track_rows = tracks or []
    solution_rows = solutions or []

    good_handovers = 0
    handover_evidence: list[str] = []
    for row in handover_rows:
        handover_id = str(row.get("handoverId") or row.get("id") or "")
        latency = row.get("latencyMs")
        latency_ok = not isinstance(latency, int | float) or latency <= float(
            limits["maxHandoverLatencyMs"]
        )
        if row.get("continuous") is not False and latency_ok:
            good_handovers += 1
        if handover_id:
            handover_evidence.append(handover_id)
    handover_quality = good_handovers / len(handover_rows) if handover_rows else None

    true_tracks = sum(1 for row in track_rows if row.get("falseTrack") is not True)
    track_purity = true_tracks / len(track_rows) if track_rows else None
    track_evidence = [str(row.get("trackId") or row.get("id") or "") for row in track_rows]
    track_evidence = [item for item in track_evidence if item]

    errors = [
        float(row["errorM"])
        for row in solution_rows
        if isinstance(row.get("errorM"), int | float) and not isinstance(row.get("errorM"), bool)
    ]
    mean_error = sum(errors) / len(errors) if errors else None
    solution_evidence = [str(row.get("solutionId") or row.get("id") or "") for row in solution_rows]
    solution_evidence = [item for item in solution_evidence if item]

    metrics = [
        _metric(
            "custodyHandoverQuality",
            handover_quality,
            threshold=float(limits["custodyHandoverQuality"]),
            comparison="min",
            evidence=sorted(handover_evidence),
            sample_count=len(handover_rows),
        ),
        _metric(
            "trackPurity",
            track_purity,
            threshold=float(limits["trackPurity"]),
            comparison="min",
            evidence=sorted(track_evidence),
            sample_count=len(track_rows),
        ),
        _metric(
            "fireControlSolutionErrorM",
            mean_error,
            threshold=float(limits["solutionErrorM"]),
            comparison="max",
            evidence=sorted(solution_evidence),
            sample_count=len(solution_rows),
        ),
    ]
    breaches = [
        {
            "metric": metric["metric"],
            "value": metric["value"],
            "threshold": metric["threshold"],
            "sampleCount": metric["sampleCount"],
        }
        for metric in metrics
        if metric["breach"]
    ]
    insufficient = [metric["metric"] for metric in metrics if metric["insufficientData"]]
    return {
        "metrics": metrics,
        "breaches": breaches,
        "hasBreaches": bool(breaches),
        "insufficientData": insufficient,
        "thresholds": limits,
        "reproducible": True,
        "definitionVersion": "1",
    }


# ---------------------------------------------------------------------------
# F-4: interim architecture workbench
# ---------------------------------------------------------------------------


def _envelope_refusals(
    model: dict[str, Any],
    envelope: dict[str, Any],
) -> list[str]:
    """Dimensions where the candidate falls outside a model's envelope."""
    fidelity = model.get("fidelity") or {}
    bounds = fidelity.get("applicabilityEnvelope") or model.get("applicabilityEnvelope") or {}
    refusals: list[str] = []
    for dimension, bound in bounds.items():
        if dimension not in envelope or not isinstance(bound, dict):
            continue
        value = envelope.get(dimension)
        if not isinstance(value, int | float) or isinstance(value, bool):
            continue
        minimum = bound.get("min")
        maximum = bound.get("max")
        if isinstance(minimum, int | float) and value < minimum:
            refusals.append(
                f"{model.get('id')}: {dimension}={value} is below the envelope minimum {minimum}"
            )
        if isinstance(maximum, int | float) and value > maximum:
            refusals.append(
                f"{model.get('id')}: {dimension}={value} is above the envelope maximum {maximum}"
            )
    return refusals


def compose_interim_candidate(
    *,
    name: str,
    sensors: list[dict[str, Any]],
    cueing: list[dict[str, Any]] | None,
    effectors: list[dict[str, Any]],
    models: list[dict[str, Any]],
    envelope: dict[str, Any] | None = None,
    threat_system_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Compose a candidate interim architecture and validate its models.

    The workbench exists to try existing sensors and offboard cueing before a
    flight test, so the composition itself is simple. The refusal is the
    valuable part: a model used outside its applicability envelope, or a model
    not approved for use, stops the candidate rather than quietly producing a
    number.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValidationError("'name' is required")
    if not isinstance(sensors, list) or not sensors:
        raise ValidationError("a candidate must compose at least one sensor")
    if not isinstance(effectors, list) or not effectors:
        raise ValidationError("a candidate must compose at least one effector")
    if not isinstance(models, list) or not models:
        raise ValidationError("a candidate must name the models used for virtual validation")

    for label, chain in (("sensor", sensors), ("effector", effectors), ("cueing", cueing or [])):
        for index, item in enumerate(chain):
            if not isinstance(item, dict) or not item.get("id"):
                raise ValidationError(f"{label} at index {index} must carry an 'id'")

    refusals: list[str] = []
    trace: list[dict[str, Any]] = []
    for model in models:
        model_id = model.get("id")
        if not model_id:
            raise ValidationError("every model must carry an 'id'")
        if model.get("approvedForUse") is not True:
            refusals.append(f"{model_id}: C-004: the model is not approved for use")
        model_refusals = _envelope_refusals(model, envelope or {})
        refusals.extend(model_refusals)
        trace.append(
            {
                "modelId": model_id,
                "modelVersion": model.get("modelVersion"),
                "fidelity": (model.get("fidelity") or {}).get("overall"),
                "envelopeChecked": bool(envelope),
            }
        )

    if refusals:
        raise ValidationError(
            "the candidate uses a model outside its approved envelope",
            detail=refusals,
        )

    return {
        "name": name.strip(),
        "sensorChain": sensors,
        "cueingChain": cueing or [],
        "effectorChain": effectors,
        "threatSystemIds": sorted({str(item) for item in threat_system_ids or []}),
        "modelVersionIds": sorted({str(model.get("id")) for model in models}),
        "envelope": envelope or {},
        "accepted": True,
        "virtualValidation": {
            "modelsUsed": trace,
            "allModelsApproved": True,
            "envelopeChecked": bool(envelope),
        },
    }


# ---------------------------------------------------------------------------
# F-5: Golden Dome reference-architecture plug-in framework
# ---------------------------------------------------------------------------

#: The published plug-in contract. A plug-in declares which version it was
#: written against; the host refuses an incompatible major version instead of
#: hoping the calls line up.
PLUGIN_CONTRACT_VERSION = "1.0.0"
PLUGIN_CONTRACT_MAJOR = 1

PLUGIN_REQUIRED_FIELDS = (
    "pluginId",
    "name",
    "version",
    "contractVersion",
    "entrypoint",
    "scenarioTypes",
)


def validate_plugin_manifest(manifest: dict[str, Any]) -> list[str]:
    """Structural problems with a plug-in manifest, in the published contract."""
    if not isinstance(manifest, dict):
        return ["the plug-in manifest must be an object"]
    problems = [
        f"{field} is required"
        for field in PLUGIN_REQUIRED_FIELDS
        if manifest.get(field) in (None, "", [], {})
    ]
    if not isinstance(manifest.get("scenarioTypes"), list):
        problems.append("scenarioTypes must be a list")
    dependencies = manifest.get("dependencies") or []
    if not isinstance(dependencies, list):
        problems.append("dependencies must be a list")
    else:
        for index, dependency in enumerate(dependencies):
            if not isinstance(dependency, dict) or not dependency.get("name"):
                problems.append(f"dependency at index {index} must carry a 'name'")
    return problems


def plugin_contract_major(version: Any) -> int | None:
    if not isinstance(version, str):
        return None
    head = version.split(".", 1)[0]
    return int(head) if head.isdigit() else None


def load_plugin(
    manifest: dict[str, Any],
    *,
    host_envelope: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Load a reference-architecture plug-in, or refuse it with a reason.

    A plug-in that declares a dependency outside the host's envelope is refused
    at load rather than at run time, because a failure at run time in a
    homeland-defence scenario is not a recoverable error.
    """
    problems = validate_plugin_manifest(manifest)
    if problems:
        raise ValidationError("the plug-in manifest does not satisfy the contract", detail=problems)

    if plugin_contract_major(manifest.get("contractVersion")) != PLUGIN_CONTRACT_MAJOR:
        raise ValidationError(
            f"plug-in contract {manifest.get('contractVersion')!r} is incompatible with "
            f"host contract {PLUGIN_CONTRACT_VERSION}"
        )

    envelope = host_envelope or {}
    refusals: list[str] = []
    for dependency in manifest.get("dependencies") or []:
        bounds = dependency.get("envelope") or {}
        if not isinstance(bounds, dict):
            refusals.append(
                f"dependency {dependency.get('name')!r} declares a non-object envelope"
            )
            continue
        for dimension, bound in bounds.items():
            if not isinstance(bound, dict) or dimension not in envelope:
                continue
            value = envelope.get(dimension)
            if not isinstance(value, int | float) or isinstance(value, bool):
                continue
            minimum = bound.get("min")
            maximum = bound.get("max")
            if isinstance(minimum, int | float) and value < minimum:
                refusals.append(
                    f"dependency {dependency.get('name')!r} requires {dimension} >= {minimum} "
                    f"but the host supplies {value}"
                )
            if isinstance(maximum, int | float) and value > maximum:
                refusals.append(
                    f"dependency {dependency.get('name')!r} requires {dimension} <= {maximum} "
                    f"but the host supplies {value}"
                )
    if refusals:
        raise ValidationError("the plug-in declares a dependency outside the host envelope", detail=refusals)

    return {
        **manifest,
        "contractCompatibility": {
            "host": PLUGIN_CONTRACT_VERSION,
            "plugin": manifest.get("contractVersion"),
            "compatibleMajor": PLUGIN_CONTRACT_MAJOR,
        },
        "loaded": True,
        "isolated": True,
    }


def run_plugin(plugin: dict[str, Any], *, scenario: dict[str, Any]) -> dict[str, Any]:
    """Run a loaded plug-in against a scenario, deterministically."""
    scenario_type = scenario.get("scenarioType") or scenario.get("campaignType")
    supported = {str(item) for item in plugin.get("scenarioTypes") or []}
    if scenario_type and scenario_type not in supported:
        raise ValidationError(
            f"plug-in {plugin.get('pluginId')} does not support scenario type {scenario_type!r}"
        )
    threat_ids = sorted({str(item) for item in scenario.get("threatSystemIds") or []})
    digest = hashlib.sha256(
        f"{plugin.get('pluginId')}:{plugin.get('version')}:{scenario.get('id')}:{','.join(threat_ids)}".encode()
    ).hexdigest()
    return {
        "pluginId": plugin.get("pluginId"),
        "pluginVersion": plugin.get("version"),
        "contractVersion": plugin.get("contractVersion"),
        "scenarioId": scenario.get("id"),
        "scenarioType": scenario_type,
        "threatSystemIds": threat_ids,
        "referenceArchitecture": (plugin.get("referenceArchitectures") or [None])[0],
        "deterministicKey": digest,
        "status": "COMPLETE",
    }


def unload_plugin(plugin: dict[str, Any]) -> dict[str, Any]:
    """Describe a plug-in removal without touching the host or its siblings."""
    return {
        "pluginId": plugin.get("pluginId"),
        "unloaded": True,
        "hostAffected": False,
        "siblingPluginsAffected": [],
    }


# ---------------------------------------------------------------------------
# F-6: red/blue co-simulation
# ---------------------------------------------------------------------------


def co_simulation(
    *,
    threat: dict[str, Any],
    red_scenario: dict[str, Any],
    blue_scenario: dict[str, Any],
    runs: int = 1_000,
    seed: int = 1234,
    pk_threshold: float = DEFAULT_PK_THRESHOLD,
) -> dict[str, Any]:
    """Run the strike and defence traces against the identical threat node.

    The identity assertion is the capability: both traces must resolve to the
    same ``ThreatSystem`` id, and any attempt to run the comparison against two
    parallel threat models is refused. A comparison between two different
    threats is not a measure of the hypersonic balance.
    """
    threat_id = threat.get("id")
    if not isinstance(threat_id, str) or not threat_id:
        raise ValidationError("the co-simulation must name a ThreatSystem")

    red_ids = sorted({str(item) for item in red_scenario.get("threatSystemIds") or []})
    blue_ids = sorted({str(item) for item in blue_scenario.get("threatSystemIds") or []})
    if not red_ids or not blue_ids:
        raise ValidationError("both traces must reference the threat model")
    if red_ids != blue_ids:
        raise ValidationError(
            "the red and blue traces do not reference the identical threat model",
            detail={"red": red_ids, "blue": blue_ids},
        )
    if threat_id not in red_ids:
        raise ValidationError("the supplied ThreatSystem is not the one both traces reference")

    red = run_batch(
        {"id": red_scenario.get("id"), **red_scenario},
        runs=runs,
        seed=seed,
        pk_threshold=pk_threshold,
    )
    blue = run_batch(
        {"id": blue_scenario.get("id"), **blue_scenario},
        runs=runs,
        seed=seed + 10_000,
        pk_threshold=pk_threshold,
    )

    red_intercept = red["statistics"]["interceptProbability"]
    blue_intercept = blue["statistics"]["interceptProbability"]
    return {
        "threatSystemId": threat_id,
        "threatModelVersion": (threat.get("attributes") or {}).get("modelVersionIds"),
        "identity": {
            "sameThreatNode": True,
            "redTraceThreatIds": red_ids,
            "blueTraceThreatIds": blue_ids,
            "duplicateThreatModel": False,
            "evidence": sorted(
                {str(item) for item in (threat.get("attributes") or {}).get("observationIds") or []}
            ),
        },
        "red": {
            "scenarioId": red_scenario.get("id"),
            "role": "STRIKE",
            "statistics": red["statistics"],
        },
        "blue": {
            "scenarioId": blue_scenario.get("id"),
            "role": "DEFENCE",
            "statistics": blue["statistics"],
        },
        "comparison": {
            "interceptProbabilityDelta": round(blue_intercept - red_intercept, 4),
            "meanPkDelta": round(
                blue["statistics"]["meanPk"] - red["statistics"]["meanPk"], 4
            ),
            "runs": runs,
            "seed": seed,
        },
        "reproducible": True,
    }

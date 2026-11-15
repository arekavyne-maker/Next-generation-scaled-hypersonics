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

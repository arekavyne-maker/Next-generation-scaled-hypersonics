"""Deterministic anomaly detection for test and telemetry measurements.

The platform's claim for C-2 is not "a neural network runs here". It is that a
measurement that falls outside its engineering limit, or outside the variation
of its own history, is surfaced **before** it becomes a disposition. This
module implements that claim with statistics a reviewer can reproduce: limits,
rolling z-scores and a robust median/MAD score.

A flag is a review item. It never changes a result's outcome.
"""

from __future__ import annotations

from statistics import median
from typing import Any

from .errors import ValidationError


def _mad(values: list[float]) -> float:
    if not values:
        return 0.0
    centre = median(values)
    deviations = sorted(abs(value - centre) for value in values)
    return median(deviations)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if not values:
        return 0.0
    centre = _mean(values)
    return (sum((value - centre) ** 2 for value in values) / len(values)) ** 0.5


def detect_anomalies(
    series: list[dict[str, Any]] | list[float],
    *,
    threshold: float = 3.0,
    min_samples: int = 3,
    method: str = "zscore",
) -> dict[str, Any]:
    """Flag points outside the variation of their own series.

    ``series`` is either a list of numbers or a list of ``{name, value}``
    objects. The first ``min_samples`` points establish the baseline; every
    subsequent point is scored against the points before it, never against
    itself.
    """
    if not isinstance(series, list):
        raise ValidationError("'series' must be a list")
    if not isinstance(threshold, int | float) or threshold <= 0:
        raise ValidationError("'threshold' must be positive")
    if not isinstance(min_samples, int) or min_samples < 2:
        raise ValidationError("'min_samples' must be at least 2")
    normalized: list[dict[str, Any]] = []
    for index, point in enumerate(series):
        if isinstance(point, dict):
            value = point.get("value")
            name = point.get("name") or f"point-{index}"
        else:
            value = point
            name = f"point-{index}"
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise ValidationError("every series point needs a numeric value")
        normalized.append({"name": str(name), "value": float(value)})

    if method not in {"zscore", "mad"}:
        raise ValidationError("'method' must be 'zscore' or 'mad'")

    flags: list[dict[str, Any]] = []
    values: list[float] = []
    for point in normalized:
        if len(values) >= min_samples:
            if method == "zscore":
                centre = _mean(values)
                spread = _std(values)
                score = (
                    abs(point["value"] - centre) / spread
                    if spread > 0
                    else (float("inf") if point["value"] != centre else 0.0)
                )
            else:
                centre = median(values)
                spread = _mad(values)
                score = (
                    abs(point["value"] - centre) / spread
                    if spread > 0
                    else (float("inf") if point["value"] != centre else 0.0)
                )
            if score > threshold:
                flags.append(
                    {
                        "name": point["name"],
                        "value": point["value"],
                        "score": round(score, 4) if score != float("inf") else None,
                        "baseline": round(centre, 6),
                        "spread": round(spread, 6),
                        "method": method,
                        "kind": "variation",
                    }
                )
        values.append(point["value"])

    return {
        "method": method,
        "threshold": float(threshold),
        "sampleCount": len(normalized),
        "flags": flags,
        "count": len(flags),
    }


def scan_measurements(
    measurements: list[dict[str, Any]],
    *,
    limits: dict[str, dict[str, Any]] | None = None,
    history: dict[str, list[float]] | None = None,
    threshold: float = 3.0,
    min_samples: int = 3,
) -> dict[str, Any]:
    """Check measurements against engineering limits and their history.

    A limit breach is reported as ``severity: LIMIT``. A statistical outlier
    inside its limits is ``severity: VARIATION``. The two are kept separate
    because they require different engineering responses.
    """
    if not isinstance(measurements, list) or not measurements:
        raise ValidationError("'measurements' must be a non-empty list")
    limit_map = limits or {}
    history_map = history or {}

    flags: list[dict[str, Any]] = []
    for measurement in measurements:
        if not isinstance(measurement, dict):
            raise ValidationError("every measurement must be an object")
        name = measurement.get("name")
        value = measurement.get("value")
        if not isinstance(name, str) or not name:
            raise ValidationError("every measurement needs a name")
        if not isinstance(value, int | float) or isinstance(value, bool):
            raise ValidationError(f"measurement {name!r} needs a numeric value")

        limit = limit_map.get(name)
        if isinstance(limit, dict):
            low = limit.get("min")
            high = limit.get("max")
            if isinstance(low, int | float) and value < low:
                flags.append(
                    {
                        "name": name,
                        "value": float(value),
                        "severity": "LIMIT",
                        "kind": "below_min",
                        "limit": low,
                        "evidence": measurement,
                    }
                )
                continue
            if isinstance(high, int | float) and value > high:
                flags.append(
                    {
                        "name": name,
                        "value": float(value),
                        "severity": "LIMIT",
                        "kind": "above_max",
                        "limit": high,
                        "evidence": measurement,
                    }
                )
                continue

        prior = history_map.get(name) or []
        numeric_prior = [float(item) for item in prior if isinstance(item, int | float)]
        if len(numeric_prior) >= min_samples:
            centre = _mean(numeric_prior)
            spread = _std(numeric_prior)
            score = (
                abs(float(value) - centre) / spread
                if spread > 0
                else (float("inf") if float(value) != centre else 0.0)
            )
            if score > threshold:
                flags.append(
                    {
                        "name": name,
                        "value": float(value),
                        "severity": "VARIATION",
                        "kind": "history_outlier",
                        "score": round(score, 4) if score != float("inf") else None,
                        "baseline": round(centre, 6),
                        "spread": round(spread, 6),
                        "evidence": measurement,
                    }
                )

    return {
        "measurementCount": len(measurements),
        "flags": flags,
        "count": len(flags),
        "limitBreaches": sum(1 for flag in flags if flag["severity"] == "LIMIT"),
        "variationFlags": sum(1 for flag in flags if flag["severity"] == "VARIATION"),
        "reviewRequired": bool(flags),
        "method": "limits + zscore",
    }

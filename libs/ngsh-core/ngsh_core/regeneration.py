"""Deterministic model regeneration (PSDD C-3 and G-3).

When evidence disagrees with a model, the platform's job is not to "retrain
something". It is to produce a **new, reviewable model version** whose
correction can be inspected, attributed and refused.

The correction here is deliberately simple: a per-quantity affine correction
fitted to the residuals between prediction and observation. That is enough to
remove a systematic bias, it is explainable to an engineer, and it is
reproducible from the evidence. More elaborate calibration belongs in the
programme's physics tool; the platform supplies the versioning, the evidence
link and the approval gate.

A regenerated model is **never** automatically approved for use. C-004 and the
PSDD's human-approval rule require a person to accept the corrected model
before predictions from it can be relied on.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from .errors import ValidationError


def _number(value: Any) -> float | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    return None


def _pairs(evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract (name, predicted, observed) triples from evidence records.

    Evidence may arrive as test-result measurements or as a direct comparison
    list. Both shapes are accepted because the lab owns the evidence format;
    the platform owns only the requirement that each pair be named and numeric.
    """
    if not isinstance(evidence, list) or not evidence:
        raise ValidationError("regeneration requires at least one evidence record")
    pairs: list[dict[str, Any]] = []
    for record in evidence:
        if not isinstance(record, dict):
            raise ValidationError("every evidence record must be an object")
        name = record.get("name") or record.get("quantity")
        predicted = _number(
            record.get("predicted", record.get("expected", record.get("model", record.get("baseline"))))
        )
        observed = _number(
            record.get("observed", record.get("actual", record.get("measured", record.get("value"))))
        )
        if not isinstance(name, str) or not name:
            raise ValidationError("every evidence record needs a name")
        if predicted is None or observed is None:
            raise ValidationError(
                f"evidence {name!r} needs a numeric predicted/expected and observed/actual value"
            )
        pairs.append(
            {
                "name": name,
                "predicted": predicted,
                "observed": observed,
                "unit": record.get("unit"),
                "evidenceId": record.get("evidenceId") or record.get("id"),
            }
        )
    return pairs


def _version(value: str) -> str:
    parts = value.split(".")
    if all(part.isdigit() for part in parts):
        numbers = [int(part) for part in parts]
        numbers[-1] += 1
        return ".".join(str(number) for number in numbers)
    return f"{value}-r1"


def _summary(pairs: list[dict[str, Any]], coefficients: dict[str, dict[str, float]]) -> dict[str, Any]:
    residuals = []
    for pair in pairs:
        coefficient = coefficients[pair["name"]]
        corrected = pair["predicted"] * coefficient["scale"] + coefficient["offset"]
        residuals.append(corrected - pair["observed"])
    count = len(residuals)
    rmse = (sum(value * value for value in residuals) / count) ** 0.5
    mean_observed = sum(pair["observed"] for pair in pairs) / count
    normaliser = abs(mean_observed) if abs(mean_observed) > 1e-9 else 1.0
    return {
        "evidenceCount": count,
        "rmse": round(rmse, 6),
        "bias": round(sum(residuals) / count, 6),
        "maxAbsError": round(max(abs(value) for value in residuals), 6),
        "normalisedRmse": round(rmse / normaliser, 6),
    }


def regenerate_model(
    model: dict[str, Any],
    *,
    evidence: list[dict[str, Any]],
    reason: str | None = None,
    generated_at: str | None = None,
    new_model_id: str | None = None,
) -> dict[str, Any]:
    """Fit a correction to the evidence and describe the new model version.

    The function is pure: it does not write an event. The service publishes the
    returned attributes as a new ``Model`` entity, retaining the old version
    untouched so both remain in the thread.
    """
    if not isinstance(model, dict):
        raise ValidationError("regeneration requires a Model document")
    name = model.get("name")
    model_type = model.get("modelType")
    version = model.get("modelVersion")
    if not isinstance(name, str) or not name:
        raise ValidationError("the Model has no name")
    if not isinstance(model_type, str) or not model_type:
        raise ValidationError("the Model has no modelType")
    if not isinstance(version, str) or not version:
        raise ValidationError("the Model has no modelVersion")

    pairs = _pairs(evidence)
    coefficients: dict[str, dict[str, float]] = {}
    for pair in pairs:
        # Degenerate predicted values carry an offset correction only; a scale
        # fitted to zero would be arbitrary.
        scale = pair["observed"] / pair["predicted"] if abs(pair["predicted"]) > 1e-9 else 1.0
        offset = pair["observed"] - pair["predicted"] * scale
        coefficients[pair["name"]] = {"scale": round(scale, 9), "offset": round(offset, 9)}

    correction_summary = _summary(pairs, coefficients)
    fidelity = model.get("fidelity") or {}
    prior = _number(fidelity.get("overall")) if isinstance(fidelity, dict) else None
    measured = max(0.0, min(1.0, 1.0 - correction_summary["normalisedRmse"]))
    updated_overall = measured if prior is None else round(0.5 * prior + 0.5 * measured, 4)

    next_version = _version(version)
    digest_source = {
        "parentModelId": model.get("id"),
        "modelType": model_type,
        "priorVersion": version,
        "nextVersion": next_version,
        "evidence": pairs,
        "correction": coefficients,
        "summary": correction_summary,
        "reason": reason,
    }
    digest = hashlib.sha256(
        json.dumps(digest_source, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()

    attributes = {
        "name": name,
        "modelType": model_type,
        "modelVersion": next_version,
        "parentModelId": model.get("id"),
        "fidelity": {
            **(fidelity if isinstance(fidelity, dict) else {}),
            "overall": updated_overall,
            "evidenceRefs": [pair["evidenceId"] for pair in pairs if pair.get("evidenceId")],
        },
        "codeRef": model.get("codeRef"),
        "inputSchemaRef": model.get("inputSchemaRef"),
        "outputSchemaRef": model.get("outputSchemaRef"),
        "modelCard": model.get("modelCard"),
        "runtime": {
            **(model.get("runtime") or {}),
            "regeneration": {
                "method": "affine-bias-correction",
                "parentModelId": model.get("id"),
                "priorVersion": version,
                "coefficients": coefficients,
                "residuals": correction_summary,
                "reason": reason,
                "digest": digest,
                "generatedAt": generated_at or datetime.now(UTC).isoformat(),
                "reproducible": True,
            },
        },
        # A correction is evidence, not approval. A person must release it.
        "approvedForUse": False,
    }
    return {
        "modelId": new_model_id,
        "parentModelId": model.get("id"),
        "name": name,
        "modelType": model_type,
        "priorVersion": version,
        "modelVersion": next_version,
        "attributes": attributes,
        "correction": coefficients,
        "summary": correction_summary,
        "fidelity": {"prior": prior, "proposed": updated_overall},
        "requiresApproval": True,
        "reason": reason,
        "digest": digest,
        "generatedAt": generated_at or datetime.now(UTC).isoformat(),
        "reproducible": True,
    }


def residual_report(model: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Report disagreement without changing anything.

    A reviewer can ask "how far off is the current model?" before deciding
    whether a regeneration is warranted.
    """
    pairs = _pairs(evidence)
    residuals = [
        {
            "name": pair["name"],
            "predicted": pair["predicted"],
            "observed": pair["observed"],
            "residual": round(pair["observed"] - pair["predicted"], 9),
            "relativeResidual": (
                round((pair["observed"] - pair["predicted"]) / abs(pair["predicted"]), 9)
                if abs(pair["predicted"]) > 1e-9
                else None
            ),
            "unit": pair["unit"],
            "evidenceId": pair["evidenceId"],
        }
        for pair in pairs
    ]
    return {
        "modelId": model.get("id"),
        "modelVersion": model.get("modelVersion"),
        "evidence": residuals,
        "worst": max(residuals, key=lambda item: abs(item["residual"])),
        "count": len(residuals),
    }

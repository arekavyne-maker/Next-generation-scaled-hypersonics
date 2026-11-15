"""Threat digital twins (PSDD F-1).

A threat model is not free text and it is not a classified intelligence
product. In this platform it is a **derived, reproducible estimate** of what a
threat system can do, built from the recorded kinematic profile and the
observations that support it. Two analysts with the same facts get the same
model, and a disagreement points at a changed input rather than a changed mood.

The estimate is deliberately explicit about its own weakness:

* every derived quantity names the assumption behind it;
* an observation count of zero lowers confidence, it does not stop the model;
* the detection range is a first-order radar-range scaling, not a sensor
  engagement model, and it says so.

The result is written as a ``Model`` entity of type ``THREAT_KINEMATIC`` so it
enters the fidelity registry (G-4) and the digital thread like any other model.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime
from typing import Any

from .errors import ValidationError

MODEL_VERSION = "1.0.0"
SPEED_OF_SOUND_MPS = 343.0
HYPERSONIC_MACH = 5.0

#: First-order reference: a 1 m² target at the reference range. The scaling
#: from cross-section to range is the radar range equation's fourth root.
REFERENCE_DETECTION_RANGE_KM = 250.0
REFERENCE_CROSS_SECTION_M2 = 1.0


def _number(source: dict[str, Any], names: tuple[str, ...], default: float | None = None) -> float | None:
    for name in names:
        value = source.get(name)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    return default


def _characteristic_value(characteristics: list[Any], names: tuple[str, ...]) -> float | None:
    for characteristic in characteristics:
        if not isinstance(characteristic, dict):
            continue
        label = str(characteristic.get("name") or characteristic.get("kind") or "").lower()
        if any(name in label for name in names):
            value = characteristic.get("value")
            if isinstance(value, int | float) and not isinstance(value, bool):
                return float(value)
            if isinstance(value, str):
                try:
                    return float(value)
                except ValueError:
                    continue
    return None


def derive_threat_model(
    threat: dict[str, Any],
    *,
    model_id: str | None = None,
    generated_at: str | None = None,
    assumptions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic kinematic threat model from recorded facts.

    ``threat`` is the attributes of a ``ThreatSystem`` (an ``id`` is optional
    but recommended). The return value is a model description; the service
    wraps it in a ``Model`` entity so the same facts are one source of truth.
    """
    if not isinstance(threat, dict):
        raise ValidationError("a threat model requires a ThreatSystem document")
    designation = threat.get("designation")
    threat_class = threat.get("threatClass")
    if not isinstance(designation, str) or not designation:
        raise ValidationError("the ThreatSystem has no designation")
    if not isinstance(threat_class, str) or not threat_class:
        raise ValidationError("the ThreatSystem has no threatClass")

    profile = threat.get("kinematicProfile") or {}
    if not isinstance(profile, dict):
        raise ValidationError("kinematicProfile must be an object")
    characteristics = threat.get("characteristics") or []
    if not isinstance(characteristics, list):
        raise ValidationError("characteristics must be a list")

    max_speed = _number(profile, ("maxSpeedMps", "maximumSpeedMps", "speedMps"))
    cruise_speed = _number(profile, ("cruiseSpeedMps", "averageSpeedMps"), max_speed)
    terminal_speed = _number(profile, ("terminalSpeedMps", "impactSpeedMps"), cruise_speed)
    max_altitude = _number(profile, ("maxAltitudeM", "apogeeM", "altitudeM"))
    min_altitude = _number(profile, ("minAltitudeM", "glideAltitudeM"))
    maneuver_g = _number(profile, ("maneuverG", "maxManeuverG", "lateralG"))
    range_km = _number(profile, ("rangeKm", "maximumRangeKm"))
    cross_section = _number(profile, ("rcsM2", "radarCrossSectionM2"))
    if cross_section is None:
        cross_section = _characteristic_value(characteristics, ("rcs", "cross section", "signature"))

    if max_speed is None or max_speed <= 0:
        raise ValidationError(
            "the ThreatSystem kinematicProfile needs a positive maxSpeedMps to derive a model"
        )

    mach = max_speed / SPEED_OF_SOUND_MPS
    effective_cross_section = (
        cross_section
        if isinstance(cross_section, float) and cross_section > 0
        else REFERENCE_CROSS_SECTION_M2
    )
    detection_range_km = (
        REFERENCE_DETECTION_RANGE_KM * (effective_cross_section / REFERENCE_CROSS_SECTION_M2) ** 0.25
    )
    detection_range_m = detection_range_km * 1000.0
    warning_seconds = detection_range_m / max_speed
    terminal_warning_seconds = (
        detection_range_m / terminal_speed if terminal_speed and terminal_speed > 0 else None
    )

    observation_ids = threat.get("observationIds") or []
    if not isinstance(observation_ids, list):
        raise ValidationError("observationIds must be a list")
    confidence = threat.get("confidence")
    if not isinstance(confidence, int | float) or isinstance(confidence, bool):
        # No stated confidence: observations are the only honest proxy.
        confidence = min(0.9, 0.2 + 0.1 * len(observation_ids))
    confidence = max(0.0, min(1.0, float(confidence)))

    maneuver_regime = (
        "NONE" if maneuver_g is None or maneuver_g < 1.0 else "LIMITED" if maneuver_g < 5.0 else "HIGH"
    )
    speed_regime = "HYPERSONIC" if mach >= HYPERSONIC_MACH else "SUPERSONIC" if mach >= 1.0 else "SUBSONIC"

    uncertainty_fraction = round(max(0.01, (1.0 - confidence) * 0.25), 4)
    performance = {
        "maxSpeedMps": round(max_speed, 3),
        "cruiseSpeedMps": round(cruise_speed, 3) if cruise_speed is not None else None,
        "terminalSpeedMps": round(terminal_speed, 3) if terminal_speed is not None else None,
        "mach": round(mach, 3),
        "speedRegime": speed_regime,
        "maxAltitudeM": max_altitude,
        "minAltitudeM": min_altitude,
        "maneuverG": maneuver_g,
        "maneuverRegime": maneuver_regime,
        "rangeKm": range_km,
    }
    signature = {
        "radarCrossSectionM2": round(effective_cross_section, 6),
        "assumed": cross_section is None,
    }
    estimate = {
        "threatId": threat.get("id"),
        "designation": designation,
        "threatClass": threat_class,
        "modelVersion": MODEL_VERSION,
        "performance": performance,
        "signature": signature,
        "detection": {
            "referenceRangeKm": REFERENCE_DETECTION_RANGE_KM,
            "rangeKm": round(detection_range_km, 3),
            "warningSeconds": round(warning_seconds, 3),
            "terminalWarningSeconds": (
                round(terminal_warning_seconds, 3) if terminal_warning_seconds is not None else None
            ),
            "method": "radar-range-equation-fourth-root",
        },
        "confidence": {
            "overall": round(confidence, 4),
            "speedUncertaintyMps": round(max_speed * uncertainty_fraction, 3),
            "uncertaintyFraction": uncertainty_fraction,
            "observationCount": len(observation_ids),
        },
        "assumptions": {
            "speedOfSoundMps": SPEED_OF_SOUND_MPS,
            "hypersonicMach": HYPERSONIC_MACH,
            "detectionIsFirstOrder": True,
            **(assumptions or {}),
        },
        "observations": [str(item) for item in observation_ids],
    }

    digest_source = {
        "modelVersion": MODEL_VERSION,
        "threat": {
            "id": threat.get("id"),
            "designation": designation,
            "threatClass": threat_class,
            "kinematicProfile": profile,
            "characteristics": characteristics,
            "confidence": confidence,
            "observationIds": observation_ids,
        },
        "assumptions": estimate["assumptions"],
    }
    digest = hashlib.sha256(
        json.dumps(digest_source, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    estimate["modelId"] = model_id
    estimate["digest"] = digest
    estimate["generatedAt"] = generated_at or datetime.now(UTC).isoformat()
    estimate["generator"] = "ngsh_core.threatmodel"
    estimate["reproducible"] = True
    return estimate


def model_attributes(model: dict[str, Any]) -> dict[str, Any]:
    """Translate a derived threat model into ``Model`` entity attributes.

    The whole estimate is carried in ``runtime`` because it is a derived
    artefact of the threat system, not a new set of ontology fields. Fidelity's
    ``overall`` is the confidence estimate, so the model enters the G-4 release
    gate with an honest score.
    """
    return {
        "name": f"{model['designation']} kinematic model",
        "modelType": "THREAT_KINEMATIC",
        "modelVersion": model["modelVersion"],
        "fidelity": {
            "overall": model["confidence"]["overall"],
            "applicabilityEnvelope": {
                "maxSpeedMps": {"value": model["performance"]["maxSpeedMps"], "unit": "m/s"},
                "maxAltitudeM": {"value": model["performance"]["maxAltitudeM"], "unit": "m"},
                "maneuverG": {"value": model["performance"]["maneuverG"], "unit": "g"},
            },
            "evidenceRefs": model["observations"],
        },
        "runtime": {
            "generator": model["generator"],
            "threatId": model["threatId"],
            "estimate": model,
        },
        "approvedForUse": False,
        "codeRef": "ngsh_core/threatmodel.py#derive_threat_model",
    }


def detection_envelope(model: dict[str, Any], altitudes: list[float] | None = None) -> dict[str, Any]:
    """A coarse look-angle envelope for a derived model.

    Altitude changes the horizon, so the same cross-section is visible farther
    away at altitude. This is a geometric first-order estimate and reports the
    horizon distance it used rather than hiding it.
    """
    base_range = (model.get("detection") or {}).get("rangeKm")
    if not isinstance(base_range, int | float):
        raise ValidationError("the model has no detection range")
    earth_radius_km = 6371.0
    samples = []
    for altitude in altitudes or [10000.0, 20000.0, 30000.0]:
        if not isinstance(altitude, int | float) or altitude < 0:
            raise ValidationError("altitudes must be non-negative numbers of metres")
        horizon_km = math.sqrt(2.0 * earth_radius_km * (altitude / 1000.0))
        samples.append(
            {
                "altitudeM": float(altitude),
                "horizonKm": round(horizon_km, 3),
                "effectiveRangeKm": round(min(float(base_range), horizon_km), 3),
                "limitedBy": "range" if float(base_range) <= horizon_km else "horizon",
            }
        )
    return {
        "modelId": model.get("modelId"),
        "baseRangeKm": base_range,
        "samples": samples,
        "assumptions": {"earthRadiusKm": earth_radius_km, "flatTerrain": True},
    }

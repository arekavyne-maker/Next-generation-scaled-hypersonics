"""Deterministic discrete-event production simulation (Pillar B-4).

The simulation is intentionally small enough to reason about and exact enough
to be reproducible. It schedules individual units through a sequence of
stations with parallel capacity, setup time, yield loss and planned downtime,
and reports the binding station rather than only a headline rate.

Two runs with the same inputs produce the same result. That is what makes a
what-if study reviewable: a disagreement is a change in the inputs, not a
change in the random seed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .errors import ValidationError


def _draw(seed: int, station_id: str, unit: int) -> float:
    digest = hashlib.sha256(f"{seed}:{station_id}:{unit}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


def _downtime_intervals(station: dict[str, Any], horizon_minutes: float) -> list[tuple[float, float]]:
    mtbf = station.get("mtbfMinutes")
    mttr = station.get("mttrMinutes")
    if not isinstance(mtbf, int | float) or not isinstance(mttr, int | float):
        return []
    if mtbf <= 0 or mttr <= 0:
        return []
    intervals: list[tuple[float, float]] = []
    start = float(mtbf)
    while start < horizon_minutes:
        intervals.append((start, min(start + float(mttr), horizon_minutes)))
        start += float(mtbf) + float(mttr)
    return intervals


def _overlap(start: float, end: float, intervals: list[tuple[float, float]]) -> float:
    total = 0.0
    for down_start, down_end in intervals:
        overlap_start = max(start, down_start)
        overlap_end = min(end, down_end)
        if overlap_end > overlap_start:
            total += overlap_end - overlap_start
    return total


def _station(station: dict[str, Any], index: int) -> dict[str, Any]:
    station_id = station.get("stationId") or station.get("id") or f"STATION-{index + 1}"
    capacity = station.get("capacity", 1)
    if not isinstance(capacity, int) or capacity < 1:
        raise ValidationError(f"station {station_id!r} needs a positive integer capacity")
    cycle = station.get("cycleTimeMinutes")
    if not isinstance(cycle, int | float) or cycle <= 0:
        raise ValidationError(f"station {station_id!r} needs a positive cycleTimeMinutes")
    yield_rate = station.get("yieldRate", 1.0)
    if not isinstance(yield_rate, int | float) or not 0 < yield_rate <= 1:
        raise ValidationError(f"station {station_id!r} yieldRate must be in (0, 1]")
    setup = station.get("setupMinutes", 0.0)
    if not isinstance(setup, int | float) or setup < 0:
        raise ValidationError(f"station {station_id!r} setupMinutes must be non-negative")
    return {
        "stationId": str(station_id),
        "name": station.get("name") or str(station_id),
        "capacity": capacity,
        "cycleTimeMinutes": float(cycle),
        "yieldRate": float(yield_rate),
        "setupMinutes": float(setup),
        "mtbfMinutes": station.get("mtbfMinutes"),
        "mttrMinutes": station.get("mttrMinutes"),
    }


def simulate_production(
    stations: list[dict[str, Any]],
    *,
    demand_units: int,
    shifts_per_day: int = 2,
    shift_hours: float = 8.0,
    horizon_days: int = 30,
    seed: int = 2026,
) -> dict[str, Any]:
    """Schedule ``demand_units`` through ``stations`` and report the result."""
    if not isinstance(stations, list) or not stations:
        raise ValidationError("'stations' must be a non-empty list")
    if not isinstance(demand_units, int) or demand_units <= 0:
        raise ValidationError("'demandUnits' must be a positive integer")
    if not isinstance(shifts_per_day, int) or shifts_per_day <= 0:
        raise ValidationError("'shiftsPerDay' must be a positive integer")
    if not isinstance(shift_hours, int | float) or shift_hours <= 0:
        raise ValidationError("'shiftHours' must be positive")
    if not isinstance(horizon_days, int) or horizon_days <= 0:
        raise ValidationError("'horizonDays' must be a positive integer")

    normalized = [_station(station, index) for index, station in enumerate(stations)]
    horizon_minutes = float(shifts_per_day) * float(shift_hours) * 60.0 * horizon_days

    downtime = {station["stationId"]: _downtime_intervals(station, horizon_minutes) for station in normalized}
    servers = {station["stationId"]: [0.0] * station["capacity"] for station in normalized}
    processed = {station["stationId"]: 0 for station in normalized}
    busy_minutes = {station["stationId"]: 0.0 for station in normalized}
    scrap = {station["stationId"]: 0 for station in normalized}

    completed_end_times: list[float] = []
    late_units = 0
    for unit in range(demand_units):
        ready = 0.0
        scrapped = False
        late = False
        for station in normalized:
            station_id = station["stationId"]
            server_times = servers[station_id]
            server_index = min(range(len(server_times)), key=lambda idx: max(ready, server_times[idx]))
            start = max(ready, server_times[server_index])
            if start >= horizon_minutes:
                late = True
                break
            setup = station["setupMinutes"] if processed[station_id] == 0 else 0.0
            duration = station["cycleTimeMinutes"] + setup

            # Processing pauses across planned downtime. Iterate because adding
            # the first downtime overlap can push the operation into the next.
            end = start + duration
            intervals = downtime[station_id]
            for _ in range(10):
                pause = _overlap(start, end, intervals)
                if pause <= 0:
                    break
                end += pause

            server_times[server_index] = end
            processed[station_id] += 1
            busy_minutes[station_id] += max(0.0, min(end, horizon_minutes) - start)
            ready = end

            if _draw(seed, station_id, unit) > station["yieldRate"]:
                scrap[station_id] += 1
                scrapped = True
                break

        if scrapped:
            continue
        if late or ready > horizon_minutes:
            late_units += 1
            continue
        completed_end_times.append(ready)

    completed = len(completed_end_times)
    utilisation = {}
    for station in normalized:
        station_id = station["stationId"]
        capacity_minutes = horizon_minutes * station["capacity"]
        utilisation[station_id] = (
            round(min(1.0, busy_minutes[station_id] / capacity_minutes), 4) if capacity_minutes else 0.0
        )
    bottleneck = max(utilisation, key=utilisation.get) if utilisation else None

    throughput_per_day = completed / horizon_days
    mean_lead_time = sum(completed_end_times) / completed if completed else None
    max_end = max(completed_end_times) if completed_end_times else None
    result = {
        "demandUnits": demand_units,
        "completedUnits": completed,
        "scrappedUnits": demand_units - completed - late_units,
        "lateUnits": late_units,
        "throughputPerDay": round(throughput_per_day, 4),
        "meetsDemand": completed >= demand_units,
        "shortfallUnits": max(0, demand_units - completed),
        "horizonDays": horizon_days,
        "horizonMinutes": round(horizon_minutes, 2),
        "meanLeadTimeMinutes": round(mean_lead_time, 2) if mean_lead_time is not None else None,
        "completionMinutes": round(max_end, 2) if max_end is not None else None,
        "bottleneckStationId": bottleneck,
        "bottleneckUtilisation": utilisation.get(bottleneck, 0.0) if bottleneck else 0.0,
        "stations": [
            {
                "stationId": station["stationId"],
                "name": station["name"],
                "capacity": station["capacity"],
                "cycleTimeMinutes": station["cycleTimeMinutes"],
                "yieldRate": station["yieldRate"],
                "utilisation": utilisation[station["stationId"]],
                "processedUnits": processed[station["stationId"]],
                "scrappedUnits": scrap[station["stationId"]],
                "downtimeWindows": len(downtime[station["stationId"]]),
            }
            for station in normalized
        ],
        "seed": seed,
        "reproducible": True,
    }
    digest_source = {
        "demandUnits": demand_units,
        "shiftsPerDay": shifts_per_day,
        "shiftHours": shift_hours,
        "horizonDays": horizon_days,
        "seed": seed,
        "stations": normalized,
        "result": result,
    }
    result["digest"] = hashlib.sha256(
        json.dumps(digest_source, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return result

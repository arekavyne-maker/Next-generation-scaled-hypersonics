"""Pillar E domain logic: skills, credentials, work authorisation and demand gaps.

The rules here are the ones PSDD pillar capability E-3 and E-4 are assessed
on, and they are deliberately pure functions so that an assessor can read the
rule and a test can prove it:

* a credential may only be issued to a person whose citizenship permits the
  activity and whose clearance is current at issue time (C-005);
* a person referenced by a credential, a process run or a work authorisation
  must have a non-expired clearance at the time of reference (C-006);
* a lapsed credential, a suspended credential and a revoked credential are
  three different findings, and none of them authorises work;
* the workforce gap compares credentialed supply against production demand,
  by region and trade, and never confuses headcount with qualified supply.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from .errors import ValidationError

#: Clearance ordering used for the "clearance is high enough" check. This is
#: a personnel-clearance vocabulary, not a data-classification vocabulary;
#: conflating the two is a common source of silent privilege bugs.
CLEARANCE_RANK = {"NONE": 0, "PUBLIC TRUST": 1, "SECRET": 2, "TOP SECRET": 3, "SCI-CLEARED": 4}

#: Skills in the NGSH programme are export-controlled by default. A programme
#: that needs allied participation supplies its own list; the default is the
#: restrictive one, because a permissive default is a disclosure waiting to
#: happen.
DEFAULT_PERMITTED_CITIZENSHIPS = ("US",)

CREDENTIAL_STATES = ("ACTIVE", "SUSPENDED", "REVOKED", "EXPIRED")

#: Allowed lifecycle moves. Revocation is terminal; reinstatement exists so
#: that a suspension is not silently treated as a revocation.
TRANSITIONS = {
    "suspend": {"from": {"ACTIVE"}, "to": "SUSPENDED"},
    "reinstate": {"from": {"SUSPENDED"}, "to": "ACTIVE"},
    "revoke": {"from": {"ACTIVE", "SUSPENDED"}, "to": "REVOKED"},
}


def _as_datetime(value: Any, *, field_name: str) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    if isinstance(value, str) and value:
        text = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValidationError(f"{field_name} is not an ISO-8601 timestamp: {value!r}") from exc
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    raise ValidationError(f"{field_name} is required and must be an ISO-8601 timestamp")


def clearance_rank(level: Any) -> int:
    if not isinstance(level, str) or not level.strip():
        return 0
    return CLEARANCE_RANK.get(level.strip().upper(), 0)


def clearance_current(person: dict[str, Any], at: datetime) -> bool:
    """C-006: is the person's clearance current at ``at``?

    A missing expiry is *not* current. A clearance whose expiry nobody
    recorded is a claim, and C-006 exists to stop claims authorising work.
    """
    expiry = person.get("clearanceExpiry")
    if not expiry:
        return False
    return _as_datetime(expiry, field_name="clearanceExpiry") >= at


@dataclass
class IssueAssessment:
    allowed: bool
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"allowed": self.allowed, "reasons": self.reasons}


def assess_issue(
    person: dict[str, Any],
    skill: dict[str, Any],
    at: datetime,
    *,
    permitted_citizenships: tuple[str, ...] = DEFAULT_PERMITTED_CITIZENSHIPS,
) -> IssueAssessment:
    """C-005 and C-006 at credential issue time."""
    reasons: list[str] = []

    citizenship = str(person.get("citizenship") or "").strip().upper()
    if citizenship not in permitted_citizenships:
        reasons.append(
            f"C-005: citizenship {citizenship or 'UNKNOWN'} does not permit this activity "
            f"(permitted: {', '.join(permitted_citizenships)})"
        )

    if not clearance_current(person, at):
        reasons.append("C-005/C-006: the person's clearance is not current at issue time")

    required = skill.get("clearanceRequired")
    if required and clearance_rank(person.get("clearanceLevel")) < clearance_rank(required):
        reasons.append(
            f"C-005: clearance {person.get('clearanceLevel') or 'NONE'} is below the "
            f"{required} required by skill {skill.get('name') or skill.get('id')}"
        )

    return IssueAssessment(allowed=not reasons, reasons=reasons)


def credential_state(credential: dict[str, Any], at: datetime) -> str:
    """The effective state of a credential at a point in time.

    Stored ``status`` is what someone last wrote. The effective state adds
    expiry, because an expired credential whose status still says ACTIVE is
    the exact failure mode C-006 is meant to catch.
    """
    status = str(credential.get("status") or "").strip().upper()
    if status == "REVOKED":
        return "REVOKED"
    if status == "SUSPENDED":
        return "SUSPENDED"
    expiry = credential.get("expiresAt")
    if expiry and _as_datetime(expiry, field_name="expiresAt") <= at:
        return "EXPIRED"
    if status == "ACTIVE":
        return "ACTIVE"
    return status or "UNKNOWN"


def transition(credential: dict[str, Any], action: str, at: datetime) -> str:
    """Apply a lifecycle action and return the resulting stored status."""
    if action not in TRANSITIONS:
        raise ValidationError(f"unknown credential action {action!r}; expected {sorted(TRANSITIONS)}")
    current = credential_state(credential, at)
    allowed_from = TRANSITIONS[action]["from"]
    if current not in allowed_from:
        raise ValidationError(
            f"cannot {action} a credential in state {current}; allowed from {sorted(allowed_from)}"
        )
    return TRANSITIONS[action]["to"]


@dataclass
class WorkAuthorisation:
    allowed: bool
    credentialState: str
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "credentialState": self.credentialState,
            "reasons": self.reasons,
        }


def authorise(
    person: dict[str, Any],
    credential: dict[str, Any],
    skill: dict[str, Any],
    at: datetime,
    *,
    permit_skill_id: str | None = None,
) -> WorkAuthorisation:
    """Decide whether a person may perform a skill at a facility right now."""
    state = credential_state(credential, at)
    reasons: list[str] = []

    if state != "ACTIVE":
        reasons.append(f"the credential is {state.lower()}, not active")
    if permit_skill_id and str(credential.get("skillId")) != permit_skill_id:
        reasons.append("the credential is for a different skill")
    if not clearance_current(person, at):
        reasons.append("C-006: the person's clearance is not current")
    if skill.get("clearanceRequired") and clearance_rank(person.get("clearanceLevel")) < clearance_rank(
        skill.get("clearanceRequired")
    ):
        reasons.append("the person's clearance is below the skill requirement")

    return WorkAuthorisation(allowed=not reasons, credentialState=state, reasons=reasons)


def gap_report(
    *,
    demand: list[dict[str, Any]],
    persons: list[dict[str, Any]],
    credentials: list[dict[str, Any]],
    skills: list[dict[str, Any]],
    at: datetime,
) -> dict[str, Any]:
    """Supply of credentialed people against production demand, by region and trade.

    Supply counts a person once per (region, skill) where they hold a
    credential that is active at ``at``. Nominal headcount is reported
    alongside, and the two are not interchangeable: the gap that matters is
    the credentialed one.
    """
    skill_names = {skill["id"]: skill.get("name") or skill["id"] for skill in skills if skill.get("id")}
    people_by_id = {person["id"]: person for person in persons if person.get("id")}

    demand_by_key: dict[tuple[str, str], int] = {}
    for row in demand:
        region = str(row.get("region") or "UNKNOWN")
        skill_id = str(row.get("skillId") or "")
        if not skill_id:
            raise ValidationError("each demand row must name a skillId")
        headcount = row.get("headcount")
        if not isinstance(headcount, int) or headcount < 0:
            raise ValidationError("each demand row must carry a non-negative integer headcount")
        demand_by_key[(region, skill_id)] = demand_by_key.get((region, skill_id), 0) + headcount

    supply_by_key: dict[tuple[str, str], set[str]] = {}
    for credential in credentials:
        if credential_state(credential, at) != "ACTIVE":
            continue
        person = people_by_id.get(str(credential.get("personId")))
        if person is None:
            continue
        key = (str(person.get("region") or "UNKNOWN"), str(credential.get("skillId")))
        supply_by_key.setdefault(key, set()).add(str(person["id"]))

    headcount_by_region_skill: dict[tuple[str, str], int] = {}
    for person in persons:
        for skill_id in person.get("skillIds") or []:
            key = (str(person.get("region") or "UNKNOWN"), str(skill_id))
            headcount_by_region_skill[key] = headcount_by_region_skill.get(key, 0) + 1

    rows: list[dict[str, Any]] = []
    for key, demand_count in sorted(demand_by_key.items()):
        region, skill_id = key
        supply_count = len(supply_by_key.get(key, set()))
        gap = demand_count - supply_count
        rows.append(
            {
                "region": region,
                "skillId": skill_id,
                "skillName": skill_names.get(skill_id, skill_id),
                "demand": demand_count,
                "credentialedSupply": supply_count,
                "nominalHeadcount": headcount_by_region_skill.get(key, 0),
                "gap": gap,
                "coverage": round(supply_count / demand_count, 4) if demand_count else None,
                "status": "SHORTFALL" if gap > 0 else ("BALANCED" if gap == 0 else "SURPLUS"),
            }
        )

    total_demand = sum(row["demand"] for row in rows)
    total_supply = sum(row["credentialedSupply"] for row in rows)
    return {
        "asOf": at.isoformat(),
        "rows": rows,
        "summary": {
            "demand": total_demand,
            "credentialedSupply": total_supply,
            "gap": total_demand - total_supply,
            "coverage": round(total_supply / total_demand, 4) if total_demand else None,
            "shortfallRows": sum(1 for row in rows if row["status"] == "SHORTFALL"),
        },
    }

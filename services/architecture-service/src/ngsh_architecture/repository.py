"""Storage for the Pillar A read/write models.

Only two things are owned here: the configuration baselines and the interface
definitions. Everything else the service needs - requirements, test results,
articles, systems - is read from the thread projection, which is itself
rebuilt from the event log. Keeping the set small is deliberate: a baseline is
the one Pillar A fact that is not a projection of an event, because it is the
content address of a set of them.
"""

from __future__ import annotations

import json
from typing import Any

from ngsh_core.architecture import Baseline, BaselineMember
from ngsh_core.store import Executor

_BASELINES_DDL = """
CREATE TABLE IF NOT EXISTS architecture_baselines (
    baseline_id         TEXT PRIMARY KEY,
    digest              TEXT NOT NULL,
    system_id           TEXT NOT NULL,
    name                TEXT NOT NULL,
    members_json        TEXT NOT NULL,
    software_builds_json TEXT NOT NULL,
    created_by          TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    notes               TEXT,
    id_version          TEXT NOT NULL,
    tenant              TEXT NOT NULL
)
"""

_BASELINES_INDEX = """
CREATE INDEX IF NOT EXISTS idx_architecture_baselines_system
    ON architecture_baselines (tenant, system_id, created_at)
"""

_INTERFACES_DDL = """
CREATE TABLE IF NOT EXISTS architecture_interfaces (
    digest                TEXT PRIMARY KEY,
    interface_id          TEXT,
    from_system_id        TEXT NOT NULL,
    to_system_id          TEXT NOT NULL,
    characteristics_json  TEXT NOT NULL,
    created_by            TEXT NOT NULL,
    created_at            TEXT NOT NULL,
    tenant                TEXT NOT NULL
)
"""

_INTERFACES_INDEX = """
CREATE INDEX IF NOT EXISTS idx_architecture_interfaces_systems
    ON architecture_interfaces (tenant, from_system_id, to_system_id)
"""


class BaselineRepository:
    """Content-addressed configuration baselines."""

    def __init__(self, db: Executor) -> None:
        self._db = db
        self._db.execute(_BASELINES_DDL)
        self._db.execute(_BASELINES_INDEX)

    def put(self, baseline: Baseline, *, tenant: str) -> bool:
        """Store a baseline. Returns ``True`` only if it was new.

        ``ON CONFLICT DO NOTHING`` makes a repeated creation of the same
        content a no-op rather than an error. The identifier is derived from
        the content, so a conflicting row for the same id would mean the
        digest function changed without the id version being bumped.
        """
        self._db.execute(
            "INSERT INTO architecture_baselines ("
            "baseline_id, digest, system_id, name, members_json, software_builds_json, "
            "created_by, created_at, notes, id_version, tenant"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (baseline_id) DO NOTHING",
            (
                baseline.id,
                baseline.digest,
                baseline.systemId,
                baseline.name,
                json.dumps([member.to_dict() for member in baseline.members], sort_keys=True),
                json.dumps(list(baseline.softwareBuilds)),
                baseline.createdBy,
                baseline.createdAt,
                baseline.notes,
                baseline.idVersion,
                tenant,
            ),
        )
        return self._db.rowcount > 0

    def get(self, baseline_id: str) -> Baseline | None:
        row = self._db.fetchone(
            "SELECT * FROM architecture_baselines WHERE baseline_id = ?",
            (baseline_id,),
        )
        return _row_to_baseline(row) if row else None

    def list(
        self,
        *,
        system_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Baseline]:
        if system_id:
            rows = self._db.fetchall(
                "SELECT * FROM architecture_baselines WHERE system_id = ? "
                "ORDER BY created_at, baseline_id LIMIT ? OFFSET ?",
                (system_id, limit, offset),
            )
        else:
            rows = self._db.fetchall(
                "SELECT * FROM architecture_baselines ORDER BY created_at, baseline_id LIMIT ? OFFSET ?",
                (limit, offset),
            )
        return [_row_to_baseline(row) for row in rows]


class InterfaceRepository:
    """Registered interface definitions, keyed by content digest."""

    def __init__(self, db: Executor) -> None:
        self._db = db
        self._db.execute(_INTERFACES_DDL)
        self._db.execute(_INTERFACES_INDEX)

    def put(self, record: dict[str, Any], *, created_by: str, created_at: str, tenant: str) -> bool:
        self._db.execute(
            "INSERT INTO architecture_interfaces ("
            "digest, interface_id, from_system_id, to_system_id, "
            "characteristics_json, created_by, created_at, tenant"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (digest) DO NOTHING",
            (
                record["digest"],
                record.get("interfaceId"),
                record["fromSystemId"],
                record["toSystemId"],
                json.dumps(record["characteristics"], sort_keys=True),
                created_by,
                created_at,
                tenant,
            ),
        )
        return self._db.rowcount > 0

    def list(
        self,
        *,
        from_system_id: str | None = None,
        to_system_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if from_system_id:
            clauses.append("from_system_id = ?")
            params.append(from_system_id)
        if to_system_id:
            clauses.append("to_system_id = ?")
            params.append(to_system_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._db.fetchall(
            f"SELECT * FROM architecture_interfaces{where} ORDER BY created_at, digest LIMIT ?",
            (*params, limit),
        )
        return [
            {
                "interfaceId": row["interface_id"],
                "fromSystemId": row["from_system_id"],
                "toSystemId": row["to_system_id"],
                "characteristics": json.loads(row["characteristics_json"]),
                "digest": row["digest"],
                "createdBy": row["created_by"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ]


def _row_to_baseline(row: dict[str, Any]) -> Baseline:
    members = tuple(
        BaselineMember(
            entityType=member["entityType"],
            entityId=member["entityId"],
            revision=member.get("revision"),
        )
        for member in json.loads(row["members_json"])
    )
    return Baseline(
        id=row["baseline_id"],
        digest=row["digest"],
        systemId=row["system_id"],
        name=row["name"],
        members=members,
        softwareBuilds=tuple(json.loads(row["software_builds_json"])),
        createdBy=row["created_by"],
        createdAt=row["created_at"],
        notes=row["notes"],
        idVersion=row["id_version"],
    )

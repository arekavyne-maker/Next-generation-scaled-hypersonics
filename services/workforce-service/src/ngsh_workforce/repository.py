"""Content-addressed registries for the Pillar E training artefacts.

Scenarios, curriculum packages and extract manifests are *artefacts*, not
programme facts: they are content, and their identity is their content address.
Keeping them in a small registry is the same pattern the architecture service
uses for baselines, and it keeps the ontology at its published 23 entity types.

A training *completion* is different: it is an authoritative fact about a
person, so it is written as an ``entity.updated`` event on the ``Person`` and
read back from the thread. Nothing here is allowed to become a second source of
truth for a person's qualifications.
"""

from __future__ import annotations

import json
from typing import Any

from ngsh_core.store import Executor

_DDL = """
CREATE TABLE IF NOT EXISTS workforce_artefacts (
    artefact_type  TEXT NOT NULL,
    artefact_id    TEXT NOT NULL,
    body_json      TEXT NOT NULL,
    created_by     TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    tenant         TEXT NOT NULL,
    PRIMARY KEY (artefact_type, artefact_id)
)
"""

_INDEX = """
CREATE INDEX IF NOT EXISTS idx_workforce_artefacts_type
    ON workforce_artefacts (tenant, artefact_type, created_at)
"""


class ArtefactRepository:
    """A content-addressed registry keyed by artefact type and id."""

    def __init__(self, db: Executor) -> None:
        self._db = db
        self._db.execute(_DDL)
        self._db.execute(_INDEX)

    def put(
        self,
        artefact_type: str,
        artefact_id: str,
        body: dict[str, Any],
        *,
        created_by: str,
        created_at: str,
        tenant: str,
    ) -> bool:
        self._db.execute(
            "INSERT INTO workforce_artefacts "
            "(artefact_type, artefact_id, body_json, created_by, created_at, tenant) "
            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (artefact_type, artefact_id) DO NOTHING",
            (
                artefact_type,
                artefact_id,
                json.dumps(body, sort_keys=True),
                created_by,
                created_at,
                tenant,
            ),
        )
        return self._db.rowcount > 0

    def get(self, artefact_type: str, artefact_id: str) -> dict[str, Any] | None:
        row = self._db.fetchone(
            "SELECT body_json FROM workforce_artefacts WHERE artefact_type = ? AND artefact_id = ?",
            (artefact_type, artefact_id),
        )
        return json.loads(row["body_json"]) if row else None

    def list(
        self,
        artefact_type: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        rows = self._db.fetchall(
            "SELECT body_json FROM workforce_artefacts WHERE artefact_type = ? "
            "ORDER BY created_at, artefact_id LIMIT ? OFFSET ?",
            (artefact_type, limit, offset),
        )
        return [json.loads(row["body_json"]) for row in rows]

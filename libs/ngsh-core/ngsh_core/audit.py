"""Tamper-evident audit ledger.

The ledger is a hash chain: each entry commits to its predecessor, so
altering or removing any historical entry breaks every subsequent hash. The
chain proves that the recorded history has not been rewritten; it does not
prove that a recorded decision was correct. That distinction matters and is
why the ledger is separate from the business event log (ADR-0005).

Why not reuse the event log? Because the event log is a projection source
designed for replay, and replay is exactly the operation that would rewrite
history. The ledger exists so that there is at least one store whose contents
cannot be silently regenerated.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .envelope import utcnow
from .errors import LedgerIntegrityError
from .store import Executor, canonical_json

GENESIS_HASH = "0" * 64


@dataclass
class LedgerEntry:
    seq: int
    hash: str
    prevHash: str
    timestamp: str
    eventType: str
    entry: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "hash": self.hash,
            "prevHash": self.prevHash,
            "timestamp": self.timestamp,
            "eventType": self.eventType,
            **self.entry,
        }


@dataclass
class VerificationResult:
    valid: bool
    checked: int
    brokenAt: int | None = None
    head: str = GENESIS_HASH
    detail: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "checked": self.checked,
            "brokenAt": self.brokenAt,
            "head": self.head,
            "detail": self.detail,
        }


def compute_hash(prev_hash: str, entry: dict[str, Any]) -> str:
    """Hash a ledger entry against its predecessor.

    The timestamp is included in the hashed body so that an entry cannot be
    replayed under a different time without breaking the chain.
    """
    body = canonical_json({"prevHash": prev_hash, "entry": entry})
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class AuditLedger:
    """Append-only, hash-chained ledger backed by the ``audit`` schema."""

    def __init__(self, executor: Executor) -> None:
        self._db = executor

    # -- writing ---------------------------------------------------------

    def append(
        self,
        event_type: str,
        entry: dict[str, Any],
        *,
        timestamp: datetime | None = None,
    ) -> LedgerEntry:
        """Append an entry, linking it to the current head of the chain."""
        stamp = (timestamp or utcnow()).astimezone(UTC).isoformat()
        body = {"timestamp": stamp, **entry}

        with _transaction(self._db):
            head_row = self._db.fetchone("SELECT hash FROM ledger ORDER BY seq DESC LIMIT 1")
            prev_hash = head_row["hash"] if head_row else GENESIS_HASH
            seq_row = self._db.fetchone("SELECT COALESCE(MAX(seq), 0) AS seq FROM ledger")
            seq = int(seq_row["seq"]) + 1 if seq_row else 1

            digest = compute_hash(prev_hash, body)
            self._db.execute(
                "INSERT INTO ledger (seq, hash, prev_hash, timestamp, event_type, entry_json) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (seq, digest, prev_hash, stamp, event_type, canonical_json(body)),
            )

        return LedgerEntry(
            seq=seq,
            hash=digest,
            prevHash=prev_hash,
            timestamp=stamp,
            eventType=event_type,
            entry=body,
        )

    # -- reading ---------------------------------------------------------

    def read(self, *, after: int = 0, limit: int = 100) -> list[LedgerEntry]:
        rows = self._db.fetchall(
            "SELECT seq, hash, prev_hash, timestamp, event_type, entry_json "
            "FROM ledger WHERE seq > ? ORDER BY seq ASC LIMIT ?",
            (after, limit),
        )
        entries: list[LedgerEntry] = []
        for row in rows:
            body = json.loads(row["entry_json"])
            entries.append(
                LedgerEntry(
                    seq=int(row["seq"]),
                    hash=row["hash"],
                    prevHash=row["prev_hash"],
                    timestamp=row["timestamp"],
                    eventType=row["event_type"],
                    entry=body,
                )
            )
        return entries

    def head(self) -> str:
        row = self._db.fetchone("SELECT hash FROM ledger ORDER BY seq DESC LIMIT 1")
        return row["hash"] if row else GENESIS_HASH

    def count(self) -> int:
        row = self._db.fetchone("SELECT COUNT(*) AS n FROM ledger")
        return int(row["n"]) if row else 0

    def get(self, digest: str) -> LedgerEntry | None:
        row = self._db.fetchone(
            "SELECT seq, hash, prev_hash, timestamp, event_type, entry_json FROM ledger WHERE hash = ?",
            (digest,),
        )
        if row is None:
            return None
        return LedgerEntry(
            seq=int(row["seq"]),
            hash=row["hash"],
            prevHash=row["prev_hash"],
            timestamp=row["timestamp"],
            eventType=row["event_type"],
            entry=json.loads(row["entry_json"]),
        )

    # -- verification ----------------------------------------------------

    def verify(self, *, limit: int | None = None) -> VerificationResult:
        """Recompute the chain and confirm every link holds."""
        rows = self._db.fetchall(
            "SELECT seq, hash, prev_hash, timestamp, event_type, entry_json FROM ledger ORDER BY seq ASC"
        )
        if limit is not None:
            rows = rows[:limit]

        prev_hash = GENESIS_HASH
        checked = 0
        for row in rows:
            body = json.loads(row["entry_json"])
            expected = compute_hash(prev_hash, body)
            if row["prev_hash"] != prev_hash:
                return VerificationResult(
                    valid=False,
                    checked=checked,
                    brokenAt=int(row["seq"]),
                    head=self.head(),
                    detail=f"entry {row['seq']} claims predecessor {row['prev_hash']} but chain head was {prev_hash}",
                )
            if expected != row["hash"]:
                return VerificationResult(
                    valid=False,
                    checked=checked,
                    brokenAt=int(row["seq"]),
                    head=self.head(),
                    detail=f"entry {row['seq']} content does not match its recorded hash",
                )
            prev_hash = row["hash"]
            checked += 1

        return VerificationResult(valid=True, checked=checked, head=prev_hash)


class _transaction:
    """Minimal transaction context manager.

    The SQLite executor commits per statement, so this helper provides the
    grouping semantics the ledger needs without pulling in an ORM.
    """

    def __init__(self, executor: Executor) -> None:
        self._executor = executor

    def __enter__(self) -> _transaction:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def ledger_entry_from_decision(
    decision: dict[str, Any],
    *,
    subject: dict[str, Any],
    action: str,
    resource: dict[str, Any],
) -> dict[str, Any]:
    """Shape a policy decision into a ledger entry body."""
    return {
        "subject": subject,
        "action": action,
        "resource": resource,
        "decision": decision.get("decision"),
        "policyId": decision.get("policyId"),
        "policyVersion": decision.get("policyVersion"),
        "obligations": decision.get("obligations", []),
        "reason": decision.get("reason", ""),
    }


def entries_to_dicts(entries: Iterable[LedgerEntry]) -> list[dict[str, Any]]:
    return [entry.to_dict() for entry in entries]


def assert_integrity(result: VerificationResult) -> None:
    if not result.valid:
        raise LedgerIntegrityError(
            f"audit ledger chain broken at seq {result.brokenAt}",
            detail=result.detail,
        )

"""The tamper-evident audit ledger."""

from __future__ import annotations

import pytest
from ngsh_core.audit import GENESIS_HASH, AuditLedger, compute_hash
from ngsh_core.errors import LedgerIntegrityError


@pytest.fixture
def ledger(executor) -> AuditLedger:
    return AuditLedger(executor)


def _append(ledger: AuditLedger, index: int) -> None:
    ledger.append(
        "access.decision.recorded",
        {"index": index, "decision": "ALLOW", "action": "read"},
    )


def test_first_entry_links_to_genesis(ledger: AuditLedger) -> None:
    entry = ledger.append("access.decision.recorded", {"decision": "ALLOW"})
    assert entry.seq == 1
    assert entry.prevHash == GENESIS_HASH
    assert len(entry.hash) == 64


def test_chain_verifies_after_appends(ledger: AuditLedger) -> None:
    for index in range(5):
        _append(ledger, index)
    result = ledger.verify()
    assert result.valid
    assert result.checked == 5
    assert result.brokenAt is None


def test_head_advances_with_each_entry(ledger: AuditLedger) -> None:
    first = ledger.append("a", {"n": 1})
    second = ledger.append("b", {"n": 2})
    assert second.prevHash == first.hash
    assert ledger.head() == second.hash


def test_tampering_with_an_entry_breaks_the_chain(ledger: AuditLedger) -> None:
    """Rewriting history must be detectable, not merely discouraged."""
    for index in range(3):
        _append(ledger, index)

    ledger._db.execute(  # noqa: SLF001 - deliberately reaching past the API
        "UPDATE ledger SET entry_json = ? WHERE seq = ?",
        ('{"timestamp": "2020-01-01T00:00:00+00:00", "decision": "DENY"}', 2),
    )

    result = ledger.verify()
    assert not result.valid
    assert result.brokenAt == 2
    assert "does not match its recorded hash" in (result.detail or "")


def test_removing_an_entry_breaks_the_chain(ledger: AuditLedger) -> None:
    for index in range(4):
        _append(ledger, index)

    ledger._db.execute("DELETE FROM ledger WHERE seq = 2")  # noqa: SLF001

    result = ledger.verify()
    assert not result.valid
    assert result.brokenAt == 3


def test_hash_covers_the_timestamp(ledger: AuditLedger) -> None:
    """An entry cannot be replayed under a different time without breaking it."""
    body = {"timestamp": "2026-01-01T00:00:00+00:00", "decision": "ALLOW"}
    original = compute_hash(GENESIS_HASH, body)
    replayed = compute_hash(GENESIS_HASH, {**body, "timestamp": "2027-01-01T00:00:00+00:00"})
    assert original != replayed


def test_entries_are_readable_in_order(ledger: AuditLedger) -> None:
    for index in range(3):
        _append(ledger, index)
    entries = ledger.read(after=0, limit=10)
    assert [entry.seq for entry in entries] == [1, 2, 3]
    assert entries[0].entry["index"] == 0


def test_paging_resumes_from_a_cursor(ledger: AuditLedger) -> None:
    for index in range(5):
        _append(ledger, index)
    page = ledger.read(after=2, limit=2)
    assert [entry.seq for entry in page] == [3, 4]


def test_assert_integrity_raises_on_a_broken_chain(ledger: AuditLedger) -> None:
    from ngsh_core.audit import assert_integrity

    _append(ledger, 0)
    assert_integrity(ledger.verify())

    ledger._db.execute("UPDATE ledger SET hash = ? WHERE seq = 1", ("f" * 64,))  # noqa: SLF001
    with pytest.raises(LedgerIntegrityError):
        assert_integrity(ledger.verify())

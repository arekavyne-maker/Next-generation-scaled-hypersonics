"""The attribute-based access control engine."""

from __future__ import annotations

from pathlib import Path

import pytest
from ngsh_core.envelope import Actor
from ngsh_core.errors import ValidationError
from ngsh_core.policy import PolicySet, Resource, clearance_rank

REPO_ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = REPO_ROOT / "contracts" / "policy" / "access-policy.json"


@pytest.fixture(scope="module")
def policy_set() -> PolicySet:
    return PolicySet.load(POLICY_PATH)


def _subject(**overrides) -> Actor:
    base = {
        "subjectId": "usr:engineer",
        "kind": "user",
        "clearance": "TOP SECRET",
        "citizenship": "US",
        "tenant": "ngsh",
        "programs": ["NGSH-SHY"],
        "needToKnow": ["NGSH-SHY"],
    }
    base.update(overrides)
    return Actor(**base)


def _resource(**overrides) -> Resource:
    base = {
        "type": "TestResult",
        "id": "TR:0001",
        "classification": "CUI",
        "tenant": "ngsh",
        "program": "NGSH-SHY",
    }
    base.update(overrides)
    return Resource(**base)


def test_default_is_deny(policy_set: PolicySet) -> None:
    """An unmatched request must not fall through to an allow."""
    assert policy_set.default_effect == "DENY"
    decision = policy_set.evaluate(
        _subject(),
        _resource(type="SomethingNotInThePolicy"),
        "read",
    )
    assert decision.decision == "DENY"
    assert decision.policyId is None


def test_cleared_engineer_with_need_to_know_is_allowed(policy_set: PolicySet) -> None:
    decision = policy_set.evaluate(_subject(), _resource(), "read")
    assert decision.decision == "ALLOW"
    assert decision.policyId == "POL-ALLOW-012"


def test_explicit_deny_beats_an_allowing_rule(policy_set: PolicySet) -> None:
    """A foreign citizen cannot reach CUI, even though the allow rule matches."""
    decision = policy_set.evaluate(
        _subject(citizenship="FOREIGN"),
        _resource(),
        "read",
    )
    assert decision.decision == "DENY"
    assert decision.policyId == "POL-DENY-002"


def test_cross_tenant_access_is_denied(policy_set: PolicySet) -> None:
    decision = policy_set.evaluate(
        _subject(tenant="ngsh"),
        _resource(tenant="other-program"),
        "read",
    )
    assert decision.decision == "DENY"
    assert decision.policyId == "POL-DENY-001"


def test_insufficient_clearance_is_denied(policy_set: PolicySet) -> None:
    decision = policy_set.evaluate(
        _subject(clearance="SECRET"),
        _resource(classification="TOP SECRET"),
        "read",
    )
    assert decision.decision == "DENY"
    assert decision.policyId == "POL-DENY-004"


def test_missing_need_to_know_is_denied(policy_set: PolicySet) -> None:
    decision = policy_set.evaluate(
        _subject(needToKnow=[]),
        _resource(),
        "read",
    )
    assert decision.decision == "DENY"
    assert decision.policyId == "POL-DENY-007"


def test_test_results_are_immutable(policy_set: PolicySet) -> None:
    """Constraint C-003: a test result may be read but never edited in place."""
    assert policy_set.evaluate(_subject(), _resource(), "read").decision == "ALLOW"
    decision = policy_set.evaluate(_subject(), _resource(), "update")
    assert decision.decision == "DENY"
    assert decision.policyId == "POL-DENY-005"


def test_audit_ledger_is_append_only(policy_set: PolicySet) -> None:
    decision = policy_set.evaluate(
        _subject(),
        _resource(type="AuditLedger"),
        "delete",
    )
    assert decision.decision == "DENY"
    assert decision.policyId == "POL-DENY-006"


def test_sanitised_extract_is_readable_by_academic_partners(policy_set: PolicySet) -> None:
    """The extract has already been through the cross-domain guard."""
    decision = policy_set.evaluate(
        _subject(citizenship="FOREIGN", clearance="NONE", programs=[], needToKnow=[]),
        _resource(type="SanitizedExtract", classification="UNCLASSIFIED", program=None),
        "read",
    )
    assert decision.decision == "ALLOW"
    assert decision.policyId == "POL-ALLOW-013"
    assert "watermark" in decision.obligations
    assert "no-export" in decision.obligations


def test_obligations_are_derived_for_foreign_reads(policy_set: PolicySet) -> None:
    """A foreign subject reading a sanitised extract still gets no-export."""
    decision = policy_set.evaluate(
        _subject(citizenship="ALLIED", clearance="NONE", programs=[], needToKnow=[]),
        _resource(type="SanitizedExtract", classification="UNCLASSIFIED", program=None),
        "read",
    )
    assert "no-export" in decision.obligations


def test_structural_metadata_is_readable_by_everyone(policy_set: PolicySet) -> None:
    decision = policy_set.evaluate(
        _subject(clearance="NONE", citizenship="FOREIGN", programs=[], needToKnow=[]),
        _resource(type="OntologyRegistry", classification="UNCLASSIFIED", program=None),
        "read",
    )
    assert decision.decision == "ALLOW"
    assert decision.policyId == "POL-ALLOW-015"


def test_edge_agents_may_append_but_not_read(policy_set: PolicySet) -> None:
    """An edge node captures observations but never reads the wider fabric."""
    edge = _subject(subjectId="edge:factory-3", kind="edge-agent")
    assert policy_set.evaluate(edge, _resource(), "append").decision == "ALLOW"
    assert policy_set.evaluate(edge, _resource(), "read").decision == "DENY"


def test_unsupported_operator_is_an_error_not_a_silent_deny(policy_set: PolicySet) -> None:
    """A typo in a policy rule must be loud, not quietly permissive."""
    rule_set = PolicySet.from_dict(
        {
            "policyVersion": "test",
            "rules": [
                {
                    "id": "T-1",
                    "effect": "ALLOW",
                    "when": {"attr": "subject.kind", "op": "totally_made_up", "value": "user"},
                }
            ],
        }
    )
    with pytest.raises(ValidationError):
        rule_set.evaluate(_subject(), _resource(), "read")


def test_clearance_ranking() -> None:
    assert clearance_rank("NONE") == 0
    assert clearance_rank("SECRET") == 1
    assert clearance_rank("TOP SECRET") == 2
    assert clearance_rank("SCI-CLEARED") == 3
    assert clearance_rank(None) == 0

"""Identifier generation."""

from __future__ import annotations

from ngsh_core.ids import domain_id, new_ulid, split_domain_id, ulid_timestamp


def test_ulid_has_the_expected_shape() -> None:
    value = new_ulid()
    assert len(value) == 26
    assert value.isalnum()
    assert value == value.upper()


def test_ulids_sort_by_creation_time() -> None:
    """Lexicographic order must match creation order, or replay breaks."""
    generated = [new_ulid() for _ in range(200)]
    assert generated == sorted(generated)


def test_ulid_carries_a_timestamp() -> None:
    value = new_ulid()
    assert ulid_timestamp(value) > 1_600_000_000_000


def test_domain_keys_round_trip() -> None:
    key = domain_id("TR", "01J8ZABC")
    assert key == "TR:01J8ZABC"
    prefix, remainder = split_domain_id(key)
    assert prefix == "TR"
    assert remainder == "01J8ZABC"


def test_identifiers_without_a_prefix_are_tolerated() -> None:
    prefix, remainder = split_domain_id("bare-value")
    assert prefix is None
    assert remainder == "bare-value"

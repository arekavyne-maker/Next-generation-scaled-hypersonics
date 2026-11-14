"""Classification handling."""

from __future__ import annotations

import pytest
from ngsh_core.classification import (
    ClassificationLevel,
    at_least,
    join_levels,
    max_level,
    parse_level,
    partition_key,
)


def test_levels_are_ordered_by_restriction() -> None:
    assert parse_level("UNCLASSIFIED") < parse_level("CUI")
    assert parse_level("CUI") < parse_level("RESTRICTED")
    assert parse_level("RESTRICTED") < parse_level("SECRET")
    assert parse_level("SECRET") < parse_level("TOP SECRET")


def test_unknown_label_fails_closed() -> None:
    """An unrecognised marking is treated as more restricted, never less."""
    assert parse_level("SOMETHING-ELSE") == ClassificationLevel.RESTRICTED
    assert parse_level("") == ClassificationLevel.UNCLASSIFIED
    assert parse_level(None) == ClassificationLevel.UNCLASSIFIED


def test_aliases_resolve() -> None:
    assert parse_level("cui//rel") == ClassificationLevel.CUI_REL
    assert parse_level("CUI//RELATIVES") == ClassificationLevel.CUI_REL
    assert parse_level("TOPSECRET") == ClassificationLevel.TOP_SECRET


def test_max_level_picks_the_most_restrictive() -> None:
    assert max_level("CUI", "SECRET", "UNCLASSIFIED") == ClassificationLevel.SECRET
    assert join_levels(["CUI", None, "TOP SECRET"]) == ClassificationLevel.TOP_SECRET
    assert join_levels([]) == ClassificationLevel.UNCLASSIFIED


def test_at_least_compares_against_a_floor() -> None:
    assert at_least("SECRET", "CUI")
    assert at_least("CUI", "CUI")
    assert not at_least("CUI", "SECRET")


@pytest.mark.parametrize(
    ("level", "expected"),
    [
        ("UNCLASSIFIED", "unclassified"),
        ("CUI", "cui"),
        ("CUI//FOUO", "cui"),
        ("RESTRICTED", "restricted"),
        ("SECRET", "restricted"),
        ("TOP SECRET", "restricted"),
    ],
)
def test_partition_key_groups_the_storage_boundary(level: str, expected: str) -> None:
    """The accreditation boundary sits between CUI and RESTRICTED."""
    assert partition_key(level) == expected

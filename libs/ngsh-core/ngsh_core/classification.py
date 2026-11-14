"""Classification handling.

Classification is the axis that shapes every NGSH storage and transport
decision, so it is modelled explicitly rather than as a string field.

Two rules drive the design:

1. A record's classification may never be *lower* than the floor declared for
   its ontology type (registry constraint C-001). This prevents downgrade by
   construction.
2. A relation may not bridge a classification boundary unless its relation type
   is explicitly declared cross-classification-capable (constraint C-002).

Storage partitioning derives from this module: ``partition_key`` returns the
physical bucket a record must be written to.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import IntEnum


class ClassificationLevel(IntEnum):
    """Ordered handling levels. Higher value means more restricted."""

    UNCLASSIFIED = 0
    CUI = 10
    CUI_REL = 11
    CUI_FOUO = 12
    RESTRICTED = 20
    SECRET = 30
    TOP_SECRET = 40

    @property
    def label(self) -> str:
        return _LEVEL_LABELS[self]


_LEVEL_LABELS: dict[ClassificationLevel, str] = {
    ClassificationLevel.UNCLASSIFIED: "UNCLASSIFIED",
    ClassificationLevel.CUI: "CUI",
    ClassificationLevel.CUI_REL: "CUI//REL",
    ClassificationLevel.CUI_FOUO: "CUI//FOUO",
    ClassificationLevel.RESTRICTED: "RESTRICTED",
    ClassificationLevel.SECRET: "SECRET",
    ClassificationLevel.TOP_SECRET: "TOP SECRET",
}

_LABEL_TO_LEVEL: dict[str, ClassificationLevel] = {
    "UNCLASSIFIED": ClassificationLevel.UNCLASSIFIED,
    "CUI": ClassificationLevel.CUI,
    "CUI//REL": ClassificationLevel.CUI_REL,
    "CUI//RELATIVES": ClassificationLevel.CUI_REL,
    "CUI//FOUO": ClassificationLevel.CUI_FOUO,
    "RESTRICTED": ClassificationLevel.RESTRICTED,
    "SECRET": ClassificationLevel.SECRET,
    "TOP SECRET": ClassificationLevel.TOP_SECRET,
    "TOPSECRET": ClassificationLevel.TOP_SECRET,
}


def parse_level(value: str | ClassificationLevel | None) -> ClassificationLevel:
    """Parse a classification label into a level.

    ``None`` and the empty string mean "not specified" and resolve to
    UNCLASSIFIED. Any *unrecognised* label resolves to RESTRICTED, because
    failing closed is the correct behaviour for a classification parser: an
    unrecognised marking is treated as more restricted, never as
    unclassified.
    """
    if value is None:
        return ClassificationLevel.UNCLASSIFIED
    if isinstance(value, ClassificationLevel):
        return value
    key = value.strip().upper()
    if not key:
        return ClassificationLevel.UNCLASSIFIED
    if key in _LABEL_TO_LEVEL:
        return _LABEL_TO_LEVEL[key]
    return ClassificationLevel.RESTRICTED


def max_level(*levels: str | ClassificationLevel | None) -> ClassificationLevel:
    """Return the most restrictive of the supplied levels."""
    resolved = [parse_level(level) for level in levels if level is not None]
    if not resolved:
        return ClassificationLevel.UNCLASSIFIED
    return max(resolved)


def at_least(value: str | ClassificationLevel, floor: str | ClassificationLevel) -> bool:
    """True when ``value`` is at least as restrictive as ``floor``."""
    return parse_level(value) >= parse_level(floor)


def partition_key(level: str | ClassificationLevel) -> str:
    """Physical storage partition for a classification level.

    Storage separates UNCLASSIFIED and CUI records from RESTRICTED-and-above
    records, because the accreditation boundary sits there. Within a partition
    the finer-grained level is enforced by the storage policy, not by the
    partition key itself.
    """
    parsed = parse_level(level)
    if parsed >= ClassificationLevel.RESTRICTED:
        return "restricted"
    if parsed >= ClassificationLevel.CUI:
        return "cui"
    return "unclassified"


def sanitize_level(level: str | ClassificationLevel) -> ClassificationLevel:
    """Level assigned to a derived extract.

    Sanitised extracts released to academic partners are always UNCLASSIFIED;
    the caller must have already run the content review that permits the
    release. This function records that decision, it does not make it.
    """
    return ClassificationLevel.UNCLASSIFIED


def join_levels(levels: Iterable[str | ClassificationLevel | None]) -> ClassificationLevel:
    """Most restrictive level across an iterable."""
    return max_level(*list(levels))

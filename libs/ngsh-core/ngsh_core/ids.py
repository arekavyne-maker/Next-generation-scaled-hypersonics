"""Identifier generation.

NGSH uses two identifier families:

``ULID``
    128-bit, Crockford base32, lexicographically sortable by creation time.
    Used for events, where sort order must match causal order so that replay
    is deterministic and a cursor can be a plain string.

``Domain key``
    Human-referenceable identifiers such as ``TR:01J8Z...`` or ``PART:NSN-4472``.
    The prefix comes from the ontology registry (``idPrefix``) and makes the
    entity type obvious in a log line, a terminal, or a person's clipboard.
"""

from __future__ import annotations

import os
import threading
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_LENGTH = 26

_lock = threading.Lock()
_last_timestamp = 0
_last_random = 0


def _encode(value: int, length: int) -> str:
    chars = []
    for _ in range(length):
        chars.append(_CROCKFORD[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def _encode_timestamp(ms: int) -> str:
    return _encode(ms, 10)


def _encode_random(value: int) -> str:
    return _encode(value, 16)


def new_ulid(timestamp_ms: int | None = None) -> str:
    """Return a fresh ULID.

    Within the same millisecond the random component is incremented rather than
    regenerated, so ULIDs minted in a tight loop still sort in creation order.
    """
    global _last_timestamp, _last_random

    now = int(time.time() * 1000) if timestamp_ms is None else timestamp_ms
    with _lock:
        if now == _last_timestamp:
            _last_random = (_last_random + 1) & ((1 << 80) - 1)
        else:
            if now < _last_timestamp:
                # Clock went backwards. Keep monotonicity by staying on the last
                # timestamp and bumping the random component.
                now = _last_timestamp
                _last_random = (_last_random + 1) & ((1 << 80) - 1)
            else:
                _last_timestamp = now
                _last_random = int.from_bytes(os.urandom(10), "big")
        return _encode_timestamp(now) + _encode_random(_last_random)


def ulid_timestamp(ulid: str) -> int:
    """Extract the epoch-millisecond timestamp encoded in a ULID."""
    if len(ulid) < 10:
        raise ValueError(f"not a ULID: {ulid!r}")
    value = 0
    for char in ulid[:10]:
        value = (value << 5) | _CROCKFORD.index(char.upper())
    return value


def domain_id(prefix: str, identifier: str) -> str:
    """Build a domain key such as ``TR:01J8Z...``."""
    return f"{prefix}:{identifier}"


def split_domain_id(value: str) -> tuple[str | None, str]:
    """Split ``PREFIX:key`` into its parts.

    Returns ``(None, value)`` when the identifier carries no prefix.
    """
    if ":" not in value:
        return None, value
    prefix, _, remainder = value.partition(":")
    if not prefix or not remainder:
        return None, value
    return prefix, remainder

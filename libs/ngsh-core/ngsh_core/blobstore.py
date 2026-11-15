"""Content-addressed object storage for the test-data lake (C-1).

The lake is not a second source of truth. It holds **bytes** whose identity is
their SHA-256, and the thread holds the entity that references them. A dataset
URI can therefore be resolved, re-hashed and verified independently of any
catalogue: the catalogue can be rebuilt, the bytes cannot silently change.

The local backend is a directory tree. An accredited deployment swaps the
backend for the enclave object store; the digest, metadata and verification
contract stays the same.
"""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import NotFoundError, ValidationError

_DIGEST_LENGTH = 64


def is_digest(value: str) -> bool:
    if not isinstance(value, str) or len(value) != _DIGEST_LENGTH:
        return False
    return all(character in "0123456789abcdef" for character in value.lower())


class BlobStore:
    """A content-addressed blob store rooted at a local directory."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _paths(self, digest: str) -> tuple[Path, Path]:
        if not is_digest(digest):
            raise ValidationError("a lakehouse digest must be 64 hexadecimal characters")
        directory = self.root / "objects" / digest[:2] / digest[2:4]
        return directory / f"{digest}.bin", directory / f"{digest}.json"

    @staticmethod
    def digest(content: bytes) -> str:
        if not isinstance(content, bytes):
            raise ValidationError("lakehouse content must be bytes")
        return hashlib.sha256(content).hexdigest()

    def put(
        self,
        content: bytes,
        *,
        media_type: str = "application/octet-stream",
        metadata: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        """Write bytes once and return their content-addressed record."""
        digest = self.digest(content)
        binary, sidecar = self._paths(digest)
        binary.parent.mkdir(parents=True, exist_ok=True)

        with self._lock:
            if not binary.exists():
                temporary = binary.with_suffix(".tmp")
                temporary.write_bytes(content)
                temporary.replace(binary)
            record = {
                "digest": digest,
                "uri": f"ngsh-lake://{digest}",
                "sizeBytes": len(content),
                "mediaType": media_type,
                "createdAt": created_at or datetime.now(UTC).isoformat(),
                "metadata": metadata or {},
                "storage": "local-content-addressed",
            }
            sidecar.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        return record

    def metadata(self, digest: str) -> dict[str, Any]:
        binary, sidecar = self._paths(digest)
        if not binary.exists() or not sidecar.exists():
            raise NotFoundError(f"no lakehouse object with digest {digest!r}")
        record = json.loads(sidecar.read_text())
        record["sizeBytes"] = binary.stat().st_size
        return record

    def get(self, digest: str) -> tuple[bytes, dict[str, Any]]:
        binary, _ = self._paths(digest)
        if not binary.exists():
            raise NotFoundError(f"no lakehouse object with digest {digest!r}")
        return binary.read_bytes(), self.metadata(digest)

    def verify(self, digest: str) -> dict[str, Any]:
        content, record = self.get(digest)
        actual = self.digest(content)
        return {
            "digest": digest,
            "valid": actual == digest,
            "actualDigest": actual,
            "sizeBytes": len(content),
            "uri": record["uri"],
        }

    def list(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if not isinstance(limit, int) or limit < 1:
            raise ValidationError("'limit' must be a positive integer")
        records: list[dict[str, Any]] = []
        for sidecar in sorted(self.root.glob("objects/*/*/*.json")):
            try:
                record = json.loads(sidecar.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            records.append(record)
        records.sort(key=lambda item: (item.get("createdAt") or "", item.get("digest") or ""), reverse=True)
        return records[:limit]

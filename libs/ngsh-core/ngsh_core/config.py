"""Runtime configuration.

Every setting is read from the environment with a neutral default so that the
same image runs unchanged in an accredited cloud, on a segregated on-prem node,
or on a disconnected edge annex. There are no cloud-provider settings here by
design (ADR-0003): the abstraction layer is the configuration surface, and
provider-specific detail enters only through opaque connection strings.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return default if value is None or value == "" else value


def _env_alias(names: tuple[str, ...], default: str) -> str:
    """Read the first environment variable that is set among ``names``.

    Container platforms conventionally inject ``PORT`` and ``DATABASE_URL``;
    the platform's own names are ``NGSH_PORT`` and ``NGSH_DSN``. Both are
    accepted so that the same image runs unmodified in either convention,
    which is a requirement of the platform-agnostic deployment model
    (ADR-0003).
    """
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def repo_root() -> Path:
    """Locate the repository root by walking up for the contracts directory."""
    override = os.environ.get("NGSH_REPO_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    here = Path(__file__).resolve()
    for candidate in here.parents:
        if (candidate / "contracts" / "ontology" / "registry.json").exists():
            return candidate
    return here.parents[3]


@dataclass(frozen=True)
class Settings:
    """Resolved service settings."""

    service_name: str = field(default_factory=lambda: _env("NGSH_SERVICE_NAME", "ngsh-service"))
    tenant: str = field(default_factory=lambda: _env("NGSH_TENANT", "ngsh"))
    program: str | None = field(default_factory=lambda: os.environ.get("NGSH_PROGRAM"))

    # Storage. SQLite by default so the platform runs with no external
    # dependency; the DSN switches to Postgres in an accredited environment.
    dsn: str = field(
        default_factory=lambda: _env_alias(("NGSH_DSN", "DATABASE_URL"), "sqlite:///./data/ngsh.db")
    )
    db_echo: bool = field(default_factory=lambda: _env_bool("NGSH_DB_ECHO", False))

    # Deployment profile, one of: local, il5, il6, edge.
    deployment_profile: str = field(default_factory=lambda: _env("NGSH_DEPLOYMENT_PROFILE", "local"))
    deployment_zone: str = field(default_factory=lambda: _env("NGSH_DEPLOYMENT_ZONE", "central"))

    # Identity provider adapter: 'piv' | 'stub'.
    identity_provider: str = field(default_factory=lambda: _env("NGSH_IDENTITY_PROVIDER", "stub"))

    # Policy.
    policy_file: str = field(
        default_factory=lambda: _env("NGSH_POLICY_FILE", "contracts/policy/access-policy.json")
    )
    #: Identifies this service as the enforcement point that produced a
    #: decision. Recorded in the ledger and in the event so the trail shows
    #: where a decision was made, not merely that one was (ADR-0004).
    enforcement_point: str = field(
        default_factory=lambda: _env(
            "NGSH_ENFORCEMENT_POINT", f"{_env('NGSH_SERVICE_NAME', 'ngsh-service')}/pep"
        )
    )
    policy_version: str = field(default_factory=lambda: _env("NGSH_POLICY_VERSION", "1.0.0"))

    # Audit ledger.
    ledger_checkpoint_every: int = field(
        default_factory=lambda: _env_int("NGSH_LEDGER_CHECKPOINT_EVERY", 1000)
    )

    # HTTP.
    host: str = field(default_factory=lambda: _env("NGSH_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _env_int("NGSH_PORT", _env_int("PORT", 8080)))

    # Service discovery for the fabric. Falls back to in-process defaults so
    # that a single service can run standalone.
    fabric_url: str = field(default_factory=lambda: _env("NGSH_FABRIC_URL", ""))
    policy_url: str = field(default_factory=lambda: _env("NGSH_POLICY_URL", ""))
    audit_url: str = field(default_factory=lambda: _env("NGSH_AUDIT_URL", ""))
    ontology_url: str = field(default_factory=lambda: _env("NGSH_ONTOLOGY_URL", ""))
    thread_url: str = field(default_factory=lambda: _env("NGSH_THREAD_URL", ""))

    #: Citizenships permitted to hold a credential for export-controlled
    #: activity (C-005). The default is restrictive on purpose.
    permitted_citizenships: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            item.strip().upper()
            for item in _env("NGSH_PERMITTED_CITIZENSHIPS", "US").split(",")
            if item.strip()
        )
    )

    @property
    def contracts_dir(self) -> Path:
        return repo_root() / "contracts"

    @property
    def sqlite_path(self) -> Path | None:
        if self.dsn.startswith("sqlite:///"):
            raw = self.dsn[len("sqlite:///") :]
            if raw in {"", ":memory:"}:
                return None
            return Path(raw).expanduser()
        return None


def load_settings() -> Settings:
    return Settings()

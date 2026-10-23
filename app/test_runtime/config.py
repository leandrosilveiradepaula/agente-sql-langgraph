from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from app.config.context_fingerprint import (
    EXPECTED_CONTEXT_FINGERPRINT_ENV,
    validate_expected_context_fingerprint,
)
from app.config.postgres_context import (
    DEFAULT_POSTGRES_CONTEXT_SCHEMA,
    POSTGRES_CONTEXT_SCHEMA_ENV,
    validate_postgres_context_schema,
)


RUNTIME_MODE = "shadow_test"
PERSISTENCE_POSTGRES = "postgres"
CONTEXT_POSTGRES_DSN_ENV = "CONTEXT_POSTGRES_DSN"
SEMANTIC_AGENT_VERSION_ENV = "SEMANTIC_AGENT_VERSION"
POSTGRES_CONNECT_TIMEOUT_ENV = "POSTGRES_CONNECT_TIMEOUT_SECONDS"
DEFAULT_POSTGRES_CONNECT_TIMEOUT_SECONDS = 10
CONTEXT_CATALOG_TABLES_ENV = "CONTEXT_CATALOG_TABLES_JSON"
_CONTEXT_CATALOG_KEYS = frozenset({"rules", "entities", "dre", "patterns", "catalog"})
_CONTEXT_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_EXPECTED_ORGANIZATION_ID_ENV = "LANGGRAPH_EXPECTED_ORGANIZATION_ID"
_ORGANIZATION_SCOPE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


@dataclass(frozen=True, slots=True)
class ShadowTestRuntimeConfig:
    runtime_mode: str
    http_host: str
    http_port: int
    shadow_persistence: str
    shadow_database_dsn: str = field(repr=False)
    context_postgres_dsn: str = field(repr=False)
    semantic_agent_version: str
    context_schema: str
    context_connect_timeout_seconds: int
    s2s_token: str = field(repr=False)
    allow_real_sql_execution: bool
    langgraph_version: str | None
    langgraph_commit: str | None
    context_catalog_tables: Mapping[str, str | None] | None = field(
        default=None, repr=False
    )
    expected_organization_id: str | None = field(default=None, repr=False)
    expected_context_fingerprint: str | None = field(default=None, repr=False)


def load_shadow_test_runtime_config(
    environ: Mapping[str, str] | None = None,
) -> ShadowTestRuntimeConfig:
    env = os.environ if environ is None else environ
    runtime_mode = _required(env, "LANGGRAPH_RUNTIME_MODE").casefold()
    if runtime_mode != RUNTIME_MODE:
        raise RuntimeError("LANGGRAPH_RUNTIME_MODE must be shadow_test.")

    allow_real_sql_execution = _bool(
        env.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION"),
        default=False,
    )
    if allow_real_sql_execution:
        raise RuntimeError("Real SQL execution is not supported in shadow_test.")

    persistence = _required(env, "LANGGRAPH_SHADOW_PERSISTENCE").casefold()
    if persistence != PERSISTENCE_POSTGRES:
        raise RuntimeError("shadow_test persistence must be postgres.")

    dsn = _required(env, "LANGGRAPH_SHADOW_DATABASE_DSN")
    context_dsn = _required(env, CONTEXT_POSTGRES_DSN_ENV)
    if context_dsn == dsn:
        raise RuntimeError(
            "CONTEXT_POSTGRES_DSN must be separate from shadow persistence DSN."
        )
    return ShadowTestRuntimeConfig(
        runtime_mode=runtime_mode,
        http_host=_optional(env, "LANGGRAPH_HTTP_HOST", "127.0.0.1"),
        http_port=_port(_optional(env, "LANGGRAPH_HTTP_PORT", "8000")),
        shadow_persistence=persistence,
        shadow_database_dsn=dsn,
        context_postgres_dsn=context_dsn,
        semantic_agent_version=_required(env, SEMANTIC_AGENT_VERSION_ENV),
        context_schema=validate_postgres_context_schema(
            env,
            POSTGRES_CONTEXT_SCHEMA_ENV,
            default=DEFAULT_POSTGRES_CONTEXT_SCHEMA,
        ),
        context_connect_timeout_seconds=_positive_int(
            _optional(
                env,
                POSTGRES_CONNECT_TIMEOUT_ENV,
                str(DEFAULT_POSTGRES_CONNECT_TIMEOUT_SECONDS),
            ),
            POSTGRES_CONNECT_TIMEOUT_ENV,
        ),
        s2s_token=_required_secret(env, "LANGGRAPH_S2S_TOKEN"),
        allow_real_sql_execution=False,
        langgraph_version=_safe_optional(env.get("LANGGRAPH_VERSION")),
        langgraph_commit=_safe_optional(env.get("LANGGRAPH_COMMIT")),
        context_catalog_tables=_context_catalog_tables(env),
        expected_organization_id=_expected_organization_id(env),
        expected_context_fingerprint=_expected_context_fingerprint(env),
    )


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name)
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{name} must be configured explicitly.")
    return value.strip()


def _required_secret(env: Mapping[str, str], name: str) -> str:
    value = _required(env, name)
    if value != value.strip() or any(char.isspace() for char in value):
        raise RuntimeError(f"{name} must be configured explicitly.")
    if any(ord(char) < 33 or ord(char) == 127 for char in value):
        raise RuntimeError(f"{name} must be configured explicitly.")
    if len(value.encode("utf-8")) > 512:
        raise RuntimeError(f"{name} must be configured explicitly.")
    return value


def _optional(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name)
    if not isinstance(value, str) or not value.strip():
        return default
    return value.strip()


def _bool(value: str | None, *, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().casefold()
    if normalized in {"false", "0", "no", "off"}:
        return False
    if normalized in {"true", "1", "yes", "on"}:
        return True
    raise RuntimeError("Boolean runtime flag has invalid value.")


def _port(value: str) -> int:
    if not value.isdecimal():
        raise RuntimeError("LANGGRAPH_HTTP_PORT must be numeric.")
    parsed = int(value)
    if parsed <= 0 or parsed > 65535:
        raise RuntimeError("LANGGRAPH_HTTP_PORT is out of range.")
    return parsed


def _positive_int(value: str, name: str) -> int:
    if not value.isdecimal():
        raise RuntimeError(f"{name} must be numeric.")
    parsed = int(value)
    if parsed <= 0:
        raise RuntimeError(f"{name} must be positive.")
    return parsed


def _safe_optional(value: str | None) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if len(text) > 128:
        raise RuntimeError("Version metadata is too large.")
    if not all(char.isalnum() or char in "._:-" for char in text):
        raise RuntimeError("Version metadata contains invalid characters.")
    return text

def _context_catalog_tables(
    environ: Mapping[str, str],
) -> dict[str, str | None] | None:
    """Parse strictly versioned, tenant-scoped context-source identifiers."""
    raw = environ.get(CONTEXT_CATALOG_TABLES_ENV)
    if raw is None or not raw.strip():
        return None
    if len(raw) > 2048:
        raise RuntimeError("CONTEXT_CATALOG_TABLES_JSON is invalid.")
    try:
        tables = json.loads(raw)
    except (ValueError, TypeError):
        raise RuntimeError("CONTEXT_CATALOG_TABLES_JSON is invalid.") from None
    if not isinstance(tables, dict) or not tables:
        raise RuntimeError("CONTEXT_CATALOG_TABLES_JSON is invalid.")
    if set(tables) - _CONTEXT_CATALOG_KEYS:
        raise RuntimeError("CONTEXT_CATALOG_TABLES_JSON is invalid.")
    for key, name in tables.items():
        if key == "dre" and name is None:
            continue
        if not isinstance(name, str) or not _CONTEXT_IDENTIFIER.fullmatch(name):
            raise RuntimeError("CONTEXT_CATALOG_TABLES_JSON is invalid.")
    return tables


def _expected_organization_id(env: Mapping[str, str]) -> str | None:
    """Optional exact tenant binding for a single-context Shadow deployment.

    No fallback to a user claim, free-text request, model prompt or default
    tenant. Enabling this binding requires the authenticated Product session
    to supply the same organization_id explicitly.
    """
    if _EXPECTED_ORGANIZATION_ID_ENV not in env:
        return None
    value = env.get(_EXPECTED_ORGANIZATION_ID_ENV)
    if not isinstance(value, str) or not _ORGANIZATION_SCOPE_ID.fullmatch(value):
        raise RuntimeError("LANGGRAPH_EXPECTED_ORGANIZATION_ID is invalid.")
    return value


def _expected_context_fingerprint(environ: Mapping[str, str]) -> str | None:
    try:
        return validate_expected_context_fingerprint(
            environ.get(EXPECTED_CONTEXT_FINGERPRINT_ENV)
        )
    except ValueError:
        raise RuntimeError(
            "SEMANTIC_CONTEXT_EXPECTED_FINGERPRINT is invalid."
        ) from None

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field


RUNTIME_MODE = "shadow_test"
PERSISTENCE_POSTGRES = "postgres"
CONTEXT_POSTGRES_DSN_ENV = "CONTEXT_POSTGRES_DSN"
SEMANTIC_AGENT_VERSION_ENV = "SEMANTIC_AGENT_VERSION"
POSTGRES_CONNECT_TIMEOUT_ENV = "POSTGRES_CONNECT_TIMEOUT_SECONDS"
DEFAULT_POSTGRES_CONNECT_TIMEOUT_SECONDS = 10


@dataclass(frozen=True, slots=True)
class ShadowTestRuntimeConfig:
    runtime_mode: str
    http_host: str
    http_port: int
    shadow_persistence: str
    shadow_database_dsn: str = field(repr=False)
    context_postgres_dsn: str = field(repr=False)
    semantic_agent_version: str
    context_connect_timeout_seconds: int
    s2s_token: str = field(repr=False)
    allow_real_sql_execution: bool
    langgraph_version: str | None
    langgraph_commit: str | None


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

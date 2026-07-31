from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, TypedDict
from urllib.parse import urlparse

from app.domain.engine_preflight import EnginePreflightCapabilities
from app.domain.engine_preflight_sanitization import (
    safe_optional_text,
    safe_provider_name,
)


ENGINE_PREFLIGHT_PROVIDER_TYPE_ENV = "ENGINE_PREFLIGHT_PROVIDER_TYPE"
ENGINE_PREFLIGHT_CAPABILITY_MODE_ENV = "ENGINE_PREFLIGHT_CAPABILITY_MODE"
ENGINE_PREFLIGHT_DIALECT_ENV = "ENGINE_PREFLIGHT_DIALECT"
ENGINE_PREFLIGHT_ENDPOINT_ENV = "ENGINE_PREFLIGHT_ENDPOINT"
ENGINE_PREFLIGHT_AUTH_MODE_ENV = "ENGINE_PREFLIGHT_AUTH_MODE"
ENGINE_PREFLIGHT_OPERATION_ENV = "ENGINE_PREFLIGHT_OPERATION"
ENGINE_PREFLIGHT_TIMEOUT_ENV = "ENGINE_PREFLIGHT_TIMEOUT_SECONDS"
ENGINE_PREFLIGHT_SSL_VERIFY_ENV = "ENGINE_PREFLIGHT_SSL_VERIFY"

MAX_TIMEOUT_SECONDS = 60

CapabilityMode = Literal[
    "unavailable",
    "parse",
    "plan",
    "dry_run",
    "explain_without_analyze",
    "normal_execution",
]

AuthMode = Literal[
    "none",
    "bearer",
    "api_key",
    "iam",
    "external",
]

CAPABILITY_MODES: frozenset[str] = frozenset(
    {
        "unavailable",
        "parse",
        "plan",
        "dry_run",
        "explain_without_analyze",
        "normal_execution",
    }
)

AUTH_MODES: frozenset[str] = frozenset(
    {"none", "bearer", "api_key", "iam", "external"}
)

PROVIDER_TYPES: frozenset[str] = frozenset({"capability_diagnostic"})


class EnginePreflightRuntimeConfigError(ValueError):
    """
    Erro conhecido ao carregar configuracao do preflight live.
    """


class EnginePreflightCapabilityDiagnostic(TypedDict):
    provider_type: str
    capability_mode: CapabilityMode
    dialect: str | None
    endpoint_configured: bool
    operation: str | None
    timeout_seconds: int
    can_preflight: bool
    adapter_available: bool
    reason: str
    error_code: str | None
    capabilities: EnginePreflightCapabilities


@dataclass(frozen=True, slots=True)
class EnginePreflightRuntimeConfig:
    """
    Configuracao explicita para provider live de Engine Preflight.

    A classe nao le arquivos, nao guarda credenciais e nao cria provider
    padrao. Valores sensiveis devem ser injetados fora deste objeto.
    """

    provider_type: str
    capability_mode: CapabilityMode
    dialect: str | None
    timeout_seconds: int
    auth_mode: AuthMode = "none"
    endpoint: str | None = None
    operation: str | None = None
    ssl_verify: bool = True

    def __post_init__(self) -> None:
        provider_type = _provider_type(self.provider_type)
        capability_mode = _capability_mode(self.capability_mode)
        dialect = _optional_name(self.dialect)
        endpoint = _optional_endpoint(self.endpoint)
        operation = _optional_name(self.operation)
        auth_mode = _auth_mode(self.auth_mode)
        timeout_seconds = _timeout_seconds(self.timeout_seconds)

        if capability_mode == "dry_run" and endpoint is None:
            raise EnginePreflightRuntimeConfigError(
                "endpoint e obrigatorio para capability_mode dry_run."
            )

        object.__setattr__(self, "provider_type", provider_type)
        object.__setattr__(self, "capability_mode", capability_mode)
        object.__setattr__(self, "dialect", dialect)
        object.__setattr__(self, "endpoint", endpoint)
        object.__setattr__(self, "operation", operation)
        object.__setattr__(self, "auth_mode", auth_mode)
        object.__setattr__(self, "timeout_seconds", timeout_seconds)


def load_engine_preflight_runtime_config(
    environ: Mapping[str, str] | None = None,
) -> EnginePreflightRuntimeConfig:
    source = os.environ if environ is None else environ
    return EnginePreflightRuntimeConfig(
        provider_type=_required_text(source, ENGINE_PREFLIGHT_PROVIDER_TYPE_ENV),
        capability_mode=_required_text(
            source,
            ENGINE_PREFLIGHT_CAPABILITY_MODE_ENV,
        ),  # type: ignore[arg-type]
        dialect=_optional_text(source, ENGINE_PREFLIGHT_DIALECT_ENV),
        endpoint=_optional_text(source, ENGINE_PREFLIGHT_ENDPOINT_ENV),
        auth_mode=(
            _optional_text(source, ENGINE_PREFLIGHT_AUTH_MODE_ENV) or "none"
        ),  # type: ignore[arg-type]
        operation=_optional_text(source, ENGINE_PREFLIGHT_OPERATION_ENV),
        timeout_seconds=_positive_integer(
            source,
            ENGINE_PREFLIGHT_TIMEOUT_ENV,
            default=5,
        ),
        ssl_verify=_boolean(
            source,
            ENGINE_PREFLIGHT_SSL_VERIFY_ENV,
            default=True,
        ),
    )


def evaluate_engine_preflight_capabilities(
    config: EnginePreflightRuntimeConfig,
) -> EnginePreflightCapabilityDiagnostic:
    mode = config.capability_mode
    safe_mode = mode in {
        "parse",
        "plan",
        "dry_run",
        "explain_without_analyze",
    }
    unsafe_mode = mode == "normal_execution"
    capabilities = _capabilities_for_config(config)
    can_preflight = False
    reason = (
        "normal_execution_is_not_safe_for_preflight"
        if unsafe_mode
        else (
            "no_live_engine_preflight_adapter_implemented"
            if safe_mode
            else "capability_not_declared"
        )
    )
    return {
        "provider_type": safe_provider_name(config.provider_type),
        "capability_mode": mode,
        "dialect": safe_optional_text(config.dialect),
        "endpoint_configured": config.endpoint is not None,
        "operation": safe_optional_text(config.operation),
        "timeout_seconds": config.timeout_seconds,
        "can_preflight": can_preflight,
        "adapter_available": False,
        "reason": reason,
        "error_code": "ENGINE_PREFLIGHT_CAPABILITY_UNAVAILABLE",
        "capabilities": capabilities,
    }


def _capabilities_for_config(
    config: EnginePreflightRuntimeConfig,
) -> EnginePreflightCapabilities:
    mode = config.capability_mode
    safe_parse = mode == "parse"
    safe_plan = mode == "plan"
    safe_explain = mode == "explain_without_analyze"
    safe_dry_run = mode == "dry_run"
    supported_dialects = [config.dialect] if config.dialect else []
    return {
        "supports_parse": safe_parse,
        "supports_plan": safe_plan or safe_dry_run,
        "supports_explain": safe_explain,
        "supports_explain_analyze": False,
        "syntax": safe_parse or safe_plan or safe_explain or safe_dry_run,
        "schema_resolution": safe_plan or safe_explain or safe_dry_run,
        "table_resolution": safe_plan or safe_explain or safe_dry_run,
        "column_resolution": safe_plan or safe_explain or safe_dry_run,
        "alias_resolution": safe_plan or safe_explain or safe_dry_run,
        "function_resolution": safe_plan or safe_explain or safe_dry_run,
        "grouping_validation": safe_plan or safe_explain or safe_dry_run,
        "ordering_validation": safe_plan or safe_explain or safe_dry_run,
        "type_validation": safe_plan or safe_explain or safe_dry_run,
        "cast_validation": safe_plan or safe_explain or safe_dry_run,
        "join_planning": safe_plan or safe_explain or safe_dry_run,
        "cte_validation": safe_plan or safe_explain or safe_dry_run,
        "subquery_validation": safe_plan or safe_explain or safe_dry_run,
        "dialect_validation": bool(config.dialect)
        and (safe_parse or safe_plan or safe_explain or safe_dry_run),
        "explain_without_analyze": safe_explain,
        "executes_query": False,
        "returns_rows": False,
        "supports_sqlstate": False,
        "supports_error_position": False,
        "supports_related_object": False,
        "supported_dialects": sorted(
            {item.casefold() for item in supported_dialects}
        ),
    }


def _required_text(
    source: Mapping[str, str],
    variable_name: str,
) -> str:
    raw_value = source.get(variable_name)
    if raw_value is None:
        raise EnginePreflightRuntimeConfigError(
            f"A variavel {variable_name} nao esta definida."
        )
    return _required_text_value(raw_value, variable_name)


def _required_text_value(value: str, field_name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise EnginePreflightRuntimeConfigError(
            f"{field_name} nao pode estar vazio."
        )
    return normalized


def _provider_type(value: str) -> str:
    normalized = _required_text_value(value, "provider_type").casefold()
    if normalized not in PROVIDER_TYPES:
        raise EnginePreflightRuntimeConfigError(
            "provider_type nao suportado."
        )
    return normalized


def _optional_text(
    source: Mapping[str, str],
    variable_name: str,
) -> str | None:
    raw_value = source.get(variable_name)
    if raw_value is None:
        return None
    return _optional_name(raw_value)


def _optional_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _capability_mode(value: str) -> CapabilityMode:
    normalized = _required_text_value(value, "capability_mode").casefold()
    if normalized not in CAPABILITY_MODES:
        raise EnginePreflightRuntimeConfigError(
            "capability_mode nao suportado."
        )
    return normalized  # type: ignore[return-value]


def _auth_mode(value: str) -> AuthMode:
    normalized = _required_text_value(value, "auth_mode").casefold()
    if normalized not in AUTH_MODES:
        raise EnginePreflightRuntimeConfigError("auth_mode nao suportado.")
    return normalized  # type: ignore[return-value]


def _optional_endpoint(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    normalized = str(value).strip()
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.netloc:
        raise EnginePreflightRuntimeConfigError(
            "endpoint deve usar HTTPS e possuir host."
        )
    return normalized


def _positive_integer(
    source: Mapping[str, str],
    variable_name: str,
    *,
    default: int,
) -> int:
    raw_value = source.get(variable_name)
    if raw_value is None:
        return default
    try:
        value = int(str(raw_value).strip())
    except ValueError as error:
        raise EnginePreflightRuntimeConfigError(
            f"A variavel {variable_name} deve ser um inteiro positivo."
        ) from error
    return _timeout_seconds(value)


def _timeout_seconds(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise EnginePreflightRuntimeConfigError(
            "timeout_seconds deve ser um inteiro positivo."
        )
    if value > MAX_TIMEOUT_SECONDS:
        raise EnginePreflightRuntimeConfigError(
            f"timeout_seconds nao pode exceder {MAX_TIMEOUT_SECONDS}."
        )
    return value


def _boolean(
    source: Mapping[str, str],
    variable_name: str,
    *,
    default: bool,
) -> bool:
    raw_value = source.get(variable_name)
    if raw_value is None:
        return default
    normalized = str(raw_value).strip().casefold()
    if normalized in {"1", "true", "yes", "sim"}:
        return True
    if normalized in {"0", "false", "no", "nao"}:
        return False
    raise EnginePreflightRuntimeConfigError(
        f"A variavel {variable_name} deve ser booleana."
    )

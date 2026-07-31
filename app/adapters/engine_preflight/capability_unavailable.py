from __future__ import annotations

from copy import deepcopy

from app.config.engine_preflight_runtime import (
    EnginePreflightRuntimeConfig,
    evaluate_engine_preflight_capabilities,
)
from app.domain.engine_preflight import (
    EnginePreflightProviderResult,
    EnginePreflightRequest,
)
from app.domain.engine_preflight_sanitization import safe_provider_name


class CapabilityUnavailableEnginePreflight:
    """
    Provider diagnostico que falha fechado quando nao ha capability segura.

    Ele implementa a porta apenas para permitir injecao explicita e diagnostico
    estruturado. Nao e adapter live real, nao abre transporte e nao executa SQL.
    """

    provider_version = "capability-diagnostic-v1"

    def __init__(
        self,
        *,
        config: EnginePreflightRuntimeConfig,
    ) -> None:
        self.config = config
        self.diagnostic = evaluate_engine_preflight_capabilities(config)
        self.calls = 0
        self.last_request: EnginePreflightRequest | None = None

    def preflight(
        self,
        request: EnginePreflightRequest,
    ) -> EnginePreflightProviderResult:
        self.calls += 1
        self.last_request = deepcopy(request)
        provider_name = safe_provider_name(
            f"{self.config.provider_type}_capability_diagnostic",
            forbidden_texts=(request.get("sql", ""),),
        )
        return {
            "status": "error",
            "provider_name": provider_name,
            "provider_version": self.provider_version,
            "duration_ms": 0,
            "failure_category": "capability_unavailable",
            "error_code": "ENGINE_PREFLIGHT_CAPABILITY_UNAVAILABLE",
            "message": (
                "Engine Preflight live nao possui capability segura "
                "comprovada para o provider configurado."
            ),
            "repairable": False,
            "capabilities": deepcopy(self.diagnostic["capabilities"]),
            "statement_planned": False,
            "executed": False,
            "rows_returned": 0,
            "warnings": [],
        }

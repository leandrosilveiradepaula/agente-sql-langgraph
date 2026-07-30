from __future__ import annotations

from copy import deepcopy

from app.domain.engine_preflight import (
    EnginePreflightFailureCategory,
    EnginePreflightProviderResult,
    EnginePreflightRequest,
)


class FakeEnginePreflight:
    """
    Fake explicito para testes locais.

    Nao deve ser usado como provider padrao em producao.
    """

    def __init__(
        self,
        *,
        status: str = "approved",
        failure_category: EnginePreflightFailureCategory = "none",
        message: str = "preflight approved",
        repairable: bool | None = None,
        raises: Exception | None = None,
        responses: list[EnginePreflightProviderResult] | None = None,
        duration_ms: int = 3,
        provider_name: str = "fake_engine_preflight",
        provider_version: str = "test-v1",
    ) -> None:
        self.status = status
        self.failure_category = failure_category
        self.message = message
        self.repairable = repairable
        self.raises = raises
        self.responses = list(responses or [])
        self.duration_ms = duration_ms
        self.provider_name = provider_name
        self.provider_version = provider_version
        self.calls = 0
        self.last_request: EnginePreflightRequest | None = None

    def preflight(
        self,
        request: EnginePreflightRequest,
    ) -> EnginePreflightProviderResult:
        self.calls += 1
        self.last_request = deepcopy(request)
        assert "context" not in request
        assert "rules" not in repr(request).casefold()
        assert "password" not in repr(request).casefold()
        assert "token" not in repr(request).casefold()
        if self.raises is not None:
            raise self.raises
        if self.responses:
            return deepcopy(self.responses.pop(0))
        result: EnginePreflightProviderResult = {
            "status": self.status,  # type: ignore[typeddict-item]
            "provider_name": self.provider_name,
            "provider_version": self.provider_version,
            "duration_ms": self.duration_ms,
            "statement_planned": self.status == "approved",
            "executed": False,
            "rows_returned": 0,
            "warnings": [],
        }
        if self.status != "approved":
            result.update(
                {
                    "failure_category": self.failure_category,
                    "message": self.message,
                }
            )
            if self.repairable is not None:
                result["repairable"] = self.repairable
        return result

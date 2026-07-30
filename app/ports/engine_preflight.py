from __future__ import annotations

from typing import Protocol

from app.domain.engine_preflight import (
    EnginePreflightProviderResult,
    EnginePreflightRequest,
)


class EnginePreflight(Protocol):
    """
    Porta pequena para validacao de planejamento do motor.

    Implementacoes recebem somente EnginePreflightRequest.
    """

    def preflight(
        self,
        request: EnginePreflightRequest,
    ) -> EnginePreflightProviderResult:
        """
        Retorna resultado estruturado sem executar a consulta de negocio.
        """

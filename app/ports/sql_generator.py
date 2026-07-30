from __future__ import annotations

from typing import Protocol

from app.domain.sql_generation import (
    SqlGenerationProviderResult,
    SqlGenerationRequest,
)


class SqlGenerator(Protocol):
    """
    Porta pequena para provedores de geracao SQL.

    Implementacoes recebem somente a requisicao derivada do QueryPlan.
    """

    def generate(
        self,
        request: SqlGenerationRequest,
    ) -> SqlGenerationProviderResult:
        """
        Retorna a resposta bruta normalizada do provedor.
        """

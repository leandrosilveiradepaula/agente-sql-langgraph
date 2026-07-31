from __future__ import annotations

from typing import Protocol

from app.domain.sql_execution import (
    SqlExecutionProviderResult,
    SqlExecutionRequest,
)


class SqlExecutor(Protocol):
    """
    Porta pequena para execucao controlada de SQL aprovada.

    Implementacoes recebem somente SqlExecutionRequest.
    """

    def execute(
        self,
        request: SqlExecutionRequest,
    ) -> SqlExecutionProviderResult:
        """
        Retorna resultado estruturado da execucao.
        """

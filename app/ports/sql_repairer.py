from __future__ import annotations

from typing import Protocol

from app.domain.sql_repair import (
    SqlRepairProviderResult,
    SqlRepairRequest,
)


class SqlRepairer(Protocol):
    """
    Porta pequena para provedores de reparo SQL.

    Implementacoes recebem somente SqlRepairRequest.
    """

    def repair(
        self,
        request: SqlRepairRequest,
    ) -> SqlRepairProviderResult:
        """
        Retorna resposta bruta do provedor sem executar SQL.
        """

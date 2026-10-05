from __future__ import annotations

from typing import Protocol

from app.ports.sql_generator import SqlGenerator


class SqlGeneratorResolver(Protocol):
    """
    Resolve um gerador SQL a partir de uma selecao de provider/modelo versionada.
    """

    def resolve(
        self,
        *,
        provider_key: str,
        model_key: str,
        config_version: str,
    ) -> SqlGenerator:
        """
        Retorna o generator autorizado para a selecao informada.

        Deve falhar explicitamente quando a selecao nao estiver disponivel.
        """

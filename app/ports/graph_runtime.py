from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


class GraphRuntime(Protocol):
    """
    Porta minima para executar o grafo compilado.

    A porta conhece somente estado de entrada e saida. Ela nao conhece
    ApplicationRequest, adapters, SQL ou sinks.
    """

    def invoke(
        self,
        initial_state: Mapping[str, object],
    ) -> Mapping[str, object]:
        """
        Executa o grafo uma unica vez e retorna o estado final.
        """

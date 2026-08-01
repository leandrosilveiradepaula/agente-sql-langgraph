from __future__ import annotations

from typing import Protocol

from app.integrations.watson.flow_contracts import (
    WatsonFlowRunRequest,
    WatsonFlowRunResult,
)


class WatsonFlowClient(Protocol):
    """
    Porta minima para invocar um Flow Watson por adapter externo.
    """

    def run_flow(
        self,
        request: WatsonFlowRunRequest,
    ) -> WatsonFlowRunResult:
        """
        Retorna resultado estruturado do Flow, sem transporte live nesta fase.
        """

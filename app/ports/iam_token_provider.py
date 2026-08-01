from __future__ import annotations

from typing import Protocol

from app.integrations.watson.iam_contracts import (
    IamTokenRequest,
    IamTokenResult,
)


class IamTokenProvider(Protocol):
    """
    Porta minima para obtencao de token tecnico IAM.
    """

    def get_token(self, request: IamTokenRequest) -> IamTokenResult:
        """
        Retorna token sensivel ou falha canonica, sem expor segredo.
        """

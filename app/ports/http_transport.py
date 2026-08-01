from __future__ import annotations

from typing import Protocol

from app.infrastructure.http.http_contracts import (
    HttpTransportRequest,
    HttpTransportResult,
)


class HttpTransport(Protocol):
    def send(self, request: HttpTransportRequest) -> HttpTransportResult:
        """
        Envia requisicao HTTP de fronteira live, sem expor headers sensiveis.
        """

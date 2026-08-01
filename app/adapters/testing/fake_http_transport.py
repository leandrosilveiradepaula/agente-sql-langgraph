from __future__ import annotations

from copy import deepcopy

from app.infrastructure.http.http_contracts import (
    HttpTransportRequest,
    HttpTransportResult,
)


class FakeHttpTransport:
    def __init__(
        self,
        *,
        result: HttpTransportResult | None = None,
        sequence: list[HttpTransportResult] | None = None,
        exception: Exception | None = None,
    ) -> None:
        self.result = deepcopy(result)
        self.sequence = list(sequence or [])
        self.exception = exception
        self.calls = 0
        self.requests: list[HttpTransportRequest] = []

    @property
    def last_request(self) -> HttpTransportRequest | None:
        return self.requests[-1] if self.requests else None

    def __repr__(self) -> str:
        return "FakeHttpTransport(<safe>)"

    def send(self, request: HttpTransportRequest) -> HttpTransportResult:
        self.calls += 1
        self.requests.append(deepcopy(request))
        if self.exception is not None:
            raise self.exception
        if self.sequence:
            return deepcopy(self.sequence.pop(0))
        if self.result is None:
            raise AssertionError("FakeHttpTransport exige resultado explicito.")
        return deepcopy(self.result)

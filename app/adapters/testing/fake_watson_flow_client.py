from __future__ import annotations

from copy import deepcopy

from app.integrations.watson.flow_contracts import (
    WatsonFlowRunRequest,
    WatsonFlowRunResult,
)


class FakeWatsonFlowClient:
    """
    Fake explicito para testes offline Watson.
    """

    def __init__(
        self,
        *,
        result: WatsonFlowRunResult | None = None,
        sequence: list[WatsonFlowRunResult] | None = None,
        exception: Exception | None = None,
    ) -> None:
        self.result = deepcopy(result)
        self.sequence = list(sequence or [])
        self.exception = exception
        self.calls = 0
        self.requests: list[WatsonFlowRunRequest] = []

    @property
    def last_request(self) -> WatsonFlowRunRequest | None:
        return self.requests[-1] if self.requests else None

    def __repr__(self) -> str:
        return "FakeWatsonFlowClient(<safe>)"

    def run_flow(
        self,
        request: WatsonFlowRunRequest,
    ) -> WatsonFlowRunResult:
        self.calls += 1
        captured = deepcopy(request)
        assert repr(captured["bearer_token"]) == "SensitiveBearerToken(<redacted>)"
        assert set(captured["payload"].keys()) == {"sql_query"}
        self.requests.append(captured)
        if self.exception is not None:
            raise self.exception
        if self.sequence:
            return deepcopy(self.sequence.pop(0))
        if self.result is None:
            raise AssertionError("FakeWatsonFlowClient exige resultado explicito.")
        return deepcopy(self.result)

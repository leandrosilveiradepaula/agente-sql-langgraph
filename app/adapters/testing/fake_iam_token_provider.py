from __future__ import annotations

from copy import deepcopy

from app.integrations.watson.iam_contracts import (
    IamTokenRequest,
    IamTokenResult,
)


class FakeIamTokenProvider:
    """
    Fake explicito para testes offline Watson.
    """

    def __init__(
        self,
        *,
        result: IamTokenResult | None = None,
        sequence: list[IamTokenResult] | None = None,
        exception: Exception | None = None,
    ) -> None:
        self.result = deepcopy(result)
        self.sequence = list(sequence or [])
        self.exception = exception
        self.calls = 0
        self.requests: list[IamTokenRequest] = []

    @property
    def last_request(self) -> IamTokenRequest | None:
        return self.requests[-1] if self.requests else None

    def __repr__(self) -> str:
        return "FakeIamTokenProvider(<safe>)"

    def get_token(self, request: IamTokenRequest) -> IamTokenResult:
        self.calls += 1
        self.requests.append(deepcopy(request))
        if self.exception is not None:
            raise self.exception
        if self.sequence:
            return deepcopy(self.sequence.pop(0))
        if self.result is None:
            raise AssertionError("FakeIamTokenProvider exige resultado explicito.")
        return deepcopy(self.result)

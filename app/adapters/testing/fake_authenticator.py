from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.security.auth_types import (
    AuthenticationContext,
    AuthenticationResult,
    BearerCredential,
    authentication_result,
)


class FakeAuthenticator:
    def __init__(
        self,
        *,
        result: AuthenticationResult | None = None,
        results: list[AuthenticationResult] | None = None,
        exception: Exception | None = None,
    ) -> None:
        if result is None and results is None and exception is None:
            raise RuntimeError("FakeAuthenticator exige resultado explicito.")
        self.result = deepcopy(result) if result is not None else None
        self.results = deepcopy(results or [])
        self.exception = exception
        self.calls = 0
        self.credential_seen = False
        self.credential_length = 0
        self.contexts: list[AuthenticationContext] = []

    def authenticate(
        self,
        credential: BearerCredential,
        context: AuthenticationContext,
    ) -> AuthenticationResult:
        self.calls += 1
        self.credential_seen = True
        self.credential_length = len(
            credential.reveal_for_authenticator().encode("utf-8")
        )
        self.contexts.append(deepcopy(context))
        if self.exception is not None:
            raise self.exception
        if self.results:
            return deepcopy(self.results.pop(0))
        if self.result is not None:
            return deepcopy(self.result)
        return authentication_result(
            status="invalid_credentials",
            error_code="AUTHENTICATION_INVALID_CREDENTIALS",
        )

    def __repr__(self) -> str:
        return "FakeAuthenticator(<redacted>)"

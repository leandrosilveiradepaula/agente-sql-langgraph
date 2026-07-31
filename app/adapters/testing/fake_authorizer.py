from __future__ import annotations

from copy import deepcopy

from app.security.auth_types import (
    AuthenticatedPrincipal,
    AuthorizationDecision,
    AuthorizationRequest,
    authorization_decision,
)


class FakeAuthorizer:
    def __init__(
        self,
        *,
        decision: AuthorizationDecision | None = None,
        decisions: list[AuthorizationDecision] | None = None,
        exception: Exception | None = None,
    ) -> None:
        if decision is None and decisions is None and exception is None:
            raise RuntimeError("FakeAuthorizer exige decisao explicita.")
        self.decision = deepcopy(decision) if decision is not None else None
        self.decisions = deepcopy(decisions or [])
        self.exception = exception
        self.calls = 0
        self.principals: list[AuthenticatedPrincipal] = []
        self.requests: list[AuthorizationRequest] = []

    def authorize(
        self,
        principal: AuthenticatedPrincipal,
        request: AuthorizationRequest,
    ) -> AuthorizationDecision:
        self.calls += 1
        self.principals.append(deepcopy(principal))
        self.requests.append(deepcopy(request))
        if self.exception is not None:
            raise self.exception
        if self.decisions:
            return deepcopy(self.decisions.pop(0))
        if self.decision is not None:
            return deepcopy(self.decision)
        return authorization_decision(
            status="denied",
            error_code="AUTHORIZATION_DENIED",
        )

    def __repr__(self) -> str:
        return "FakeAuthorizer(<redacted>)"

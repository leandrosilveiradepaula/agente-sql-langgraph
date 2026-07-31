from __future__ import annotations

from typing import Protocol

from app.security.auth_types import (
    AuthenticatedPrincipal,
    AuthorizationDecision,
    AuthorizationRequest,
)


class Authorizer(Protocol):
    def authorize(
        self,
        principal: AuthenticatedPrincipal,
        request: AuthorizationRequest,
    ) -> AuthorizationDecision:
        ...

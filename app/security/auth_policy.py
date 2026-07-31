from __future__ import annotations

from app.security.auth_types import (
    AuthenticatedPrincipal,
    AuthorizationDecision,
    AuthorizationRequest,
    authorization_decision,
)


class ScopeAuthorizationPolicy:
    def __init__(self, *, required_scope: str) -> None:
        if not isinstance(required_scope, str) or not required_scope.strip():
            raise ValueError("required_scope deve ser informado.")
        if any(ord(char) < 32 or ord(char) == 127 for char in required_scope):
            raise ValueError("required_scope invalido.")
        self._required_scope = required_scope

    @property
    def required_scope(self) -> str:
        return self._required_scope

    def authorize(
        self,
        principal: AuthenticatedPrincipal,
        request: AuthorizationRequest,
    ) -> AuthorizationDecision:
        if request.get("action") != "sql_agent.query.execute":
            return authorization_decision(
                status="denied",
                error_code="AUTHORIZATION_DENIED",
            )
        if request.get("resource") != "sql_agent.query":
            return authorization_decision(
                status="denied",
                error_code="AUTHORIZATION_DENIED",
            )
        if self._required_scope in principal.scopes:
            return authorization_decision(status="allowed")
        return authorization_decision(
            status="denied",
            error_code="AUTHORIZATION_DENIED",
        )

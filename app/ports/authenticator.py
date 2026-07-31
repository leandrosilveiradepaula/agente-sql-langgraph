from __future__ import annotations

from typing import Protocol

from app.security.auth_types import (
    AuthenticationContext,
    AuthenticationResult,
    BearerCredential,
)


class Authenticator(Protocol):
    def authenticate(
        self,
        credential: BearerCredential,
        context: AuthenticationContext,
    ) -> AuthenticationResult:
        ...

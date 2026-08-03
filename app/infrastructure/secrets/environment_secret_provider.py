from __future__ import annotations

import os
from collections.abc import Mapping

from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.ports.secret_value_provider import (
    SecretLookupResult,
    SecretName,
    secret_lookup_failure,
    secret_lookup_success,
)


class EnvironmentSecretProvider:
    def __init__(
        self,
        *,
        environ: Mapping[str, str] | None = None,
        max_secret_bytes: int = 8192,
        unavailable: bool = False,
    ) -> None:
        self._environ = environ
        self._max_secret_bytes = max_secret_bytes
        self._unavailable = unavailable
        self.calls = 0
        self.requested_names: list[str] = []

    def __repr__(self) -> str:
        return "EnvironmentSecretProvider(<safe>)"

    def get_secret(self, secret_name: SecretName) -> SecretLookupResult:
        self.calls += 1
        self.requested_names.append(str(secret_name))
        if self._unavailable:
            return secret_lookup_failure("unavailable")
        try:
            source = os.environ if self._environ is None else self._environ
            if str(secret_name) not in source:
                return secret_lookup_failure("missing")
            return secret_lookup_success(
                SensitiveSecret(
                    source[str(secret_name)],
                    max_bytes=self._max_secret_bytes,
                )
            )
        except Exception:
            return secret_lookup_failure("invalid")

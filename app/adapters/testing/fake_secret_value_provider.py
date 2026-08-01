from __future__ import annotations

from copy import deepcopy

from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.ports.secret_value_provider import (
    SecretLookupResult,
    SecretName,
    secret_lookup_failure,
    secret_lookup_success,
)


class FakeSecretValueProvider:
    def __init__(
        self,
        *,
        secret: SensitiveSecret | None = None,
        result: SecretLookupResult | None = None,
        sequence: list[SecretLookupResult] | None = None,
        exception: Exception | None = None,
    ) -> None:
        if secret is not None and result is not None:
            raise ValueError("Use secret ou result.")
        self.result = deepcopy(result) if result is not None else (
            secret_lookup_success(secret) if secret is not None else None
        )
        self.sequence = list(sequence or [])
        self.exception = exception
        self.calls = 0
        self.secret_names: list[str] = []

    def __repr__(self) -> str:
        return "FakeSecretValueProvider(<safe>)"

    def get_secret(self, secret_name: SecretName) -> SecretLookupResult:
        self.calls += 1
        self.secret_names.append(str(secret_name))
        if self.exception is not None:
            raise self.exception
        if self.sequence:
            return deepcopy(self.sequence.pop(0))
        if self.result is None:
            return secret_lookup_failure("missing")
        return deepcopy(self.result)

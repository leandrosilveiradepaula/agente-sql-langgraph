from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Literal, Protocol, TypedDict

from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.integrations.watson.flow_limits import WatsonFlowContractError


SecretLookupStatus = Literal[
    "success",
    "missing",
    "unavailable",
    "invalid",
    "unexpected_error",
]


class SecretName(str):
    def __new__(cls, value: str) -> "SecretName":
        if not isinstance(value, str) or not value.strip():
            raise WatsonFlowContractError("SecretName invalido.")
        text = value.strip()
        if len(text.encode("utf-8")) > 128:
            raise WatsonFlowContractError("SecretName excede limite.")
        if any(ord(char) < 32 or ord(char) == 127 for char in text):
            raise WatsonFlowContractError("SecretName contem controle.")
        allowed = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_")
        if any(char not in allowed for char in text):
            raise WatsonFlowContractError("SecretName deve usar nome estrutural.")
        return str.__new__(cls, text)


class SecretLookupResult(TypedDict, total=False):
    status: SecretLookupStatus
    secret: SensitiveSecret
    public_error_code: str
    public_error_message: str
    diagnostics: dict[str, Any]


class SecretValueProvider(Protocol):
    def get_secret(self, secret_name: SecretName) -> SecretLookupResult:
        """
        Busca um secret sensivel por nome validado sem expor seu valor.
        """


_ERROR_MESSAGES = {
    "missing": "Secret nao configurado.",
    "unavailable": "Secret provider indisponivel.",
    "invalid": "Secret configurado e invalido.",
    "unexpected_error": "Secret provider falhou.",
}


def secret_lookup_success(secret: SensitiveSecret) -> SecretLookupResult:
    if not isinstance(secret, SensitiveSecret):
        raise WatsonFlowContractError("secret deve ser SensitiveSecret.")
    return {"status": "success", "secret": secret, "diagnostics": {}}


def secret_lookup_failure(
    status: SecretLookupStatus,
    *,
    diagnostics: Mapping[str, Any] | None = None,
) -> SecretLookupResult:
    if status == "success" or status not in _ERROR_MESSAGES:
        raise WatsonFlowContractError("status de secret invalido.")
    return {
        "status": status,
        "public_error_code": f"SECRET_{status.upper()}",
        "public_error_message": _ERROR_MESSAGES[status],
        "diagnostics": _sanitized_diagnostics(diagnostics),
    }


def _sanitized_diagnostics(value: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    output: dict[str, Any] = {}
    blocked = {"secret", "value", "apikey", "api_key", "token", "authorization", "env"}
    for key, raw in value.items():
        if not isinstance(key, str) or key.casefold() in blocked:
            continue
        if isinstance(raw, (str, int, bool)) or raw is None:
            text = str(raw).casefold()
            if any(marker in text for marker in ("apikey", "bearer", "token", "secret")):
                continue
            output[key[:64]] = deepcopy(raw)
    return output

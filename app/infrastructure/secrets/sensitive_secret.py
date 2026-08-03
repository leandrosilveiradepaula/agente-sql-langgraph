from __future__ import annotations

from app.integrations.watson.flow_limits import WatsonFlowContractError


class SensitiveSecret:
    __slots__ = ("_secret", "_max_bytes")

    def __init__(self, secret: str, *, max_bytes: int = 8192) -> None:
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
            raise WatsonFlowContractError("Limite de secret invalido.")
        if max_bytes <= 0 or max_bytes > 64_000:
            raise WatsonFlowContractError("Limite de secret fora do intervalo.")
        if not isinstance(secret, str) or not secret.strip():
            raise WatsonFlowContractError("Secret invalido.")
        encoded = secret.encode("utf-8")
        if len(encoded) > max_bytes:
            raise WatsonFlowContractError("Secret excede limite.")
        if any(ord(char) < 32 or ord(char) == 127 for char in secret):
            raise WatsonFlowContractError("Secret contem controle.")
        object.__setattr__(self, "_secret", secret)
        object.__setattr__(self, "_max_bytes", max_bytes)

    def reveal_for_transport(self) -> str:
        """
        Deve ser chamado somente na fronteira live de transporte.
        """

        return self._secret

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("SensitiveSecret e imutavel.")

    def __deepcopy__(self, memo: dict[int, object]) -> "SensitiveSecret":
        del memo
        return self

    def __repr__(self) -> str:
        return "SensitiveSecret(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SensitiveSecret) and self._secret == other._secret

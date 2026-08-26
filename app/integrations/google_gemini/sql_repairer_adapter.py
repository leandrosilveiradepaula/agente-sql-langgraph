from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.domain.sql_repair import (
    SQL_REPAIR_CONTRACT_VERSION,
    SqlRepairProviderError,
    SqlRepairProviderResult,
    SqlRepairRequest,
)
from app.integrations.google_gemini.configuration import (
    GOOGLE_GEMINI_PROVIDER_NAME,
)
from app.integrations.google_gemini.contracts import (
    GeminiClientResult,
    build_gemini_repair_payload,
)


class GoogleGeminiSqlRepairerAdapter:
    def __init__(self, *, client) -> None:
        if client is None or not callable(getattr(client, "generate_content", None)):
            raise RuntimeError("client deve expor generate_content.")
        self._client = client

    def __repr__(self) -> str:
        return "GoogleGeminiSqlRepairerAdapter(<safe>)"

    def repair(
        self,
        request: SqlRepairRequest,
    ) -> SqlRepairProviderResult:
        if not isinstance(request, Mapping):
            raise SqlRepairProviderError(
                "Requisicao de reparo Gemini invalida."
            )
        if request.get("contract_version") != SQL_REPAIR_CONTRACT_VERSION:
            raise SqlRepairProviderError(
                "Contrato de reparo Gemini invalido."
            )
        result = self._client.generate_content(
            request,
            payload_builder=build_gemini_repair_payload,
        )
        if not isinstance(result, Mapping):
            raise SqlRepairProviderError(
                "Google Gemini retornou resultado invalido."
            )
        if result.get("status") != "success":
            raise SqlRepairProviderError(
                "Google Gemini falhou de forma sanitizada."
            )
        output_text = result.get("output_text")
        if not isinstance(output_text, str):
            raise SqlRepairProviderError(
                "Google Gemini retornou texto invalido."
            )
        return {
            "provider_name": GOOGLE_GEMINI_PROVIDER_NAME,
            "provider_model": _public_text(result.get("token_usage"), "model"),
            "output_text": output_text,
            "duration_ms": _duration_ms(result),
            "token_usage": _token_usage(result),
        }


def _duration_ms(result: GeminiClientResult | Mapping[str, object]) -> int:
    value = result.get("duration_ms")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value


def _token_usage(
    result: GeminiClientResult | Mapping[str, object],
) -> dict[str, int | str | None]:
    usage = result.get("token_usage")
    if not isinstance(usage, Mapping):
        usage = {}
    return {
        "provider": _public_text(usage, "provider"),
        "model": _public_text(usage, "model"),
        "prompt_tokens": _token_count(usage.get("prompt_tokens")),
        "response_tokens": _token_count(usage.get("response_tokens")),
        "total_tokens": _token_count(usage.get("total_tokens")),
    }


def _token_count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _public_text(value: object, key: str) -> str | None:
    if not isinstance(value, Mapping):
        return None
    raw = value.get(key)
    if not isinstance(raw, str) or not raw.strip():
        return None
    text = raw.strip()
    lowered = text.casefold()
    if any(
        marker in lowered
        for marker in ("bearer", "apikey", "api_key", "token", "secret")
    ):
        return None
    return text[:128]

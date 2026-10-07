from __future__ import annotations

from collections.abc import Mapping

from app.domain.sql_generation import (
    SQL_GENERATION_CONTRACT_VERSION,
    SqlGenerationProviderError,
    SqlGenerationProviderResult,
    SqlGenerationRequest,
)
from app.integrations.openai_compatible.configuration import (
    OpenAiCompatibleConfiguration,
)


class OpenAiCompatibleSqlGeneratorAdapter:
    def __init__(
        self,
        *,
        client,
        configuration: OpenAiCompatibleConfiguration,
    ) -> None:
        if client is None or not callable(getattr(client, "generate_content", None)):
            raise RuntimeError("client deve expor generate_content.")
        self._client = client
        self._configuration = configuration

    def __repr__(self) -> str:
        return "OpenAiCompatibleSqlGeneratorAdapter(<safe>)"

    def generate(
        self,
        request: SqlGenerationRequest,
    ) -> SqlGenerationProviderResult:
        if not isinstance(request, Mapping):
            raise SqlGenerationProviderError(
                "Requisicao OpenAI-compatible invalida."
            )
        if request.get("contract_version") != SQL_GENERATION_CONTRACT_VERSION:
            raise SqlGenerationProviderError(
                "Contrato OpenAI-compatible invalido."
            )

        result = self._client.generate_content(request)
        if not isinstance(result, Mapping) or result.get("status") != "success":
            reason = (
                result.get("error_code")
                if isinstance(result, Mapping)
                else "provider_failed"
            )
            raise SqlGenerationProviderError(
                "Provider OpenAI-compatible falhou de forma sanitizada.",
                reason=str(reason or "provider_failed"),
            )

        output_text = result.get("output_text")
        if not isinstance(output_text, str):
            raise SqlGenerationProviderError(
                "Provider OpenAI-compatible retornou texto invalido."
            )

        usage = result.get("token_usage")
        usage = usage if isinstance(usage, Mapping) else {}

        return {
            "provider_name": self._configuration.provider_key,
            "provider_model": self._configuration.model_id,
            "output_text": output_text,
            "duration_ms": (
                result.get("duration_ms")
                if isinstance(result.get("duration_ms"), int)
                else 0
            ),
            "token_usage": {
                "provider": _text(usage.get("provider")),
                "model": _text(usage.get("model")),
                "prompt_tokens": _token(usage.get("prompt_tokens")),
                "response_tokens": _token(usage.get("response_tokens")),
                "total_tokens": _token(usage.get("total_tokens")),
            },
        }


def _token(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _text(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()[:128]

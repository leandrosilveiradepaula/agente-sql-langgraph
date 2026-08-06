from __future__ import annotations

from collections.abc import Mapping

from app.domain.sql_generation import (
    SQL_GENERATION_CONTRACT_VERSION,
    SqlGenerationProviderError,
    SqlGenerationProviderResult,
    SqlGenerationRequest,
)
from app.integrations.google_gemini.configuration import (
    GOOGLE_GEMINI_PROVIDER_NAME,
)
from app.integrations.google_gemini.contracts import GeminiClientResult


class GoogleGeminiSqlGeneratorAdapter:
    def __init__(self, *, client) -> None:
        if client is None or not callable(getattr(client, "generate_content", None)):
            raise RuntimeError("client deve expor generate_content.")
        self._client = client

    def __repr__(self) -> str:
        return "GoogleGeminiSqlGeneratorAdapter(<safe>)"

    def generate(
        self,
        request: SqlGenerationRequest,
    ) -> SqlGenerationProviderResult:
        if not isinstance(request, Mapping):
            raise SqlGenerationProviderError(
                "Requisicao de geracao Gemini invalida."
            )
        if request.get("contract_version") != SQL_GENERATION_CONTRACT_VERSION:
            raise SqlGenerationProviderError(
                "Contrato de geracao Gemini invalido."
            )
        result = self._client.generate_content(request)
        if not isinstance(result, Mapping):
            raise SqlGenerationProviderError(
                "Google Gemini retornou resultado invalido."
            )
        if result.get("status") != "success":
            raise SqlGenerationProviderError(
                "Google Gemini falhou de forma sanitizada."
            )
        output_text = result.get("output_text")
        if not isinstance(output_text, str):
            raise SqlGenerationProviderError(
                "Google Gemini retornou texto invalido."
            )
        duration = _duration_ms(result)
        return {
            "provider_name": GOOGLE_GEMINI_PROVIDER_NAME,
            "output_text": output_text,
            "duration_ms": duration,
        }


def _duration_ms(result: GeminiClientResult | Mapping[str, object]) -> int:
    value = result.get("duration_ms")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value

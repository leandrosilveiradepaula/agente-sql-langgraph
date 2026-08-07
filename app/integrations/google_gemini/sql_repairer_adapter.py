from __future__ import annotations

from collections.abc import Mapping

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
            "output_text": output_text,
            "duration_ms": _duration_ms(result),
        }


def _duration_ms(result: GeminiClientResult | Mapping[str, object]) -> int:
    value = result.get("duration_ms")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return 0
    return value

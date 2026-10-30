from __future__ import annotations

from collections.abc import Mapping

from app.domain.sql_repair import (
    SQL_REPAIR_CONTRACT_VERSION,
    SqlRepairProviderError,
    SqlRepairProviderResult,
    SqlRepairRequest,
)
from app.integrations.openai_compatible.configuration import (
    OpenAiCompatibleConfiguration,
)


class OpenAiCompatibleSqlRepairerAdapter:
    """Repair adapter sharing the configured, authorized private LLM transport."""

    def __init__(self, *, client, configuration: OpenAiCompatibleConfiguration) -> None:
        if client is None or not callable(getattr(client, "generate_content", None)):
            raise RuntimeError("OpenAI-compatible repair client is unavailable.")
        self._client = client
        self._configuration = configuration

    def __repr__(self) -> str:
        return "OpenAiCompatibleSqlRepairerAdapter(<safe>)"

    def repair(self, request: SqlRepairRequest) -> SqlRepairProviderResult:
        if not isinstance(request, Mapping):
            raise SqlRepairProviderError("Invalid SQL repair request.")
        if request.get("contract_version") != SQL_REPAIR_CONTRACT_VERSION:
            raise SqlRepairProviderError("Invalid SQL repair contract.")
        result = self._client.generate_content(request)
        if not isinstance(result, Mapping) or result.get("status") != "success":
            # Never expose provider raw responses, headers, token or request.
            raise SqlRepairProviderError("Private SQL repair provider failed.")
        content = result.get("output_text")
        if not isinstance(content, str):
            raise SqlRepairProviderError("Private SQL repair response is invalid.")
        usage = result.get("token_usage")
        if not isinstance(usage, Mapping):
            usage = {}
        duration = result.get("duration_ms")
        return {
            "provider_name": self._configuration.provider_key,
            "provider_model": self._configuration.model_id,
            "output_text": content,
            "duration_ms": (duration if isinstance(duration, int)
                            and not isinstance(duration, bool) and duration >= 0 else 0),
            "token_usage": {
                "provider": self._configuration.provider_key,
                "model": self._configuration.model_id,
                "prompt_tokens": _count(usage.get("prompt_tokens")),
                "response_tokens": _count(usage.get("response_tokens")),
                "total_tokens": _count(usage.get("total_tokens")),
            },
        }


def _count(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None

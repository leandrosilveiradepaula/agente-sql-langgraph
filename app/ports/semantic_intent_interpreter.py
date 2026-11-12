"""Provider-neutral interpreter and optional private-model implementation.

Model output is untrusted until validated against a versioned tenant catalog.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class SemanticIntentInterpreter(Protocol):
    def interpret(self, request: Mapping[str, Any]) -> dict[str, Any]:
        """Return model text, model identity and sanitized token counts."""


class OpenAiCompatibleSemanticIntentInterpreter:
    """Uses the already configured private-model client and bounded transport."""

    def __init__(
        self, client: Any, *, provider_name: str, provider_model: str
    ) -> None:
        if not callable(getattr(client, "generate_content", None)):
            raise ValueError("semantic_client_invalid")
        if (not isinstance(provider_name, str) or not provider_name.strip()
                or not isinstance(provider_model, str) or not provider_model.strip()):
            raise ValueError("semantic_provider_identity_invalid")
        self._client = client
        self._provider_name = provider_name
        self._provider_model = provider_model

    def interpret(self, request: Mapping[str, Any]) -> dict[str, Any]:
        response = self._client.generate_content(request)
        if not isinstance(response, Mapping) or response.get("status") != "success":
            raise RuntimeError("semantic_interpretation_provider_unavailable")
        result = response.get("output_text")
        if not isinstance(result, str) or not result:
            raise RuntimeError("semantic_interpretation_response_invalid")
        raw_usage = response.get("token_usage")
        usage = raw_usage if isinstance(raw_usage, Mapping) else {}
        return {
            "output_text": result,
            "provider_name": self._provider_name,
            "provider_model": self._provider_model,
            "token_usage": {
                key: value
                for key in ("prompt_tokens", "response_tokens", "total_tokens")
                if type(value := usage.get(key)) is int and value >= 0
            },
        }

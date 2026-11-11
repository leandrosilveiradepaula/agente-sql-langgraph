"""Adapter for a provider-neutral semantic intent interpretation call.

The transport is injected. It is never allowed to produce SQL or touch a DB.
The caller validates every model-proposed intent and concept independently.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class SemanticIntentInterpreter(Protocol):
    def interpret(self, request: Mapping[str, Any]) -> str:
        """Return model text; all text remains untrusted until validation."""


class OpenAiCompatibleSemanticIntentInterpreter:
    """Uses the already configured private-model client and its budgeted transport."""

    def __init__(self, client: Any) -> None:
        if not callable(getattr(client, "generate_content", None)):
            raise ValueError("semantic_client_invalid")
        self._client = client

    def interpret(self, request: Mapping[str, Any]) -> str:
        response = self._client.generate_content(request)
        if not isinstance(response, Mapping) or response.get("status") != "success":
            raise RuntimeError("semantic_interpretation_provider_unavailable")
        result = response.get("output_text")
        if not isinstance(result, str) or not result:
            raise RuntimeError("semantic_interpretation_response_invalid")
        return result

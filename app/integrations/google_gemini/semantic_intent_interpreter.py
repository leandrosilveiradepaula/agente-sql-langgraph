"""Gemini implementation of the provider-neutral semantic intent port.

Uses the existing authenticated Gemini client. Only a tenant's authorized
semantic intent projection is sent; no SQL, benchmark answer or physical
schema is present. The returned text is checked by the shared fail-closed
validator before any planning.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.integrations.google_gemini.configuration import GoogleGeminiConfiguration


class GeminiSemanticIntentInterpreter:
    def __init__(self, *, client: Any, configuration: GoogleGeminiConfiguration) -> None:
        if not callable(getattr(client, "generate_content", None)):
            raise ValueError("semantic_client_invalid")
        self._client = client
        self._config = configuration

    def interpret(self, request: Mapping[str, Any]) -> dict[str, Any]:
        def build_payload(*, request: Mapping[str, Any], configuration: GoogleGeminiConfiguration) -> bytes:
            instruction = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            payload = {
                "contents": [{"role": "user", "parts": [{"text": instruction}]}],
                "generationConfig": {
                    "temperature": configuration.temperature,
                    "topP": configuration.top_p,
                    "topK": configuration.top_k,
                    "maxOutputTokens": configuration.max_output_tokens,
                    "responseMimeType": configuration.response_mime_type,
                    "thinkingConfig": {"thinkingBudget": configuration.thinking_budget},
                },
            }
            return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")

        response = self._client.generate_content(request, payload_builder=build_payload)
        if not isinstance(response, Mapping) or response.get("status") != "success":
            raise RuntimeError("semantic_interpretation_provider_unavailable")
        output = response.get("output_text")
        if not isinstance(output, str) or not output:
            raise RuntimeError("semantic_interpretation_response_invalid")
        usage = response.get("token_usage")
        usage = usage if isinstance(usage, Mapping) else {}
        return {
            "output_text": output,
            "provider_name": "google_gemini",
            "provider_model": self._config.model_id,
            "token_usage": {
                key: value
                for key in ("prompt_tokens", "response_tokens", "total_tokens")
                if type(value := usage.get(key)) is int and value >= 0
            },
        }

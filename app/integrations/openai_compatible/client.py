from __future__ import annotations

import json
import time
from collections.abc import Mapping

from app.infrastructure.http.http_contracts import (
    HttpHeader,
    HttpTransportRequest,
)
from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.integrations.openai_compatible.configuration import (
    OpenAiCompatibleConfiguration,
    build_chat_completions_url,
)
from app.ports.http_transport import HttpTransport
from app.ports.secret_value_provider import SecretName, SecretValueProvider


class OpenAiCompatibleClient:
    def __init__(
        self,
        *,
        configuration: OpenAiCompatibleConfiguration,
        secret_provider: SecretValueProvider,
        http_transport: HttpTransport,
    ) -> None:
        self._configuration = configuration
        self._secret_provider = secret_provider
        self._http = http_transport

    def __repr__(self) -> str:
        return "OpenAiCompatibleClient(<safe>)"

    def generate_content(self, request: object) -> dict[str, object]:
        started = time.monotonic()
        if not isinstance(request, Mapping):
            return _failure("invalid_request", started)

        secret_result = self._secret_provider.get_secret(
            SecretName(self._configuration.api_key_secret_name)
        )
        if secret_result.get("status") != "success":
            return _failure("secret_unavailable", started)
        secret = secret_result.get("secret")
        if not isinstance(secret, SensitiveSecret):
            return _failure("secret_invalid", started)

        try:
            body = json.dumps(
                {
                    "model": self._configuration.model_id,
                    "messages": [
                        {
                            "role": "user",
                            "content": _prompt_text(request),
                        }
                    ],
                    "temperature": self._configuration.temperature,
                    "max_tokens": self._configuration.max_tokens,
                    "stream": False,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except Exception:
            return _failure("invalid_request", started)

        bearer = SensitiveSecret(
            "Bearer " + secret.reveal_for_transport()
        )

        result = self._http.send(
            HttpTransportRequest(
                method="POST",
                url=build_chat_completions_url(self._configuration),
                headers=(
                    HttpHeader("Content-Type", public_value="application/json"),
                    HttpHeader("Accept", public_value="application/json"),
                    HttpHeader("Authorization", sensitive_value=bearer),
                ),
                body=body,
                connect_timeout_seconds=self._configuration.connect_timeout_seconds,
                read_timeout_seconds=self._configuration.read_timeout_seconds,
                max_response_bytes=self._configuration.max_response_bytes,
                operation_name="openai_compatible_chat_completions",
                allow_private_http=self._configuration.allow_private_http,
            )
        )
        if result.status != "success" or result.response is None:
            return _failure(str(result.status), started)

        response = result.response
        if response.status_code in {401, 403}:
            return _failure("authentication_failed", started)
        if response.status_code == 429:
            return _failure("rate_limited", started)
        if response.status_code < 200 or response.status_code > 299:
            return _failure("provider_unavailable", started)

        try:
            payload = json.loads(response.body.decode("utf-8"))
            text = payload["choices"][0]["message"]["content"]
            usage = payload.get("usage", {})
            if not isinstance(text, str) or not text.strip():
                raise ValueError
        except Exception:
            return _failure("invalid_response", started)

        return {
            "status": "success",
            "output_text": text,
            "duration_ms": (
                response.duration_ms
                if isinstance(response.duration_ms, int)
                else _elapsed_ms(started)
            ),
            "token_usage": {
                "provider": self._configuration.provider_key,
                "model": self._configuration.model_id,
                "prompt_tokens": _token(usage.get("prompt_tokens")),
                "response_tokens": _token(usage.get("completion_tokens")),
                "total_tokens": _token(usage.get("total_tokens")),
            },
        }


def _prompt_text(request: Mapping[str, object]) -> str:
    return json.dumps(
        request,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _token(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _failure(code: str, started: float) -> dict[str, object]:
    return {
        "status": "failure",
        "error_code": code[:64],
        "duration_ms": _elapsed_ms(started),
    }


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))

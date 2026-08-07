from __future__ import annotations

import time
from collections.abc import Mapping

from app.infrastructure.http.http_contracts import (
    HttpHeader,
    HttpTransportRequest,
)
from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.integrations.google_gemini.configuration import (
    GEMINI_API_KEY_SECRET_NAME,
    GoogleGeminiConfiguration,
    build_gemini_generate_content_url,
)
from app.integrations.google_gemini.contracts import (
    GeminiClientResult,
    build_gemini_payload,
    extract_gemini_text,
    gemini_failure,
    gemini_success,
    parse_gemini_json_response,
)
from app.ports.http_transport import HttpTransport
from app.ports.secret_value_provider import SecretName, SecretValueProvider


class GoogleGeminiClient:
    def __init__(
        self,
        *,
        configuration: GoogleGeminiConfiguration,
        secret_provider: SecretValueProvider,
        http_transport: HttpTransport,
        api_key_secret_name: SecretName = SecretName(
            GEMINI_API_KEY_SECRET_NAME
        ),
    ) -> None:
        if not isinstance(configuration, GoogleGeminiConfiguration):
            raise RuntimeError("configuration deve ser injetada.")
        self._configuration = configuration
        self._secret_provider = secret_provider
        self._http = http_transport
        self._api_key_secret_name = SecretName(str(api_key_secret_name))

    def __repr__(self) -> str:
        return "GoogleGeminiClient(<safe>)"

    def generate_content(
        self,
        request,
        *,
        payload_builder=build_gemini_payload,
    ) -> GeminiClientResult:
        started = time.monotonic()
        try:
            if not isinstance(request, Mapping):
                return gemini_failure("invalid_response")
            secret_result = self._secret_provider.get_secret(
                self._api_key_secret_name
            )
            status = secret_result.get("status")
            if status != "success":
                return _secret_failure(status)
            secret = secret_result.get("secret")
            if not isinstance(secret, SensitiveSecret):
                return gemini_failure("secret_invalid")
            body = payload_builder(
                request=request,
                configuration=self._configuration,
            )
            transport_result = self._http.send(
                HttpTransportRequest(
                    method="POST",
                    url=build_gemini_generate_content_url(
                        self._configuration
                    ),
                    headers=(
                        HttpHeader(
                            "Content-Type",
                            public_value="application/json",
                        ),
                        HttpHeader(
                            "Accept",
                            public_value="application/json",
                        ),
                        HttpHeader(
                            "Accept-Encoding",
                            public_value="identity",
                        ),
                        HttpHeader(
                            "x-goog-api-key",
                            sensitive_value=secret,
                        ),
                    ),
                    body=body,
                    connect_timeout_seconds=(
                        self._configuration.connect_timeout_seconds
                    ),
                    read_timeout_seconds=(
                        self._configuration.read_timeout_seconds
                    ),
                    max_response_bytes=(
                        self._configuration.max_response_bytes
                    ),
                    operation_name="google_gemini_generate_content",
                )
            )
            if (
                transport_result.status != "success"
                or transport_result.response is None
            ):
                return _transport_failure(transport_result.status)
            response = transport_result.response
            duration_ms = (
                response.duration_ms
                if isinstance(response.duration_ms, int)
                else _elapsed_ms(started)
            )
            http_status = response.status_code
            if http_status in {401, 403}:
                return gemini_failure(
                    "authentication_failed",
                    duration_ms=duration_ms,
                )
            if http_status == 408:
                return gemini_failure(
                    "transport_timeout",
                    duration_ms=duration_ms,
                )
            if http_status == 429:
                return gemini_failure(
                    "rate_limited",
                    duration_ms=duration_ms,
                )
            if 500 <= http_status <= 599:
                return gemini_failure(
                    "provider_unavailable",
                    duration_ms=duration_ms,
                )
            if 400 <= http_status <= 499:
                return gemini_failure(
                    "http_error",
                    duration_ms=duration_ms,
                    diagnostics={"http_status": http_status},
                )
            if not 200 <= http_status <= 299:
                return gemini_failure(
                    "invalid_response",
                    duration_ms=duration_ms,
                )
            try:
                payload = parse_gemini_json_response(response.body)
                output_text, finish_reasons = extract_gemini_text(payload)
            except Exception:
                return gemini_failure(
                    "invalid_response",
                    duration_ms=duration_ms,
                )
            return gemini_success(
                output_text=output_text,
                finish_reasons=finish_reasons,
                duration_ms=duration_ms,
            )
        except Exception:
            return gemini_failure(
                "unexpected_error",
                duration_ms=_elapsed_ms(started),
            )


def _secret_failure(status: object) -> GeminiClientResult:
    if status == "missing":
        return gemini_failure("secret_missing")
    if status == "unavailable":
        return gemini_failure("secret_unavailable")
    if status == "invalid":
        return gemini_failure("secret_invalid")
    return gemini_failure("unexpected_error")


def _transport_failure(status: object) -> GeminiClientResult:
    if status == "timeout":
        return gemini_failure("transport_timeout")
    if status in {"dns_failure", "tls_failure", "connection_failure"}:
        return gemini_failure("transport_unavailable")
    if status in {"response_too_large", "invalid_response"}:
        return gemini_failure("invalid_response")
    return gemini_failure("unexpected_error")


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))

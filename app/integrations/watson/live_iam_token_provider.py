from __future__ import annotations

import json
from collections.abc import Mapping
from urllib.parse import urlencode

from app.infrastructure.http.http_contracts import HttpHeader, HttpTransportRequest
from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.integrations.watson.configuration import WatsonFlowConfiguration
from app.integrations.watson.iam_contracts import (
    IamTokenRequest,
    IamTokenResult,
    SensitiveBearerToken,
    iam_token_failure,
    iam_token_success,
)
from app.ports.http_transport import HttpTransport
from app.ports.secret_value_provider import SecretName, SecretValueProvider


MAX_IAM_EXPIRES_IN = 86_400 * 30


class LiveIamTokenProvider:
    def __init__(
        self,
        *,
        configuration: WatsonFlowConfiguration,
        api_key_secret_name: SecretName,
        secret_provider: SecretValueProvider,
        http_transport: HttpTransport,
    ) -> None:
        self._configuration = configuration
        self._secret_name = SecretName(str(api_key_secret_name))
        self._secret_provider = secret_provider
        self._http = http_transport

    def __repr__(self) -> str:
        return "LiveIamTokenProvider(<safe>)"

    def get_token(self, request: IamTokenRequest) -> IamTokenResult:
        if not isinstance(request, Mapping):
            return iam_token_failure("invalid_response")
        secret_result = self._secret_provider.get_secret(self._secret_name)
        if secret_result.get("status") != "success":
            return _secret_failure(secret_result.get("status"))
        secret = secret_result.get("secret")
        if not isinstance(secret, SensitiveSecret):
            return iam_token_failure("invalid_response")
        body = urlencode(
            (
                ("grant_type", "urn:ibm:params:oauth:grant-type:apikey"),
                ("apikey", secret.reveal_for_transport()),
            )
        ).encode("ascii")
        transport_result = self._http.send(
            HttpTransportRequest(
                method="POST",
                url=self._configuration.iam_token_url,
                headers=(
                    HttpHeader("Content-Type", public_value="application/x-www-form-urlencoded"),
                    HttpHeader("Accept", public_value="application/json"),
                    HttpHeader("Accept-Encoding", public_value="identity"),
                ),
                body=body,
                connect_timeout_seconds=self._configuration.connect_timeout_seconds,
                read_timeout_seconds=self._configuration.request_timeout_seconds,
                max_response_bytes=self._configuration.max_response_bytes,
                operation_name="watson_iam_token",
                request_id=str(request.get("request_id", "")) or None,
            )
        )
        if transport_result.status != "success" or transport_result.response is None:
            return _transport_failure(transport_result.status)
        response = transport_result.response
        if response.status_code in {400, 401, 403}:
            return iam_token_failure("authentication_failed")
        if response.status_code == 408:
            return iam_token_failure("timeout")
        if response.status_code == 429 or 500 <= response.status_code <= 599:
            return iam_token_failure("unavailable")
        if response.status_code != 200:
            return iam_token_failure("invalid_response")
        if not _is_json_content_type(response.headers.get("content-type")):
            return iam_token_failure("invalid_response")
        try:
            payload = _loads_json_mapping(response.body)
        except ValueError:
            return iam_token_failure("invalid_response")
        access_token = payload.get("access_token")
        if not isinstance(access_token, str):
            return iam_token_failure("invalid_response")
        token_type = payload.get("token_type", "Bearer")
        if token_type != "Bearer":
            return iam_token_failure("invalid_response")
        expires_in = payload.get("expires_in")
        if expires_in is not None:
            if isinstance(expires_in, bool) or not isinstance(expires_in, int):
                return iam_token_failure("invalid_response")
            if expires_in <= 0 or expires_in > MAX_IAM_EXPIRES_IN:
                return iam_token_failure("invalid_response")
        try:
            token = SensitiveBearerToken(access_token)
        except Exception:
            return iam_token_failure("invalid_response")
        return iam_token_success(token, token_type="Bearer", expires_in=expires_in)


def _secret_failure(status: object) -> IamTokenResult:
    if status == "missing" or status == "invalid":
        return iam_token_failure("authentication_failed")
    if status == "unavailable":
        return iam_token_failure("unavailable")
    return iam_token_failure("unexpected_error")


def _transport_failure(status: object) -> IamTokenResult:
    return {
        "timeout": iam_token_failure("timeout"),
        "dns_failure": iam_token_failure("unavailable"),
        "tls_failure": iam_token_failure("unavailable"),
        "connection_failure": iam_token_failure("unavailable"),
        "response_too_large": iam_token_failure("invalid_response"),
        "invalid_response": iam_token_failure("invalid_response"),
    }.get(status, iam_token_failure("unexpected_error"))


def _is_json_content_type(value: str | None) -> bool:
    if not isinstance(value, str):
        return False
    parts = [part.strip() for part in value.split(";")]
    media = parts[0].casefold()
    if media != "application/json" and not media.endswith("+json"):
        return False
    for part in parts[1:]:
        if part.casefold().startswith("charset="):
            charset = part.split("=", 1)[1].strip().strip('"').casefold()
            if charset not in {"utf-8", "utf8"}:
                return False
    return True


def _loads_json_mapping(body: bytes) -> dict[str, object]:
    text = body.decode("utf-8", errors="strict")

    def reject_constant(value: str) -> object:
        raise ValueError(value)

    def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        output: dict[str, object] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError("duplicate key")
            output[key] = value
        return output

    parsed = json.loads(
        text,
        object_pairs_hook=no_duplicates,
        parse_constant=reject_constant,
    )
    if not isinstance(parsed, dict):
        raise ValueError("root")
    return parsed

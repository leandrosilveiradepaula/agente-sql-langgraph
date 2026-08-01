from __future__ import annotations

import json
from collections.abc import Mapping

from app.infrastructure.http.http_contracts import HttpHeader, HttpTransportRequest
from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.integrations.watson.configuration import WatsonFlowConfiguration
from app.integrations.watson.flow_contracts import (
    WatsonFlowRunRequest,
    WatsonFlowRunResult,
    watson_flow_failure,
    watson_flow_success,
)
from app.integrations.watson.flow_limits import WatsonFlowLimits
from app.integrations.watson.live_configuration import build_watson_flow_run_url
from app.ports.http_transport import HttpTransport


class LiveWatsonFlowClient:
    def __init__(
        self,
        *,
        configuration: WatsonFlowConfiguration,
        http_transport: HttpTransport,
        limits: WatsonFlowLimits,
    ) -> None:
        self._configuration = configuration
        self._http = http_transport
        self._limits = limits

    def __repr__(self) -> str:
        return "LiveWatsonFlowClient(<safe>)"

    def run_flow(self, request: WatsonFlowRunRequest) -> WatsonFlowRunResult:
        if not isinstance(request, Mapping):
            return watson_flow_failure("invalid_response", invocation_id="invalid")
        invocation_id = str(request.get("invocation_id") or "invalid")
        try:
            payload = dict(request["payload"])
            if set(payload.keys()) != {"sql_query"}:
                return watson_flow_failure("invalid_response", invocation_id=invocation_id)
            body = json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        except Exception:
            return watson_flow_failure("invalid_response", invocation_id=invocation_id)
        if len(body) > self._limits.max_payload_bytes:
            return watson_flow_failure("invalid_response", invocation_id=invocation_id)
        bearer = request.get("bearer_token")
        try:
            token = bearer.reveal_for_client()  # type: ignore[attr-defined]
        except Exception:
            return watson_flow_failure("authentication_failed", invocation_id=invocation_id)
        transport_result = self._http.send(
            HttpTransportRequest(
                method="POST",
                url=build_watson_flow_run_url(self._configuration),
                headers=(
                    HttpHeader("Authorization", sensitive_value=SensitiveSecret(f"Bearer {token}")),
                    HttpHeader("Content-Type", public_value="application/json"),
                    HttpHeader("Accept", public_value="application/json"),
                    HttpHeader("Accept-Encoding", public_value="identity"),
                ),
                body=body,
                connect_timeout_seconds=self._configuration.connect_timeout_seconds,
                read_timeout_seconds=self._configuration.request_timeout_seconds,
                max_response_bytes=self._configuration.max_response_bytes,
                operation_name=f"watson_flow_{request.get('purpose', 'unknown')}",
                request_id=str(request.get("request_id", "")) or None,
            )
        )
        if transport_result.status != "success" or transport_result.response is None:
            return _transport_failure(transport_result.status, invocation_id)
        response = transport_result.response
        retry_after = _retry_after(response.headers.get("retry-after"))
        status = _map_status(response.status_code)
        if status != "success":
            return watson_flow_failure(
                status,
                invocation_id=invocation_id,
                http_status=response.status_code,
                retry_after_seconds=retry_after if status == "rate_limited" else None,
                duration_ms=response.duration_ms,
            )
        if not _is_json_content_type(response.headers.get("content-type")):
            return watson_flow_failure("invalid_response", invocation_id=invocation_id)
        try:
            payload = _loads_json_mapping(response.body)
        except ValueError:
            return watson_flow_failure("invalid_response", invocation_id=invocation_id)
        return watson_flow_success(
            payload,
            invocation_id=invocation_id,
            duration_ms=response.duration_ms,
        )


def _transport_failure(status: object, invocation_id: str) -> WatsonFlowRunResult:
    return {
        "timeout": watson_flow_failure("timeout", invocation_id=invocation_id),
        "dns_failure": watson_flow_failure("unavailable", invocation_id=invocation_id),
        "tls_failure": watson_flow_failure("unavailable", invocation_id=invocation_id),
        "connection_failure": watson_flow_failure("unavailable", invocation_id=invocation_id),
        "response_too_large": watson_flow_failure("invalid_response", invocation_id=invocation_id),
        "invalid_response": watson_flow_failure("invalid_response", invocation_id=invocation_id),
    }.get(status, watson_flow_failure("unexpected_error", invocation_id=invocation_id))


def _map_status(status_code: int):
    if 200 <= status_code <= 299:
        return "success"
    if status_code in {401, 403}:
        return "authentication_failed"
    if status_code == 408:
        return "timeout"
    if status_code == 429:
        return "rate_limited"
    if 500 <= status_code <= 599 or status_code == 404:
        return "unavailable"
    if 400 <= status_code <= 499:
        return "http_error"
    return "invalid_response"


def _retry_after(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    if parsed < 0 or parsed > 86_400:
        return None
    return parsed


def _is_json_content_type(value: str | None) -> bool:
    from app.integrations.watson.live_iam_token_provider import _is_json_content_type as check

    return check(value)


def _loads_json_mapping(body: bytes) -> dict[str, object]:
    from app.integrations.watson.live_iam_token_provider import _loads_json_mapping as load

    return load(body)

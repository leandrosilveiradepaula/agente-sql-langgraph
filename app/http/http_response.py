from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from app.domain.application_response_types import (
    APPLICATION_RESPONSE_CONTRACT_VERSION,
    ApplicationResponse,
    ApplicationResponseStatus,
)
from app.domain.result_normalization import stable_fingerprint
from app.http.http_response_types import (
    HttpResponseEnvelope,
    HttpResponseLimits,
)
from app.http.security_headers import security_headers
from app.http.status_mapping import http_status_for_application_response

_MIN_RESPONSE_BODY_BYTES = 640


def default_http_response_limits() -> HttpResponseLimits:
    return {
        "max_response_body_bytes": 1_000_000,
        "max_header_count": 16,
        "max_header_name_length": 64,
        "max_header_value_length": 256,
    }


def validate_http_response_limits(
    limits: Mapping[str, Any],
) -> HttpResponseLimits:
    defaults = default_http_response_limits()
    maximums = {
        "max_response_body_bytes": 10_000_000,
        "max_header_count": 100,
        "max_header_name_length": 256,
        "max_header_value_length": 2_000,
    }
    output: dict[str, int] = {}
    for key, maximum in maximums.items():
        value = limits.get(key, defaults[key])
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Limite HTTP invalido.")
        if value <= 0 or value > maximum:
            raise ValueError("Limite HTTP fora da faixa.")
        if key == "max_response_body_bytes" and value < _MIN_RESPONSE_BODY_BYTES:
            raise ValueError("Limite HTTP fora da faixa.")
        output[key] = value
    return output  # type: ignore[return-value]


def application_response_to_http_response(
    response: Mapping[str, Any],
    *,
    limits: HttpResponseLimits,
    status_code: int | None = None,
) -> HttpResponseEnvelope:
    safe_response = deepcopy(dict(response))
    body = _json_bytes(safe_response)
    if len(body) > limits["max_response_body_bytes"]:
        safe_response = minimal_http_application_response(
            status="infrastructure_error",
            code="HTTP_RESPONSE_TOO_LARGE",
        )
        body = _json_bytes(safe_response)
        if len(body) > limits["max_response_body_bytes"]:
            safe_response = _tiny_http_application_response()
            body = _json_bytes(safe_response)
        status_code = 503
    headers = _response_headers(safe_response, limits)
    return {
        "status_code": (
            status_code
            if status_code is not None
            else http_status_for_application_response(safe_response)
        ),
        "headers": headers,
        "body": body,
    }


def minimal_http_application_response(
    *,
    status: ApplicationResponseStatus,
    code: str,
    request_id: str = "",
    run_id: str = "",
) -> ApplicationResponse:
    response: ApplicationResponse = {
        "contract_version": APPLICATION_RESPONSE_CONTRACT_VERSION,
        "response_id": stable_fingerprint(
            {
                "contract_version": APPLICATION_RESPONSE_CONTRACT_VERSION,
                "request_id": request_id,
                "run_id": run_id,
                "source": "http_entry_adapter",
                "code": code,
            }
        ),
        "request_id": request_id,
        "run_id": run_id,
        "status": status,
        "original_outcome": status,
        "message": (
            "A solicitacao HTTP nao pode ser processada."
            if status == "rejected"
            else "O processamento HTTP nao pode ser concluido."
        ),
        "data": None,
        "errors": [
            {
                "code": code,
                "category": "http",
                "stage": "http_entry_adapter",
                "message": (
                    "A requisicao HTTP nao pode ser processada."
                    if status == "rejected"
                    else "O processamento HTTP nao pode ser concluido."
                ),
                "retryable": status == "infrastructure_error",
            }
        ],
        "warnings": [],
        "metadata": {
            "persisted": False,
            "audited": False,
            "observability_degraded": False,
            "original_outcome": status,
            "finalization_status": "incomplete",
            "contract_versions": {
                "application_response": APPLICATION_RESPONSE_CONTRACT_VERSION
            },
            "lineage": {},
        },
        "finalization": {
            "status": "incomplete",
            "run_record_built": False,
            "persisted": False,
            "persistence_record_id": None,
            "audited": False,
            "audit_event_id": None,
            "observability_emitted": False,
            "observability_degraded": False,
            "error_codes": [code],
        },
        "response_fingerprint": "",
    }
    payload = deepcopy(response)
    payload.pop("response_fingerprint", None)
    response["response_fingerprint"] = stable_fingerprint(payload)
    return deepcopy(response)


def _tiny_http_application_response() -> ApplicationResponse:
    response: ApplicationResponse = {
        "contract_version": APPLICATION_RESPONSE_CONTRACT_VERSION,
        "response_id": stable_fingerprint(
            {
                "contract_version": APPLICATION_RESPONSE_CONTRACT_VERSION,
                "source": "http_entry_adapter",
                "code": "HTTP_RESPONSE_TOO_LARGE",
                "fallback": "tiny",
            }
        ),
        "request_id": "",
        "run_id": "",
        "status": "infrastructure_error",
        "original_outcome": "infrastructure_error",
        "message": "O processamento HTTP nao pode ser concluido.",
        "data": None,
        "errors": [
            {
                "code": "HTTP_RESPONSE_TOO_LARGE",
                "category": "http",
                "stage": "http_entry_adapter",
                "message": "O processamento HTTP nao pode ser concluido.",
                "retryable": True,
            }
        ],
        "warnings": [],
        "metadata": {"lineage": {}},
        "finalization": {"status": "incomplete"},
        "response_fingerprint": "",
    }
    payload = deepcopy(response)
    payload.pop("response_fingerprint", None)
    response["response_fingerprint"] = stable_fingerprint(payload)
    return deepcopy(response)


def _json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _response_headers(
    response: Mapping[str, Any],
    limits: HttpResponseLimits,
) -> dict[str, str]:
    headers = security_headers()
    for source, header in [
        ("request_id", "X-Request-ID"),
        ("run_id", "X-Run-ID"),
        ("response_id", "X-Response-ID"),
    ]:
        value = response.get(source)
        if _safe_header_value(value, limits["max_header_value_length"]):
            headers[header] = str(value)
    if len(headers) > limits["max_header_count"]:
        raise ValueError("Quantidade de headers excede limite.")
    for name, value in headers.items():
        if len(name.encode("utf-8")) > limits["max_header_name_length"]:
            raise ValueError("Nome de header excede limite.")
        if len(value.encode("utf-8")) > limits["max_header_value_length"]:
            raise ValueError("Valor de header excede limite.")
    return headers


def _safe_header_value(value: object, max_length: int) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if len(value.encode("utf-8")) > max_length:
        return False
    return all(char.isalnum() or char in "._:-" for char in value)

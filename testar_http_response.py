from __future__ import annotations

import json
from copy import deepcopy

from app.domain.application_response_types import (
    APPLICATION_RESPONSE_CONTRACT_VERSION,
)
from app.domain.result_normalization import stable_fingerprint
from app.http.http_response import (
    application_response_to_http_response,
    default_http_response_limits,
    minimal_http_application_response,
)
from app.http.status_mapping import http_status_for_application_response


def _response(status="success", *, request_id="req-1", run_id="run-1", data=None):
    if data is None and status == "success":
        data = {
            "result": {
                "contract_version": "v1",
                "columns": [{"name": "valor"}],
                "rows": [{"cells": [{"value": "ação"}]}],
                "result_fingerprint": "result-1",
            },
            "pagination": {
                "mode": "none",
                "has_more": False,
                "next_cursor": None,
                "total_rows": 1,
                "returned_rows": 1,
            },
        }
    response = {
        "contract_version": APPLICATION_RESPONSE_CONTRACT_VERSION,
        "response_id": "response-1",
        "request_id": request_id,
        "run_id": run_id,
        "status": status,
        "original_outcome": status,
        "message": "Mensagem pública",
        "data": data if status == "success" else None,
        "errors": [],
        "warnings": [],
        "metadata": {"lineage": {}, "canonical_json": None},
        "finalization": {"status": "completed" if status == "success" else "incomplete"},
        "response_fingerprint": "",
    }
    payload = deepcopy(response)
    payload.pop("response_fingerprint", None)
    response["response_fingerprint"] = stable_fingerprint(payload)
    return response


def _body(http_response):
    return json.loads(http_response["body"].decode("utf-8"))


def test_serializacao_status_headers_e_utf8() -> None:
    for status, expected in [
        ("success", 200),
        ("rejected", 422),
        ("infrastructure_error", 503),
    ]:
        response = _response(status)
        original = deepcopy(response)
        http = application_response_to_http_response(
            response,
            limits=default_http_response_limits(),
        )
        assert http["status_code"] == expected
        assert http["headers"]["Content-Type"] == "application/json; charset=utf-8"
        assert http["headers"]["X-Content-Type-Options"] == "nosniff"
        assert http["headers"]["Cache-Control"] == "no-store"
        assert http["headers"]["Pragma"] == "no-cache"
        assert http["headers"]["Referrer-Policy"] == "no-referrer"
        assert http["headers"]["X-Request-ID"] == "req-1"
        assert http["headers"]["X-Run-ID"] == "run-1"
        assert http["headers"]["X-Response-ID"] == "response-1"
        assert _body(http)["response_fingerprint"] == response["response_fingerprint"]
        assert response == original


def test_json_safe_bytes_payload_e_sem_canonical_armazenado() -> None:
    response = _response()
    http = application_response_to_http_response(
        response,
        limits=default_http_response_limits(),
    )
    assert len(http["body"]) == len(http["body"].decode("utf-8").encode("utf-8"))
    json.dumps(_body(http), allow_nan=False)
    assert _body(http)["metadata"]["canonical_json"] is None
    assert "payload" not in _body(http)
    assert _body(http)["data"] == response["data"]


def test_status_mapping_e_id_invalido_nao_refletido() -> None:
    assert http_status_for_application_response({"status": "success"}) == 200
    assert http_status_for_application_response({"status": "rejected"}) == 422
    assert http_status_for_application_response({"status": "infrastructure_error"}) == 503
    response = _response(request_id="bad header", run_id="run-1")
    http = application_response_to_http_response(
        response,
        limits=default_http_response_limits(),
    )
    assert "X-Request-ID" not in http["headers"]
    assert http["headers"]["X-Run-ID"] == "run-1"


def test_resposta_acima_do_limite_e_copia_independente() -> None:
    response = _response(data={"large": "x" * 2000})
    original = deepcopy(response)
    http = application_response_to_http_response(
        response,
        limits={**default_http_response_limits(), "max_response_body_bytes": 900},
    )
    body = _body(http)
    assert http["status_code"] == 503
    assert body["status"] == "infrastructure_error"
    assert body["data"] is None
    assert body["errors"][0]["code"] == "HTTP_RESPONSE_TOO_LARGE"
    assert response == original
    body["status"] = "changed"
    assert response["status"] == "success"


def test_resposta_minima() -> None:
    response = minimal_http_application_response(
        status="rejected",
        code="HTTP_JSON_INVALID",
    )
    assert response["status"] == "rejected"
    assert response["data"] is None
    assert response["errors"][0]["code"] == "HTTP_JSON_INVALID"


def main() -> None:
    tests = [
        test_serializacao_status_headers_e_utf8,
        test_json_safe_bytes_payload_e_sem_canonical_armazenado,
        test_status_mapping_e_id_invalido_nao_refletido,
        test_resposta_acima_do_limite_e_copia_independente,
        test_resposta_minima,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()

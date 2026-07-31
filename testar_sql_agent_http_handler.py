from __future__ import annotations

import json
from copy import deepcopy

from app.domain.application_response_types import (
    APPLICATION_RESPONSE_CONTRACT_VERSION,
)
from app.domain.result_normalization import stable_fingerprint
from app.adapters.testing.fake_authenticator import FakeAuthenticator
from app.adapters.testing.fake_authorizer import FakeAuthorizer
from app.http.http_request import default_http_request_limits
from app.http.http_response import default_http_response_limits
from app.http.sql_agent_http_handler import SqlAgentHttpHandler
from app.security.auth_types import (
    authentication_result,
    authorization_decision,
    create_authenticated_principal,
    default_auth_security_limits,
)


class FakeApplicationService:
    def __init__(self, response=None, exception=None) -> None:
        self.response = response if response is not None else _response()
        self.exception = exception
        self.calls = 0
        self.requests = []

    def execute(self, request):
        self.calls += 1
        self.requests.append(deepcopy(request))
        if self.exception:
            raise self.exception
        return deepcopy(self.response)


def _response(status="success", *, request_id="req-1", run_id="run-1", data=None):
    if data is None and status == "success":
        data = {
            "result": {
                "contract_version": "v1",
                "columns": [],
                "rows": [],
                "result_fingerprint": "result-1",
            },
            "pagination": {
                "mode": "none",
                "has_more": False,
                "next_cursor": None,
                "total_rows": 0,
                "returned_rows": 0,
            },
        }
    response = {
        "contract_version": APPLICATION_RESPONSE_CONTRACT_VERSION,
        "response_id": "response-1",
        "request_id": request_id,
        "run_id": run_id,
        "status": status,
        "original_outcome": status,
        "message": "Public message",
        "data": data if status == "success" else None,
        "errors": [],
        "warnings": [],
        "metadata": {"lineage": {}},
        "finalization": {"status": "completed" if status == "success" else "incomplete"},
        "response_fingerprint": "",
    }
    payload = deepcopy(response)
    payload.pop("response_fingerprint", None)
    response["response_fingerprint"] = stable_fingerprint(payload)
    return response


def _principal():
    return create_authenticated_principal(
        {
            "subject_id": "principal-1",
            "email": "principal@example.invalid",
            "profile": "generic-profile",
            "organization_id": "org-1",
            "roles": ["role.local"],
            "scopes": ["scope.local"],
        },
        limits=default_auth_security_limits(),
    )


def _authenticator():
    return FakeAuthenticator(
        result=authentication_result(
            status="authenticated",
            principal=_principal(),
        )
    )


def _authorizer():
    return FakeAuthorizer(decision=authorization_decision(status="allowed"))


def _handler(service=None, response_limits=None):
    return SqlAgentHttpHandler(
        application_service=service or FakeApplicationService(),
        authenticator=_authenticator(),
        authorizer=_authorizer(),
        auth_limits=default_auth_security_limits(),
        request_limits=default_http_request_limits(),
        response_limits=response_limits or default_http_response_limits(),
    )


def _request(body=b'{"question":"ok","request_id":"req-1","run_id":"run-1"}', **overrides):
    request = {
        "method": "POST",
        "path": "/v1/sql-agent/query",
        "headers": {"Content-Type": "application/json", "Authorization": "Bearer test-opaque-token"},
        "body": body,
    }
    request.update(overrides)
    return request


def _body(response):
    return json.loads(response["body"].decode("utf-8"))


def test_request_valida_chama_service_uma_vez_e_delega_payload() -> None:
    service = FakeApplicationService()
    handler = _handler(service)
    http = handler.handle(_request())
    assert service.calls == 1
    assert service.requests[0] == {
        "question": "ok",
        "request_id": "req-1",
        "run_id": "run-1",
        "user": {
            "id": "principal-1",
            "email": "principal@example.invalid",
            "profile": "generic-profile",
            "organization_id": "org-1",
        },
    }
    assert http["status_code"] == 200
    assert _body(http)["status"] == "success"


def test_request_invalida_nao_chama_service() -> None:
    service = FakeApplicationService()
    handler = _handler(service)
    http = handler.handle(_request(body=b"{"))
    assert service.calls == 0
    assert http["status_code"] == 400
    assert _body(http)["errors"][0]["code"] == "HTTP_JSON_INVALID"


def test_status_mapping() -> None:
    for status, expected in [
        ("success", 200),
        ("rejected", 422),
        ("infrastructure_error", 503),
    ]:
        service = FakeApplicationService(_response(status=status))
        http = _handler(service).handle(_request())
        assert http["status_code"] == expected


def test_erros_de_transporte_status_e_allow() -> None:
    handler = _handler()
    cases = [
        (_request(body=b"x" * 100, headers={"Content-Type": "application/json", "Authorization": "Bearer test-opaque-token"}), 413),
        (_request(headers={"Content-Type": "text/plain", "Authorization": "Bearer test-opaque-token"}), 415),
        (_request(headers={"Content-Type": "application/json", "Accept": "text/html", "Authorization": "Bearer test-opaque-token"}), 406),
        (_request(path="/missing"), 404),
    ]
    small_handler = SqlAgentHttpHandler(
        application_service=FakeApplicationService(),
        authenticator=_authenticator(),
        authorizer=_authorizer(),
        auth_limits=default_auth_security_limits(),
        request_limits={**default_http_request_limits(), "max_request_body_bytes": 8},
        response_limits=default_http_response_limits(),
    )
    assert small_handler.handle(cases[0][0])["status_code"] == 413
    for request, expected in cases[1:]:
        assert handler.handle(request)["status_code"] == expected
    method = handler.handle(_request(method="GET"))
    assert method["status_code"] == 405
    assert method["headers"]["Allow"] == "POST"


def test_exception_tipo_invalido_sem_vazamento_e_sem_retry() -> None:
    service = FakeApplicationService(exception=RuntimeError("SELECT token body"))
    http = _handler(service).handle(_request())
    assert service.calls == 1
    assert http["status_code"] == 500
    serialized = repr(_body(http)).casefold()
    assert "select token body" not in serialized
    assert "graphstate" not in serialized
    invalid = _handler(FakeApplicationService(response="bad")).handle(_request())
    assert invalid["status_code"] == 500
    graph_state = _handler(
        FakeApplicationService(
            response={
                "contract_version": APPLICATION_RESPONSE_CONTRACT_VERSION,
                "response_id": "response-1",
                "request_id": "req-1",
                "run_id": "run-1",
                "status": "success",
                "original_outcome": "success",
                "message": "Public message",
                "data": {
                    "result": {
                        "contract_version": "v1",
                        "columns": [],
                        "rows": [],
                        "result_fingerprint": "result-1",
                    },
                    "pagination": {
                        "mode": "none",
                        "has_more": False,
                        "next_cursor": None,
                        "total_rows": 0,
                        "returned_rows": 0,
                    },
                },
                "errors": [],
                "warnings": [],
                "metadata": {"lineage": {}},
                "finalization": {"status": "completed"},
                "response_fingerprint": "not-canonical",
                "current_sql": "SELECT 1",
                "GraphState": True,
            }
        )
    ).handle(_request())
    assert graph_state["status_code"] == 500
    serialized = repr(_body(graph_state)).casefold()
    assert "select 1" not in serialized
    assert "graphstate" not in serialized


def test_accept_q_zero_nao_chama_service() -> None:
    service = FakeApplicationService()
    http = _handler(service).handle(
        _request(headers={"Content-Type": "application/json", "Accept": "application/json;q=0", "Authorization": "Bearer test-opaque-token"})
    )
    assert service.calls == 0
    assert http["status_code"] == 406
    assert _body(http)["errors"][0]["code"] == "HTTP_NOT_ACCEPTABLE"


def test_retorno_com_fingerprint_divergente_nao_atravessa() -> None:
    response = _response()
    response["response_fingerprint"] = "wrong"
    http = _handler(FakeApplicationService(response=response)).handle(_request())
    assert http["status_code"] == 500
    body = _body(http)
    assert body["status"] == "infrastructure_error"
    assert "wrong" not in repr(body)


def test_headers_ids_json_safe_response_limit_e_imutabilidade() -> None:
    response = _response(data={"large": "x" * 2000})
    original = deepcopy(response)
    service = FakeApplicationService(response)
    http = _handler(
        service,
        response_limits={
            **default_http_response_limits(),
            "max_response_body_bytes": 900,
        },
    ).handle(_request())
    body = _body(http)
    assert http["status_code"] == 503
    assert body["errors"][0]["code"] == "HTTP_RESPONSE_TOO_LARGE"
    assert response == original
    assert http["headers"]["Content-Type"] == "application/json; charset=utf-8"
    assert http["headers"]["X-Content-Type-Options"] == "nosniff"
    json.dumps(body, allow_nan=False)


def test_sem_graphstate_sql_body_em_erros() -> None:
    body = _body(_handler().handle(_request(body=b'{"sql":"SELECT 1"')) )
    serialized = repr(body).casefold()
    assert "select 1" not in serialized
    assert "graphstate" not in serialized
    assert "payload" not in body


def main() -> None:
    tests = [
        test_request_valida_chama_service_uma_vez_e_delega_payload,
        test_request_invalida_nao_chama_service,
        test_status_mapping,
        test_erros_de_transporte_status_e_allow,
        test_exception_tipo_invalido_sem_vazamento_e_sem_retry,
        test_accept_q_zero_nao_chama_service,
        test_retorno_com_fingerprint_divergente_nao_atravessa,
        test_headers_ids_json_safe_response_limit_e_imutabilidade,
        test_sem_graphstate_sql_body_em_erros,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()

from __future__ import annotations

import json
from copy import deepcopy

from app.adapters.testing.fake_authenticator import FakeAuthenticator
from app.adapters.testing.fake_authorizer import FakeAuthorizer
from app.adapters.testing.fake_graph_runtime import FakeGraphRuntime
from app.application.sql_agent_service import SqlAgentApplicationService
from app.domain.application_response_types import APPLICATION_RESPONSE_CONTRACT_VERSION
from app.domain.result_normalization import stable_fingerprint
from app.http.http_request import default_http_request_limits
from app.http.http_response import default_http_response_limits
from app.http.sql_agent_http_handler import SqlAgentHttpHandler
from app.security.auth_types import (
    authentication_result,
    authorization_decision,
    create_authenticated_principal,
    default_auth_security_limits,
)


TOKEN = "test-opaque-token"


class Ids:
    def __init__(self) -> None:
        self.values = ["req-1", "run-1"]

    def __call__(self) -> str:
        return self.values.pop(0)


class ResponseRuntime:
    def __init__(self, status="success") -> None:
        self.status = status
        self.calls = 0
        self.last_initial_state = None

    def invoke(self, initial_state):
        self.calls += 1
        self.last_initial_state = deepcopy(initial_state)
        return {"application_response": _response(self.status, initial_state)}


def _response(status, initial_state):
    response = {
        "contract_version": APPLICATION_RESPONSE_CONTRACT_VERSION,
        "response_id": "response-1",
        "request_id": initial_state["request_id"],
        "run_id": initial_state["run_id"],
        "status": status,
        "original_outcome": status,
        "message": "Public",
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
        }
        if status == "success"
        else None,
        "errors": [],
        "warnings": [],
        "metadata": {"lineage": {}},
        "finalization": {
            "status": "completed" if status == "success" else "incomplete",
            "run_record_built": status == "success",
            "persisted": status == "success",
            "audited": status == "success",
        },
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


def _authenticator(result=None):
    return FakeAuthenticator(
        result=result
        if result is not None
        else authentication_result(
            status="authenticated",
            principal=_principal(),
        )
    )


def _authorizer(decision=None):
    return FakeAuthorizer(
        decision=decision
        if decision is not None
        else authorization_decision(status="allowed")
    )


def _handler(runtime=None, authenticator=None, authorizer=None):
    selected_runtime = runtime or ResponseRuntime()
    service = SqlAgentApplicationService(
        runtime=selected_runtime,
        id_generator=Ids(),
    )
    return (
        SqlAgentHttpHandler(
            application_service=service,
            authenticator=authenticator or _authenticator(),
            authorizer=authorizer or _authorizer(),
            auth_limits=default_auth_security_limits(),
            request_limits=default_http_request_limits(),
            response_limits=default_http_response_limits(),
        ),
        selected_runtime,
    )


def _request(body=b'{"question":"ok"}', headers=None):
    return {
        "method": "POST",
        "path": "/v1/sql-agent/query",
        "headers": headers
        if headers is not None
        else {"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"},
        "body": body,
    }


def _body(http):
    return json.loads(http["body"].decode("utf-8"))


def test_autenticado_autorizado_success() -> None:
    handler, runtime = _handler(ResponseRuntime("success"))
    http = handler.handle(_request())
    assert http["status_code"] == 200
    assert runtime.calls == 1


def test_autenticado_autorizado_rejected_do_dominio() -> None:
    handler, runtime = _handler(ResponseRuntime("rejected"))
    http = handler.handle(_request())
    assert http["status_code"] == 422
    assert runtime.calls == 1


def test_autenticado_autorizado_infrastructure_error() -> None:
    handler, runtime = _handler(ResponseRuntime("infrastructure_error"))
    http = handler.handle(_request())
    assert http["status_code"] == 503
    assert runtime.calls == 1


def test_credencial_invalida() -> None:
    auth = _authenticator(
        authentication_result(
            status="invalid_credentials",
            error_code="AUTHENTICATION_INVALID_CREDENTIALS",
        )
    )
    handler, runtime = _handler(ResponseRuntime(), authenticator=auth)
    assert handler.handle(_request())["status_code"] == 401
    assert runtime.calls == 0


def test_autorizacao_negada() -> None:
    handler, runtime = _handler(
        ResponseRuntime(),
        authorizer=_authorizer(
            authorization_decision(status="denied", error_code="AUTHORIZATION_DENIED")
        ),
    )
    assert handler.handle(_request())["status_code"] == 403
    assert runtime.calls == 0


def test_authenticator_unavailable() -> None:
    auth = _authenticator(
        authentication_result(
            status="unavailable",
            error_code="AUTHENTICATION_SERVICE_UNAVAILABLE",
        )
    )
    handler, runtime = _handler(ResponseRuntime(), authenticator=auth)
    assert handler.handle(_request())["status_code"] == 503
    assert runtime.calls == 0


def test_authorizer_unavailable() -> None:
    handler, runtime = _handler(
        ResponseRuntime(),
        authorizer=_authorizer(
            authorization_decision(
                status="unavailable",
                error_code="AUTHORIZATION_SERVICE_UNAVAILABLE",
            )
        ),
    )
    assert handler.handle(_request())["status_code"] == 503
    assert runtime.calls == 0


def test_user_no_body() -> None:
    handler, runtime = _handler(ResponseRuntime())
    assert handler.handle(_request(body=b'{"question":"ok","user":{"id":"body"}}'))["status_code"] == 400
    assert runtime.calls == 0


def test_principal_vira_application_request_user() -> None:
    handler, runtime = _handler(ResponseRuntime())
    handler.handle(_request())
    assert runtime.last_initial_state["user"] == {
        "id": "principal-1",
        "email": "principal@example.invalid",
        "profile": "generic-profile",
        "organization_id": "org-1",
    }


def test_grafo_chamado_uma_vez_somente_quando_permitido() -> None:
    handler, runtime = _handler(ResponseRuntime())
    handler.handle(_request())
    assert runtime.calls == 1
    auth = _authenticator(
        authentication_result(
            status="invalid_credentials",
            error_code="AUTHENTICATION_INVALID_CREDENTIALS",
        )
    )
    blocked_handler, blocked_runtime = _handler(ResponseRuntime(), authenticator=auth)
    blocked_handler.handle(_request())
    assert blocked_runtime.calls == 0


def test_nenhum_graphstate_exposto() -> None:
    runtime = FakeGraphRuntime(final_state={"GraphState": True})
    handler, _ = _handler(runtime)
    serialized = repr(_body(handler.handle(_request()))).casefold()
    assert "graphstate" not in serialized


def test_nenhum_token_exposto() -> None:
    handler, runtime = _handler(ResponseRuntime())
    http = handler.handle(_request())
    serialized = repr(_body(http)).casefold() + repr(runtime.last_initial_state).casefold()
    assert TOKEN not in serialized


def main() -> None:
    tests = [
        test_autenticado_autorizado_success,
        test_autenticado_autorizado_rejected_do_dominio,
        test_autenticado_autorizado_infrastructure_error,
        test_credencial_invalida,
        test_autorizacao_negada,
        test_authenticator_unavailable,
        test_authorizer_unavailable,
        test_user_no_body,
        test_principal_vira_application_request_user,
        test_grafo_chamado_uma_vez_somente_quando_permitido,
        test_nenhum_graphstate_exposto,
        test_nenhum_token_exposto,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()

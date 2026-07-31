from __future__ import annotations

import json
from copy import deepcopy

from app.adapters.testing.fake_authenticator import FakeAuthenticator
from app.adapters.testing.fake_authorizer import FakeAuthorizer
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


class FakeApplicationService:
    def __init__(self, response=None) -> None:
        self.response = response if response is not None else _response()
        self.calls = 0
        self.requests = []

    def execute(self, request):
        self.calls += 1
        self.requests.append(deepcopy(request))
        return deepcopy(self.response)


def _response(status="success"):
    response = {
        "contract_version": APPLICATION_RESPONSE_CONTRACT_VERSION,
        "response_id": "response-1",
        "request_id": "req-1",
        "run_id": "run-1",
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
        "finalization": {"status": "completed" if status == "success" else "incomplete"},
        "response_fingerprint": "",
    }
    payload = deepcopy(response)
    payload.pop("response_fingerprint", None)
    response["response_fingerprint"] = stable_fingerprint(payload)
    return response


def _principal(**overrides):
    data = {
        "subject_id": "principal-1",
        "email": "principal@example.invalid",
        "profile": "generic-profile",
        "organization_id": "org-1",
        "roles": ["role.local"],
        "scopes": ["scope.local"],
    }
    data.update(overrides)
    return create_authenticated_principal(
        data,
        limits=default_auth_security_limits(),
    )


def _authenticator(result=None, exception=None):
    return FakeAuthenticator(
        result=result
        if result is not None
        else authentication_result(
            status="authenticated",
            principal=_principal(),
        ),
        exception=exception,
    )


def _authorizer(decision=None, exception=None):
    return FakeAuthorizer(
        decision=decision
        if decision is not None
        else authorization_decision(status="allowed"),
        exception=exception,
    )


def _handler(service=None, authenticator=None, authorizer=None):
    return SqlAgentHttpHandler(
        application_service=service or FakeApplicationService(),
        authenticator=authenticator or _authenticator(),
        authorizer=authorizer or _authorizer(),
        auth_limits=default_auth_security_limits(),
        request_limits=default_http_request_limits(),
        response_limits=default_http_response_limits(),
    )


def _request(body=b'{"question":"ok","request_id":"req-1","run_id":"run-1"}', headers=None):
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


def test_header_ausente_401() -> None:
    service = FakeApplicationService()
    http = _handler(service).handle(_request(headers={"Content-Type": "application/json"}))
    assert http["status_code"] == 401
    assert service.calls == 0


def test_www_authenticate_bearer() -> None:
    http = _handler().handle(_request(headers={"Content-Type": "application/json"}))
    assert http["headers"]["WWW-Authenticate"] == "Bearer"


def test_scheme_invalido_401() -> None:
    http = _handler().handle(
        _request(headers={"Content-Type": "application/json", "Authorization": f"Basic {TOKEN}"})
    )
    assert http["status_code"] == 401


def test_credential_invalida_401() -> None:
    auth = _authenticator(
        authentication_result(
            status="invalid_credentials",
            error_code="AUTHENTICATION_INVALID_CREDENTIALS",
        )
    )
    http = _handler(authenticator=auth).handle(_request())
    assert http["status_code"] == 401


def test_authenticator_unavailable_503() -> None:
    auth = _authenticator(
        authentication_result(
            status="unavailable",
            error_code="AUTHENTICATION_SERVICE_UNAVAILABLE",
        )
    )
    assert _handler(authenticator=auth).handle(_request())["status_code"] == 503


def test_authenticator_exception_fail_closed() -> None:
    service = FakeApplicationService()
    http = _handler(service, authenticator=_authenticator(exception=RuntimeError("token secret"))).handle(_request())
    assert http["status_code"] == 500
    assert service.calls == 0
    assert "token secret" not in repr(_body(http)).casefold()


def test_principal_invalido_fail_closed() -> None:
    auth = FakeAuthenticator(
        result={
            "contract_version": "v1.0.0-http-auth-boundary",
            "status": "authenticated",
            "principal": object(),
            "error_code": None,
            "diagnostics": [],
        }
    )
    http = _handler(authenticator=auth).handle(_request())
    assert http["status_code"] == 500


def test_authorization_denied_403() -> None:
    service = FakeApplicationService()
    http = _handler(
        service,
        authorizer=_authorizer(
            authorization_decision(status="denied", error_code="AUTHORIZATION_DENIED")
        ),
    ).handle(_request())
    assert http["status_code"] == 403
    assert service.calls == 0


def test_authorizer_unavailable_503() -> None:
    http = _handler(
        authorizer=_authorizer(
            authorization_decision(
                status="unavailable",
                error_code="AUTHORIZATION_SERVICE_UNAVAILABLE",
            )
        )
    ).handle(_request())
    assert http["status_code"] == 503


def test_authorizer_exception_fail_closed() -> None:
    service = FakeApplicationService()
    http = _handler(service, authorizer=_authorizer(exception=RuntimeError("role secret"))).handle(_request())
    assert http["status_code"] == 500
    assert service.calls == 0
    assert "role secret" not in repr(_body(http)).casefold()


def test_allowed_chama_service_uma_vez() -> None:
    service = FakeApplicationService()
    http = _handler(service).handle(_request())
    assert http["status_code"] == 200
    assert service.calls == 1


def test_auth_failure_nao_chama_service() -> None:
    service = FakeApplicationService()
    auth = _authenticator(
        authentication_result(
            status="invalid_credentials",
            error_code="AUTHENTICATION_INVALID_CREDENTIALS",
        )
    )
    _handler(service, authenticator=auth).handle(_request())
    assert service.calls == 0


def test_denied_nao_chama_service() -> None:
    service = FakeApplicationService()
    _handler(
        service,
        authorizer=_authorizer(
            authorization_decision(status="denied", error_code="AUTHORIZATION_DENIED")
        ),
    ).handle(_request())
    assert service.calls == 0


def test_user_no_body_rejeitado() -> None:
    service = FakeApplicationService()
    http = _handler(service).handle(_request(body=b'{"question":"ok","user":{"id":"body"}}'))
    assert http["status_code"] == 400
    assert _body(http)["errors"][0]["code"] == "HTTP_IDENTITY_FIELD_FORBIDDEN"
    assert service.calls == 0


def test_body_user_nao_e_ignorado() -> None:
    assert _handler().handle(_request(body=b'{"question":"ok","user":{}}'))["status_code"] == 400


def test_body_user_nao_sobrescreve_principal() -> None:
    service = FakeApplicationService()
    _handler(service).handle(_request(body=b'{"question":"ok"}'))
    assert service.requests[0]["user"]["id"] == "principal-1"


def test_application_request_user_vem_do_principal() -> None:
    service = FakeApplicationService()
    _handler(service).handle(_request())
    assert service.requests[0]["user"] == {
        "id": "principal-1",
        "email": "principal@example.invalid",
        "profile": "generic-profile",
        "organization_id": "org-1",
    }


def test_roles_scopes_nao_atravessam() -> None:
    service = FakeApplicationService()
    _handler(service).handle(_request())
    assert "roles" not in service.requests[0]["user"]
    assert "scopes" not in service.requests[0]["user"]


def test_token_nao_atravessa() -> None:
    service = FakeApplicationService()
    http = _handler(service).handle(_request())
    serialized = repr(_body(http)).casefold() + repr(service.requests).casefold()
    assert TOKEN not in serialized


def test_authorization_nao_aparece_na_resposta() -> None:
    assert "authorization" not in repr(_body(_handler().handle(_request()))).casefold()


def test_principal_nao_aparece_na_resposta() -> None:
    serialized = repr(_body(_handler().handle(_request()))).casefold()
    assert "principal-1" not in serialized
    assert "principal@example.invalid" not in serialized


def test_www_authenticate_nao_aparece_no_403() -> None:
    http = _handler(
        authorizer=_authorizer(
            authorization_decision(status="denied", error_code="AUTHORIZATION_DENIED")
        )
    ).handle(_request())
    assert "WWW-Authenticate" not in http["headers"]


def test_headers_de_seguranca_preservados() -> None:
    headers = _handler().handle(_request())["headers"]
    assert headers["Content-Type"] == "application/json; charset=utf-8"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "Access-Control-Allow-Origin" not in headers


def test_status_success_rejected_infrastructure_apos_autorizacao() -> None:
    for status, expected in [
        ("success", 200),
        ("rejected", 422),
        ("infrastructure_error", 503),
    ]:
        assert _handler(FakeApplicationService(_response(status))).handle(_request())["status_code"] == expected


def test_nenhum_retry() -> None:
    auth = _authenticator()
    authorizer = _authorizer()
    service = FakeApplicationService()
    _handler(service, authenticator=auth, authorizer=authorizer).handle(_request())
    assert auth.calls == 1
    assert authorizer.calls == 1
    assert service.calls == 1


def test_authenticator_chamado_uma_vez() -> None:
    auth = _authenticator()
    _handler(authenticator=auth).handle(_request())
    assert auth.calls == 1


def test_authorizer_chamado_uma_vez() -> None:
    authorizer = _authorizer()
    _handler(authorizer=authorizer).handle(_request())
    assert authorizer.calls == 1


def test_service_chamado_uma_vez() -> None:
    service = FakeApplicationService()
    _handler(service).handle(_request())
    assert service.calls == 1


def test_authorizer_nao_chamado_quando_auth_falha() -> None:
    authorizer = _authorizer()
    auth = _authenticator(
        authentication_result(
            status="invalid_credentials",
            error_code="AUTHENTICATION_INVALID_CREDENTIALS",
        )
    )
    _handler(authenticator=auth, authorizer=authorizer).handle(_request())
    assert authorizer.calls == 0


def test_service_nao_chamado_quando_authorizer_falha() -> None:
    service = FakeApplicationService()
    _handler(service, authorizer=_authorizer(exception=RuntimeError("x"))).handle(_request())
    assert service.calls == 0


def main() -> None:
    tests = [
        test_header_ausente_401,
        test_www_authenticate_bearer,
        test_scheme_invalido_401,
        test_credential_invalida_401,
        test_authenticator_unavailable_503,
        test_authenticator_exception_fail_closed,
        test_principal_invalido_fail_closed,
        test_authorization_denied_403,
        test_authorizer_unavailable_503,
        test_authorizer_exception_fail_closed,
        test_allowed_chama_service_uma_vez,
        test_auth_failure_nao_chama_service,
        test_denied_nao_chama_service,
        test_user_no_body_rejeitado,
        test_body_user_nao_e_ignorado,
        test_body_user_nao_sobrescreve_principal,
        test_application_request_user_vem_do_principal,
        test_roles_scopes_nao_atravessam,
        test_token_nao_atravessa,
        test_authorization_nao_aparece_na_resposta,
        test_principal_nao_aparece_na_resposta,
        test_www_authenticate_nao_aparece_no_403,
        test_headers_de_seguranca_preservados,
        test_status_success_rejected_infrastructure_apos_autorizacao,
        test_nenhum_retry,
        test_authenticator_chamado_uma_vez,
        test_authorizer_chamado_uma_vez,
        test_service_chamado_uma_vez,
        test_authorizer_nao_chamado_quando_auth_falha,
        test_service_nao_chamado_quando_authorizer_falha,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()

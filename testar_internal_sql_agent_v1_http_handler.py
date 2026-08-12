from __future__ import annotations

import json
from copy import deepcopy

from app.http.http_request import default_http_request_limits
from app.http.http_response import default_http_response_limits
from app.http.internal_sql_agent_v1_handler import (
    InternalSqlAgentV1HttpHandler,
)
from app.http.internal_service_auth_handler import (
    protect_internal_service_http_handler,
)
from app.security.internal_service_auth import InternalServiceAuthConfig


S2S_TOKEN = "test-s2s-token"


class FakeUseCase:
    def __init__(self, response=None) -> None:
        self.response = response or _response()
        self.calls = 0
        self.requests = []

    def execute(self, request):
        self.calls += 1
        self.requests.append(deepcopy(request))
        return deepcopy(self.response)


def _response(
    *,
    status: str = "success",
    agent_run_id: str = "agent-run-1",
    run_id: str = "lg-run-1",
) -> dict:
    from app.domain.result_normalization import stable_fingerprint

    response = {
        "contract_version": "1",
        "response_id": "",
        "agent_run_id": agent_run_id,
        "run_id": run_id,
        "status": status,
        "message": "ok",
        "errors": [],
        "metadata": {"lineage": {}},
        "response_fingerprint": "",
    }
    response["response_id"] = stable_fingerprint(
        {
            "contract_version": response["contract_version"],
            "agent_run_id": response["agent_run_id"],
            "run_id": response["run_id"],
            "status": response["status"],
            "message": response["message"],
        }
    )
    payload = deepcopy(response)
    payload.pop("response_fingerprint", None)
    response["response_fingerprint"] = stable_fingerprint(payload)
    return response


def _handler(generate=None, execute_shadow=None):
    return InternalSqlAgentV1HttpHandler(
        generate_use_case=generate or FakeUseCase(),
        execute_approved_shadow_use_case=execute_shadow or FakeUseCase(),
        request_limits=default_http_request_limits(),
        response_limits=default_http_response_limits(),
    )


def _protected_handler(generate=None, execute_shadow=None):
    return protect_internal_service_http_handler(
        inner=_handler(generate, execute_shadow),
        auth_config=InternalServiceAuthConfig(expected_token=S2S_TOKEN),
    )


def _request(path: str, body: dict | bytes | None = None, **overrides):
    if body is None:
        body = {
            "contract_version": "1",
            "agent_run_id": "agent-run-1",
            "question": "ok",
            "principal": {"id": "user-1"},
        }
    raw_body = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    request = {
        "method": "POST",
        "path": path,
        "headers": {"Content-Type": "application/json"},
        "body": raw_body,
    }
    request.update(overrides)
    return request


def _body(response):
    return json.loads(response["body"].decode("utf-8"))


def test_generate_route_chama_generate_use_case() -> None:
    generate = FakeUseCase(_response(run_id="lg-run-generate"))
    execute_shadow = FakeUseCase()
    response = _handler(generate, execute_shadow).handle(
        _request("/v1/internal/sql-agent/generate")
    )

    assert response["status_code"] == 200
    assert generate.calls == 1
    assert execute_shadow.calls == 0
    assert generate.requests[0]["contract_version"] == "1"
    assert _body(response)["run_id"] == "lg-run-generate"


def test_execute_approved_shadow_route_chama_shadow_use_case() -> None:
    generate = FakeUseCase()
    execute_shadow = FakeUseCase(_response(run_id="lg-run-shadow"))
    response = _handler(generate, execute_shadow).handle(
        _request(
            "/v1/internal/sql-agent/execute-approved-shadow",
            {
                "contract_version": "1",
                "agent_run_id": "agent-run-2",
                "approved_sql": "SELECT id FROM schema_test.table_test",
                "principal": {"id": "user-1"},
            },
        )
    )

    assert response["status_code"] == 200
    assert generate.calls == 0
    assert execute_shadow.calls == 1
    assert execute_shadow.requests[0]["approved_sql"].startswith("SELECT")
    assert _body(response)["run_id"] == "lg-run-shadow"


def test_rota_legada_nao_e_consumida_pelo_handler_interno() -> None:
    generate = FakeUseCase()
    response = _handler(generate).handle(
        _request("/v1/sql-agent/query")
    )

    assert response["status_code"] == 404
    assert generate.calls == 0


def test_method_content_type_json_e_headers_sensiveis() -> None:
    handler = _handler()
    assert handler.handle(
        _request("/v1/internal/sql-agent/generate", method="GET")
    )["status_code"] == 405
    assert handler.handle(
        _request(
            "/v1/internal/sql-agent/generate",
            headers={"Content-Type": "text/plain"},
        )
    )["status_code"] == 415
    assert handler.handle(
        _request(
            "/v1/internal/sql-agent/generate",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer test-s2s-token",
            },
        )
    )["status_code"] == 200
    assert handler.handle(
        _request(
            "/v1/internal/sql-agent/generate",
            headers={
                "Content-Type": "application/json",
                "Cookie": "session=browser",
            },
        )
    )["status_code"] == 400


def test_auth_boundary_bloqueia_antes_do_use_case() -> None:
    generate = FakeUseCase()
    response = _protected_handler(generate).handle(
        _request("/v1/internal/sql-agent/generate")
    )
    body = _body(response)

    assert response["status_code"] == 401
    assert response["headers"]["WWW-Authenticate"] == "Bearer"
    assert body["error"]["code"] == "UNAUTHORIZED_SERVICE"
    assert generate.calls == 0


def test_auth_boundary_permite_token_correto_sem_repassar_authorization() -> None:
    generate = FakeUseCase()
    response = _protected_handler(generate).handle(
        _request(
            "/v1/internal/sql-agent/generate",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {S2S_TOKEN}",
            },
        )
    )

    assert response["status_code"] == 200
    assert generate.calls == 1
    assert "Authorization" not in generate.requests[0]


def test_response_invalida_nao_vaza_payload() -> None:
    generate = FakeUseCase(
        {
            "contract_version": "1",
            "status": "success",
            "current_sql": "SELECT token FROM hidden",
            "response_fingerprint": "wrong",
        }
    )
    response = _handler(generate).handle(
        _request("/v1/internal/sql-agent/generate")
    )
    body = _body(response)
    serialized = repr(body).casefold()

    assert response["status_code"] == 500
    assert "select token" not in serialized
    assert "hidden" not in serialized


def main() -> None:
    tests = [
        test_generate_route_chama_generate_use_case,
        test_execute_approved_shadow_route_chama_shadow_use_case,
        test_rota_legada_nao_e_consumida_pelo_handler_interno,
        test_method_content_type_json_e_headers_sensiveis,
        test_auth_boundary_bloqueia_antes_do_use_case,
        test_auth_boundary_permite_token_correto_sem_repassar_authorization,
        test_response_invalida_nao_vaza_payload,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()

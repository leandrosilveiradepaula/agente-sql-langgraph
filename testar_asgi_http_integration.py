from __future__ import annotations

import asyncio
import json
from copy import deepcopy

from app.adapters.testing.fake_authenticator import FakeAuthenticator
from app.adapters.testing.fake_authorizer import FakeAuthorizer
from app.application.sql_agent_service import SqlAgentApplicationService
from app.asgi.asgi_limits import default_asgi_adapter_limits
from app.asgi.sql_agent_asgi_app import AsgiSqlAgentApplication
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


TOKEN = "test-asgi-token"


class Ids:
    def __init__(self) -> None:
        self.values = ["req-1", "run-1"]

    def __call__(self) -> str:
        return self.values.pop(0)


class Runtime:
    def __init__(self, status="success", extra=None) -> None:
        self.status = status
        self.extra = extra or {}
        self.calls = 0
        self.last_initial_state = None

    def invoke(self, initial_state):
        self.calls += 1
        self.last_initial_state = deepcopy(initial_state)
        return {"application_response": _response(self.status, initial_state, self.extra)}


def _response(status, initial_state, extra):
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
        "metadata": {"lineage": {}, **extra},
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


class Receive:
    def __init__(self, body, headers=None):
        self.messages = [{"type": "http.request", "body": body, "more_body": False}]

    async def __call__(self):
        return deepcopy(self.messages.pop(0))


class Send:
    def __init__(self):
        self.events = []

    async def __call__(self, event):
        self.events.append(deepcopy(event))


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
        else authentication_result(status="authenticated", principal=_principal())
    )


def _authorizer(decision=None):
    return FakeAuthorizer(
        decision=decision
        if decision is not None
        else authorization_decision(status="allowed")
    )


def _app(runtime=None, authenticator=None, authorizer=None):
    selected_runtime = runtime or Runtime()
    service = SqlAgentApplicationService(
        runtime=selected_runtime,
        id_generator=Ids(),
    )
    handler = SqlAgentHttpHandler(
        application_service=service,
        authenticator=authenticator or _authenticator(),
        authorizer=authorizer or _authorizer(),
        auth_limits=default_auth_security_limits(),
        request_limits=default_http_request_limits(),
        response_limits=default_http_response_limits(),
    )
    return (
        AsgiSqlAgentApplication(
            http_handler=handler,
            asgi_limits=default_asgi_adapter_limits(),
        ),
        selected_runtime,
        authenticator,
        authorizer,
    )


def _scope(headers=None):
    return {
        "type": "http",
        "method": "POST",
        "path": "/v1/sql-agent/query",
        "query_string": b"",
        "headers": headers
        if headers is not None
        else [
            (b"content-type", b"application/json"),
            (b"authorization", f"Bearer {TOKEN}".encode("ascii")),
        ],
    }


def _run(app, body=b'{"question":"ok"}', headers=None):
    send = Send()
    asyncio.run(app(_scope(headers), Receive(body), send))
    return send.events


def _body(events):
    return json.loads(events[1]["body"].decode("utf-8"))


def test_success() -> None:
    app, runtime, _auth, _authz = _app(Runtime("success"))
    events = _run(app)
    assert events[0]["status"] == 200
    assert runtime.calls == 1


def test_auth_e_authorization_status() -> None:
    app, runtime, _auth, _authz = _app(Runtime())
    assert _run(app, headers=[(b"content-type", b"application/json")])[0]["status"] == 401
    assert runtime.calls == 0
    invalid = _authenticator(
        authentication_result(
            status="invalid_credentials",
            error_code="AUTHENTICATION_INVALID_CREDENTIALS",
        )
    )
    app, runtime, _auth, _authz = _app(Runtime(), authenticator=invalid)
    assert _run(app)[0]["status"] == 401
    denied = _authorizer(
        authorization_decision(status="denied", error_code="AUTHORIZATION_DENIED")
    )
    app, runtime, _auth, _authz = _app(Runtime(), authorizer=denied)
    assert _run(app)[0]["status"] == 403


def test_unavailable_e_dominio() -> None:
    unavailable = _authenticator(
        authentication_result(
            status="unavailable",
            error_code="AUTHENTICATION_SERVICE_UNAVAILABLE",
        )
    )
    app, _runtime, _auth, _authz = _app(Runtime(), authenticator=unavailable)
    assert _run(app)[0]["status"] == 503
    for status, expected in [("rejected", 422), ("infrastructure_error", 503)]:
        app, runtime, _auth, _authz = _app(Runtime(status))
        assert _run(app)[0]["status"] == expected
        assert runtime.calls == 1


def test_user_json_invalido_body_grande_duplicate_auth() -> None:
    app, runtime, _auth, _authz = _app(Runtime())
    assert _run(app, body=b'{"question":"ok","user":null}')[0]["status"] == 400
    assert _run(app, body=b"{bad json}")[0]["status"] == 400
    assert _run(app, body=b"x" * 70_000)[0]["status"] == 413
    assert (
        _run(
            app,
            headers=[
                (b"content-type", b"application/json"),
                (b"authorization", b"Bearer one"),
                (b"authorization", b"Bearer two"),
            ],
        )[0]["status"]
        == 401
    )
    assert runtime.calls == 0


def test_sem_vazamentos_e_chamadas() -> None:
    app, runtime, _auth, _authz = _app(Runtime("success"))
    events = _run(app)
    serialized = repr(_body(events)).casefold() + repr(runtime.last_initial_state).casefold()
    assert TOKEN not in serialized
    assert "graphstate" not in serialized
    assert "current_sql" not in serialized
    assert runtime.calls == 1
    assert events[0]["type"] == "http.response.start"
    assert events[1]["type"] == "http.response.body"


def main() -> None:
    tests = [
        test_success,
        test_auth_e_authorization_status,
        test_unavailable_e_dominio,
        test_user_json_invalido_body_grande_duplicate_auth,
        test_sem_vazamentos_e_chamadas,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()

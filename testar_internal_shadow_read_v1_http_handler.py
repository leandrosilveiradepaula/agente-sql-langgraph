from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from typing import Any

from app.adapters.testing.fake_shadow_evidence_repository import (
    FakeShadowEvidenceRepository,
)
from app.adapters.testing.shadow_run_visualization_fixtures import (
    SYNTHETIC_QUESTION,
    SYNTHETIC_SQL,
    all_records,
)
from app.application.internal_shadow_read_v1 import (
    GetShadowRunSafeViewUseCase,
    GetShadowRunVisualizationUseCase,
    ListAgentShadowRunsUseCase,
)
from app.http.http_response import default_http_response_limits
from app.http.internal_shadow_read_v1_handler import (
    create_internal_shadow_read_v1_http_handler,
)
from app.http.internal_service_auth_handler import (
    protect_internal_service_http_handler,
)
from app.security.internal_service_auth import InternalServiceAuthConfig
from app.test_runtime.composition import create_shadow_test_runtime
from app.test_runtime.offline_adapters import (
    OFFLINE_SQL,
    ShadowTestContextRepository,
    ShadowTestSqlGenerator,
    ShadowTestSqlRepairer,
)


AGENT_RUN_ID = "agent-run-shadow-read-http"
S2S_TOKEN = "test-s2s-token"


class FailingRepository:
    def fetch_by_shadow_record_id(self, shadow_record_id: str):
        del shadow_record_id
        raise RuntimeError("raw postgresql://secret value")

    def list_by_agent_run_id(self, agent_run_id: str):
        del agent_run_id
        raise RuntimeError("raw postgresql://secret value")


class CountingRepository:
    def __init__(self) -> None:
        self.fetch_calls = 0
        self.list_calls = 0

    def fetch_by_shadow_record_id(self, shadow_record_id: str):
        del shadow_record_id
        self.fetch_calls += 1
        return {
            "status": "not_found",
            "record": None,
            "diagnostic": {
                "code": "SHADOW_RECORD_NOT_FOUND",
                "message": "not found",
                "failure_category": "not_found",
                "safe_details": {},
            },
        }

    def list_by_agent_run_id(self, agent_run_id: str):
        del agent_run_id
        self.list_calls += 1
        return {"status": "ok", "records": [], "diagnostic": None}


class Receive:
    def __init__(self, body: bytes) -> None:
        self.messages = [{"type": "http.request", "body": body, "more_body": False}]

    async def __call__(self) -> dict[str, Any]:
        return deepcopy(self.messages.pop(0))


class Send:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def __call__(self, event: dict[str, Any]) -> None:
        self.events.append(deepcopy(event))


def main() -> None:
    tests = [
        _test_get_shadow_run_handler,
        _test_get_list_handler,
        _test_get_visualization_handler,
        _test_http_errors,
        _test_auth_boundary_bloqueia_read_antes_do_repository,
        _test_auth_boundary_permite_read_com_token_correto,
        _test_content_negotiation_and_limit_edges,
        _test_asgi_read_routes_and_old_posts,
        _test_read_logging_sanitized,
        _test_repository_failure_safe,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")
    print("testar_internal_shadow_read_v1_http_handler.py: 48/48 OK")


def _repo_with_records(*records):
    repo = FakeShadowEvidenceRepository()
    for record in records:
        repo.create(record)
    return repo


def _handler(repo):
    return create_internal_shadow_read_v1_http_handler(
        get_shadow_run_use_case=GetShadowRunSafeViewUseCase(repository=repo),
        list_agent_shadow_runs_use_case=ListAgentShadowRunsUseCase(repository=repo),
        get_shadow_run_visualization_use_case=GetShadowRunVisualizationUseCase(
            repository=repo,
        ),
        response_limits=default_http_response_limits(),
    )


def _protected_handler(repo):
    return protect_internal_service_http_handler(
        inner=_handler(repo),
        auth_config=InternalServiceAuthConfig(expected_token=S2S_TOKEN),
    )


def _request(
    method: str,
    path: str,
    *,
    query_string: str = "",
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "method": method,
        "path": path,
        "query_string": query_string,
        "headers": {"Accept": "application/json"} if headers is None else headers,
        "body": b"",
    }


def _body(response) -> dict[str, Any]:
    return json.loads(response["body"].decode("utf-8"))


def _test_get_shadow_run_handler() -> None:
    record = all_records()["generate_with_repair"]
    repo = _repo_with_records(record)
    response = _handler(repo).handle(
        _request("GET", f"/v1/internal/shadow-runs/{record['shadow_record_id']}")
    )
    body = _body(response)
    serialized = repr(body)
    assert response["status_code"] == 200
    assert response["headers"]["Content-Type"] == "application/json; charset=utf-8"
    assert body["shadow_record_id"] == record["shadow_record_id"]
    assert body["event_type"] == "generate"
    assert "fingerprints" in body
    assert SYNTHETIC_SQL not in serialized
    assert SYNTHETIC_QUESTION not in serialized
    assert "semantic_context" not in serialized
    assert "raw_response" not in serialized


def _test_get_list_handler() -> None:
    records = all_records()
    repo = _repo_with_records(
        records["execute_approved_valid"],
        records["generate_without_repair"],
    )
    response = _handler(repo).handle(
        _request(
            "GET",
            f"/v1/internal/agent-runs/{records['generate_without_repair']['agent_run_id']}/shadow-runs",
            query_string="limit=1",
        )
    )
    body = _body(response)
    assert response["status_code"] == 200
    assert body["limit"] == 1
    assert len(body["items"]) == 1
    assert body["items"][0]["event_type"] == "generate"


def _test_get_visualization_handler() -> None:
    records = all_records()
    record = records["generate_with_two_repairs"]
    secret_record = records["generate_with_secret_metadata"]
    handler = _handler(_repo_with_records(record, secret_record))
    response = handler.handle(
        _request(
            "GET",
            f"/v1/internal/shadow-runs/{record['shadow_record_id']}/visualization",
        )
    )
    body = _body(response)
    labels = [step["label"] for step in body["steps"]]
    assert response["status_code"] == 200
    assert body["contract_version"] == "1"
    assert body["run"]["shadow_record_id"] == record["shadow_record_id"]
    assert labels.count("repair_sql") == 2
    assert "mermaid" not in body
    secret_response = handler.handle(
        _request(
            "GET",
            f"/v1/internal/shadow-runs/{secret_record['shadow_record_id']}/visualization",
        )
    )
    assert "sensitive-password-value" not in repr(_body(secret_response))


def _test_http_errors() -> None:
    handler = _handler(_repo_with_records(all_records()["generate_without_repair"]))
    assert handler.handle(_request("POST", "/v1/internal/shadow-runs/x"))[
        "status_code"
    ] == 405
    assert handler.handle(_request("GET", "/v1/internal/shadow-runs/bad id"))[
        "status_code"
    ] == 400
    assert handler.handle(_request("GET", "/v1/internal/shadow-runs/agent-á"))[
        "status_code"
    ] == 400
    assert handler.handle(
        _request("GET", "/v1/internal/agent-runs/agent/shadow-runs", query_string="limit=0")
    )["status_code"] == 400
    assert handler.handle(
        _request("GET", "/v1/internal/agent-runs/agent/shadow-runs", query_string="limit=-1")
    )["status_code"] == 400
    assert handler.handle(
        _request("GET", "/v1/internal/agent-runs/agent/shadow-runs", query_string="limit=101")
    )["status_code"] == 400
    assert handler.handle(_request("GET", "/v1/internal/shadow-runs/missing"))[
        "status_code"
    ] == 404
    response = handler.handle(
        {
            **_request("GET", "/v1/internal/shadow-runs/x"),
            "headers": {"Cookie": "session=browser"},
        }
    )
    assert response["status_code"] == 400


def _test_auth_boundary_bloqueia_read_antes_do_repository() -> None:
    repo = CountingRepository()
    response = _protected_handler(repo).handle(
        _request("GET", "/v1/internal/shadow-runs/shadow-any")
    )
    body = _body(response)

    assert response["status_code"] == 401
    assert response["headers"]["WWW-Authenticate"] == "Bearer"
    assert body["error"]["code"] == "UNAUTHORIZED_SERVICE"
    assert repo.fetch_calls == 0
    assert repo.list_calls == 0


def _test_auth_boundary_permite_read_com_token_correto() -> None:
    repo = CountingRepository()
    response = _protected_handler(repo).handle(
        _request(
            "GET",
            "/v1/internal/agent-runs/agent-run-any/shadow-runs",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {S2S_TOKEN}",
            },
        )
    )
    body = _body(response)

    assert response["status_code"] == 200
    assert body["items"] == []
    assert repo.fetch_calls == 0
    assert repo.list_calls == 1


def _test_content_negotiation_and_limit_edges() -> None:
    record = all_records()["generate_without_repair"]
    handler = _handler(_repo_with_records(record))
    shadow_path = f"/v1/internal/shadow-runs/{record['shadow_record_id']}"
    list_path = f"/v1/internal/agent-runs/{record['agent_run_id']}/shadow-runs"
    assert handler.handle(
        _request("GET", shadow_path, headers={"Accept": "application/json"})
    )["status_code"] == 200
    assert handler.handle(
        _request("GET", shadow_path, headers={"Accept": "*/*"})
    )["status_code"] == 200
    assert handler.handle(_request("GET", shadow_path, headers={}))["status_code"] == 200
    response = handler.handle(
        _request("GET", shadow_path, headers={"Accept": "text/plain"})
    )
    assert response["status_code"] == 406
    assert _body(response)["error"]["code"] == "HTTP_NOT_ACCEPTABLE"
    for query_string in (
        "limit=",
        "limit=abc",
        "limit=1.5",
        "limit=0",
        "limit=-1",
        "limit=101",
        "limit=10&limit=20",
    ):
        response = handler.handle(
            _request("GET", list_path, query_string=query_string)
        )
        assert response["status_code"] == 400
        assert _body(response)["error"]["code"] == "SHADOW_RUN_LIMIT_INVALID"
    leading_zero = handler.handle(
        _request("GET", list_path, query_string="limit=001")
    )
    assert leading_zero["status_code"] == 200
    assert _body(leading_zero)["limit"] == 1
    unknown_query = handler.handle(
        _request("GET", list_path, query_string="limit=10&foo=bar")
    )
    assert unknown_query["status_code"] == 200
    assert _body(unknown_query)["limit"] == 10


def _test_repository_failure_safe() -> None:
    response = _handler(FailingRepository()).handle(
        _request("GET", "/v1/internal/shadow-runs/shadow-any")
    )
    body = _body(response)
    serialized = repr(body).casefold()
    assert response["status_code"] == 503
    assert body["error"]["code"] == "SHADOW_REPOSITORY_UNAVAILABLE"
    assert "postgresql://" not in serialized
    assert "secret" not in serialized
    list_response = _handler(FailingRepository()).handle(
        _request("GET", "/v1/internal/agent-runs/agent-run-any/shadow-runs")
    )
    list_body = _body(list_response)
    list_serialized = repr(list_body).casefold()
    assert list_response["status_code"] == 503
    assert list_body["error"]["code"] == "SHADOW_REPOSITORY_UNAVAILABLE"
    assert "postgresql://" not in list_serialized
    assert "secret" not in list_serialized
    assert "traceback" not in list_serialized


class TestLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


def _test_read_logging_sanitized() -> None:
    logger = TestLogger()
    runtime = create_shadow_test_runtime(
        _env(),
        shadow_repository_override=FakeShadowEvidenceRepository(),
        context_repository_override=ShadowTestContextRepository(),
        sql_generator_override=ShadowTestSqlGenerator(),
        sql_repairer_override=ShadowTestSqlRepairer(),
        logger=logger,
    )
    _run_asgi(
        runtime.app,
        "POST",
        "/v1/internal/sql-agent/generate",
        _generate_payload(),
    )
    shadow_record_id = next(iter(runtime.raw_shadow_repository.records))
    _run_asgi(runtime.app, "GET", f"/v1/internal/shadow-runs/{shadow_record_id}")
    serialized = repr(logger.messages)
    assert "/v1/internal/shadow-runs/" in serialized
    assert shadow_record_id in serialized
    assert "duration_ms" in serialized
    assert SYNTHETIC_QUESTION not in serialized
    assert OFFLINE_SQL not in serialized
    assert "authorization" not in serialized.casefold()


def _test_asgi_read_routes_and_old_posts() -> None:
    runtime = create_shadow_test_runtime(
        _env(),
        shadow_repository_override=FakeShadowEvidenceRepository(),
        context_repository_override=ShadowTestContextRepository(),
        sql_generator_override=ShadowTestSqlGenerator(),
        sql_repairer_override=ShadowTestSqlRepairer(),
    )
    health_status, health = _run_asgi(runtime.app, "GET", "/health")
    generate_status, generate = _run_asgi(
        runtime.app,
        "POST",
        "/v1/internal/sql-agent/generate",
        _generate_payload(),
    )
    shadow_record_id = next(iter(runtime.raw_shadow_repository.records))
    get_status, shadow_run = _run_asgi(
        runtime.app,
        "GET",
        f"/v1/internal/shadow-runs/{shadow_record_id}",
    )
    visualization_status, visualization = _run_asgi(
        runtime.app,
        "GET",
        f"/v1/internal/shadow-runs/{shadow_record_id}/visualization",
    )
    execute_status, execute = _run_asgi(
        runtime.app,
        "POST",
        "/v1/internal/sql-agent/execute-approved-shadow",
        _execute_payload(),
    )
    list_status, listed = _run_asgi(
        runtime.app,
        "GET",
        f"/v1/internal/agent-runs/{AGENT_RUN_ID}/shadow-runs",
        query_string="limit=10",
    )
    serialized = repr(shadow_run) + repr(visualization) + repr(listed)
    assert health_status == 200
    assert health["status"] == "ok"
    assert generate_status == 200
    assert generate["status"] == "success"
    assert get_status == 200
    assert shadow_run["shadow_record_id"] == shadow_record_id
    assert visualization_status == 200
    assert visualization["run"]["shadow_record_id"] == shadow_record_id
    assert execute_status == 200
    assert execute["status"] == "success"
    assert list_status == 200
    assert len(listed["items"]) == 2
    assert SYNTHETIC_QUESTION not in serialized
    assert OFFLINE_SQL not in serialized


def _env() -> dict[str, str]:
    return {
        "LANGGRAPH_RUNTIME_MODE": "shadow_test",
        "LANGGRAPH_HTTP_HOST": "127.0.0.1",
        "LANGGRAPH_HTTP_PORT": "8000",
        "LANGGRAPH_SHADOW_PERSISTENCE": "postgres",
        "LANGGRAPH_SHADOW_DATABASE_DSN": "postgresql://shadow-test-placeholder",
        "CONTEXT_POSTGRES_DSN": "postgresql://context-test-placeholder",
        "SEMANTIC_AGENT_VERSION": "semantic-version-test",
        "LANGGRAPH_S2S_TOKEN": S2S_TOKEN,
        "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "false",
    }


def _scope(method: str, path: str, query_string: str) -> dict[str, Any]:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": query_string.encode("ascii"),
        "headers": [
            (b"content-type", b"application/json"),
            (b"accept", b"application/json"),
            (b"authorization", f"Bearer {S2S_TOKEN}".encode("ascii")),
        ],
    }


def _run_asgi(
    app: Any,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    query_string: str = "",
) -> tuple[int, dict[str, Any]]:
    send = Send()
    body = json.dumps(payload or {}, separators=(",", ":")).encode("utf-8")
    asyncio.run(
        app(
            _scope(method, path, query_string),
            Receive(body),
            send,
        )
    )
    return send.events[0]["status"], json.loads(send.events[1]["body"].decode("utf-8"))


def _generate_payload() -> dict[str, Any]:
    return {
        "contract_version": "1",
        "agent_run_id": AGENT_RUN_ID,
        "question": "Execute uma generic analysis de teste.",
        "principal": {"id": "user-1", "email": "user@example.invalid", "profile": "admin"},
        "correlation_metadata": {"source": "shadow_read_http_test"},
    }


def _execute_payload() -> dict[str, Any]:
    return {
        "contract_version": "1",
        "agent_run_id": AGENT_RUN_ID,
        "approved_sql": OFFLINE_SQL,
        "principal": {"id": "user-1", "email": "user@example.invalid", "profile": "admin"},
        "correlation_metadata": {"source": "shadow_read_http_test"},
    }


if __name__ == "__main__":
    main()

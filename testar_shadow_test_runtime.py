from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from typing import Any

from app.adapters.testing.fake_shadow_evidence_repository import (
    FakeShadowEvidenceRepository,
)
from app.infrastructure.persistence.postgres_shadow_evidence_repository import (
    FINALIZE_SHADOW_RUN_SQL,
    INSERT_SHADOW_RUN_SQL,
    PostgresShadowEvidenceRepository,
)
from app.adapters.postgres.context_repository import PostgresContextRepository
from app.integrations.google_gemini.sql_generator_adapter import (
    GoogleGeminiSqlGeneratorAdapter,
)
from app.integrations.google_gemini.sql_repairer_adapter import (
    GoogleGeminiSqlRepairerAdapter,
)
from app.test_runtime.composition import create_shadow_test_runtime
from app.test_runtime.config import load_shadow_test_runtime_config
from app.test_runtime.offline_adapters import (
    OFFLINE_SQL,
    ShadowTestContextRepository,
    ShadowTestSqlGenerator,
    ShadowTestSqlRepairer,
)


DSN_PLACEHOLDER = "postgresql://shadow-test-placeholder"
AGENT_RUN_ID = "agent-run-shadow-test"
S2S_TOKEN = "test-s2s-token"
CONTEXT_DSN_PLACEHOLDER = "postgresql://context-test-placeholder"
SEMANTIC_AGENT_VERSION = "semantic-version-test"


class TestLogger:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(self, message: str) -> None:
        self.messages.append(message)


class FailingLogger:
    def info(self, message: str) -> None:
        del message
        raise RuntimeError("logger failure with sensitive text")


class Receive:
    def __init__(self, messages: list[dict[str, Any]]) -> None:
        self.messages = list(messages)

    async def __call__(self) -> dict[str, Any]:
        return deepcopy(self.messages.pop(0))


class Send:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def __call__(self, event: dict[str, Any]) -> None:
        self.events.append(deepcopy(event))


class FakePostgresCursor:
    def __init__(self) -> None:
        self.rowcount = 1
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __enter__(self) -> "FakePostgresCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb

    def execute(self, query: str, parameters: dict[str, Any]) -> None:
        self.calls.append((query, deepcopy(parameters)))


class FakePostgresConnection:
    def __init__(self, cursor: FakePostgresCursor) -> None:
        self.cursor_instance = cursor
        self.commits = 0

    def __enter__(self) -> "FakePostgresConnection":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        del exc_type, exc, tb

    def cursor(self) -> FakePostgresCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.commits += 1


class FakePostgresConnect:
    def __init__(self) -> None:
        self.cursor = FakePostgresCursor()
        self.calls = 0
        self.args: list[tuple[Any, ...]] = []
        self.kwargs: list[dict[str, Any]] = []

    def __call__(self, *args: Any, **kwargs: Any) -> FakePostgresConnection:
        self.calls += 1
        self.args.append(args)
        self.kwargs.append(deepcopy(kwargs))
        return FakePostgresConnection(self.cursor)


def _env(**overrides: str) -> dict[str, str]:
    values = {
        "LANGGRAPH_RUNTIME_MODE": "shadow_test",
        "LANGGRAPH_HTTP_HOST": "127.0.0.1",
        "LANGGRAPH_HTTP_PORT": "8000",
        "LANGGRAPH_SHADOW_PERSISTENCE": "postgres",
        "LANGGRAPH_SHADOW_DATABASE_DSN": DSN_PLACEHOLDER,
        "CONTEXT_POSTGRES_DSN": CONTEXT_DSN_PLACEHOLDER,
        "SEMANTIC_AGENT_VERSION": SEMANTIC_AGENT_VERSION,
        "LANGGRAPH_S2S_TOKEN": S2S_TOKEN,
        "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "false",
    }
    values.update(overrides)
    return values


def _scope(method: str, path: str) -> dict[str, Any]:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": [
            (b"content-type", b"application/json"),
            (b"accept", b"application/json"),
            (b"authorization", f"Bearer {S2S_TOKEN}".encode("ascii")),
        ],
    }


def _body(send: Send) -> dict[str, Any]:
    return json.loads(send.events[1]["body"].decode("utf-8"))


def _run_asgi(app: Any, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    send = Send()
    body = json.dumps(payload or {}, separators=(",", ":")).encode("utf-8")
    asyncio.run(
        app(
            _scope(method, path),
            Receive([{"type": "http.request", "body": body, "more_body": False}]),
            send,
        )
    )
    return send.events[0]["status"], _body(send)


def _generate_payload() -> dict[str, Any]:
    return {
        "contract_version": "1",
        "agent_run_id": AGENT_RUN_ID,
        "question": "Execute uma generic analysis de teste.",
        "principal": {"id": "user-1", "email": "user@example.invalid", "profile": "admin"},
        "correlation_metadata": {"source": "shadow_test_unit"},
    }


def _execute_payload() -> dict[str, Any]:
    return {
        "contract_version": "1",
        "agent_run_id": AGENT_RUN_ID,
        "approved_sql": OFFLINE_SQL,
        "principal": {"id": "user-1", "email": "user@example.invalid", "profile": "admin"},
        "correlation_metadata": {"source": "shadow_test_unit"},
    }


def _runtime_with_fake_repo(logger: TestLogger | None = None):
    return create_shadow_test_runtime(
        _env(),
        shadow_repository_override=FakeShadowEvidenceRepository(),
        context_repository_override=ShadowTestContextRepository(),
        sql_generator_override=ShadowTestSqlGenerator(),
        sql_repairer_override=ShadowTestSqlRepairer(),
        logger=logger,
    )


def test_config_shadow_test_valida() -> None:
    config = load_shadow_test_runtime_config(_env())
    assert config.runtime_mode == "shadow_test"
    assert config.allow_real_sql_execution is False
    assert config.s2s_token == S2S_TOKEN
    assert config.shadow_database_dsn == DSN_PLACEHOLDER
    assert config.context_postgres_dsn == CONTEXT_DSN_PLACEHOLDER
    assert config.semantic_agent_version == SEMANTIC_AGENT_VERSION
    assert config.context_schema == "public"


def test_config_shadow_test_carrega_schema_contexto() -> None:
    config = load_shadow_test_runtime_config(
        _env(POSTGRES_CONTEXT_SCHEMA="semantic_context")
    )

    assert config.context_schema == "semantic_context"


def test_config_shadow_test_rejeita_schema_contexto_invalido() -> None:
    invalid_values = [
        "public.foo",
        "public;drop table x",
        '"public"',
        "public schema",
    ]

    for invalid_value in invalid_values:
        try:
            load_shadow_test_runtime_config(
                _env(POSTGRES_CONTEXT_SCHEMA=invalid_value)
            )
        except ValueError as error:
            assert "POSTGRES_CONTEXT_SCHEMA" in str(error)
        else:
            raise AssertionError("invalid context schema should fail closed")


def test_config_repr_nao_expoe_dsn() -> None:
    dsn = "postgresql://example.invalid/test?marker=opaque-marker"
    secret = "test-hidden-s2s-token"
    config = load_shadow_test_runtime_config(
        _env(
            LANGGRAPH_SHADOW_DATABASE_DSN=dsn,
            CONTEXT_POSTGRES_DSN="postgresql://context-hidden",
            LANGGRAPH_S2S_TOKEN=secret,
        )
    )
    assert config.shadow_database_dsn == dsn
    assert config.context_postgres_dsn == "postgresql://context-hidden"
    assert config.s2s_token == secret
    serialized = repr(config) + str(config)
    assert "opaque-marker" not in serialized
    assert dsn not in serialized
    assert "context-hidden" not in serialized
    assert secret not in serialized


def test_config_ausente_falha_fechado() -> None:
    try:
        load_shadow_test_runtime_config({})
    except RuntimeError as error:
        assert "LANGGRAPH_RUNTIME_MODE" in str(error)
    else:
        raise AssertionError("missing config should fail closed")


def test_s2s_token_ausente_falha_startup() -> None:
    env = _env()
    del env["LANGGRAPH_S2S_TOKEN"]
    try:
        load_shadow_test_runtime_config(env)
    except RuntimeError as error:
        assert "LANGGRAPH_S2S_TOKEN" in str(error)
    else:
        raise AssertionError("missing S2S token should fail closed")


def test_real_sql_execution_true_falha_startup() -> None:
    try:
        load_shadow_test_runtime_config(_env(LANGGRAPH_ALLOW_REAL_SQL_EXECUTION="true"))
    except RuntimeError as error:
        assert "Real SQL execution" in str(error)
    else:
        raise AssertionError("real SQL execution must not be enabled")


def test_context_dsn_ausente_falha_startup() -> None:
    env = _env()
    del env["CONTEXT_POSTGRES_DSN"]
    try:
        load_shadow_test_runtime_config(env)
    except RuntimeError as error:
        assert "CONTEXT_POSTGRES_DSN" in str(error)
    else:
        raise AssertionError("missing context DSN should fail closed")


def test_context_dsn_nao_pode_reutilizar_persistencia() -> None:
    try:
        load_shadow_test_runtime_config(
            _env(CONTEXT_POSTGRES_DSN=DSN_PLACEHOLDER)
        )
    except RuntimeError as error:
        assert "separate" in str(error)
    else:
        raise AssertionError("context DSN must be separated")


def test_healthcheck_responde_sem_segredos() -> None:
    runtime = _runtime_with_fake_repo()
    status, body = _run_asgi(runtime.app, "GET", "/health")
    serialized = repr(body).casefold()
    assert status == 200
    assert body["runtime_mode"] == "shadow_test"
    assert body["real_sql_execution"] is False
    assert "dsn" not in serialized
    assert "postgresql://" not in serialized


def test_generate_endpoint_v1_exposto() -> None:
    runtime = _runtime_with_fake_repo()
    status, body = _run_asgi(
        runtime.app,
        "POST",
        "/v1/internal/sql-agent/generate",
        _generate_payload(),
    )
    assert status == 200
    assert body["status"] == "success"
    assert body["sql"] == OFFLINE_SQL


def test_execute_approved_shadow_endpoint_v1_exposto() -> None:
    runtime = _runtime_with_fake_repo()
    status, body = _run_asgi(
        runtime.app,
        "POST",
        "/v1/internal/sql-agent/execute-approved-shadow",
        _execute_payload(),
    )
    assert status == 200
    assert body["status"] == "success"
    assert body["approved_sql_original"] == OFFLINE_SQL


def test_watson_e_execute_sql_real_nao_instanciados() -> None:
    runtime = _runtime_with_fake_repo()
    serialized = repr(runtime).casefold()
    assert "watson" not in serialized
    assert "sqlexecutor" not in serialized
    assert "sql_executor" not in serialized


def test_postgres_repository_selecionado_quando_configurado() -> None:
    runtime = create_shadow_test_runtime(_env())
    assert isinstance(runtime.raw_shadow_repository, PostgresShadowEvidenceRepository)
    assert isinstance(runtime.context_repository, PostgresContextRepository)
    assert isinstance(runtime.sql_generator, GoogleGeminiSqlGeneratorAdapter)
    assert isinstance(runtime.sql_repairer, GoogleGeminiSqlRepairerAdapter)


def test_shadow_runtime_propaga_schema_contexto_para_repository() -> None:
    runtime = create_shadow_test_runtime(
        _env(POSTGRES_CONTEXT_SCHEMA="semantic_context")
    )

    assert isinstance(runtime.context_repository, PostgresContextRepository)
    assert (
        "semantic_context.ai_ducklake_agent_rules"
        in runtime.context_repository._load_sql
    )
    assert "public.ai_ducklake_agent_rules" not in (
        runtime.context_repository._load_sql
    )


def test_fake_repository_nao_e_usado_no_composition_root_test_real() -> None:
    runtime = create_shadow_test_runtime(_env())
    assert not isinstance(runtime.raw_shadow_repository, FakeShadowEvidenceRepository)


def test_dsn_nao_aparece_em_logs_ou_erros() -> None:
    logger = TestLogger()
    runtime = _runtime_with_fake_repo(logger)
    _run_asgi(
        runtime.app,
        "POST",
        "/v1/internal/sql-agent/generate",
        _generate_payload(),
    )
    serialized = repr(logger.messages).casefold()
    assert DSN_PLACEHOLDER.casefold() not in serialized
    assert "postgresql://" not in serialized


def test_request_logging_sanitizado() -> None:
    logger = TestLogger()
    runtime = _runtime_with_fake_repo(logger)
    _run_asgi(
        runtime.app,
        "POST",
        "/v1/internal/sql-agent/generate",
        _generate_payload(),
    )
    serialized = repr(logger.messages).casefold()
    assert "shadow_test_request_accepted" in serialized
    assert "shadow_test_request_completed" in serialized
    assert "generic analysis" not in serialized
    assert OFFLINE_SQL.casefold() not in serialized
    assert "authorization" not in serialized
    assert "cookie" not in serialized
    assert "secret" not in serialized


def test_logger_falha_nao_quebra_request_ou_persistencia() -> None:
    runtime = _runtime_with_fake_repo(FailingLogger())
    status, body = _run_asgi(
        runtime.app,
        "POST",
        "/v1/internal/sql-agent/generate",
        _generate_payload(),
    )
    assert status == 200
    assert body["status"] == "success"
    assert runtime.shadow_repository.last_results_by_shadow_id


def test_postgres_wiring_create_e_finalize_com_fake_connect() -> None:
    connect = FakePostgresConnect()
    runtime = create_shadow_test_runtime(
        _env(),
        connect_override=connect,
        context_repository_override=ShadowTestContextRepository(),
        sql_generator_override=ShadowTestSqlGenerator(),
        sql_repairer_override=ShadowTestSqlRepairer(),
    )
    status, body = _run_asgi(
        runtime.app,
        "POST",
        "/v1/internal/sql-agent/generate",
        _generate_payload(),
    )
    assert status == 200
    assert body["status"] == "success"
    assert connect.calls == 3
    queries = [call[0] for call in connect.cursor.calls]
    parameters = [call[1] for call in connect.cursor.calls]
    assert queries[0] == INSERT_SHADOW_RUN_SQL
    assert queries[-1] == FINALIZE_SHADOW_RUN_SQL
    assert parameters[0]["agent_run_id"] == AGENT_RUN_ID
    assert parameters[0]["run_id"] == body["run_id"]
    assert parameters[0]["event_type"] == "generate"
    assert parameters[-1]["shadow_record_id"] == parameters[0]["shadow_record_id"]


def test_postgres_wiring_execute_event_type() -> None:
    connect = FakePostgresConnect()
    runtime = create_shadow_test_runtime(
        _env(),
        connect_override=connect,
        context_repository_override=ShadowTestContextRepository(),
        sql_generator_override=ShadowTestSqlGenerator(),
        sql_repairer_override=ShadowTestSqlRepairer(),
    )
    status, body = _run_asgi(
        runtime.app,
        "POST",
        "/v1/internal/sql-agent/execute-approved-shadow",
        _execute_payload(),
    )
    assert status == 200
    assert body["status"] == "success"
    assert connect.cursor.calls[0][1]["agent_run_id"] == AGENT_RUN_ID
    assert connect.cursor.calls[0][1]["run_id"] == body["run_id"]
    assert connect.cursor.calls[0][1]["event_type"] == "execute_approved_shadow"


def main() -> None:
    tests = [
        test_config_shadow_test_valida,
        test_config_shadow_test_carrega_schema_contexto,
        test_config_shadow_test_rejeita_schema_contexto_invalido,
        test_config_repr_nao_expoe_dsn,
        test_config_ausente_falha_fechado,
        test_s2s_token_ausente_falha_startup,
        test_real_sql_execution_true_falha_startup,
        test_context_dsn_ausente_falha_startup,
        test_context_dsn_nao_pode_reutilizar_persistencia,
        test_healthcheck_responde_sem_segredos,
        test_generate_endpoint_v1_exposto,
        test_execute_approved_shadow_endpoint_v1_exposto,
        test_watson_e_execute_sql_real_nao_instanciados,
        test_postgres_repository_selecionado_quando_configurado,
        test_shadow_runtime_propaga_schema_contexto_para_repository,
        test_fake_repository_nao_e_usado_no_composition_root_test_real,
        test_dsn_nao_aparece_em_logs_ou_erros,
        test_request_logging_sanitizado,
        test_logger_falha_nao_quebra_request_ou_persistencia,
        test_postgres_wiring_create_e_finalize_com_fake_connect,
        test_postgres_wiring_execute_event_type,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()

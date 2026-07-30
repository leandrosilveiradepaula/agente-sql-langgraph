from __future__ import annotations

from copy import deepcopy

from app.domain.engine_preflight import (
    ENGINE_PREFLIGHT_CONTRACT_VERSION,
    EnginePreflightInputError,
    build_engine_preflight_request,
    normalize_engine_preflight_result,
    request_fingerprint,
)
from testar_planner import _context
from app.domain.planner import build_query_plan


def _query_plan() -> dict:
    result = build_query_plan(
        context=_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="generic analysis",
    )
    assert result["query_plan"] is not None
    return result["query_plan"]


def _security_result() -> dict:
    return {
        "status": "approved",
        "sql_fingerprint": "a" * 64,
        "errors": [],
        "warnings": [],
    }


def _contract_result() -> dict:
    return {
        "status": "approved",
        "sql_fingerprint": "a" * 64,
        "errors": [],
        "warnings": [],
    }


def _request(sql: str = "SELECT id FROM schema_test.table_test") -> dict:
    return build_engine_preflight_request(
        current_sql=sql,
        query_plan=_query_plan(),
        security_result=_security_result(),
        contract_result=_contract_result(),
        options={"engine_preflight_timeout_ms": 2500},
    )


def _provider_result(category: str, **extra):
    result = {
        "status": "rejected",
        "provider_name": "fake_engine_preflight",
        "provider_version": "test-v1",
        "failure_category": category,
        "message": f"{category} detected",
        "duration_ms": 4,
        "statement_planned": False,
        "executed": False,
        "rows_returned": 0,
    }
    result.update(extra)
    return result


def test_constroi_requisicao_minima() -> None:
    request = _request()

    assert request["contract_version"] == (
        ENGINE_PREFLIGHT_CONTRACT_VERSION
    )
    assert request["sql"] == "SELECT id FROM schema_test.table_test"
    assert len(request["sql_fingerprint"]) == 64
    assert request["context_version"] == "context-test-v1"
    assert request["intent_name"] == "generic_test_intent"
    assert request["allowed_schemas"] == ["schema_test"]
    assert request["planned_tables"] == ["schema_test.table_test"]
    assert request["timeout_ms"] == 2500
    assert request["capabilities_requested"]["executes_query"] is False


def test_requisicao_usa_current_sql() -> None:
    request = _request("SELECT value FROM schema_test.table_test")

    assert request["sql"] == "SELECT value FROM schema_test.table_test"


def test_requisicao_nao_contem_context_snapshot_ou_credenciais() -> None:
    request = _request()
    serialized = repr(request).casefold()

    assert "intent_catalog" not in serialized
    assert "query_patterns" not in serialized
    assert "table_catalog" not in serialized
    assert "password" not in serialized
    assert "token" not in serialized
    assert "postgresql://" not in serialized
    assert "'context'" not in serialized


def test_fingerprint_ordem_e_imutabilidade() -> None:
    plan = _query_plan()
    original = deepcopy(plan)
    first = build_engine_preflight_request(
        current_sql="SELECT id FROM schema_test.table_test",
        query_plan=plan,
        security_result=_security_result(),
        contract_result=_contract_result(),
        options={},
    )
    second = build_engine_preflight_request(
        current_sql="SELECT id FROM schema_test.table_test",
        query_plan=plan,
        security_result=_security_result(),
        contract_result=_contract_result(),
        options={},
    )

    assert first == second
    assert request_fingerprint(first) == request_fingerprint(second)
    assert plan == original


def test_rejeita_precondicoes_invalidas() -> None:
    cases = [
        (
            "",
            _query_plan(),
            _security_result(),
            _contract_result(),
            "ENGINE_PREFLIGHT_SQL_MISSING",
        ),
        (
            "SELECT 1",
            {},
            _security_result(),
            _contract_result(),
            "ENGINE_PREFLIGHT_PLAN_MISSING",
        ),
        (
            "SELECT 1",
            _query_plan(),
            {"status": "rejected"},
            _contract_result(),
            "ENGINE_PREFLIGHT_SECURITY_NOT_APPROVED",
        ),
        (
            "SELECT 1",
            _query_plan(),
            _security_result(),
            {"status": "rejected"},
            "ENGINE_PREFLIGHT_CONTRACT_NOT_APPROVED",
        ),
    ]

    for sql, plan, security, contract, code in cases:
        try:
            build_engine_preflight_request(
                current_sql=sql,
                query_plan=plan,
                security_result=security,
                contract_result=contract,
                options={},
            )
        except EnginePreflightInputError as error:
            assert error.code == code
        else:
            raise AssertionError(f"Era esperado {code}.")


def test_resultado_aprovado() -> None:
    request = _request()
    result = normalize_engine_preflight_result(
        request=request,
        provider_result={
            "status": "approved",
            "provider_name": "fake_engine_preflight",
            "provider_version": "test-v1",
            "duration_ms": 2,
            "statement_planned": True,
            "executed": False,
            "rows_returned": 0,
        },
    )

    assert result["status"] == "approved"
    assert result["approved"] is True
    assert result["repairable"] is False
    assert result["executed"] is False
    assert result["rows_returned"] == 0
    assert result["statement_planned"] is True
    assert request["sql"] not in repr(result)


def _assert_category(category: str, code: str, repairable: bool = True) -> None:
    request = _request()
    result = normalize_engine_preflight_result(
        request=request,
        provider_result=_provider_result(category),
    )

    assert result["status"] == "rejected"
    assert result["failure_category"] == category
    assert result["repairable"] is repairable
    assert result["errors"][0]["code"] == code
    assert result["executed"] is False
    assert result["rows_returned"] == 0


def test_categorias_reparaveis() -> None:
    cases = [
        ("syntax_error", "ENGINE_PREFLIGHT_SYNTAX_ERROR"),
        ("table_not_found", "ENGINE_PREFLIGHT_TABLE_NOT_FOUND"),
        ("column_not_found", "ENGINE_PREFLIGHT_COLUMN_NOT_FOUND"),
        ("ambiguous_column", "ENGINE_PREFLIGHT_AMBIGUOUS_COLUMN"),
        ("function_not_found", "ENGINE_PREFLIGHT_FUNCTION_NOT_FOUND"),
        ("invalid_grouping", "ENGINE_PREFLIGHT_INVALID_GROUPING"),
        ("type_mismatch", "ENGINE_PREFLIGHT_TYPE_MISMATCH"),
        ("planning_error", "ENGINE_PREFLIGHT_PLANNING_ERROR"),
        ("unknown_sql_error", "ENGINE_PREFLIGHT_UNKNOWN_SQL_ERROR"),
    ]
    for category, code in cases:
        _assert_category(category, code)


def test_categorias_infraestrutura() -> None:
    cases = [
        ("provider_unavailable", "ENGINE_PREFLIGHT_PROVIDER_UNAVAILABLE"),
        ("timeout", "ENGINE_PREFLIGHT_TIMEOUT"),
        (
            "authentication_failed",
            "ENGINE_PREFLIGHT_AUTHENTICATION_FAILED",
        ),
    ]
    request = _request()
    for category, code in cases:
        result = normalize_engine_preflight_result(
            request=request,
            provider_result={
                **_provider_result(category),
                "status": "error",
            },
        )
        assert result["status"] == "error"
        assert result["repairable"] is False
        assert result["errors"][0]["code"] == code


def test_resposta_invalida() -> None:
    result = normalize_engine_preflight_result(
        request=_request(),
        provider_result={"provider_name": "fake"},
    )

    assert result["status"] == "error"
    assert result["errors"][0]["code"] == (
        "ENGINE_PREFLIGHT_RESPONSE_INVALID"
    )


def test_sanitiza_mensagem_dsn_senha_token() -> None:
    request = _request()
    result = normalize_engine_preflight_result(
        request=request,
        provider_result=_provider_result(
            "unknown_sql_error",
            message=(
                "failed dsn=postgresql://example.invalid/db "
                "password=hidden token=abc"
            ),
            hint="api_key=abc use another object",
        ),
    )
    serialized = repr(result).casefold()

    assert "postgresql://" not in serialized
    assert "hidden" not in serialized
    assert "token=abc" not in serialized
    assert "api_key=abc" not in serialized


def test_provider_nao_pode_marcar_execucao() -> None:
    result = normalize_engine_preflight_result(
        request=_request(),
        provider_result={
            "status": "approved",
            "provider_name": "bad_provider",
            "executed": True,
            "rows_returned": 10,
        },
    )

    assert result["status"] == "error"
    assert result["approved"] is False
    assert result["executed"] is False
    assert result["rows_returned"] == 0


def test_comportamento_deterministico() -> None:
    request = _request()
    first = normalize_engine_preflight_result(
        request=request,
        provider_result=_provider_result("column_not_found"),
    )
    second = normalize_engine_preflight_result(
        request=request,
        provider_result=_provider_result("column_not_found"),
    )

    assert first == second


def main() -> None:
    tests = [
        ("constroi requisicao", test_constroi_requisicao_minima),
        ("usa current_sql", test_requisicao_usa_current_sql),
        (
            "sem snapshot ou credenciais",
            test_requisicao_nao_contem_context_snapshot_ou_credenciais,
        ),
        (
            "fingerprint ordem imutabilidade",
            test_fingerprint_ordem_e_imutabilidade,
        ),
        ("precondicoes invalidas", test_rejeita_precondicoes_invalidas),
        ("resultado aprovado", test_resultado_aprovado),
        ("categorias reparaveis", test_categorias_reparaveis),
        ("categorias infraestrutura", test_categorias_infraestrutura),
        ("resposta invalida", test_resposta_invalida),
        ("sanitiza mensagem", test_sanitiza_mensagem_dsn_senha_token),
        ("executed false", test_provider_nao_pode_marcar_execucao),
        ("determinismo", test_comportamento_deterministico),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

from __future__ import annotations

from copy import deepcopy

from app.domain.engine_preflight import (
    build_engine_preflight_request,
    normalize_engine_preflight_result,
)
from app.domain.planner import build_query_plan
from app.domain.sql_contract import run_sql_contract_gate
from app.domain.sql_execution import (
    build_sql_execution_request,
    normalize_sql_execution_result,
    request_fingerprint,
)
from app.domain.sql_security import run_sql_security_gate
from testar_planner import _context


SQL = "SELECT id FROM schema_test.table_test"


def _query_plan() -> dict:
    result = build_query_plan(
        context=_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="generic analysis",
    )
    assert result["query_plan"] is not None
    return result["query_plan"]


def _approved_inputs(sql: str = SQL) -> dict:
    query_plan = _query_plan()
    security_result, analysis = run_sql_security_gate(
        current_sql=sql,
        query_plan=query_plan,
    )
    contract_result, _ = run_sql_contract_gate(
        current_sql=sql,
        query_plan=query_plan,
        analysis=analysis,
    )
    preflight_request = build_engine_preflight_request(
        current_sql=sql,
        query_plan=query_plan,
        security_result=security_result,
        contract_result=contract_result,
        options={"attempt": 1},
    )
    preflight_result = normalize_engine_preflight_result(
        request=preflight_request,
        provider_result={
            "status": "approved",
            "provider_name": "fake_engine_preflight",
            "statement_planned": True,
            "executed": False,
            "rows_returned": 0,
        },
    )
    return {
        "current_sql": sql,
        "query_plan": query_plan,
        "security_result": security_result,
        "contract_result": contract_result,
        "engine_preflight_result": preflight_result,
        "request_id": "request-1",
        "run_id": "run-1",
        "options": {
            "sql_execution_limits": {
                "timeout_seconds": 10,
                "max_rows": 5,
                "max_response_bytes": 4096,
                "max_cell_bytes": 128,
            }
        },
    }


def _request(**overrides):
    inputs = _approved_inputs()
    inputs.update(overrides)
    return build_sql_execution_request(**inputs)


def _provider_result(**overrides):
    result = {
        "status": "success",
        "provider_name": "fake_sql_executor",
        "provider_version": "test-v1",
        "columns": [{"name": "id", "type": "int"}],
        "rows": [{"id": 1}],
        "row_count": 1,
        "duration_ms": 2,
        "executed": True,
        "statement_type": "select",
        "warnings": [],
    }
    result.update(overrides)
    return result


def test_request_valida() -> None:
    request = _request()
    assert request["current_sql"] == SQL
    assert request["intent_name"] == "generic_test_intent"
    assert request["limits"]["max_rows"] == 5
    assert "query_plan" not in request
    assert "context" not in request


def test_current_sql_preservada_exatamente() -> None:
    sql = "SELECT id\nFROM schema_test.table_test"
    request = _request(**_approved_inputs(sql))
    assert request["current_sql"] == sql


def test_fingerprint_deterministico() -> None:
    first = _request()
    second = _request()
    assert first["request_fingerprint"] == second["request_fingerprint"]
    assert request_fingerprint(first) == first["request_fingerprint"]


def test_sem_mutacao() -> None:
    inputs = _approved_inputs()
    original = deepcopy(inputs)
    build_sql_execution_request(**inputs)
    assert inputs == original


def test_security_nao_aprovado() -> None:
    try:
        _request(security_result={"status": "rejected"})
    except Exception as error:
        assert getattr(error, "code") == (
            "SQL_EXECUTION_SECURITY_NOT_APPROVED"
        )
    else:
        raise AssertionError("Era esperado erro.")


def test_contract_nao_aprovado() -> None:
    try:
        _request(contract_result={"status": "rejected"})
    except Exception as error:
        assert getattr(error, "code") == (
            "SQL_EXECUTION_CONTRACT_NOT_APPROVED"
        )
    else:
        raise AssertionError("Era esperado erro.")


def test_preflight_nao_aprovado() -> None:
    inputs = _approved_inputs()
    inputs["engine_preflight_result"] = {
        **inputs["engine_preflight_result"],
        "status": "rejected",
        "approved": False,
    }
    try:
        build_sql_execution_request(**inputs)
    except Exception as error:
        assert getattr(error, "code") == (
            "SQL_EXECUTION_PREFLIGHT_NOT_APPROVED"
        )
    else:
        raise AssertionError("Era esperado erro.")


def test_capability_unavailable() -> None:
    inputs = _approved_inputs()
    inputs["engine_preflight_result"] = {
        **inputs["engine_preflight_result"],
        "failure_category": "capability_unavailable",
    }
    try:
        build_sql_execution_request(**inputs)
    except Exception as error:
        assert getattr(error, "code") == (
            "SQL_EXECUTION_CAPABILITY_UNAVAILABLE"
        )
    else:
        raise AssertionError("Era esperado erro.")


def test_preflight_executed_true() -> None:
    inputs = _approved_inputs()
    inputs["engine_preflight_result"] = {
        **inputs["engine_preflight_result"],
        "executed": True,
    }
    try:
        build_sql_execution_request(**inputs)
    except Exception as error:
        assert getattr(error, "code") == (
            "SQL_EXECUTION_PREFLIGHT_NOT_APPROVED"
        )
    else:
        raise AssertionError("Era esperado erro.")


def test_preflight_rows_returned() -> None:
    inputs = _approved_inputs()
    inputs["engine_preflight_result"] = {
        **inputs["engine_preflight_result"],
        "rows_returned": 1,
    }
    try:
        build_sql_execution_request(**inputs)
    except Exception as error:
        assert getattr(error, "code") == (
            "SQL_EXECUTION_PREFLIGHT_NOT_APPROVED"
        )
    else:
        raise AssertionError("Era esperado erro.")


def test_limites_invalidos() -> None:
    inputs = _approved_inputs()
    inputs["options"] = {"sql_execution_limits": {"max_rows": 1}}
    try:
        build_sql_execution_request(**inputs)
    except Exception as error:
        assert getattr(error, "code") == "SQL_EXECUTION_REQUEST_INVALID"
    else:
        raise AssertionError("Era esperado erro.")


def test_sql_vazia() -> None:
    try:
        _request(current_sql="")
    except Exception as error:
        assert getattr(error, "code") == "SQL_EXECUTION_REQUEST_INVALID"
    else:
        raise AssertionError("Era esperado erro.")


def test_sql_nao_read_only() -> None:
    try:
        _request(current_sql="UPDATE schema_test.table_test SET id = 1")
    except Exception as error:
        assert getattr(error, "code") == "SQL_EXECUTION_NOT_AUTHORIZED"
    else:
        raise AssertionError("Era esperado erro.")


def test_resposta_valida() -> None:
    result = normalize_sql_execution_result(
        request=_request(),
        provider_result=_provider_result(),
    )
    assert result["status"] == "success"
    assert result["executed"] is True
    assert result["row_count"] == 1


def test_resposta_vazia_valida() -> None:
    result = normalize_sql_execution_result(
        request=_request(),
        provider_result=_provider_result(rows=[], row_count=0),
    )
    assert result["status"] == "success"
    assert result["rows"] == []


def test_resposta_inconsistente() -> None:
    result = normalize_sql_execution_result(
        request=_request(),
        provider_result=_provider_result(row_count=2),
    )
    assert result["status"] == "rejected"
    assert result["error_code"] == "SQL_EXECUTION_RESPONSE_INVALID"


def test_row_limit() -> None:
    result = normalize_sql_execution_result(
        request=_request(),
        provider_result=_provider_result(
            rows=[{"id": index} for index in range(6)],
            row_count=6,
        ),
    )
    assert result["error_code"] == "SQL_EXECUTION_ROW_LIMIT_EXCEEDED"


def test_byte_limit() -> None:
    request = _request()
    request["limits"]["max_response_bytes"] = 10
    result = normalize_sql_execution_result(
        request=request,
        provider_result=_provider_result(),
    )
    assert result["error_code"] == "SQL_EXECUTION_BYTE_LIMIT_EXCEEDED"


def test_cell_limit() -> None:
    result = normalize_sql_execution_result(
        request=_request(),
        provider_result=_provider_result(
            rows=[{"id": "x" * 200}],
            row_count=1,
        ),
    )
    assert result["error_code"] == "SQL_EXECUTION_CELL_LIMIT_EXCEEDED"


def test_timeout() -> None:
    result = normalize_sql_execution_result(
        request=_request(),
        provider_result={
            "status": "error",
            "failure_category": "timeout",
            "message": "timeout",
        },
    )
    assert result["status"] == "infrastructure_error"
    assert result["error_code"] == "SQL_EXECUTION_TIMEOUT"


def test_autenticacao() -> None:
    result = normalize_sql_execution_result(
        request=_request(),
        provider_result={
            "status": "error",
            "failure_category": "authentication_failed",
            "message": "token=hidden",
        },
    )
    assert result["status"] == "infrastructure_error"
    assert "hidden" not in repr(result)


def test_provider_failure() -> None:
    result = normalize_sql_execution_result(
        request=_request(),
        provider_result={
            "status": "error",
            "failure_category": "provider_failed",
            "message": "provider failed",
        },
    )
    assert result["error_code"] == "SQL_EXECUTION_PROVIDER_FAILED"


def test_sanitizacao_token() -> None:
    result = normalize_sql_execution_result(
        request=_request(),
        provider_result={
            "status": "rejected",
            "message": "token=abc123",
        },
    )
    assert "abc123" not in repr(result)


def test_sanitizacao_dsn() -> None:
    result = normalize_sql_execution_result(
        request=_request(),
        provider_result={
            "status": "error",
            "failure_category": "provider_failed",
            "message": "dsn=postgresql://secret.example/db",
        },
    )
    assert "secret.example" not in repr(result)


def test_sql_integral_removida_de_erros() -> None:
    result = normalize_sql_execution_result(
        request=_request(),
        provider_result={
            "status": "error",
            "failure_category": "provider_failed",
            "message": f"failed for {SQL}",
        },
    )
    assert SQL.casefold() not in repr(result).casefold()


def test_request_sem_graphstate() -> None:
    assert "graphstate" not in repr(_request()).casefold()


def test_request_sem_contextsnapshot() -> None:
    assert "contextsnapshot" not in repr(_request()).casefold()


def test_provider_chamado_uma_vez_por_fake() -> None:
    from app.adapters.testing.fake_sql_executor import FakeSqlExecutor

    fake = FakeSqlExecutor()
    fake.execute(_request())
    assert fake.calls == 1


def main() -> None:
    tests = [
        ("request valida", test_request_valida),
        ("current_sql preservada", test_current_sql_preservada_exatamente),
        ("fingerprint deterministico", test_fingerprint_deterministico),
        ("sem mutacao", test_sem_mutacao),
        ("Security nao aprovado", test_security_nao_aprovado),
        ("Contract nao aprovado", test_contract_nao_aprovado),
        ("Preflight nao aprovado", test_preflight_nao_aprovado),
        ("capability unavailable", test_capability_unavailable),
        ("preflight executed true", test_preflight_executed_true),
        ("preflight rows_returned", test_preflight_rows_returned),
        ("limites invalidos", test_limites_invalidos),
        ("SQL vazia", test_sql_vazia),
        ("SQL nao read-only", test_sql_nao_read_only),
        ("resposta valida", test_resposta_valida),
        ("resposta vazia valida", test_resposta_vazia_valida),
        ("resposta inconsistente", test_resposta_inconsistente),
        ("row limit", test_row_limit),
        ("byte limit", test_byte_limit),
        ("cell limit", test_cell_limit),
        ("timeout", test_timeout),
        ("autenticacao", test_autenticacao),
        ("provider failure", test_provider_failure),
        ("sanitizacao token", test_sanitizacao_token),
        ("sanitizacao dsn", test_sanitizacao_dsn),
        ("SQL integral removida de erros", test_sql_integral_removida_de_erros),
        ("request sem GraphState", test_request_sem_graphstate),
        ("request sem ContextSnapshot", test_request_sem_contextsnapshot),
        ("provider chamado uma vez", test_provider_chamado_uma_vez_por_fake),
    ]
    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

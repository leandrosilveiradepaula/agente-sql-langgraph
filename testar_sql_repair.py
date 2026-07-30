from __future__ import annotations

from copy import deepcopy

from app.domain.engine_preflight import normalize_engine_preflight_result
from app.domain.sql_repair import (
    SqlRepairInputError,
    build_sql_repair_request,
    create_sql_repair_error_result,
    create_sql_repair_success_result,
    request_fingerprint,
    response_fingerprint,
    sql_fingerprint,
    validate_sql_repair_response,
)
from testar_engine_preflight import _query_plan, _request


CURRENT_SQL = "SELECT id FROM schema_test.table_test"
REPAIRED_SQL = "SELECT value FROM schema_test.table_test"


def _preflight_result(*, repairable: bool = True) -> dict:
    return normalize_engine_preflight_result(
        request=_request(CURRENT_SQL),
        provider_result={
            "status": "rejected",
            "provider_name": "fake_engine_preflight",
            "failure_category": "column_not_found",
            "message": "column not found",
            "repairable": repairable,
            "provider_code": "GENERIC_CODE",
            "sqlstate": "42703",
            "line": 1,
            "column": 8,
            "executed": False,
            "rows_returned": 0,
        },
    )


def _repair_request(**overrides) -> dict:
    values = {
        "current_sql": CURRENT_SQL,
        "query_plan": _query_plan(),
        "engine_preflight_result": _preflight_result(),
        "repair_attempts": 0,
        "max_repair_attempts": 2,
        "repair_history": [],
    }
    values.update(overrides)
    return build_sql_repair_request(**values)


def test_constroi_requisicao_minima() -> None:
    request = _repair_request()
    serialized = repr(request).casefold()

    assert request["current_sql"] == CURRENT_SQL
    assert request["attempt"] == 1
    assert request["max_attempts"] == 2
    assert request["failure"]["category"] == "column_not_found"
    assert request["failure"]["sqlstate"] == "42703"
    assert len(request["request_fingerprint"]) == 64
    assert "intent_catalog" not in serialized
    assert "query_patterns" not in serialized
    assert "table_catalog" not in serialized
    assert "'context'" not in serialized
    assert "password" not in serialized
    assert "token" not in serialized


def test_fingerprint_e_imutabilidade() -> None:
    plan = _query_plan()
    preflight = _preflight_result()
    history = []
    original_plan = deepcopy(plan)
    original_preflight = deepcopy(preflight)

    first = build_sql_repair_request(
        current_sql=CURRENT_SQL,
        query_plan=plan,
        engine_preflight_result=preflight,
        repair_attempts=0,
        max_repair_attempts=2,
        repair_history=history,
    )
    second = build_sql_repair_request(
        current_sql=CURRENT_SQL,
        query_plan=plan,
        engine_preflight_result=preflight,
        repair_attempts=0,
        max_repair_attempts=2,
        repair_history=history,
    )

    assert first == second
    assert request_fingerprint(first) == request_fingerprint(second)
    assert plan == original_plan
    assert preflight == original_preflight
    assert history == []


def test_rejeita_limite_zero_limite_atingido_e_nao_reparavel() -> None:
    cases = [
        (
            {"max_repair_attempts": 0},
            "SQL_REPAIR_DISABLED",
        ),
        (
            {"repair_attempts": 2, "max_repair_attempts": 2},
            "SQL_REPAIR_LIMIT_REACHED",
        ),
        (
            {"engine_preflight_result": _preflight_result(repairable=False)},
            "SQL_REPAIR_PREFLIGHT_NOT_REPAIRABLE",
        ),
    ]
    for overrides, code in cases:
        try:
            _repair_request(**overrides)
        except SqlRepairInputError as error:
            assert error.code == code
        else:
            raise AssertionError(f"Era esperado {code}.")


def test_valida_resposta_sql() -> None:
    assert validate_sql_repair_response(
        provider_result={"output_text": REPAIRED_SQL},
        current_sql=CURRENT_SQL,
        repair_history=[],
    ) == REPAIRED_SQL


def test_rejeita_respostas_invalidas() -> None:
    cases = [
        ("", "SQL_REPAIR_RESPONSE_EMPTY"),
        ("```sql\nSELECT 1\n```", "SQL_REPAIR_RESPONSE_INVALID"),
        ("Segue a SQL: SELECT 1", "SQL_REPAIR_RESPONSE_INVALID"),
        ("SELECT 1; SELECT 2", "SQL_REPAIR_MULTIPLE_STATEMENTS"),
        ("UPDATE schema_test.table_test SET id = 1", "SQL_REPAIR_NON_READ_ONLY"),
        (CURRENT_SQL, "SQL_REPAIR_UNCHANGED_SQL"),
    ]
    for output_text, code in cases:
        try:
            validate_sql_repair_response(
                provider_result={"output_text": output_text},
                current_sql=CURRENT_SQL,
                repair_history=[],
            )
        except SqlRepairInputError as error:
            assert error.code == code
        else:
            raise AssertionError(f"Era esperado {code}.")


def test_rejeita_sql_repetida_no_historico() -> None:
    try:
        validate_sql_repair_response(
            provider_result={"output_text": REPAIRED_SQL},
            current_sql=CURRENT_SQL,
            repair_history=[
                {
                    "attempt": 1,
                    "sql_after_fingerprint": sql_fingerprint(REPAIRED_SQL),
                }
            ],
        )
    except SqlRepairInputError as error:
        assert error.code == "SQL_REPAIR_REPEATED_SQL"
    else:
        raise AssertionError("Era esperado SQL_REPAIR_REPEATED_SQL.")


def test_resultado_sucesso_e_historico_sem_sql_integral() -> None:
    request = _repair_request()
    result = create_sql_repair_success_result(
        request=request,
        repaired_sql=REPAIRED_SQL,
        provider_result={
            "provider_name": "fake_sql_repairer",
            "output_text": REPAIRED_SQL,
            "duration_ms": 3,
        },
    )
    serialized_history = repr(result["history_entry"]).casefold()

    assert result["status"] == "repaired"
    assert result["sql"] == REPAIRED_SQL
    assert result["repair_applied"] is True
    assert result["history_entry"]["repair_applied"] is True
    assert result["history_entry"]["sql_before_fingerprint"] == (
        sql_fingerprint(CURRENT_SQL)
    )
    assert result["history_entry"]["sql_after_fingerprint"] == (
        sql_fingerprint(REPAIRED_SQL)
    )
    assert CURRENT_SQL.casefold() not in serialized_history
    assert REPAIRED_SQL.casefold() not in serialized_history


def test_resultado_erro_sanitizado() -> None:
    request = _repair_request()
    result = create_sql_repair_error_result(
        request=request,
        code="SQL_REPAIR_PROVIDER_FAILED",
        message=(
            "falhou dsn=postgresql://example.invalid/db "
            "token=abc password=hidden "
            f"{CURRENT_SQL}"
        ),
        reason="sql_repair_provider_failed",
        status="infrastructure_error",
        current_sql=CURRENT_SQL,
        attempt=1,
        max_attempts=2,
        provider_result={
            "provider_name": "provider token=abc",
            "output_text": CURRENT_SQL,
            "duration_ms": 5,
        },
    )
    serialized = repr(result).casefold()

    assert "postgresql://" not in serialized
    assert "token=abc" not in serialized
    assert "hidden" not in serialized
    assert CURRENT_SQL.casefold() not in serialized
    assert result["history_entry"]["repair_applied"] is False


def test_comportamento_deterministico() -> None:
    request = _repair_request()
    first = create_sql_repair_success_result(
        request=request,
        repaired_sql=REPAIRED_SQL,
        provider_result={
            "provider_name": "fake_sql_repairer",
            "output_text": REPAIRED_SQL,
            "duration_ms": 3,
        },
    )
    second = create_sql_repair_success_result(
        request=request,
        repaired_sql=REPAIRED_SQL,
        provider_result={
            "provider_name": "fake_sql_repairer",
            "output_text": REPAIRED_SQL,
            "duration_ms": 3,
        },
    )

    assert first == second
    assert response_fingerprint(REPAIRED_SQL) == (
        first["diagnostic"]["response_fingerprint"]
    )


def main() -> None:
    tests = [
        ("constroi requisicao", test_constroi_requisicao_minima),
        ("fingerprint imutabilidade", test_fingerprint_e_imutabilidade),
        (
            "limites e reparabilidade",
            test_rejeita_limite_zero_limite_atingido_e_nao_reparavel,
        ),
        ("resposta valida", test_valida_resposta_sql),
        ("respostas invalidas", test_rejeita_respostas_invalidas),
        ("sql repetida", test_rejeita_sql_repetida_no_historico),
        (
            "historico sem SQL",
            test_resultado_sucesso_e_historico_sem_sql_integral,
        ),
        ("erro sanitizado", test_resultado_erro_sanitizado),
        ("determinismo", test_comportamento_deterministico),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

from __future__ import annotations

from copy import deepcopy

from app.domain.planner import build_query_plan
from app.domain.sql_security import (
    build_sql_security_policy,
    run_sql_security_gate,
)
from testar_planner import _context


def _query_plan() -> dict:
    result = build_query_plan(
        context=_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="generic analysis",
    )
    assert result["query_plan"] is not None
    return result["query_plan"]


def _plan_with_ambiguous_bare_table() -> dict:
    plan = deepcopy(_query_plan())
    projection = plan["planning_context"]
    projection["required_tables"].append(
        {
            "schema_name": "schema_other",
            "table_name": "table_test",
            "qualified_name": "schema_other.table_test",
            "columns": [{"name": "id"}],
        }
    )
    projection["allowed_schemas"].append("schema_other")
    projection["relevant_columns"]["schema_other.table_test"] = [
        {"name": "id"}
    ]
    return plan


def _run(sql: str, plan: dict | None = None):
    return run_sql_security_gate(
        current_sql=sql,
        query_plan=plan or _query_plan(),
    )[0]


def test_select_autorizada_aprovada() -> None:
    result = _run("SELECT id FROM schema_test.table_test")

    assert result["status"] == "approved"
    assert result["tables"] == ["schema_test.table_test"]


def test_with_autorizada_aprovada() -> None:
    result = _run(
        "WITH generic_cte AS ("
        "SELECT id FROM schema_test.table_test"
        ") SELECT id FROM generic_cte"
    )

    assert result["status"] == "approved"


def test_tabela_nao_autorizada_rejeitada() -> None:
    result = _run("SELECT id FROM schema_test.table_other")

    assert result["status"] == "rejected"
    assert result["errors"][0]["code"] == (
        "SQL_SECURITY_UNAUTHORIZED_TABLE"
    )


def test_schema_nao_autorizado_rejeitado() -> None:
    result = _run("SELECT id FROM schema_other.table_test")

    codes = {error["code"] for error in result["errors"]}
    assert "SQL_SECURITY_UNAUTHORIZED_SCHEMA" in codes


def test_comandos_de_escrita_rejeitados() -> None:
    cases = [
        "INSERT INTO schema_test.table_test VALUES (1)",
        "UPDATE schema_test.table_test SET id = 1",
        "DELETE FROM schema_test.table_test",
        "DROP TABLE schema_test.table_test",
        "CREATE TABLE schema_test.table_copy (id int)",
        "COPY schema_test.table_test TO STDOUT",
        "SET search_path TO schema_test",
    ]

    for sql in cases:
        result = _run(sql)
        codes = {error["code"] for error in result["errors"]}
        assert (
            "SQL_SECURITY_FORBIDDEN_COMMAND" in codes
            or "SQL_SECURITY_NON_READ_ONLY" in codes
        )


def test_multiplos_statements_rejeitados() -> None:
    result = _run(
        "SELECT id FROM schema_test.table_test; "
        "SELECT id FROM schema_test.table_test"
    )

    assert result["status"] == "rejected"
    assert result["errors"][0]["code"] == (
        "SQL_SECURITY_ANALYSIS_FAILED"
    )


def test_select_into_rejeitado() -> None:
    result = _run(
        "SELECT id INTO schema_test.table_copy "
        "FROM schema_test.table_test"
    )

    assert result["status"] == "rejected"
    assert any(
        error["code"] == "SQL_SECURITY_SELECT_INTO"
        for error in result["errors"]
    )


def test_palavra_proibida_em_string_aceita() -> None:
    result = _run(
        "SELECT id FROM schema_test.table_test "
        "WHERE value = 'DELETE value'"
    )

    assert result["status"] == "approved"


def test_palavra_proibida_em_comentario_nao_rejeita() -> None:
    result = _run(
        "SELECT id FROM schema_test.table_test -- DROP ignored"
    )

    assert result["status"] == "approved"


def test_objeto_ambiguo_rejeitado() -> None:
    result = _run(
        "SELECT id FROM table_test",
        _plan_with_ambiguous_bare_table(),
    )

    assert result["status"] == "rejected"
    assert result["errors"][0]["code"] == (
        "SQL_SECURITY_AMBIGUOUS_TABLE"
    )


def test_cte_nao_e_tabela_externa() -> None:
    result = _run(
        "WITH generic_cte AS ("
        "SELECT id FROM schema_test.table_test"
        ") SELECT id FROM generic_cte"
    )

    assert "generic_cte" not in result["tables"]
    assert result["status"] == "approved"


def test_resultado_nao_contem_sql_completa() -> None:
    sql = "SELECT id FROM schema_test.table_test"
    result = _run(sql)

    assert sql not in repr(result)
    assert result["sql_fingerprint"]


def test_determinismo_e_ausencia_de_mutacao() -> None:
    plan = _query_plan()
    original = deepcopy(plan)
    sql = "SELECT id FROM schema_test.table_test"

    first = _run(sql, plan)
    second = _run(sql, plan)

    assert first["status"] == second["status"] == "approved"
    assert first["tables"] == second["tables"]
    assert build_sql_security_policy(plan) == build_sql_security_policy(plan)
    assert plan == original


def main() -> None:
    tests = [
        ("SELECT autorizada", test_select_autorizada_aprovada),
        ("WITH autorizada", test_with_autorizada_aprovada),
        ("tabela nao autorizada", test_tabela_nao_autorizada_rejeitada),
        ("schema nao autorizado", test_schema_nao_autorizado_rejeitado),
        ("comandos escrita", test_comandos_de_escrita_rejeitados),
        ("multiplos statements", test_multiplos_statements_rejeitados),
        ("SELECT INTO", test_select_into_rejeitado),
        ("palavra em string", test_palavra_proibida_em_string_aceita),
        ("palavra em comentario", test_palavra_proibida_em_comentario_nao_rejeita),
        ("objeto ambiguo", test_objeto_ambiguo_rejeitado),
        ("CTE nao externa", test_cte_nao_e_tabela_externa),
        ("sem SQL completa", test_resultado_nao_contem_sql_completa),
        ("determinismo", test_determinismo_e_ausencia_de_mutacao),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

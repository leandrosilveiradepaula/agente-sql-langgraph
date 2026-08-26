from __future__ import annotations

from copy import deepcopy

from app.domain.planner import build_query_plan
from app.domain.sql_generation import (
    SQL_GENERATION_CONTRACT_VERSION,
    SqlGenerationInputError,
    SqlGenerationValidationError,
    build_sql_generation_request,
    request_fingerprint,
    validate_sql_generation_response,
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


def _provider_result(output_text):
    return {
        "provider_name": "fake_sql_generator",
        "output_text": output_text,
        "duration_ms": 1,
    }


def test_constroi_requisicao_do_query_plan() -> None:
    request = build_sql_generation_request(_query_plan())

    assert request["contract_version"] == (
        SQL_GENERATION_CONTRACT_VERSION
    )
    context = request["generation_context"]
    assert context["context_version"] == "context-test-v1"
    assert context["intent_name"] == "generic_test_intent"
    assert context["authorized_tables"][0]["qualified_name"] == (
        "schema_test.table_test"
    )
    assert context["pattern_metadata"]["sql_pattern_metadata"] == (
        "SELECT 1"
    )


def test_requisicao_nao_contem_snapshot_catalogo_ou_credenciais() -> None:
    request = build_sql_generation_request(_query_plan())
    serialized = repr(request).casefold()

    assert "intent_catalog" not in serialized
    assert "signals" not in serialized
    assert "postgres_dsn" not in serialized
    assert "password" not in serialized
    assert "token" not in serialized
    assert "'context'" not in serialized
    assert "table_catalog" not in serialized
    assert "query_patterns" not in serialized


def test_requisicao_nao_contem_campos_esperados_de_benchmark() -> None:
    query_plan = _query_plan()
    query_plan["benchmark_id"] = "benchmark-1"
    query_plan["benchmark_mode"] = True
    query_plan["benchmark_target"] = "TEST"
    query_plan["tabelas_obrigatorias"] = ["forbidden_table"]
    query_plan["filtros_obrigatorios"] = ["forbidden_filter"]
    query_plan["deve_conter_sql"] = ["forbidden_must"]
    query_plan["nao_deve_conter_sql"] = ["forbidden_must_not"]
    query_plan["criterio_semantico"] = "forbidden_criterion"
    query_plan["expected_sql"] = "SELECT forbidden"
    query_plan["expected_answer"] = "forbidden_answer"
    query_plan["golden answer"] = "forbidden_golden"

    request = build_sql_generation_request(query_plan)
    serialized = repr(request).casefold()

    assert "benchmark-1" not in serialized
    assert "benchmark_mode" not in serialized
    assert "benchmark_target" not in serialized
    assert "tabelas_obrigatorias" not in serialized
    assert "filtros_obrigatorios" not in serialized
    assert "deve_conter_sql" not in serialized
    assert "nao_deve_conter_sql" not in serialized
    assert "criterio_semantico" not in serialized
    assert "expected_sql" not in serialized
    assert "expected_answer" not in serialized
    assert "golden" not in serialized
    assert "forbidden" not in serialized


def test_ordem_fingerprint_e_imutabilidade() -> None:
    query_plan = _query_plan()
    original = deepcopy(query_plan)

    first = build_sql_generation_request(query_plan)
    second = build_sql_generation_request(query_plan)

    assert first == second
    assert request_fingerprint(first) == request_fingerprint(second)
    assert query_plan == original


def test_rejeita_plano_invalido() -> None:
    try:
        build_sql_generation_request({})
    except SqlGenerationInputError as error:
        assert "planning_context" in str(error)
    else:
        raise AssertionError("Era esperado SqlGenerationInputError.")


def test_aceita_select_simples() -> None:
    sql = validate_sql_generation_response(
        _provider_result("SELECT id FROM schema_test.table_test")
    )

    assert sql == "SELECT id FROM schema_test.table_test"


def test_aceita_with_cte() -> None:
    sql = validate_sql_generation_response(
        _provider_result(
            "WITH generic_cte AS (SELECT id FROM schema_test.table_test) "
            "SELECT id FROM generic_cte"
        )
    )

    assert sql.startswith("WITH generic_cte")


def test_normaliza_ponto_e_virgula_final() -> None:
    sql = validate_sql_generation_response(
        _provider_result("SELECT id FROM schema_test.table_test;")
    )

    assert sql == "SELECT id FROM schema_test.table_test"


def _assert_validation_error(output_text, expected_code: str) -> None:
    try:
        validate_sql_generation_response(
            _provider_result(output_text)
        )
    except SqlGenerationValidationError as error:
        assert error.code == expected_code
    else:
        raise AssertionError(
            f"Era esperado {expected_code}."
        )


def test_rejeita_markdown() -> None:
    _assert_validation_error(
        "```sql\nSELECT id FROM schema_test.table_test\n```",
        "SQL_GENERATION_RESPONSE_INVALID",
    )


def test_rejeita_texto_explicativo() -> None:
    _assert_validation_error(
        "Aqui esta a SQL: SELECT id FROM schema_test.table_test",
        "SQL_GENERATION_RESPONSE_INVALID",
    )


def test_rejeita_resposta_vazia() -> None:
    _assert_validation_error(
        "   ",
        "SQL_GENERATION_RESPONSE_EMPTY",
    )


def test_rejeita_multiplas_instrucoes() -> None:
    _assert_validation_error(
        "SELECT id FROM schema_test.table_test; SELECT id FROM schema_test.table_test",
        "SQL_GENERATION_MULTIPLE_STATEMENTS",
    )


def test_rejeita_comandos_de_escrita_e_ddl() -> None:
    cases = [
        ("INSERT INTO schema_test.table_test VALUES (1)", "INSERT"),
        ("UPDATE schema_test.table_test SET id = 1", "UPDATE"),
        ("DELETE FROM schema_test.table_test", "DELETE"),
        ("DROP TABLE schema_test.table_test", "DROP"),
        ("CREATE TABLE schema_test.table_test (id int)", "CREATE"),
        ("COPY schema_test.table_test TO STDOUT", "COPY"),
    ]

    for sql, command in cases:
        try:
            validate_sql_generation_response(_provider_result(sql))
        except SqlGenerationValidationError as error:
            assert error.code == "SQL_GENERATION_NON_READ_ONLY"
        else:
            raise AssertionError(f"{command} deveria ser rejeitado.")


def test_palavra_perigosa_em_literal_nao_rejeita() -> None:
    sql = validate_sql_generation_response(
        _provider_result(
            "SELECT id FROM schema_test.table_test "
            "WHERE generic_text = 'DROP VALUE'"
        )
    )

    assert "DROP VALUE" in sql


def test_rejeita_apenas_ponto_e_virgula_comentario_e_controle() -> None:
    _assert_validation_error(";", "SQL_GENERATION_RESPONSE_EMPTY")
    _assert_validation_error("-- generic comment", "SQL_GENERATION_RESPONSE_INVALID")
    _assert_validation_error(
        "SELECT id FROM schema_test.table_test\x00",
        "SQL_GENERATION_RESPONSE_INVALID",
    )


def test_rejeita_resposta_nao_textual() -> None:
    try:
        validate_sql_generation_response(
            {
                "provider_name": "fake_sql_generator",
                "output_text": None,
            }
        )
    except SqlGenerationValidationError as error:
        assert error.code == "SQL_GENERATION_RESPONSE_INVALID"
    else:
        raise AssertionError("Era esperado erro estrutural.")


def test_comportamento_deterministico_repetido() -> None:
    query_plan = _query_plan()
    outputs = [
        build_sql_generation_request(query_plan)
        for _ in range(3)
    ]

    assert outputs[0] == outputs[1] == outputs[2]
    assert len({request_fingerprint(item) for item in outputs}) == 1


def main() -> None:
    tests = [
        ("constroi requisicao", test_constroi_requisicao_do_query_plan),
        (
            "sem snapshot catalogo ou credenciais",
            test_requisicao_nao_contem_snapshot_catalogo_ou_credenciais,
        ),
        (
            "sem campos esperados de benchmark",
            test_requisicao_nao_contem_campos_esperados_de_benchmark,
        ),
        (
            "ordem fingerprint e imutabilidade",
            test_ordem_fingerprint_e_imutabilidade,
        ),
        ("rejeita plano invalido", test_rejeita_plano_invalido),
        ("aceita SELECT", test_aceita_select_simples),
        ("aceita WITH", test_aceita_with_cte),
        (
            "normaliza ponto e virgula",
            test_normaliza_ponto_e_virgula_final,
        ),
        ("rejeita Markdown", test_rejeita_markdown),
        ("rejeita texto explicativo", test_rejeita_texto_explicativo),
        ("rejeita vazio", test_rejeita_resposta_vazia),
        (
            "rejeita multiplas instrucoes",
            test_rejeita_multiplas_instrucoes,
        ),
        (
            "rejeita comandos proibidos",
            test_rejeita_comandos_de_escrita_e_ddl,
        ),
        (
            "literal com palavra perigosa",
            test_palavra_perigosa_em_literal_nao_rejeita,
        ),
        (
            "rejeita pontuacao comentario e controle",
            test_rejeita_apenas_ponto_e_virgula_comentario_e_controle,
        ),
        ("rejeita nao textual", test_rejeita_resposta_nao_textual),
        (
            "deterministico repetido",
            test_comportamento_deterministico_repetido,
        ),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

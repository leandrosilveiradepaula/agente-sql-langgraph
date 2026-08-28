from __future__ import annotations

from copy import deepcopy

from app.domain.sql_analysis import (
    SqlAnalysisError,
    analysis_fingerprint,
    analyze_sql,
)


def test_select_simples() -> None:
    analysis = analyze_sql("SELECT id FROM schema_test.table_test")

    assert analysis["statement_type"] == "select"
    assert analysis["tables"] == ["schema_test.table_test"]
    assert analysis["column_references"][0]["column"] == "id"


def test_with_cte() -> None:
    analysis = analyze_sql(
        "WITH generic_cte AS ("
        "SELECT id FROM schema_test.table_test"
        ") SELECT id FROM generic_cte"
    )

    assert analysis["statement_type"] == "with"
    assert analysis["with_body_is_select"] is True
    assert analysis["ctes"] == ["generic_cte"]
    assert "schema_test.table_test" in analysis["tables"]
    assert any(item["is_cte"] for item in analysis["object_references"])


def test_subquery() -> None:
    analysis = analyze_sql(
        "SELECT id FROM ("
        "SELECT id FROM schema_test.table_test"
        ") AS generic_subquery"
    )

    assert analysis["tables"] == ["schema_test.table_test"]


def test_join() -> None:
    analysis = analyze_sql(
        "SELECT t.id FROM schema_test.table_test t "
        "JOIN schema_test.table_other o ON t.id = o.id"
    )

    assert "schema_test.table_test" in analysis["tables"]
    assert "schema_test.table_other" in analysis["tables"]
    assert len(analysis["joins"]) == 1


def test_union() -> None:
    analysis = analyze_sql(
        "SELECT id FROM schema_test.table_test "
        "UNION ALL SELECT id FROM schema_test.table_test"
    )

    assert analysis["statement_count"] == 1
    assert analysis["token_norms"].count("union") == 1


def test_aliases() -> None:
    analysis = analyze_sql(
        "SELECT t.id AS generic_alias FROM schema_test.table_test AS t "
        "ORDER BY generic_alias"
    )

    assert analysis["aliases"]["t"] == "schema_test.table_test"
    assert analysis["expression_aliases"] == ["generic_alias"]


def test_string_com_palavra_perigosa() -> None:
    analysis = analyze_sql(
        "SELECT id FROM schema_test.table_test "
        "WHERE value = 'DELETE value; still string'"
    )

    assert analysis["statement_count"] == 1
    assert "delete" not in [
        token["normalized"]
        for token in analysis["tokens"]
        if token["kind"] == "word"
    ]


def test_comentario_com_drop() -> None:
    analysis = analyze_sql(
        "SELECT id FROM schema_test.table_test -- DROP TABLE hidden"
    )

    assert analysis["has_comments"] is True
    assert "drop" not in analysis["token_norms"]


def test_identificador_entre_aspas() -> None:
    analysis = analyze_sql(
        'SELECT t."value" FROM schema_test.table_test t'
    )

    assert any(
        column["column"] == "value"
        for column in analysis["column_references"]
    )


def test_ponto_e_virgula_em_string() -> None:
    analysis = analyze_sql(
        "SELECT id FROM schema_test.table_test WHERE value = ';'"
    )

    assert analysis["statement_count"] == 1


def test_multiplos_statements_reais() -> None:
    try:
        analyze_sql(
            "SELECT id FROM schema_test.table_test; "
            "SELECT id FROM schema_test.table_test"
        )
    except SqlAnalysisError as error:
        assert error.code == "SQL_ANALYSIS_MULTIPLE_STATEMENTS"
    else:
        raise AssertionError("Era esperado erro de multiplos statements.")


def test_select_into() -> None:
    analysis = analyze_sql(
        "SELECT id INTO schema_test.table_copy "
        "FROM schema_test.table_test"
    )

    assert analysis["has_select_into"] is True


def test_cte_nao_confundida_com_tabela() -> None:
    analysis = analyze_sql(
        "WITH generic_cte AS ("
        "SELECT id FROM schema_test.table_test"
        ") SELECT id FROM generic_cte"
    )

    cte_refs = [
        item
        for item in analysis["object_references"]
        if item["table"] == "generic_cte"
    ]
    assert cte_refs[0]["is_cte"] is True


def test_schema_table_e_tabela_sem_schema() -> None:
    qualified = analyze_sql("SELECT id FROM schema_test.table_test")
    bare = analyze_sql("SELECT id FROM table_test")

    assert qualified["tables"] == ["schema_test.table_test"]
    assert bare["tables"] == ["table_test"]


def test_coluna_qualificada_e_nao_qualificada() -> None:
    analysis = analyze_sql(
        "SELECT t.id, value FROM schema_test.table_test t"
    )

    assert any(column["qualifier"] == "t" for column in analysis["column_references"])
    assert any(column["column"] == "value" for column in analysis["column_references"])


def test_group_order_having() -> None:
    analysis = analyze_sql(
        "SELECT value FROM schema_test.table_test "
        "GROUP BY value HAVING value > 0 ORDER BY value"
    )

    clauses = {column["clause"] for column in analysis["column_references"]}
    assert {"group", "having", "order"} <= clauses


def test_limit_e_funcoes() -> None:
    analysis = analyze_sql(
        "SELECT count(value) AS generic_count "
        "FROM schema_test.table_test LIMIT 10"
    )

    assert analysis["has_limit"] is True
    assert "count" in analysis["functions"]


def test_expressoes_temporais_nao_viram_colunas() -> None:
    analysis = analyze_sql(
        "SELECT DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month') AS mes "
        "FROM schema_test.table_test"
    )

    columns = {column["column"] for column in analysis["column_references"]}
    assert "current_date" not in columns
    assert "interval" not in columns
    assert "date_trunc" in analysis["functions"]


def test_cte_output_alias_qualificado_nao_vira_coluna_fisica() -> None:
    analysis = analyze_sql(
        "WITH realizado AS ("
        "SELECT t.id, SUM(t.value) AS realizado "
        "FROM schema_test.table_test t GROUP BY t.id"
        ") SELECT r.realizado FROM realizado r"
    )

    assert analysis["cte_output_columns"]["realizado"] == ["id", "realizado"]
    assert not any(
        column["qualifier"] == "r" and column["column"] == "realizado"
        for column in analysis["column_references"]
    )


def test_cte_alias_nao_sobrescreve_alias_fisico() -> None:
    analysis = analyze_sql(
        "WITH orcado AS ("
        "SELECT o.id, SUM(o.value) AS orcado "
        "FROM schema_test.table_test o GROUP BY o.id"
        ") SELECT o.orcado FROM orcado o"
    )

    assert analysis["aliases"]["o"] == "schema_test.table_test"
    assert not any(
        column["qualifier"] == "o" and column["column"] == "orcado"
        for column in analysis["column_references"]
    )


def test_caractere_de_controle() -> None:
    try:
        analyze_sql("SELECT id FROM schema_test.table_test\x00")
    except SqlAnalysisError as error:
        assert error.code == "SQL_ANALYSIS_CONTROL_CHARACTER"
    else:
        raise AssertionError("Era esperado erro de controle.")


def test_sql_malformada() -> None:
    try:
        analyze_sql("SELECT id FROM (SELECT id FROM schema_test.table_test")
    except SqlAnalysisError as error:
        assert error.code == "SQL_ANALYSIS_UNSUPPORTED_STRUCTURE"
    else:
        raise AssertionError("Era esperado erro estrutural.")


def test_determinismo_e_ausencia_de_mutacao() -> None:
    sql = "SELECT id FROM schema_test.table_test"
    original = deepcopy(sql)
    first = analyze_sql(sql)
    second = analyze_sql(sql)

    assert sql == original
    assert first == second
    assert analysis_fingerprint(first) == analysis_fingerprint(second)


def main() -> None:
    tests = [
        ("SELECT simples", test_select_simples),
        ("WITH CTE", test_with_cte),
        ("subquery", test_subquery),
        ("JOIN", test_join),
        ("UNION", test_union),
        ("aliases", test_aliases),
        ("string perigosa", test_string_com_palavra_perigosa),
        ("comentario com DROP", test_comentario_com_drop),
        ("identificador aspas", test_identificador_entre_aspas),
        ("ponto e virgula em string", test_ponto_e_virgula_em_string),
        ("multiplos statements", test_multiplos_statements_reais),
        ("SELECT INTO", test_select_into),
        ("CTE nao e tabela externa", test_cte_nao_confundida_com_tabela),
        ("schema e tabela sem schema", test_schema_table_e_tabela_sem_schema),
        ("colunas qualificadas", test_coluna_qualificada_e_nao_qualificada),
        ("GROUP ORDER HAVING", test_group_order_having),
        ("LIMIT e funcoes", test_limit_e_funcoes),
        ("expressoes temporais", test_expressoes_temporais_nao_viram_colunas),
        (
            "CTE output qualificado",
            test_cte_output_alias_qualificado_nao_vira_coluna_fisica,
        ),
        (
            "CTE alias preserva fisico",
            test_cte_alias_nao_sobrescreve_alias_fisico,
        ),
        ("controle", test_caractere_de_controle),
        ("SQL malformada", test_sql_malformada),
        ("determinismo", test_determinismo_e_ausencia_de_mutacao),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

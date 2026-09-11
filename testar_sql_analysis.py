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
    assert "month" not in columns
    assert "current_date" not in columns
    assert "interval" not in columns
    assert "date_trunc" in analysis["functions"]


def test_partes_temporais_nao_viram_colunas_fisicas() -> None:
    analysis = analyze_sql(
        "SELECT DATE_TRUNC('year', event_date), "
        "DATE_TRUNC(MONTH, event_date), "
        "event_date + INTERVAL 1 MONTH "
        "FROM schema_test.table_test"
    )

    columns = {column["column"] for column in analysis["column_references"]}
    assert {"month", "year", "interval"}.isdisjoint(columns)
    assert "event_date" in columns


def test_literal_de_funcao_generica_nao_vira_coluna() -> None:
    analysis = analyze_sql(
        "SELECT GENERIC_FUNC('literal_value', real_column) "
        "FROM schema_test.table_test"
    )

    columns = {column["column"] for column in analysis["column_references"]}
    assert "literal_value" not in columns
    assert "real_column" in columns


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


def test_nomes_arbitrarios_de_cte_nao_viram_colunas_fisicas() -> None:
    analysis = analyze_sql(
        "WITH cte_a AS ("
        "SELECT t.id, SUM(t.value) AS total_a "
        "FROM schema_test.table_test t GROUP BY t.id"
        "), cte_b AS ("
        "SELECT t.id, SUM(t.value) AS total_b "
        "FROM schema_test.table_test t GROUP BY t.id"
        "), totais AS ("
        "SELECT a.id, a.total_a, b.total_b "
        "FROM cte_a a JOIN cte_b b ON a.id = b.id"
        ") SELECT base_x.id, base_x.total_a "
        "FROM totais base_x ORDER BY base_x.total_a"
    )

    columns = {column["column"] for column in analysis["column_references"]}
    assert {"cte_a", "cte_b", "totais", "base_x"}.isdisjoint(columns)
    assert analysis["cte_output_columns"]["totais"] == [
        "id",
        "total_a",
        "total_b",
    ]


def test_modificadores_de_join_nao_viram_colunas_fisicas() -> None:
    analysis = analyze_sql(
        "WITH cte_a AS ("
        "SELECT t.id FROM schema_test.table_test t"
        "), cte_b AS ("
        "SELECT t.id FROM schema_test.table_test t"
        ") SELECT t.id, o.other_value "
        "FROM schema_test.table_test t "
        "CROSS JOIN cte_a ca "
        "INNER JOIN schema_test.table_other o ON o.id = t.id "
        "LEFT JOIN cte_b cb ON cb.id = t.id "
        "RIGHT JOIN schema_test.table_other r ON r.id = t.id "
        "FULL OUTER JOIN schema_test.table_other f ON f.id = t.id"
    )

    columns = {column["column"] for column in analysis["column_references"]}
    structural_tokens = {
        "cross",
        "inner",
        "left",
        "right",
        "full",
        "outer",
        "join",
        "on",
        "using",
        "lateral",
        "natural",
    }
    assert structural_tokens.isdisjoint(columns)
    assert {"id", "other_value"} <= columns


def _root_scope(analysis: dict) -> dict:
    roots = [
        scope
        for scope in analysis["query_scopes"]
        if scope["is_root"] is True
    ]
    assert len(roots) == 1
    return roots[0]


def test_root_order_resolve_alias_para_select_item_agregado() -> None:
    analysis = analyze_sql(
        "SELECT region, SUM(amount) AS total "
        "FROM schema_test.fact "
        "GROUP BY region "
        "ORDER BY total DESC"
    )

    root = _root_scope(analysis)

    assert root["scope_id"] == "root"
    assert root["select_items"][1]["alias"] == "total"
    assert root["select_items"][1]["functions"] == ["sum"]
    assert {
        column["column"]
        for column in root["select_items"][1]["column_references"]
    } == {"amount"}
    assert root["order_by_items"] == [
        {
            "expression": "total",
            "direction": "desc",
            "direction_explicit": True,
            "nulls": None,
            "referenced_alias": "total",
            "resolved_select_item_index": 1,
        }
    ]


def test_cte_order_by_isolado_do_root_order_by() -> None:
    analysis = analyze_sql(
        "WITH x AS ("
        "SELECT region, SUM(amount) AS total "
        "FROM schema_test.fact "
        "GROUP BY region "
        "ORDER BY total ASC"
        ") SELECT * FROM x ORDER BY total DESC"
    )

    scopes = {scope["scope_id"]: scope for scope in analysis["query_scopes"]}

    assert scopes["cte:x"]["order_by_items"][0]["direction"] == "asc"
    assert scopes["root"]["order_by_items"][0]["direction"] == "desc"
    assert scopes["root"]["order_by_items"][0]["expression"] == "total"


def test_subquery_order_by_isolado_e_alias_nao_vira_coluna_espuria() -> None:
    analysis = analyze_sql(
        "SELECT * FROM ("
        "SELECT region, SUM(amount) AS total "
        "FROM schema_test.fact "
        "GROUP BY region "
        "ORDER BY total ASC"
        ") s ORDER BY total DESC"
    )

    scopes = {scope["scope_id"]: scope for scope in analysis["query_scopes"]}
    columns = {column["column"] for column in analysis["column_references"]}

    assert scopes["subquery:1"]["order_by_items"][0]["direction"] == "asc"
    assert scopes["root"]["order_by_items"][0]["direction"] == "desc"
    assert "s" not in columns


def test_root_order_by_expressao_direta_sem_alias() -> None:
    analysis = analyze_sql(
        "SELECT region, amount FROM schema_test.fact ORDER BY amount DESC"
    )

    order_item = _root_scope(analysis)["order_by_items"][0]

    assert order_item["expression"] == "amount"
    assert order_item["direction"] == "desc"
    assert order_item["referenced_alias"] is None
    assert order_item["resolved_select_item_index"] is None


def test_root_order_by_multiplos_itens_e_default_asc() -> None:
    analysis = analyze_sql(
        "SELECT region, amount FROM schema_test.fact "
        "ORDER BY amount DESC, region"
    )

    order_items = _root_scope(analysis)["order_by_items"]

    assert order_items[0]["expression"] == "amount"
    assert order_items[0]["direction"] == "desc"
    assert order_items[0]["direction_explicit"] is True
    assert order_items[1]["expression"] == "region"
    assert order_items[1]["direction"] == "asc"
    assert order_items[1]["direction_explicit"] is False


def test_select_item_resolve_coluna_fisica_por_alias_do_scope() -> None:
    analysis = analyze_sql(
        "SELECT f.region, SUM(f.amount) AS total "
        "FROM schema_test.fact f "
        "ORDER BY total DESC"
    )

    total_item = _root_scope(analysis)["select_items"][1]
    columns = total_item["column_references"]

    assert columns == [
        {
            "raw": "f.amount",
            "qualifier": "f",
            "schema": "schema_test",
            "table": "fact",
            "column": "amount",
            "clause": "select",
            "is_wildcard": False,
        }
    ]


def test_select_item_nao_resolve_coluna_ambigua_silenciosamente() -> None:
    analysis = analyze_sql(
        "SELECT SUM(amount) AS total "
        "FROM schema_test.fact_a a "
        "JOIN schema_test.fact_b b ON b.id = a.id "
        "ORDER BY total DESC"
    )

    total_item = _root_scope(analysis)["select_items"][0]
    columns = total_item["column_references"]

    assert columns[0]["column"] == "amount"
    assert columns[0].get("schema") is None
    assert columns[0].get("table") is None


def test_order_by_nulls_last_preserva_direcao() -> None:
    analysis = analyze_sql(
        "SELECT amount AS total FROM schema_test.fact "
        "ORDER BY total DESC NULLS LAST"
    )

    order_item = _root_scope(analysis)["order_by_items"][0]

    assert order_item["expression"] == "total"
    assert order_item["direction"] == "desc"
    assert order_item["nulls"] == "last"


def test_order_by_nulls_first_preserva_direcao() -> None:
    analysis = analyze_sql(
        "SELECT amount AS total FROM schema_test.fact "
        "ORDER BY total ASC NULLS FIRST"
    )

    order_item = _root_scope(analysis)["order_by_items"][0]

    assert order_item["expression"] == "total"
    assert order_item["direction"] == "asc"
    assert order_item["nulls"] == "first"


def test_order_by_termina_antes_de_offset() -> None:
    analysis = analyze_sql(
        "SELECT amount AS total FROM schema_test.fact "
        "ORDER BY total DESC OFFSET 10"
    )

    order_item = _root_scope(analysis)["order_by_items"][0]

    assert order_item["expression"] == "total"
    assert order_item["direction"] == "desc"


def test_scope_metadata_select_simples_root() -> None:
    analysis = analyze_sql("SELECT id FROM schema_test.table_test")

    root = _root_scope(analysis)

    assert root["scope_type"] == "root"
    assert root["scope_name"] is None
    assert root["physical_tables"] == ["schema_test.table_test"]
    assert root["child_scopes"] == []
    assert root["group_by_items"] == []
    assert root["has_aggregate"] is False
    assert root["raw_table_join_count"] == 0
    assert root["aggregated_scope_join_count"] == 0


def test_cte_sem_agregacao_scope_metadata() -> None:
    analysis = analyze_sql(
        "WITH operand_a AS ("
        "SELECT dimension_x, metric_x FROM schema_test.fact_a"
        ") SELECT dimension_x, metric_x FROM operand_a"
    )

    scopes = {scope["scope_id"]: scope for scope in analysis["query_scopes"]}

    assert scopes["cte:operand_a"]["scope_type"] == "cte"
    assert scopes["cte:operand_a"]["scope_name"] == "operand_a"
    assert scopes["cte:operand_a"]["physical_tables"] == ["schema_test.fact_a"]
    assert scopes["cte:operand_a"]["has_aggregate"] is False
    assert scopes["cte:operand_a"]["has_reducing_aggregate"] is False
    assert scopes["root"]["child_scopes"] == ["cte:operand_a"]


def test_cte_com_agregacao_scope_metadata() -> None:
    analysis = analyze_sql(
        "WITH operand_a AS ("
        "SELECT dimension_x, SUM(metric_x) AS metric_a "
        "FROM schema_test.fact_a GROUP BY dimension_x"
        ") SELECT dimension_x, metric_a FROM operand_a"
    )

    cte_scope = {
        scope["scope_id"]: scope for scope in analysis["query_scopes"]
    }["cte:operand_a"]

    assert cte_scope["has_aggregate"] is True
    assert cte_scope["has_reducing_aggregate"] is True
    assert cte_scope["group_by_items"] == ["dimension_x"]
    assert cte_scope["select_items"][1]["alias"] == "metric_a"


def test_duas_ctes_agregadas_combinadas_no_root() -> None:
    analysis = analyze_sql(
        "WITH operand_a AS ("
        "SELECT dimension_x, SUM(metric_x) AS metric_a "
        "FROM schema_test.fact_a GROUP BY dimension_x"
        "), operand_b AS ("
        "SELECT dimension_x, SUM(metric_y) AS metric_b "
        "FROM schema_test.fact_b GROUP BY dimension_x"
        ") SELECT operand_a.dimension_x, operand_a.metric_a, operand_b.metric_b "
        "FROM operand_a JOIN operand_b "
        "ON operand_a.dimension_x = operand_b.dimension_x"
    )

    root = _root_scope(analysis)

    assert root["physical_tables"] == []
    assert root["child_scopes"] == ["cte:operand_a", "cte:operand_b"]
    assert root["raw_table_join_count"] == 0
    assert root["aggregated_scope_join_count"] == 1
    assert {
        (item["source_scope_id"], item["source_output"])
        for item in root["output_lineage"]
    } == {
        ("cte:operand_a", "dimension_x"),
        ("cte:operand_a", "metric_a"),
        ("cte:operand_b", "metric_b"),
    }


def test_join_direto_duas_tabelas_fisicas_no_mesmo_scope() -> None:
    analysis = analyze_sql(
        "SELECT a.dimension_x, b.metric_y "
        "FROM schema_test.fact_a a "
        "JOIN schema_test.fact_b b ON a.id = b.id"
    )

    root = _root_scope(analysis)

    assert root["physical_tables"] == [
        "schema_test.fact_a",
        "schema_test.fact_b",
    ]
    assert root["raw_table_join_count"] == 1
    assert root["aggregated_scope_join_count"] == 0


def test_root_select_lineage_para_output_de_cte() -> None:
    analysis = analyze_sql(
        "WITH operand_a AS ("
        "SELECT dimension_x, SUM(metric_x) AS metric_a "
        "FROM schema_test.fact_a GROUP BY dimension_x"
        ") SELECT operand_a.metric_a FROM operand_a"
    )

    root = _root_scope(analysis)

    assert root["output_lineage"] == [
        {
            "select_item_index": 0,
            "output_name": "metric_a",
            "source_scope_id": "cte:operand_a",
            "source_output": "metric_a",
        }
    ]


def test_subquery_agregada_scope_metadata() -> None:
    analysis = analyze_sql(
        "SELECT s.metric_a FROM ("
        "SELECT dimension_x, SUM(metric_x) AS metric_a "
        "FROM schema_test.fact_a GROUP BY dimension_x"
        ") s"
    )

    scopes = {scope["scope_id"]: scope for scope in analysis["query_scopes"]}

    assert scopes["root"]["has_aggregate"] is False
    assert scopes["root"]["has_reducing_aggregate"] is False
    assert scopes["root"]["physical_tables"] == []
    assert scopes["root"]["child_scopes"] == ["subquery:1"]
    assert scopes["subquery:1"]["scope_type"] == "subquery"
    assert scopes["subquery:1"]["has_aggregate"] is True
    assert scopes["subquery:1"]["has_reducing_aggregate"] is True
    assert scopes["subquery:1"]["group_by_items"] == ["dimension_x"]
    assert scopes["root"]["output_lineage"] == [
        {
            "select_item_index": 0,
            "output_name": "metric_a",
            "source_scope_id": "subquery:1",
            "source_output": "metric_a",
        }
    ]


def test_cte_referencia_cte_anterior_sem_virar_tabela_fisica() -> None:
    analysis = analyze_sql(
        "WITH operand_a AS ("
        "SELECT id FROM schema_test.fact_a"
        "), operand_b AS ("
        "SELECT id FROM operand_a"
        ") SELECT id FROM operand_b"
    )

    scopes = {scope["scope_id"]: scope for scope in analysis["query_scopes"]}

    assert scopes["cte:operand_b"]["physical_tables"] == []
    assert scopes["cte:operand_b"]["object_references"][0]["is_cte"] is True
    assert scopes["cte:operand_b"]["object_references"][0]["table"] == "operand_a"


def test_subquery_referencia_cte_sem_virar_tabela_fisica() -> None:
    analysis = analyze_sql(
        "WITH operand_a AS ("
        "SELECT id FROM schema_test.fact_a"
        ") SELECT s.id FROM (SELECT id FROM operand_a) s"
    )

    scopes = {scope["scope_id"]: scope for scope in analysis["query_scopes"]}

    assert scopes["subquery:1"]["physical_tables"] == []
    assert scopes["subquery:1"]["object_references"][0]["is_cte"] is True
    assert scopes["subquery:1"]["object_references"][0]["table"] == "operand_a"
    assert scopes["root"]["physical_tables"] == []


def test_sum_simples_eh_reducing_aggregate() -> None:
    analysis = analyze_sql("SELECT SUM(metric_x) AS total FROM schema_test.fact_a")

    root = _root_scope(analysis)

    assert root["has_aggregate"] is True
    assert root["has_reducing_aggregate"] is True


def test_group_by_sum_eh_reducing_aggregate() -> None:
    analysis = analyze_sql(
        "SELECT dimension_x, SUM(metric_x) AS total "
        "FROM schema_test.fact_a GROUP BY dimension_x"
    )

    root = _root_scope(analysis)

    assert root["has_reducing_aggregate"] is True
    assert root["group_by_items"] == ["dimension_x"]


def test_sum_over_nao_eh_reducing_aggregate() -> None:
    analysis = analyze_sql(
        "SELECT dimension_x, "
        "SUM(metric_x) OVER (PARTITION BY dimension_x) AS total "
        "FROM schema_test.fact_a"
    )

    root = _root_scope(analysis)

    assert root["has_aggregate"] is True
    assert root["has_reducing_aggregate"] is False


def test_sum_filter_over_nao_eh_reducing_aggregate() -> None:
    analysis = analyze_sql(
        "SELECT dimension_x, "
        "SUM(metric_x) FILTER (WHERE flag_x = 1) "
        "OVER (PARTITION BY dimension_x) AS total "
        "FROM schema_test.fact_a"
    )

    root = _root_scope(analysis)

    assert root["has_aggregate"] is True
    assert root["has_reducing_aggregate"] is False


def test_sum_filter_sem_over_eh_reducing_aggregate() -> None:
    analysis = analyze_sql(
        "SELECT SUM(metric_x) FILTER (WHERE flag_x = 1) AS total "
        "FROM schema_test.fact_a"
    )

    assert _root_scope(analysis)["has_reducing_aggregate"] is True


def test_coalesce_sum_eh_reducing_aggregate() -> None:
    analysis = analyze_sql(
        "SELECT COALESCE(SUM(metric_x), 0) AS total FROM schema_test.fact_a"
    )

    assert _root_scope(analysis)["has_reducing_aggregate"] is True


def test_sum_mais_max_eh_reducing_aggregate() -> None:
    analysis = analyze_sql(
        "SELECT SUM(metric_x) + MAX(metric_y) AS total FROM schema_test.fact_a"
    )

    assert _root_scope(analysis)["has_reducing_aggregate"] is True


def test_reducing_aggregate_mais_window_aggregate_eh_reducing() -> None:
    analysis = analyze_sql(
        "SELECT SUM(metric_x) + "
        "MAX(metric_y) OVER (PARTITION BY dimension_x) AS total "
        "FROM schema_test.fact_a"
    )

    assert _root_scope(analysis)["has_reducing_aggregate"] is True


def test_multiplas_window_aggregates_nao_sao_reducing() -> None:
    analysis = analyze_sql(
        "SELECT SUM(metric_x) OVER (PARTITION BY dimension_x) + "
        "MAX(metric_y) OVER (PARTITION BY dimension_x) AS total "
        "FROM schema_test.fact_a"
    )

    root = _root_scope(analysis)

    assert root["has_aggregate"] is True
    assert root["has_reducing_aggregate"] is False


def test_join_de_scopes_com_window_nao_conta_como_agregado_seguro() -> None:
    analysis = analyze_sql(
        "WITH operand_a AS ("
        "SELECT dimension_x, "
        "SUM(metric_x) OVER (PARTITION BY dimension_x) AS metric_a "
        "FROM schema_test.fact_a"
        "), operand_b AS ("
        "SELECT dimension_x, "
        "SUM(metric_y) OVER (PARTITION BY dimension_x) AS metric_b "
        "FROM schema_test.fact_b"
        ") SELECT operand_a.dimension_x, operand_a.metric_a, operand_b.metric_b "
        "FROM operand_a JOIN operand_b "
        "ON operand_a.dimension_x = operand_b.dimension_x"
    )

    scopes = {scope["scope_id"]: scope for scope in analysis["query_scopes"]}

    assert scopes["cte:operand_a"]["has_aggregate"] is True
    assert scopes["cte:operand_a"]["has_reducing_aggregate"] is False
    assert scopes["cte:operand_b"]["has_aggregate"] is True
    assert scopes["cte:operand_b"]["has_reducing_aggregate"] is False
    assert scopes["root"]["aggregated_scope_join_count"] == 0


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


def test_predicados_where_estruturados_preservam_literal() -> None:
    analysis = analyze_sql(
        "SELECT t.id FROM schema_test.table_test t "
        "WHERE t.value = 'Case Sensitive' AND t.id >= 10"
    )
    assert analysis["predicates"] == [
        {
            "clause": "where", "qualifier": "t", "column": "value",
            "operator": "=", "literal_type": "string", "value": "Case Sensitive",
            "supported": True, "reason": "simple_comparison",
        },
        {
            "clause": "where", "qualifier": "t", "column": "id",
            "operator": ">=", "literal_type": "number", "value": 10,
            "supported": True, "reason": "simple_comparison",
        },
    ]


def test_predicado_where_nao_suportado_e_explicito() -> None:
    predicate = analyze_sql(
        "SELECT id FROM schema_test.table_test WHERE value LIKE 'x%'"
    )["predicates"][0]
    assert predicate["supported"] is False
    assert predicate["reason"] == "operator_not_supported"


def main() -> None:
    tests = [
        ("predicados WHERE estruturados", test_predicados_where_estruturados_preservam_literal),
        ("predicado WHERE nao suportado", test_predicado_where_nao_suportado_e_explicito),
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
            "partes temporais",
            test_partes_temporais_nao_viram_colunas_fisicas,
        ),
        (
            "literal funcao generica",
            test_literal_de_funcao_generica_nao_vira_coluna,
        ),
        (
            "CTE output qualificado",
            test_cte_output_alias_qualificado_nao_vira_coluna_fisica,
        ),
        (
            "CTE alias preserva fisico",
            test_cte_alias_nao_sobrescreve_alias_fisico,
        ),
        (
            "CTE nomes arbitrarios",
            test_nomes_arbitrarios_de_cte_nao_viram_colunas_fisicas,
        ),
        (
            "JOIN modifiers nao coluna",
            test_modificadores_de_join_nao_viram_colunas_fisicas,
        ),
        (
            "root ORDER BY alias",
            test_root_order_resolve_alias_para_select_item_agregado,
        ),
        (
            "CTE ORDER BY isolado",
            test_cte_order_by_isolado_do_root_order_by,
        ),
        (
            "subquery ORDER BY isolado",
            test_subquery_order_by_isolado_e_alias_nao_vira_coluna_espuria,
        ),
        (
            "ORDER BY expressao direta",
            test_root_order_by_expressao_direta_sem_alias,
        ),
        (
            "ORDER BY multiplos itens",
            test_root_order_by_multiplos_itens_e_default_asc,
        ),
        (
            "select item coluna fisica por alias",
            test_select_item_resolve_coluna_fisica_por_alias_do_scope,
        ),
        (
            "select item coluna ambigua",
            test_select_item_nao_resolve_coluna_ambigua_silenciosamente,
        ),
        (
            "ORDER BY NULLS LAST",
            test_order_by_nulls_last_preserva_direcao,
        ),
        (
            "ORDER BY NULLS FIRST",
            test_order_by_nulls_first_preserva_direcao,
        ),
        (
            "ORDER BY termina antes OFFSET",
            test_order_by_termina_antes_de_offset,
        ),
        (
            "scope root metadata",
            test_scope_metadata_select_simples_root,
        ),
        (
            "CTE sem agregacao scope metadata",
            test_cte_sem_agregacao_scope_metadata,
        ),
        (
            "CTE com agregacao scope metadata",
            test_cte_com_agregacao_scope_metadata,
        ),
        (
            "duas CTEs agregadas no root",
            test_duas_ctes_agregadas_combinadas_no_root,
        ),
        (
            "join direto fisico no mesmo scope",
            test_join_direto_duas_tabelas_fisicas_no_mesmo_scope,
        ),
        (
            "lineage root para CTE",
            test_root_select_lineage_para_output_de_cte,
        ),
        (
            "subquery agregada scope metadata",
            test_subquery_agregada_scope_metadata,
        ),
        (
            "CTE referencia CTE anterior",
            test_cte_referencia_cte_anterior_sem_virar_tabela_fisica,
        ),
        (
            "subquery referencia CTE",
            test_subquery_referencia_cte_sem_virar_tabela_fisica,
        ),
        (
            "SUM simples reducing aggregate",
            test_sum_simples_eh_reducing_aggregate,
        ),
        (
            "GROUP BY SUM reducing aggregate",
            test_group_by_sum_eh_reducing_aggregate,
        ),
        (
            "SUM OVER nao reducing aggregate",
            test_sum_over_nao_eh_reducing_aggregate,
        ),
        (
            "SUM FILTER OVER nao reducing aggregate",
            test_sum_filter_over_nao_eh_reducing_aggregate,
        ),
        (
            "SUM FILTER sem OVER reducing aggregate",
            test_sum_filter_sem_over_eh_reducing_aggregate,
        ),
        (
            "COALESCE SUM reducing aggregate",
            test_coalesce_sum_eh_reducing_aggregate,
        ),
        (
            "SUM mais MAX reducing aggregate",
            test_sum_mais_max_eh_reducing_aggregate,
        ),
        (
            "reducing aggregate mais window aggregate",
            test_reducing_aggregate_mais_window_aggregate_eh_reducing,
        ),
        (
            "multiplas window aggregates nao reducing",
            test_multiplas_window_aggregates_nao_sao_reducing,
        ),
        (
            "window scopes nao contam aggregate-before-combine",
            test_join_de_scopes_com_window_nao_conta_como_agregado_seguro,
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

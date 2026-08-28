from __future__ import annotations

from copy import deepcopy

from app.domain.planner import build_query_plan
from app.domain.sql_contract import (
    build_sql_contract_policy,
    run_sql_contract_gate,
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


def _with_rule(rule_content: dict) -> dict:
    plan = deepcopy(_query_plan())
    plan["planning_context"]["rules"][0]["rule_content"] = rule_content
    return plan


def _with_second_table(*, authorized_join: bool = True) -> dict:
    plan = deepcopy(_query_plan())
    projection = plan["planning_context"]
    projection["required_tables"].append(
        {
            "schema_name": "schema_test",
            "table_name": "table_other",
            "qualified_name": "schema_test.table_other",
            "primary_key": ["id"],
            "key_columns": ["id"],
            "metric_columns": ["other_value"],
            "date_columns": ["event_date"],
            "join_rules": [],
            "columns": [
                {"name": "id"},
                {"name": "other_value"},
                {"name": "event_date"},
            ],
        }
    )
    projection["relevant_columns"]["schema_test.table_other"] = [
        {"name": "id"},
        {"name": "other_value"},
        {"name": "event_date"},
    ]
    if authorized_join:
        projection["authorized_joins"] = [
            {
                "source_table": "schema_test.table_test",
                "join_rules": [
                    {"target_table": "schema_test.table_other"}
                ],
                "interpretation": "preserved_selected_table_rules",
            }
        ]
    else:
        projection["authorized_joins"] = []
    return plan


def _with_opaque_join() -> dict:
    plan = _with_second_table(authorized_join=False)
    plan["planning_context"]["authorized_joins"] = [
        {
            "source_table": "schema_test.table_test",
            "join_rules": {"opaque": True},
            "interpretation": "preserved_uninterpreted",
        }
    ]
    return plan


def _run(sql: str, plan: dict | None = None):
    return run_sql_contract_gate(
        current_sql=sql,
        query_plan=plan or _query_plan(),
    )[0]


def _unidade_negocio_plan() -> dict:
    plan = deepcopy(_query_plan())
    projection = plan["planning_context"]
    table = {
        "schema_name": "main_gold",
        "table_name": "gold_unidade_negocio",
        "qualified_name": "main_gold.gold_unidade_negocio",
        "primary_key": ["sk"],
        "key_columns": ["sk", "nk_unide_neg"],
        "metric_columns": [],
        "date_columns": [],
        "join_rules": [],
        "columns": [
            {"name": "sk"},
            {"name": "nk_unide_neg"},
            {"name": "marca"},
        ],
    }
    projection["required_tables"] = [table]
    projection["relevant_columns"] = {
        "main_gold.gold_unidade_negocio": [
            {"name": "sk"},
            {"name": "nk_unide_neg"},
            {"name": "marca"},
        ]
    }
    projection["authorized_joins"] = []
    return plan


def test_contrato_valido_aprovado() -> None:
    result = _run("SELECT id, value FROM schema_test.table_test")

    assert result["status"] == "approved"
    assert result["required_tables"][0]["status"] == "satisfied"


def test_required_table_ausente() -> None:
    result = _run(
        "SELECT id FROM schema_test.table_test",
        _with_second_table(),
    )

    assert result["status"] == "rejected"
    assert any(
        error["code"] == "SQL_CONTRACT_REQUIRED_TABLE_MISSING"
        for error in result["errors"]
    )


def test_tabela_adicional() -> None:
    result = _run("SELECT id FROM schema_test.table_other")

    assert result["status"] == "rejected"
    assert any(
        error["code"] == "SQL_CONTRACT_UNPLANNED_TABLE"
        for error in result["errors"]
    )


def test_coluna_inexistente() -> None:
    result = _run("SELECT missing_column FROM schema_test.table_test")

    assert result["status"] == "rejected"
    assert result["errors"][0]["code"] == "SQL_CONTRACT_UNKNOWN_COLUMN"


def test_alias_invalido() -> None:
    result = _run("SELECT x.id FROM schema_test.table_test t")

    assert result["status"] == "rejected"
    assert result["errors"][0]["code"] == "SQL_CONTRACT_INVALID_ALIAS"


def test_alias_de_expressao_no_where_rejeitado() -> None:
    result = _run(
        "SELECT value AS generic_alias FROM schema_test.table_test "
        "WHERE generic_alias = 1"
    )

    assert result["status"] == "rejected"
    assert result["errors"][0]["code"] == "SQL_CONTRACT_UNKNOWN_COLUMN"


def test_coluna_nao_qualificada_ambigua() -> None:
    result = _run(
        "SELECT id FROM schema_test.table_test t "
        "JOIN schema_test.table_other o ON t.id = o.id",
        _with_second_table(),
    )

    assert result["status"] == "rejected"
    assert any(
        error["code"] == "SQL_CONTRACT_AMBIGUOUS_COLUMN"
        for error in result["errors"]
    )


def test_required_rule_estruturada_satisfeita() -> None:
    result = _run(
        "SELECT id FROM schema_test.table_test WHERE value = 1",
        _with_rule({"required_filters": ["where value ="]}),
    )

    assert result["status"] == "approved"
    assert result["rules"][0]["status"] == "satisfied"


def test_required_rule_estruturada_ausente() -> None:
    result = _run(
        "SELECT id FROM schema_test.table_test",
        _with_rule({"required_filters": ["where value ="]}),
    )

    assert result["status"] == "rejected"
    assert result["errors"][0]["code"] == "SQL_CONTRACT_RULE_VIOLATED"


def test_forbidden_fragment_presente() -> None:
    result = _run(
        "SELECT id FROM schema_test.table_test WHERE value = 1",
        _with_rule({"forbidden_sql_fragments": ["where value ="]}),
    )

    assert result["status"] == "rejected"


def test_required_filter_presente_e_ausente() -> None:
    present = _run(
        "SELECT id FROM schema_test.table_test WHERE value = 1",
        _with_rule({"required_filters": ["where value ="]}),
    )
    missing = _run(
        "SELECT id FROM schema_test.table_test",
        _with_rule({"required_filters": ["where value ="]}),
    )

    assert present["status"] == "approved"
    assert missing["status"] == "rejected"


def test_forbidden_filter_com_literal_rejeita() -> None:
    result = _run(
        "SELECT id FROM schema_test.table_test WHERE value = 'cancelled'",
        _with_rule({"forbidden_filters": ["value = 'cancelled'"]}),
    )

    assert result["status"] == "rejected"
    assert result["errors"][0]["code"] == "SQL_CONTRACT_RULE_VIOLATED"
    assert "cancelled" not in str(result)


def test_limit_proibido_permitido_e_exigido() -> None:
    forbidden = _run(
        "SELECT id FROM schema_test.table_test LIMIT 10",
        _with_rule({"limit_policy": "forbid"}),
    )
    allowed = _run(
        "SELECT id FROM schema_test.table_test LIMIT 10",
        _with_rule({"limit_policy": "allow"}),
    )
    required = _run(
        "SELECT id FROM schema_test.table_test",
        _with_rule({"limit_policy": "require"}),
    )

    assert forbidden["status"] == "rejected"
    assert allowed["status"] == "approved"
    assert required["status"] == "rejected"


def test_join_autorizado() -> None:
    result = _run(
        "SELECT t.value, o.other_value "
        "FROM schema_test.table_test t "
        "JOIN schema_test.table_other o ON t.id = o.id",
        _with_second_table(),
    )

    assert result["status"] == "approved"
    assert result["joins"][0]["status"] == "satisfied"


def test_join_divergente() -> None:
    result = _run(
        "SELECT t.value, o.other_value "
        "FROM schema_test.table_test t "
        "JOIN schema_test.table_other o ON t.id = o.id",
        _with_second_table(authorized_join=False),
    )

    assert result["status"] == "rejected"
    assert result["errors"][0]["code"] == "SQL_CONTRACT_JOIN_VIOLATED"


def test_join_opaco_unverifiable() -> None:
    result = _run(
        "SELECT t.value, o.other_value "
        "FROM schema_test.table_test t "
        "JOIN schema_test.table_other o ON t.id = o.id",
        _with_opaque_join(),
    )

    assert result["status"] == "approved"
    assert result["joins"][0]["status"] == "unverifiable"


def test_regra_opaca_unverifiable() -> None:
    result = _run("SELECT id FROM schema_test.table_test")

    assert result["status"] == "approved"
    assert result["unverifiable_rules"]


def test_select_star_politica_padrao_e_rejeicao() -> None:
    default = _run("SELECT * FROM schema_test.table_test")
    rejected = _run(
        "SELECT * FROM schema_test.table_test",
        _with_rule({"select_star_policy": "reject"}),
    )

    assert default["status"] == "approved"
    assert default["warnings"]
    assert rejected["status"] == "rejected"


def test_table_star_politica_padrao() -> None:
    result = _run("SELECT t.* FROM schema_test.table_test t")

    assert result["status"] == "approved"
    assert result["warnings"]


def test_cte_e_subquery_validas() -> None:
    cte = _run(
        "WITH generic_cte AS ("
        "SELECT id FROM schema_test.table_test"
        ") SELECT id FROM generic_cte"
    )
    subquery = _run(
        "SELECT id FROM ("
        "SELECT id FROM schema_test.table_test"
        ") AS generic_subquery"
    )

    assert cte["status"] == "approved"
    assert subquery["status"] == "approved"


def test_expressoes_sql_nao_coluna_aprovadas() -> None:
    result = _run(
        "SELECT DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month') AS mes "
        "FROM schema_test.table_test"
    )

    assert result["status"] == "approved"


def test_cte_output_alias_qualificado_aprovado() -> None:
    result = _run(
        "WITH realizado AS ("
        "SELECT t.id, SUM(t.value) AS realizado "
        "FROM schema_test.table_test t GROUP BY t.id"
        ") SELECT r.realizado FROM realizado r"
    )

    assert result["status"] == "approved"


def test_cte_output_com_alias_colidido_nao_vira_coluna_fisica() -> None:
    result = _run(
        "WITH table_test AS ("
        "SELECT t.id, SUM(t.value) AS realizado "
        "FROM schema_test.table_test t GROUP BY t.id"
        ") SELECT t.realizado FROM table_test t"
    )

    assert result["status"] == "approved"


def test_alias_fisico_continua_validado_contra_tabela_correta() -> None:
    result = _run("SELECT t.missing_column FROM schema_test.table_test t")

    assert result["status"] == "rejected"
    assert result["errors"][0]["code"] == "SQL_CONTRACT_UNKNOWN_COLUMN"


def test_cte_output_desconhecido_continua_rejeitado() -> None:
    result = _run(
        "WITH realizado AS ("
        "SELECT t.id, SUM(t.value) AS realizado "
        "FROM schema_test.table_test t GROUP BY t.id"
        ") SELECT r.missing_column FROM realizado r"
    )

    assert result["status"] == "rejected"
    assert result["errors"][0]["code"] == "SQL_CONTRACT_INVALID_ALIAS"


def test_nomes_de_cte_nao_viram_unknown_columns_mas_coluna_real_invalida_sim() -> None:
    result = _run(
        "WITH cte_a AS ("
        "SELECT t.id, SUM(t.value) AS total_a "
        "FROM schema_test.table_test t GROUP BY t.id"
        "), cte_b AS ("
        "SELECT t.id, SUM(t.value) AS total_b "
        "FROM schema_test.table_test t GROUP BY t.id"
        "), totais AS ("
        "SELECT a.id, a.total_a, b.total_b "
        "FROM cte_a a JOIN cte_b b ON a.id = b.id"
        ") SELECT base_x.id, base_x.missing_column "
        "FROM totais base_x ORDER BY base_x.total_a"
    )

    violated = [
        column["column"]
        for column in result["columns"]
        if column["status"] == "violated"
    ]
    assert result["status"] == "rejected"
    assert "missing_column" in violated
    assert not {"cte_a", "cte_b", "totais", "base_x"} & set(violated)


def test_unidade_negocio_valida_sk_e_nk_unide_neg_sem_replace_global() -> None:
    plan = _unidade_negocio_plan()
    valid = _run(
        "SELECT un.sk, un.nk_unide_neg "
        "FROM main_gold.gold_unidade_negocio un",
        plan,
    )
    invalid = _run(
        "SELECT un.sk_unid_neg "
        "FROM main_gold.gold_unidade_negocio un",
        plan,
    )

    assert valid["status"] == "approved"
    assert invalid["status"] == "rejected"
    assert invalid["errors"][0]["code"] == "SQL_CONTRACT_UNKNOWN_COLUMN"
    assert invalid["columns"][0]["table"] == "main_gold.gold_unidade_negocio"
    assert invalid["columns"][0]["column"] == "sk_unid_neg"


def test_diagnostico_determinismo_e_sem_mutacao() -> None:
    plan = _query_plan()
    original = deepcopy(plan)
    sql = "SELECT id FROM schema_test.table_test"

    first = _run(sql, plan)
    second = _run(sql, plan)

    assert first["status"] == second["status"] == "approved"
    assert first["sql_fingerprint"] == second["sql_fingerprint"]
    assert build_sql_contract_policy(plan) == build_sql_contract_policy(plan)
    assert plan == original
    assert sql not in repr(first)


def main() -> None:
    tests = [
        ("contrato valido", test_contrato_valido_aprovado),
        ("required_table ausente", test_required_table_ausente),
        ("tabela adicional", test_tabela_adicional),
        ("coluna inexistente", test_coluna_inexistente),
        ("alias invalido", test_alias_invalido),
        ("alias expressao where", test_alias_de_expressao_no_where_rejeitado),
        ("coluna ambigua", test_coluna_nao_qualificada_ambigua),
        ("regra satisfeita", test_required_rule_estruturada_satisfeita),
        ("regra ausente", test_required_rule_estruturada_ausente),
        ("fragmento proibido", test_forbidden_fragment_presente),
        ("filtro presente ausente", test_required_filter_presente_e_ausente),
        ("filtro proibido literal", test_forbidden_filter_com_literal_rejeita),
        ("LIMIT politicas", test_limit_proibido_permitido_e_exigido),
        ("join autorizado", test_join_autorizado),
        ("join divergente", test_join_divergente),
        ("join opaco", test_join_opaco_unverifiable),
        ("regra opaca", test_regra_opaca_unverifiable),
        ("SELECT star", test_select_star_politica_padrao_e_rejeicao),
        ("table star", test_table_star_politica_padrao),
        ("CTE subquery", test_cte_e_subquery_validas),
        ("expressoes SQL nao coluna", test_expressoes_sql_nao_coluna_aprovadas),
        ("CTE output qualificado", test_cte_output_alias_qualificado_aprovado),
        (
            "CTE alias colidido",
            test_cte_output_com_alias_colidido_nao_vira_coluna_fisica,
        ),
        (
            "alias fisico validado",
            test_alias_fisico_continua_validado_contra_tabela_correta,
        ),
        (
            "CTE output desconhecido",
            test_cte_output_desconhecido_continua_rejeitado,
        ),
        (
            "CTE relation nao unknown",
            test_nomes_de_cte_nao_viram_unknown_columns_mas_coluna_real_invalida_sim,
        ),
        (
            "unidade negocio chaves",
            test_unidade_negocio_valida_sk_e_nk_unide_neg_sem_replace_global,
        ),
        ("diagnostico determinismo", test_diagnostico_determinismo_e_sem_mutacao),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

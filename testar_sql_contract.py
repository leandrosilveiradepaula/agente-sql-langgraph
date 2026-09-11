from __future__ import annotations

from copy import deepcopy

import app.domain.sql_contract as sql_contract
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


def _dimension_test_plan() -> dict:
    plan = deepcopy(_query_plan())
    projection = plan["planning_context"]
    table = {
        "schema_name": "schema_test",
        "table_name": "dimension_test",
        "qualified_name": "schema_test.dimension_test",
        "primary_key": ["pk_id"],
        "key_columns": ["pk_id", "business_key"],
        "metric_columns": ["amount", "other_amount"],
        "date_columns": [],
        "join_rules": [],
        "columns": [
            {"name": "pk_id"},
            {"name": "business_key"},
            {"name": "label"},
            {"name": "amount"},
            {"name": "other_amount"},
        ],
    }
    projection["required_tables"] = [table]
    projection["relevant_columns"] = {
        "schema_test.dimension_test": [
            {"name": "pk_id"},
            {"name": "business_key"},
            {"name": "label"},
            {"name": "amount"},
            {"name": "other_amount"},
        ]
    }
    projection["authorized_joins"] = []
    return plan


def _with_grouping_dimension() -> dict:
    plan = _dimension_test_plan()
    plan["planning_context"]["detected_dimensions"] = [
        {
            "canonical_value": "dimension_test",
            "target_table": "schema_test.dimension_test",
            "target_column": "business_key",
            "grouping_requested": True,
            "source": "entity_alias",
        }
    ]
    return plan


def _with_ranking_operation(
    *,
    direction: str = "descending",
    requested_limit=None,
    metric_ref: str = "metric-synthetic",
    metric_table: str = "schema_test.dimension_test",
    metric_column: str = "amount",
    duplicate_metric: bool = False,
) -> dict:
    plan = _with_grouping_dimension()
    plan["planning_context"]["analytical_operations"] = [
        {
            "operation_type": "ranking",
            "canonical_value": "ranking",
            "direction": direction,
            "requested_limit": requested_limit,
            "metric_ref": metric_ref,
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "entity_alias",
        }
    ]
    metric = {
        "metric_ref": "metric-synthetic",
        "metric_concept": "synthetic_metric",
        "target_table": metric_table,
        "target_column": metric_column,
        "aggregate": None,
        "detection_source": "intent_semantic_evidence",
        "mapping_source": "entity_alias",
    }
    plan["planning_context"]["planned_metrics"] = [metric]
    if duplicate_metric:
        plan["planning_context"]["planned_metrics"].append(deepcopy(metric))
    return plan


def _with_metric_binding_plan() -> dict:
    plan = _dimension_test_plan()
    plan["planning_context"]["planned_metrics"] = [
        {
            "metric_ref": "metric-synthetic",
            "metric_concept": "synthetic_metric",
            "target_table": "schema_test.dimension_test",
            "target_column": "amount",
            "aggregate": None,
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "metric_binding",
            "binding_ref": "binding-synthetic",
            "binding_conditions": {
                "when_present": ["mode_a"],
                "when_absent": [],
            },
            "binding_source": "entity_alias",
        }
    ]
    return plan


def _comparison_plan(
    *,
    grouped: bool = False,
    join_semantics: str = "",
    operand_refs: list[str] | None = None,
    cardinality: dict | None = None,
) -> dict:
    plan = deepcopy(_query_plan())
    projection = plan["planning_context"]
    tables = [
        {
            "schema_name": "schema_test",
            "table_name": "fact_left",
            "qualified_name": "schema_test.fact_left",
            "primary_key": ["id"],
            "key_columns": ["id", "group_id"],
            "metric_columns": ["amount_left"],
            "date_columns": [],
            "join_rules": [],
            "columns": [
                {"name": "id"},
                {"name": "group_id"},
                {"name": "amount_left"},
            ],
        },
        {
            "schema_name": "schema_test",
            "table_name": "fact_right",
            "qualified_name": "schema_test.fact_right",
            "primary_key": ["id"],
            "key_columns": ["id", "group_id"],
            "metric_columns": ["amount_right"],
            "date_columns": [],
            "join_rules": [],
            "columns": [
                {"name": "id"},
                {"name": "group_id"},
                {"name": "amount_right"},
            ],
        },
    ]
    if grouped:
        tables.append(
            {
                "schema_name": "schema_test",
                "table_name": "dim_group",
                "qualified_name": "schema_test.dim_group",
                "primary_key": ["group_id"],
                "key_columns": ["group_id", "group_key"],
                "metric_columns": [],
                "date_columns": [],
                "join_rules": [],
                "columns": [
                    {"name": "group_id"},
                    {"name": "group_key"},
                ],
            }
        )
    projection["required_tables"] = tables
    projection["relevant_columns"] = {
        table["qualified_name"]: table["columns"] for table in tables
    }
    projection["authorized_joins"] = []
    if grouped:
        projection["authorized_joins"] = [
            {
                "source_table": "schema_test.fact_left",
                "join_rules": {"opaque": True},
                "interpretation": "preserved_uninterpreted",
            }
        ]
        projection["detected_dimensions"] = [
            {
                "canonical_value": "group",
                "target_table": "schema_test.dim_group",
                "target_column": "group_key",
                "grouping_requested": True,
                "source": "entity_alias",
            }
        ]
    projection["planned_metrics"] = [
        {
            "metric_ref": "metric-left",
            "metric_concept": "synthetic_amount",
            "target_table": "schema_test.fact_left",
            "target_column": "amount_left",
            "aggregate": None,
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "metric_binding",
            "binding_ref": "binding-left",
        },
        {
            "metric_ref": "metric-right",
            "metric_concept": "synthetic_amount",
            "target_table": "schema_test.fact_right",
            "target_column": "amount_right",
            "aggregate": None,
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "metric_binding",
            "binding_ref": "binding-right",
        },
    ]
    operation = {
        "operation_type": "comparison",
        "canonical_value": "comparison",
        "output_behavior": "side_by_side",
        "combination_strategy": "aggregate_then_combine",
        "operand_metric_refs": operand_refs or ["metric-left", "metric-right"],
        "multiple_metric_sources": True,
        "binding_cardinality": cardinality
        or {
            "mode": "multiple",
            "minimum": 2,
            "maximum": 2,
            "same_metric_concept": True,
            "distinct_bindings": True,
        },
        "detection_source": "intent_semantic_evidence",
        "mapping_source": "entity_alias",
    }
    if join_semantics:
        operation["join_semantics"] = join_semantics
    projection["analytical_operations"] = [operation]
    return plan


def _same_source_comparison_plan(*, multiple_metric_sources=True) -> dict:
    plan = deepcopy(_query_plan())
    projection = plan["planning_context"]
    table = {
        "schema_name": "schema_test",
        "table_name": "fact_same",
        "qualified_name": "schema_test.fact_same",
        "primary_key": ["id"],
        "key_columns": ["id"],
        "metric_columns": ["metric_a", "metric_b"],
        "date_columns": [],
        "join_rules": [],
        "columns": [
            {"name": "id"},
            {"name": "metric_a"},
            {"name": "metric_b"},
        ],
    }
    projection["required_tables"] = [table]
    projection["relevant_columns"] = {
        "schema_test.fact_same": table["columns"]
    }
    projection["authorized_joins"] = []
    projection["detected_dimensions"] = []
    projection["planned_metrics"] = [
        {
            "metric_ref": "metric-a",
            "metric_concept": "synthetic_amount",
            "target_table": "schema_test.fact_same",
            "target_column": "metric_a",
            "aggregate": None,
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "metric_binding",
            "binding_ref": "binding-a",
        },
        {
            "metric_ref": "metric-b",
            "metric_concept": "synthetic_amount",
            "target_table": "schema_test.fact_same",
            "target_column": "metric_b",
            "aggregate": None,
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "metric_binding",
            "binding_ref": "binding-b",
        },
    ]
    projection["analytical_operations"] = [
        {
            "operation_type": "comparison",
            "canonical_value": "comparison",
            "output_behavior": "side_by_side",
            "combination_strategy": "aggregate_then_combine",
            "operand_metric_refs": ["metric-a", "metric-b"],
            "multiple_metric_sources": multiple_metric_sources,
            "binding_cardinality": {
                "mode": "multiple",
                "minimum": 2,
                "maximum": 2,
                "same_metric_concept": True,
                "distinct_bindings": True,
            },
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "entity_alias",
        }
    ]
    return plan


def _comparison_sql(
    *,
    grouped: bool = False,
    root_join: str = "CROSS JOIN",
    raw_join: bool = False,
    right_aggregate: str = "SUM",
    right_projects: bool = True,
    right_group: bool = True,
    left_window: bool = False,
) -> str:
    if raw_join:
        return (
            "SELECT SUM(l.amount_left) AS left_total, "
            "SUM(r.amount_right) AS right_total "
            "FROM schema_test.fact_left l "
            "JOIN schema_test.fact_right r ON r.id = l.id"
        )
    if not grouped:
        left_expr = (
            "SUM(l.amount_left) OVER () AS left_total"
            if left_window
            else "SUM(l.amount_left) AS left_total"
        )
        right_expr = (
            f"{right_aggregate}(r.amount_right) AS right_total"
            if right_projects
            else "COUNT(*) AS row_count"
        )
        return (
            f"WITH left_operand AS (SELECT {left_expr} "
            "FROM schema_test.fact_left l), "
            f"right_operand AS (SELECT {right_expr} "
            "FROM schema_test.fact_right r) "
            "SELECT left_operand.left_total, right_operand.right_total "
            "FROM left_operand "
            f"{root_join} right_operand"
        )
    right_expr = (
        f"{right_aggregate}(r.amount_right) AS right_total"
        if right_projects
        else "COUNT(*) AS row_count"
    )
    right_group_by = "GROUP BY d.group_key" if right_group else ""
    return (
        "WITH left_operand AS ("
        "SELECT d.group_key, SUM(l.amount_left) AS left_total "
        "FROM schema_test.fact_left l "
        "JOIN schema_test.dim_group d ON d.group_id = l.group_id "
        "GROUP BY d.group_key"
        "), right_operand AS ("
        f"SELECT d.group_key, {right_expr} "
        "FROM schema_test.fact_right r "
        "JOIN schema_test.dim_group d ON d.group_id = r.group_id "
        f"{right_group_by}"
        ") "
        "SELECT COALESCE(left_operand.group_key, right_operand.group_key) "
        "AS group_key, left_operand.left_total, right_operand.right_total "
        "FROM left_operand "
        f"{root_join} right_operand "
        "ON left_operand.group_key = right_operand.group_key"
    )


def _same_source_comparison_sql(
    *,
    raw_operand: bool = False,
    window_operand: bool = False,
    both_window: bool = False,
) -> str:
    first = (
        "SUM(metric_a) OVER () AS operand_a"
        if both_window
        else "SUM(metric_a) AS operand_a"
    )
    if both_window or window_operand:
        second = "SUM(metric_b) OVER () AS operand_b"
    elif raw_operand:
        second = "metric_b AS operand_b"
    else:
        second = "SUM(metric_b) AS operand_b"
    return (
        f"SELECT {first}, "
        f"{second} "
        "FROM schema_test.fact_same"
    )


def _comparison_reason(result: dict) -> str:
    for error in result["errors"]:
        reason = error["details"].get("reason")
        if isinstance(reason, str) and reason.startswith("comparison_"):
            return reason
    return ""


def _with_cross_schema_grouping_dimension() -> dict:
    plan = deepcopy(_query_plan())
    projection = plan["planning_context"]
    tables = []
    relevant_columns = {}
    for schema_name in ("schema_a", "schema_b"):
        qualified_name = f"{schema_name}.dimension_test"
        table = {
            "schema_name": schema_name,
            "table_name": "dimension_test",
            "qualified_name": qualified_name,
            "primary_key": ["pk_id"],
            "key_columns": ["pk_id", "business_key"],
            "metric_columns": [],
            "date_columns": [],
            "join_rules": [],
            "columns": [
                {"name": "pk_id"},
                {"name": "business_key"},
            ],
        }
        tables.append(table)
        relevant_columns[qualified_name] = [
            {"name": "pk_id"},
            {"name": "business_key"},
        ]
    projection["required_tables"] = tables
    projection["relevant_columns"] = relevant_columns
    projection["allowed_schemas"] = ["schema_a", "schema_b"]
    projection["authorized_joins"] = [
        {
            "source_table": "schema_a.dimension_test",
            "join_rules": [
                {"target_table": "schema_b.dimension_test"}
            ],
            "interpretation": "synthetic_cross_schema_join",
        }
    ]
    projection["detected_dimensions"] = [
        {
            "canonical_value": "dimension_test",
            "target_table": "schema_a.dimension_test",
            "target_column": "business_key",
            "grouping_requested": True,
            "source": "entity_alias",
        }
    ]
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


def test_literais_de_funcoes_e_intervalos_nao_viram_colunas() -> None:
    result = _run(
        "SELECT DATE_TRUNC('year', event_date), "
        "DATE_TRUNC(MONTH, event_date), "
        "GENERIC_FUNC('literal_value', value), "
        "event_date + INTERVAL 1 MONTH "
        "FROM schema_test.table_test"
    )

    assert result["status"] == "approved"


def test_coluna_real_desconhecida_continua_rejeitada_apos_literais() -> None:
    result = _run(
        "SELECT DATE_TRUNC('month', event_date), unknown_field "
        "FROM schema_test.table_test"
    )

    violated = [
        column["column"]
        for column in result["columns"]
        if column["status"] == "violated"
    ]
    assert result["status"] == "rejected"
    assert violated == ["unknown_field"]


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


def test_modificadores_de_join_nao_mascaram_coluna_fisica_invalida() -> None:
    result = _run(
        "SELECT t.id, o.other_value, r.missing_column "
        "FROM schema_test.table_test t "
        "CROSS JOIN schema_test.table_other o "
        "INNER JOIN schema_test.table_other r ON r.id = t.id "
        "LEFT JOIN schema_test.table_other l ON l.id = t.id "
        "RIGHT JOIN schema_test.table_other rr ON rr.id = t.id "
        "FULL OUTER JOIN schema_test.table_other f ON f.id = t.id",
        _with_second_table(),
    )

    violated = [
        column["column"]
        for column in result["columns"]
        if column["status"] == "violated"
    ]
    structural_tokens = {"cross", "inner", "left", "right", "full", "outer"}
    assert result["status"] == "rejected"
    assert "missing_column" in violated
    assert structural_tokens.isdisjoint(violated)


def test_tabela_sintetica_valida_chaves_sem_replace_automatico() -> None:
    plan = _dimension_test_plan()
    valid = _run(
        "SELECT d.pk_id, d.business_key "
        "FROM schema_test.dimension_test d",
        plan,
    )
    invalid = _run(
        "SELECT d.invalid_key "
        "FROM schema_test.dimension_test d",
        plan,
    )

    assert valid["status"] == "approved"
    assert invalid["status"] == "rejected"
    assert invalid["errors"][0]["code"] == "SQL_CONTRACT_UNKNOWN_COLUMN"
    assert invalid["columns"][0]["table"] == "schema_test.dimension_test"
    assert invalid["columns"][0]["column"] == "invalid_key"


def test_dimensao_planejada_agrupada_por_coluna_alvo_aprova() -> None:
    result = _run(
        "SELECT d.business_key, COUNT(*) "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key",
        _with_grouping_dimension(),
    )

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "grouping_dimensions") == "passed"


def test_dimensao_planejada_aceita_alias_sql_da_tabela() -> None:
    result = _run(
        "SELECT dim.business_key, COUNT(*) "
        "FROM schema_test.dimension_test dim "
        "GROUP BY dim.business_key",
        _with_grouping_dimension(),
    )

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "grouping_dimensions") == "passed"


def test_dimensao_planejada_rejeita_outra_coluna_fisica_valida() -> None:
    result = _run(
        "SELECT d.label, COUNT(*) "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.label",
        _with_grouping_dimension(),
    )

    assert result["status"] == "rejected"
    assert any(
        error["code"] == "SQL_CONTRACT_GROUPING_DIMENSION_MISMATCH"
        for error in result["errors"]
    )


def test_dimensao_planejada_rejeita_group_by_ausente() -> None:
    result = _run(
        "SELECT COUNT(*) FROM schema_test.dimension_test d",
        _with_grouping_dimension(),
    )

    assert result["status"] == "rejected"
    assert any(
        error["code"] == "SQL_CONTRACT_GROUPING_DIMENSION_MISMATCH"
        for error in result["errors"]
    )


def test_sem_dimensao_planejada_nao_exige_group_by() -> None:
    result = _run(
        "SELECT COUNT(*) FROM schema_test.dimension_test d",
        _dimension_test_plan(),
    )

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "grouping_dimensions") == "passed"


def test_ranking_descendente_com_order_by_metrica_desc_aprova() -> None:
    result = _run(
        "SELECT d.business_key, SUM(d.amount) AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key "
        "ORDER BY total_amount DESC",
        _with_ranking_operation(direction="descending"),
    )

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "analytical_operations") == "passed"
    assert result["errors"] == []


def test_ranking_select_item_coluna_direta_aprova() -> None:
    result = _run(
        "SELECT d.business_key, d.amount AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key, d.amount "
        "ORDER BY total_amount DESC",
        _with_ranking_operation(direction="descending"),
    )

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "analytical_operations") == "passed"


def test_ranking_select_item_repetindo_mesma_coluna_aprova() -> None:
    result = _run(
        "SELECT d.business_key, "
        "SUM(d.amount) + SUM(d.amount) AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key "
        "ORDER BY total_amount DESC",
        _with_ranking_operation(direction="descending"),
    )

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "analytical_operations") == "passed"


def test_ranking_ascendente_com_order_by_metrica_asc_aprova() -> None:
    result = _run(
        "SELECT d.business_key, SUM(d.amount) AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key "
        "ORDER BY total_amount ASC",
        _with_ranking_operation(direction="ascending"),
    )

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "analytical_operations") == "passed"


def test_ranking_expressao_com_outra_coluna_fica_unverifiable() -> None:
    result = _run(
        "SELECT d.business_key, d.amount / d.other_amount AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key, d.amount, d.other_amount "
        "ORDER BY total_amount DESC",
        _with_ranking_operation(direction="descending"),
    )

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "analytical_operations") == "warning"
    assert result["errors"] == []


def test_ranking_expressao_com_desconto_fica_unverifiable() -> None:
    result = _run(
        "SELECT d.business_key, "
        "SUM(d.amount) - SUM(d.other_amount) AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key "
        "ORDER BY total_amount DESC",
        _with_ranking_operation(direction="descending"),
    )

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "analytical_operations") == "warning"
    assert result["errors"] == []


def test_ranking_target_com_coluna_nao_resolvida_fica_unverifiable() -> None:
    plan = _with_second_table()
    plan["planning_context"]["detected_dimensions"] = []
    plan["planning_context"]["planned_metrics"] = [
        {
            "metric_ref": "metric-synthetic",
            "metric_concept": "synthetic_metric",
            "target_table": "schema_test.table_test",
            "target_column": "value",
            "aggregate": None,
        }
    ]
    plan["planning_context"]["analytical_operations"] = [
        {
            "operation_type": "ranking",
            "canonical_value": "ranking",
            "direction": "descending",
            "requested_limit": None,
            "metric_ref": "metric-synthetic",
        }
    ]
    result = _run(
        "SELECT SUM(t.value) + mystery_value AS total_amount "
        "FROM schema_test.table_test t "
        "JOIN schema_test.table_other o ON t.id = o.id "
        "ORDER BY total_amount DESC",
        plan,
    )

    assert result["status"] == "rejected"
    assert any(
        error["code"] == "SQL_CONTRACT_UNKNOWN_COLUMN"
        for error in result["errors"]
    )
    assert _check_status_by_name(result, "analytical_operations") == "warning"


def test_ranking_somente_outra_coluna_rejeita_missing() -> None:
    result = _run(
        "SELECT d.business_key, SUM(d.other_amount) AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key "
        "ORDER BY total_amount DESC",
        _with_ranking_operation(direction="descending"),
    )

    assert result["status"] == "rejected"
    assert any(
        error["details"].get("reason") == "ranking_metric_select_item_missing"
        for error in result["errors"]
    )


def test_ranking_descendente_com_order_by_asc_rejeita_direcao() -> None:
    result = _run(
        "SELECT d.business_key, SUM(d.amount) AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key "
        "ORDER BY total_amount ASC",
        _with_ranking_operation(direction="descending"),
    )

    assert result["status"] == "rejected"
    assert _check_status_by_name(result, "analytical_operations") == "failed"
    assert any(
        error["details"].get("reason") == "ranking_order_direction_mismatch"
        for error in result["errors"]
    )


def test_ranking_sem_order_by_rejeita() -> None:
    result = _run(
        "SELECT d.business_key, SUM(d.amount) AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key",
        _with_ranking_operation(direction="descending"),
    )

    assert result["status"] == "rejected"
    assert _check_status_by_name(result, "analytical_operations") == "failed"
    assert any(
        error["details"].get("reason") == "ranking_root_order_by_missing"
        for error in result["errors"]
    )


def test_ranking_order_by_dimensao_rejeita_target() -> None:
    result = _run(
        "SELECT d.business_key, SUM(d.amount) AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key "
        "ORDER BY d.business_key DESC",
        _with_ranking_operation(direction="descending"),
    )

    assert result["status"] == "rejected"
    assert any(
        error["details"].get("reason") == "ranking_order_target_mismatch"
        for error in result["errors"]
    )


def test_ranking_order_by_outra_metrica_rejeita_target() -> None:
    result = _run(
        "SELECT d.business_key, "
        "SUM(d.amount) AS total_amount, "
        "SUM(d.other_amount) AS other_total "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key "
        "ORDER BY other_total DESC",
        _with_ranking_operation(direction="descending"),
    )

    assert result["status"] == "rejected"
    assert any(
        error["details"].get("reason") == "ranking_order_target_mismatch"
        for error in result["errors"]
    )


def test_ranking_cte_order_by_interno_nao_satisfaz_root() -> None:
    result = _run(
        "WITH internal_scope AS ("
        "SELECT d.business_key, SUM(d.amount) AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key "
        "ORDER BY total_amount DESC"
        ") "
        "SELECT business_key, total_amount FROM internal_scope",
        _with_ranking_operation(direction="descending"),
    )

    assert result["status"] == "rejected"
    assert any(
        error["details"].get("reason") == "ranking_metric_select_item_missing"
        for error in result["errors"]
    )


def test_ranking_subquery_order_by_interno_nao_satisfaz_root() -> None:
    result = _run(
        "SELECT business_key, total_amount FROM ("
        "SELECT d.business_key, SUM(d.amount) AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key "
        "ORDER BY total_amount DESC"
        ") scoped",
        _with_ranking_operation(direction="descending"),
    )

    assert result["status"] == "rejected"
    assert any(
        error["details"].get("reason") == "ranking_metric_select_item_missing"
        for error in result["errors"]
    )


def test_ranking_root_order_by_vence_order_by_interno() -> None:
    result = _run(
        "WITH internal_scope AS ("
        "SELECT d.business_key, SUM(d.amount) AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key "
        "ORDER BY total_amount ASC"
        ") "
        "SELECT d.business_key, SUM(d.amount) AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key "
        "ORDER BY total_amount DESC",
        _with_ranking_operation(direction="descending"),
    )

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "analytical_operations") == "passed"


def test_ranking_tabela_da_metrica_precisa_bater_com_select_item() -> None:
    plan = _with_second_table()
    plan["planning_context"]["detected_dimensions"] = []
    plan["planning_context"]["planned_metrics"] = [
        {
            "metric_ref": "metric-synthetic",
            "metric_concept": "synthetic_metric",
            "target_table": "schema_test.table_test",
            "target_column": "value",
            "aggregate": None,
        }
    ]
    plan["planning_context"]["analytical_operations"] = [
        {
            "operation_type": "ranking",
            "canonical_value": "ranking",
            "direction": "descending",
            "requested_limit": None,
            "metric_ref": "metric-synthetic",
        }
    ]
    result = _run(
        "SELECT SUM(o.other_value) AS total_amount "
        "FROM schema_test.table_test t "
        "JOIN schema_test.table_other o ON t.id = o.id "
        "ORDER BY total_amount DESC",
        plan,
    )

    assert result["status"] == "rejected"
    assert any(
        error["details"].get("reason") == "ranking_metric_select_item_missing"
        for error in result["errors"]
    )


def test_ranking_sem_metric_ref_permanece_unverifiable() -> None:
    result = _run(
        "SELECT d.business_key, SUM(d.amount) AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key "
        "ORDER BY total_amount DESC",
        _with_ranking_operation(metric_ref=""),
    )

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "analytical_operations") == "warning"
    assert result["errors"] == []


def test_ranking_metric_ref_sem_planned_metric_permanece_unverifiable() -> None:
    result = _run(
        "SELECT d.business_key, SUM(d.amount) AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key "
        "ORDER BY total_amount DESC",
        _with_ranking_operation(metric_ref="metric-missing"),
    )

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "analytical_operations") == "warning"
    assert result["errors"] == []


def test_ranking_metric_ref_duplicado_permanece_unverifiable() -> None:
    result = _run(
        "SELECT d.business_key, SUM(d.amount) AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key "
        "ORDER BY total_amount DESC",
        _with_ranking_operation(duplicate_metric=True),
    )

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "analytical_operations") == "warning"
    assert result["errors"] == []


def test_ranking_order_by_sem_direcao_normaliza_asc() -> None:
    result = _run(
        "SELECT d.business_key, SUM(d.amount) AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key "
        "ORDER BY total_amount",
        _with_ranking_operation(direction="ascending"),
    )

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "analytical_operations") == "passed"


def test_ranking_requested_limit_positivo_deixa_limit_pending() -> None:
    result = _run(
        "SELECT d.business_key, SUM(d.amount) AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key "
        "ORDER BY total_amount DESC",
        _with_ranking_operation(direction="descending", requested_limit=5),
    )

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "analytical_operations") == "warning"
    assert result["errors"] == []


def test_comparison_multi_source_sem_dimensao_cross_join_aprova() -> None:
    result = _run(_comparison_sql(), _comparison_plan())

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "analytical_operations") == "passed"


def test_comparison_grouped_preserve_all_full_outer_aprova() -> None:
    result = _run(
        _comparison_sql(grouped=True, root_join="FULL OUTER JOIN"),
        _comparison_plan(
            grouped=True,
            join_semantics="preserve_all_operand_categories",
        ),
    )

    assert result["status"] == "approved"


def test_comparison_grouped_common_only_inner_join_aprova() -> None:
    result = _run(
        _comparison_sql(grouped=True, root_join="INNER JOIN"),
        _comparison_plan(
            grouped=True,
            join_semantics="common_operand_categories_only",
        ),
    )

    assert result["status"] == "approved"


def test_comparison_raw_source_join_antes_agregacao_rejeita() -> None:
    result = _run(_comparison_sql(raw_join=True), _comparison_plan())

    assert result["status"] == "rejected"
    assert _comparison_reason(result) == "comparison_raw_source_join_detected"


def test_comparison_finding_inclui_gate_falho() -> None:
    result = _run(_comparison_sql(raw_join=True), _comparison_plan())

    comparison_error = next(
        error
        for error in result["errors"]
        if error["details"].get("reason")
        == "comparison_raw_source_join_detected"
    )
    gates = comparison_error["details"]["comparison_evidence"]["gates"]

    assert {
        "name": "raw_source_join_absent",
        "status": "FAIL",
        "reason": "comparison_raw_source_join_detected",
    } in gates


def test_comparison_operand_sem_reducing_aggregate_rejeita() -> None:
    sql = _comparison_sql().replace(
        "SUM(r.amount_right) AS right_total",
        "r.amount_right AS right_total",
    )

    result = _run(sql, _comparison_plan())

    assert result["status"] == "rejected"
    assert _comparison_reason(result) == "comparison_operand_not_aggregated"


def test_comparison_window_aggregate_apenas_rejeita() -> None:
    result = _run(_comparison_sql(left_window=True), _comparison_plan())

    assert result["status"] == "rejected"
    assert _comparison_reason(result) == "comparison_operand_not_aggregated"


def test_comparison_operand_nao_chega_ao_root_rejeita() -> None:
    sql = _comparison_sql().replace(
        "left_operand.left_total, right_operand.right_total",
        "left_operand.left_total",
    )

    result = _run(sql, _comparison_plan())

    assert result["status"] == "rejected"
    assert _comparison_reason(result) == "comparison_root_operand_missing"


def test_comparison_grouped_faltando_dimensao_em_operand_rejeita() -> None:
    sql = _comparison_sql(
        grouped=True,
        root_join="FULL OUTER JOIN",
    ).replace(
        "SELECT d.group_key, SUM(r.amount_right) AS right_total ",
        "SELECT SUM(r.amount_right) AS right_total ",
    )

    result = _run(
        sql,
        _comparison_plan(
            grouped=True,
            join_semantics="preserve_all_operand_categories",
        ),
    )

    assert result["status"] == "rejected"
    assert _comparison_reason(result) in {
        "comparison_dimension_grain_missing",
        "comparison_lineage_unproven",
    }


def test_comparison_preserve_all_com_inner_join_rejeita() -> None:
    result = _run(
        _comparison_sql(grouped=True, root_join="INNER JOIN"),
        _comparison_plan(
            grouped=True,
            join_semantics="preserve_all_operand_categories",
        ),
    )

    assert result["status"] == "rejected"
    assert _comparison_reason(result) == "comparison_join_semantics_mismatch"


def test_comparison_common_only_com_full_outer_join_rejeita() -> None:
    result = _run(
        _comparison_sql(grouped=True, root_join="FULL OUTER JOIN"),
        _comparison_plan(
            grouped=True,
            join_semantics="common_operand_categories_only",
        ),
    )

    assert result["status"] == "rejected"
    assert _comparison_reason(result) == "comparison_join_semantics_mismatch"


def test_comparison_lineage_nao_comprovavel_rejeita() -> None:
    result = _run(
        _comparison_sql(right_projects=False),
        _comparison_plan(),
    )

    assert result["status"] == "rejected"
    assert _comparison_reason(result) == "comparison_lineage_unproven"


def test_comparison_operand_ref_inexistente_rejeita() -> None:
    result = _run(
        _comparison_sql(),
        _comparison_plan(operand_refs=["metric-left", "metric-missing"]),
    )

    assert result["status"] == "rejected"
    assert _comparison_reason(result) == "comparison_operand_missing"


def test_comparison_operand_sem_target_table_rejeita() -> None:
    plan = _comparison_plan()
    plan["planning_context"]["planned_metrics"][1].pop("target_table", None)

    result = _run(_comparison_sql(), plan)

    assert result["status"] == "rejected"
    assert _comparison_reason(result) == "comparison_operand_missing"


def test_comparison_operand_target_table_vazio_rejeita() -> None:
    plan = _comparison_plan()
    plan["planning_context"]["planned_metrics"][1]["target_table"] = ""

    result = _run(_comparison_sql(), plan)

    assert result["status"] == "rejected"
    assert _comparison_reason(result) == "comparison_operand_missing"


def test_comparison_same_source_root_aggregates_aprova() -> None:
    result = _run(
        _same_source_comparison_sql(),
        _same_source_comparison_plan(multiple_metric_sources=False),
    )

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "analytical_operations") == "passed"


def test_comparison_same_source_operand_raw_rejeita() -> None:
    result = _run(
        _same_source_comparison_sql(raw_operand=True),
        _same_source_comparison_plan(multiple_metric_sources=False),
    )

    assert result["status"] == "rejected"
    assert _comparison_reason(result) == "comparison_operand_not_aggregated"


def test_comparison_same_source_window_operand_rejeita() -> None:
    result = _run(
        _same_source_comparison_sql(window_operand=True),
        _same_source_comparison_plan(multiple_metric_sources=False),
    )

    assert result["status"] == "rejected"
    assert _comparison_reason(result) == "comparison_operand_not_aggregated"


def test_comparison_same_source_window_operands_rejeita() -> None:
    result = _run(
        _same_source_comparison_sql(both_window=True),
        _same_source_comparison_plan(multiple_metric_sources=False),
    )

    assert result["status"] == "rejected"
    assert _comparison_reason(result) == "comparison_operand_not_aggregated"


def test_comparison_planner_flag_true_derivado_false_rejeita() -> None:
    result = _run(
        _same_source_comparison_sql(),
        _same_source_comparison_plan(multiple_metric_sources=True),
    )

    assert result["status"] == "rejected"
    assert _comparison_reason(result) == "comparison_multi_source_inconsistent"


def test_comparison_planner_flag_false_derivado_true_rejeita() -> None:
    plan = _comparison_plan()
    plan["planning_context"]["analytical_operations"][0][
        "multiple_metric_sources"
    ] = False

    result = _run(_comparison_sql(), plan)

    assert result["status"] == "rejected"
    assert _comparison_reason(result) == "comparison_multi_source_inconsistent"


def test_sem_ranking_order_by_nao_e_obrigatorio() -> None:
    result = _run(
        "SELECT d.business_key, SUM(d.amount) AS total_amount "
        "FROM schema_test.dimension_test d "
        "GROUP BY d.business_key",
        _with_grouping_dimension(),
    )

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "analytical_operations") == "passed"


def test_metric_binding_planejado_estruturalmente_valido_aprova() -> None:
    result = _run(
        "SELECT amount FROM schema_test.dimension_test",
        _with_metric_binding_plan(),
    )

    assert result["status"] == "approved"
    assert _check_status_by_name(result, "analytical_operations") == "passed"


def test_metric_binding_planejado_incompleto_rejeita() -> None:
    plan = _with_metric_binding_plan()
    del plan["planning_context"]["planned_metrics"][0]["binding_ref"]

    result = _run(
        "SELECT amount FROM schema_test.dimension_test",
        plan,
    )

    assert result["status"] == "rejected"
    assert any(
        finding["details"]["reason"] == "metric_binding_incomplete"
        for finding in result["findings"]
    )


def test_metric_binding_ref_duplicado_rejeita() -> None:
    plan = _with_metric_binding_plan()
    plan["planning_context"]["planned_metrics"].append(
        deepcopy(plan["planning_context"]["planned_metrics"][0])
    )
    plan["planning_context"]["planned_metrics"][1][
        "metric_ref"
    ] = "metric-other"

    result = _run(
        "SELECT amount FROM schema_test.dimension_test",
        plan,
    )

    assert result["status"] == "rejected"
    assert any(
        finding["details"]["reason"] == "metric_binding_duplicate_ref"
        for finding in result["findings"]
    )


def test_metric_binding_target_nao_autorizado_rejeita() -> None:
    plan = _with_metric_binding_plan()
    plan["planning_context"]["planned_metrics"][0][
        "target_column"
    ] = "not_metric_column"

    result = _run(
        "SELECT amount FROM schema_test.dimension_test",
        plan,
    )

    assert result["status"] == "rejected"
    assert any(
        finding["details"]["reason"] == "metric_binding_target_not_authorized"
        for finding in result["findings"]
    )


def test_order_by_direction_helper_textual_removido() -> None:
    assert not hasattr(sql_contract, "_first_order_by_direction")


def test_dimensao_planejada_rejeita_colisao_basename_cross_schema() -> None:
    result = _run(
        "SELECT b.business_key, COUNT(*) "
        "FROM schema_a.dimension_test a "
        "INNER JOIN schema_b.dimension_test b ON b.pk_id = a.pk_id "
        "GROUP BY b.business_key",
        _with_cross_schema_grouping_dimension(),
    )

    assert result["status"] == "rejected"
    assert any(
        error["code"] == "SQL_CONTRACT_GROUPING_DIMENSION_MISMATCH"
        for error in result["errors"]
    )


def _check_status_by_name(result: dict, name: str) -> str:
    matches = [
        check["status"]
        for check in result["checks"]
        if check["name"] == name
    ]
    assert len(matches) == 1
    return matches[0]


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


def _with_required_filter() -> dict:
    plan = deepcopy(_query_plan())
    plan["planning_context"]["planned_filters"] = [{
        "filter_ref": "filter-a", "filter_concept": "synthetic_class",
        "binding_ref": "binding-a", "required": True, "scope": "row",
    }]
    plan["planning_context"]["resolved_filter_bindings"] = [{
        "binding_ref": "binding-a", "filter_concept": "synthetic_class",
        "target_table": "schema_test.table_test", "target_column": "value",
        "operator": "=", "value": "ExactValue", "required": True, "scope": "row",
        "join_path": [],
    }]
    return plan


def test_required_filter_valido_com_alias_aprova() -> None:
    result = _run(
        "SELECT t.id FROM schema_test.table_test t WHERE t.value = 'ExactValue'",
        _with_required_filter(),
    )
    assert result["status"] == "approved"
    assert result["filters"][0]["status"] == "satisfied"


def test_required_filter_ausente_divergente_e_case_sensitive_rejeita() -> None:
    plan = _with_required_filter()
    for sql in (
        "SELECT id FROM schema_test.table_test",
        "SELECT id FROM schema_test.table_test WHERE value <> 'ExactValue'",
        "SELECT id FROM schema_test.table_test WHERE value = 'exactvalue'",
    ):
        result = _run(sql, plan)
        assert result["status"] == "rejected"
        assert result["filters"][0]["status"] == "violated"


def test_required_filter_binding_ausente_duplicado_e_nao_verificavel() -> None:
    missing = _with_required_filter()
    missing["planning_context"]["resolved_filter_bindings"] = []
    assert _run("SELECT id FROM schema_test.table_test", missing)["filters"][0]["reason"] == "binding_missing"
    duplicate = _with_required_filter()
    duplicate["planning_context"]["resolved_filter_bindings"] *= 2
    assert _run("SELECT id FROM schema_test.table_test", duplicate)["filters"][0]["reason"] == "binding_ambiguous"
    unsupported = _run(
        "SELECT id FROM schema_test.table_test WHERE value LIKE 'ExactValue'",
        _with_required_filter(),
    )
    assert unsupported["filters"][0]["status"] == "unverifiable"


def test_planned_filters_vazio_preserva_comportamento() -> None:
    result = _run("SELECT id FROM schema_test.table_test")
    assert result["status"] == "approved"
    assert result["filters"] == []


def test_dois_filtros_em_ordem_inversa_e_um_ausente() -> None:
    plan = _with_required_filter()
    plan["planning_context"]["planned_filters"].append({
        "filter_ref": "filter-b", "filter_concept": "synthetic_id",
        "binding_ref": "binding-b", "required": True, "scope": "row",
    })
    plan["planning_context"]["resolved_filter_bindings"].append({
        "binding_ref": "binding-b", "filter_concept": "synthetic_id",
        "target_table": "schema_test.table_test", "target_column": "id",
        "operator": ">=", "value": 7, "required": True, "scope": "row",
    })
    approved = _run(
        "SELECT id FROM schema_test.table_test WHERE id >= 7 AND value = 'ExactValue'",
        plan,
    )
    assert approved["status"] == "approved"
    assert [item["status"] for item in approved["filters"]] == ["satisfied", "satisfied"]
    rejected = _run("SELECT id FROM schema_test.table_test WHERE id >= 7", plan)
    assert rejected["status"] == "rejected"
    assert [item["status"] for item in rejected["filters"]] == ["violated", "satisfied"]


def test_join_having_e_binding_invalido_nao_satisfazem_where() -> None:
    plan = _with_required_filter()
    for sql in (
        "SELECT t.id FROM schema_test.table_test t JOIN schema_test.table_test x "
        "ON t.value = 'ExactValue'",
        "SELECT value FROM schema_test.table_test GROUP BY value "
        "HAVING value = 'ExactValue'",
    ):
        assert _run(sql, plan)["filters"][0]["reason"] == "required_filter_missing"
    invalid = _with_required_filter()
    invalid["planning_context"]["resolved_filter_bindings"][0]["target_column"] = "unknown_key"
    assert _run("SELECT id FROM schema_test.table_test", invalid)["filters"][0]["reason"] == "binding_invalid_or_incoherent"


def main() -> None:
    tests = [
        ("required filter valido", test_required_filter_valido_com_alias_aprova),
        ("required filter divergencias", test_required_filter_ausente_divergente_e_case_sensitive_rejeita),
        ("required filter bindings fail closed", test_required_filter_binding_ausente_duplicado_e_nao_verificavel),
        ("planned filters vazio", test_planned_filters_vazio_preserva_comportamento),
        ("dois required filters", test_dois_filtros_em_ordem_inversa_e_um_ausente),
        ("scope e binding invalidos", test_join_having_e_binding_invalido_nao_satisfazem_where),
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
        (
            "literais funcoes intervalos",
            test_literais_de_funcoes_e_intervalos_nao_viram_colunas,
        ),
        (
            "unknown real apos literais",
            test_coluna_real_desconhecida_continua_rejeitada_apos_literais,
        ),
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
            "JOIN modifiers nao mascaram coluna",
            test_modificadores_de_join_nao_mascaram_coluna_fisica_invalida,
        ),
        (
            "tabela sintetica chaves",
            test_tabela_sintetica_valida_chaves_sem_replace_automatico,
        ),
        (
            "dimensao planejada coluna alvo",
            test_dimensao_planejada_agrupada_por_coluna_alvo_aprova,
        ),
        (
            "dimensao planejada alias",
            test_dimensao_planejada_aceita_alias_sql_da_tabela,
        ),
        (
            "dimensao planejada coluna errada",
            test_dimensao_planejada_rejeita_outra_coluna_fisica_valida,
        ),
        (
            "dimensao planejada sem group by",
            test_dimensao_planejada_rejeita_group_by_ausente,
        ),
        (
            "sem dimensao planejada",
            test_sem_dimensao_planejada_nao_exige_group_by,
        ),
        (
            "ranking desc order desc aprovado",
            test_ranking_descendente_com_order_by_metrica_desc_aprova,
        ),
        (
            "ranking coluna direta aprovado",
            test_ranking_select_item_coluna_direta_aprova,
        ),
        (
            "ranking mesma coluna repetida aprovado",
            test_ranking_select_item_repetindo_mesma_coluna_aprova,
        ),
        (
            "ranking asc order asc aprovado",
            test_ranking_ascendente_com_order_by_metrica_asc_aprova,
        ),
        (
            "ranking expressao outra coluna unverifiable",
            test_ranking_expressao_com_outra_coluna_fica_unverifiable,
        ),
        (
            "ranking expressao desconto unverifiable",
            test_ranking_expressao_com_desconto_fica_unverifiable,
        ),
        (
            "ranking coluna nao resolvida unverifiable",
            test_ranking_target_com_coluna_nao_resolvida_fica_unverifiable,
        ),
        (
            "ranking somente outra coluna missing",
            test_ranking_somente_outra_coluna_rejeita_missing,
        ),
        (
            "ranking desc order asc rejeita",
            test_ranking_descendente_com_order_by_asc_rejeita_direcao,
        ),
        (
            "ranking sem order by rejeita",
            test_ranking_sem_order_by_rejeita,
        ),
        (
            "ranking order dimensao rejeita",
            test_ranking_order_by_dimensao_rejeita_target,
        ),
        (
            "ranking order outra metrica rejeita",
            test_ranking_order_by_outra_metrica_rejeita_target,
        ),
        (
            "ranking cte order interno",
            test_ranking_cte_order_by_interno_nao_satisfaz_root,
        ),
        (
            "ranking subquery order interno",
            test_ranking_subquery_order_by_interno_nao_satisfaz_root,
        ),
        (
            "ranking root order vence interno",
            test_ranking_root_order_by_vence_order_by_interno,
        ),
        (
            "ranking tabela metrica precisa bater",
            test_ranking_tabela_da_metrica_precisa_bater_com_select_item,
        ),
        (
            "ranking sem metric ref",
            test_ranking_sem_metric_ref_permanece_unverifiable,
        ),
        (
            "ranking metric ref ausente",
            test_ranking_metric_ref_sem_planned_metric_permanece_unverifiable,
        ),
        (
            "ranking metric ref duplicado",
            test_ranking_metric_ref_duplicado_permanece_unverifiable,
        ),
        (
            "ranking order default asc",
            test_ranking_order_by_sem_direcao_normaliza_asc,
        ),
        (
            "ranking limit pending",
            test_ranking_requested_limit_positivo_deixa_limit_pending,
        ),
        (
            "comparison sem dimensao cross join",
            test_comparison_multi_source_sem_dimensao_cross_join_aprova,
        ),
        (
            "comparison grouped preserve all",
            test_comparison_grouped_preserve_all_full_outer_aprova,
        ),
        (
            "comparison grouped common only",
            test_comparison_grouped_common_only_inner_join_aprova,
        ),
        (
            "comparison raw source join",
            test_comparison_raw_source_join_antes_agregacao_rejeita,
        ),
        (
            "comparison finding gate falho",
            test_comparison_finding_inclui_gate_falho,
        ),
        (
            "comparison operand sem aggregate",
            test_comparison_operand_sem_reducing_aggregate_rejeita,
        ),
        (
            "comparison window aggregate",
            test_comparison_window_aggregate_apenas_rejeita,
        ),
        (
            "comparison operand fora do root",
            test_comparison_operand_nao_chega_ao_root_rejeita,
        ),
        (
            "comparison grouped faltando dimensao",
            test_comparison_grouped_faltando_dimensao_em_operand_rejeita,
        ),
        (
            "comparison preserve all inner",
            test_comparison_preserve_all_com_inner_join_rejeita,
        ),
        (
            "comparison common only full outer",
            test_comparison_common_only_com_full_outer_join_rejeita,
        ),
        (
            "comparison lineage unproven",
            test_comparison_lineage_nao_comprovavel_rejeita,
        ),
        (
            "comparison operand ref inexistente",
            test_comparison_operand_ref_inexistente_rejeita,
        ),
        (
            "comparison operand sem target table",
            test_comparison_operand_sem_target_table_rejeita,
        ),
        (
            "comparison operand target table vazio",
            test_comparison_operand_target_table_vazio_rejeita,
        ),
        (
            "comparison same-source root",
            test_comparison_same_source_root_aggregates_aprova,
        ),
        (
            "comparison same-source raw",
            test_comparison_same_source_operand_raw_rejeita,
        ),
        (
            "comparison same-source window operand",
            test_comparison_same_source_window_operand_rejeita,
        ),
        (
            "comparison same-source window operands",
            test_comparison_same_source_window_operands_rejeita,
        ),
        (
            "comparison flag true derivado false",
            test_comparison_planner_flag_true_derivado_false_rejeita,
        ),
        (
            "comparison flag false derivado true",
            test_comparison_planner_flag_false_derivado_true_rejeita,
        ),
        (
            "sem ranking sem order obrigatorio",
            test_sem_ranking_order_by_nao_e_obrigatorio,
        ),
        (
            "metric binding valido",
            test_metric_binding_planejado_estruturalmente_valido_aprova,
        ),
        (
            "metric binding incompleto",
            test_metric_binding_planejado_incompleto_rejeita,
        ),
        (
            "metric binding ref duplicado",
            test_metric_binding_ref_duplicado_rejeita,
        ),
        (
            "metric binding target nao autorizado",
            test_metric_binding_target_nao_autorizado_rejeita,
        ),
        (
            "helper textual order by removido",
            test_order_by_direction_helper_textual_removido,
        ),
        (
            "dimensao planejada colisao cross-schema",
            test_dimensao_planejada_rejeita_colisao_basename_cross_schema,
        ),
        ("diagnostico determinismo", test_diagnostico_determinismo_e_sem_mutacao),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

from __future__ import annotations

from copy import deepcopy

from app.domain.planner import (
    PLANNER_VERSION,
    PlanningInputError,
    build_query_plan,
    project_planning_context,
    select_query_pattern,
)
from app.domain.planning import SelectedPattern


def _pattern(
    *,
    pattern_name: str = "generic_pattern",
    examples: list[str] | None = None,
    priority: int | None = 1,
    required_rules: list[str] | None = None,
    required_tables: list[str] | None = None,
) -> dict:
    pattern = {
        "intent_name": "generic_test_intent",
        "pattern_name": pattern_name,
        "business_question_examples": examples or [],
        "required_tables": required_tables or [
            "schema_test.table_test",
        ],
        "required_rules": required_rules or [
            "generic_required_rule",
        ],
        "sql_pattern": "SELECT 1",
        "notes": "generic note",
    }
    if priority is not None:
        pattern["priority"] = priority
    return pattern


def _context() -> dict:
    return {
        "version": "context-test-v1",
        "source": "unit-test",
        "fingerprint": "a" * 64,
        "counts": {},
        "rules": [
            {
                "rule_group": "generic",
                "rule_name": "generic_required_rule",
                "rule_content": {
                    "enabled": True,
                },
                "applies_to_intents": [],
                "validation_hint": None,
                "severity": "error",
                "priority": 2,
            },
            {
                "rule_group": "generic",
                "rule_name": "generic_applied_rule",
                "rule_content": {
                    "enabled": True,
                },
                "applies_to_intents": [
                    "generic_test_intent",
                ],
                "validation_hint": None,
                "severity": "warning",
                "priority": 1,
            },
        ],
        "entities": [
            {
                "entity_type": "intent_signal",
                "user_term": "generic analysis",
                "canonical_value": "generic_test_intent",
                "target_table": None,
                "target_column": None,
                "sql_filter_hint": {
                    "resolver": {
                        "match_mode": "contains",
                    }
                },
                "business_rule": None,
                "priority": 1,
            },
            {
                "entity_type": "column_alias",
                "user_term": "generic value",
                "canonical_value": "value",
                "target_table": "schema_test.table_test",
                "target_column": "value",
                "sql_filter_hint": {
                    "operator": "=",
                },
                "business_rule": None,
                "priority": 2,
            },
            {
                "entity_type": "intent_definition",
                "user_term": "generic definition",
                "canonical_value": "generic_test_intent",
                "target_table": None,
                "target_column": None,
                "sql_filter_hint": None,
                "business_rule": {
                    "intent_catalog": {},
                },
                "priority": 1,
            },
        ],
        "dre_mappings": [
            {
                "dre_code": "GENERIC_CODE",
                "nivel_1_bi": "generic_group",
                "business_description": "generic mapping",
                "sign_convention": None,
                "category": "generic",
                "is_revenue": False,
                "is_deduction": False,
                "is_cost": False,
                "is_opex": False,
                "is_financial_result": False,
                "sql_filter_hint": None,
                "sort_order": 1,
            }
        ],
        "query_patterns": [_pattern()],
        "table_catalog": [
            {
                "schema_name": "schema_test",
                "table_name": "table_test",
                "table_type": "table",
                "description": "generic table",
                "grain": {
                    "kind": "generic",
                },
                "primary_key": ["id"],
                "key_columns": ["id"],
                "metric_columns": ["value"],
                "date_columns": ["event_date"],
                "join_rules": [
                    {
                        "target_table": "schema_test.table_other",
                        "condition": "generic",
                    },
                    {
                        "target_table": "schema_test.table_test",
                        "condition": "self generic",
                    },
                ],
                "ai_hint": {
                    "hint": "generic",
                },
                "priority": 1,
                "columns": [
                    {
                        "name": "id",
                        "data_type": "integer",
                        "nullable": False,
                        "description": None,
                    },
                    {
                        "name": "value",
                        "data_type": "numeric",
                        "nullable": True,
                        "description": "generic value",
                    },
                ],
            }
        ],
        "allowed_schemas": ["schema_test"],
        "component_configs": {
            "generic_component": {
                "component": "generic_component",
            }
        },
        "intent_resolution": {},
    }


def _dimension_context() -> dict:
    context = _context()
    context["intent_resolution"] = {
        "intent_catalog": [
            {
                "business_rule": {
                    "intent_catalog": {
                        "rules": [
                            {
                                "concepts": [
                                    {
                                        "concept_name": "dimension_grouping",
                                        "terms": [
                                            "por region",
                                            "por channel",
                                            "por territory",
                                            "por missing thing",
                                        ],
                                    }
                                ]
                            }
                        ]
                    }
                }
            }
        ]
    }
    context["entities"].extend(
        [
            {
                "entity_type": "dimension",
                "user_term": "region",
                "canonical_value": "region",
                "target_table": "schema_test.dim_region",
                "target_column": "region_name",
                "sql_filter_hint": None,
                "business_rule": None,
                "priority": 1,
            },
            {
                "entity_type": "dimension",
                "user_term": "channel",
                "canonical_value": "channel",
                "target_table": "schema_test.dim_channel",
                "target_column": "channel_name",
                "sql_filter_hint": None,
                "business_rule": None,
                "priority": 1,
            },
        ]
    )
    context["table_catalog"].extend(
        [
            {
                "schema_name": "schema_test",
                "table_name": "dim_region",
                "table_type": "table",
                "description": "region dimension",
                "grain": None,
                "primary_key": ["region_id"],
                "key_columns": ["region_id", "region_name"],
                "metric_columns": [],
                "date_columns": [],
                "join_rules": [
                    {"target_table": "schema_test.table_test"}
                ],
                "ai_hint": None,
                "priority": 1,
                "columns": [
                    {"name": "region_id"},
                    {"name": "region_name"},
                ],
            },
            {
                "schema_name": "schema_test",
                "table_name": "dim_channel",
                "table_type": "table",
                "description": "channel dimension",
                "grain": None,
                "primary_key": ["channel_id"],
                "key_columns": ["channel_id", "channel_name"],
                "metric_columns": [],
                "date_columns": [],
                "join_rules": [
                    {"target_table": "schema_test.table_test"}
                ],
                "ai_hint": None,
                "priority": 1,
                "columns": [
                    {"name": "channel_id"},
                    {"name": "channel_name"},
                ],
            },
            {
                "schema_name": "schema_test",
                "table_name": "dim_territory",
                "table_type": "table",
                "description": "territory dimension",
                "grain": None,
                "primary_key": ["id"],
                "key_columns": ["id", "code"],
                "metric_columns": [],
                "date_columns": [],
                "join_rules": [
                    {"target_table": "schema_test.table_test"}
                ],
                "ai_hint": None,
                "priority": 1,
                "columns": [
                    {"name": "id"},
                    {"name": "code"},
                    {"name": "label"},
                ],
            },
        ]
    )
    return context


def test_seleciona_padrao_unico() -> None:
    result = select_query_pattern(
        intent_name="generic_test_intent",
        normalized_question="generic analysis",
        query_patterns=[_pattern()],
    )

    assert result["status"] == "planned"
    assert result["selected_pattern"]["pattern_name"] == "generic_pattern"
    assert result["diagnostic"]["decision_reason"] == (
        "single_pattern_selected"
    )


def test_seleciona_exemplo_exato() -> None:
    result = select_query_pattern(
        intent_name="generic_test_intent",
        normalized_question="generic exact question",
        query_patterns=[
            _pattern(
                pattern_name="generic_other",
                examples=["generic other question"],
                priority=1,
            ),
            _pattern(
                pattern_name="generic_exact",
                examples=["Generic exact question"],
                priority=9,
            ),
        ],
    )

    assert result["selected_pattern"]["pattern_name"] == "generic_exact"
    assert result["diagnostic"]["decision_reason"] == "exact_example_match"


def test_seleciona_por_similaridade_deterministica() -> None:
    result = select_query_pattern(
        intent_name="generic_test_intent",
        normalized_question="alpha beta gamma",
        query_patterns=[
            _pattern(
                pattern_name="generic_low",
                examples=["alpha delta"],
                priority=1,
            ),
            _pattern(
                pattern_name="generic_high",
                examples=["alpha beta gamma delta"],
                priority=9,
            ),
        ],
    )

    assert result["selected_pattern"]["pattern_name"] == "generic_high"
    assert result["diagnostic"]["decision_reason"] == (
        "lexical_similarity_selected"
    )


def test_seleciona_por_prioridade() -> None:
    result = select_query_pattern(
        intent_name="generic_test_intent",
        normalized_question="generic question",
        query_patterns=[
            _pattern(pattern_name="generic_b", priority=2),
            _pattern(pattern_name="generic_a", priority=1),
        ],
    )

    assert result["selected_pattern"]["pattern_name"] == "generic_a"
    assert result["diagnostic"]["decision_reason"] == "priority_selected"
    assert result["diagnostic"]["fallback_used"] == "priority"


def test_desempate_estavel_com_evidencia() -> None:
    result = select_query_pattern(
        intent_name="generic_test_intent",
        normalized_question="alpha beta",
        query_patterns=[
            _pattern(
                pattern_name="generic_b",
                examples=["alpha beta gamma"],
                priority=1,
            ),
            _pattern(
                pattern_name="generic_a",
                examples=["alpha beta gamma"],
                priority=1,
            ),
        ],
    )

    assert result["selected_pattern"]["pattern_name"] == "generic_a"
    assert result["diagnostic"]["decision_reason"] == (
        "stable_name_tiebreak_selected"
    )
    assert result["diagnostic"]["tie_detected"] is True


def test_rejeita_empate_sem_evidencia_semantica() -> None:
    result = select_query_pattern(
        intent_name="generic_test_intent",
        normalized_question="generic question",
        query_patterns=[
            _pattern(pattern_name="generic_a", priority=1),
            _pattern(pattern_name="generic_b", priority=1),
        ],
    )

    assert result["status"] == "rejected"
    assert result["error_code"] == "PLANNING_PATTERN_AMBIGUOUS"


def test_rejeita_intencao_sem_padrao() -> None:
    result = select_query_pattern(
        intent_name="missing_intent",
        normalized_question="generic question",
        query_patterns=[_pattern()],
    )

    assert result["status"] == "rejected"
    assert result["error_code"] == "PLANNING_PATTERN_NOT_FOUND"


def test_rejeita_intencao_ausente() -> None:
    result = select_query_pattern(
        intent_name=None,
        normalized_question="generic question",
        query_patterns=[_pattern()],
    )

    assert result["status"] == "rejected"
    assert result["error_code"] == "PLANNING_INTENT_MISSING"


def test_rejeita_valor_malformado() -> None:
    try:
        select_query_pattern(
            intent_name="generic_test_intent",
            normalized_question="generic question",
            query_patterns=[
                {
                    "intent_name": "generic_test_intent",
                    "pattern_name": "generic",
                }
            ],
        )
    except PlanningInputError as error:
        assert "incompleto" in str(error)
    else:
        raise AssertionError("Era esperado PlanningInputError.")


def test_projecao_sem_mutacao_e_ordem_deterministica() -> None:
    context = _context()
    original = deepcopy(context)
    selected: SelectedPattern = {
        "intent_name": "generic_test_intent",
        "pattern_name": "generic_pattern",
        "priority": 1,
        "required_tables": ["schema_test.table_test"],
        "required_rules": ["generic_required_rule"],
        "business_question_examples": [],
        "sql_pattern": "SELECT 1",
        "notes": None,
    }

    first = project_planning_context(
        context=context,
        intent_name="generic_test_intent",
        normalized_question="generic question",
        selected_pattern=selected,
    )
    second = project_planning_context(
        context=context,
        intent_name="generic_test_intent",
        normalized_question="generic question",
        selected_pattern=selected,
    )

    assert first == second
    assert context == original
    assert [rule["rule_name"] for rule in first["rules"]] == [
        "generic_applied_rule",
        "generic_required_rule",
    ]


def test_projeta_regras_por_required_e_applies() -> None:
    plan = build_query_plan(
        context=_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="generic analysis",
    )

    rules = plan["query_plan"]["planning_context"]["rules"]
    reasons = {
        rule["rule_name"]: rule["selection_reasons"]
        for rule in rules
    }
    assert reasons["generic_required_rule"] == ["required_by_pattern"]
    assert reasons["generic_applied_rule"] == ["applies_to_intent"]


def test_rejeita_required_rule_inexistente() -> None:
    context = _context()
    context["query_patterns"] = [
        _pattern(required_rules=["missing_rule"])
    ]

    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="generic question",
    )

    assert result["status"] == "rejected"
    assert result["error_code"] == "PLANNING_REQUIRED_RULE_NOT_FOUND"


def test_rejeita_required_table_inexistente() -> None:
    context = _context()
    context["query_patterns"] = [
        _pattern(required_tables=["schema_test.missing_table"])
    ]

    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="generic question",
    )

    assert result["status"] == "rejected"
    assert result["error_code"] == "PLANNING_REQUIRED_TABLE_NOT_FOUND"


def test_projeta_catalogo_colunas_e_joins() -> None:
    plan = build_query_plan(
        context=_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="generic analysis",
    )

    projection = plan["query_plan"]["planning_context"]
    table = projection["required_tables"][0]
    assert table["qualified_name"] == "schema_test.table_test"
    assert table["metric_columns"] == ["value"]
    assert projection["relevant_columns"]["schema_test.table_test"][0][
        "name"
    ] == "id"
    join_rules = projection["authorized_joins"][0]["join_rules"]
    assert len(join_rules) == 1
    assert join_rules[0]["target_table"] == "schema_test.table_test"


def test_projeta_entidades_relevantes_e_exclui_intent_definition() -> None:
    plan = build_query_plan(
        context=_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="generic analysis",
    )

    entities = plan["query_plan"]["planning_context"][
        "relevant_entities"
    ]
    entity_types = {entity["entity_type"] for entity in entities}
    assert "intent_signal" in entity_types
    assert "column_alias" in entity_types
    assert "intent_definition" not in entity_types


def test_dre_vazio_sem_evidencia() -> None:
    plan = build_query_plan(
        context=_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="generic analysis",
    )

    projection = plan["query_plan"]["planning_context"]
    assert projection["relevant_dre_mappings"] == []
    assert projection["diagnostics"]["dre_diagnostic"]["empty_reason"] == (
        "no_explicit_context_evidence"
    )


def test_diagnostico_completo() -> None:
    result = select_query_pattern(
        intent_name="generic_test_intent",
        normalized_question="alpha beta",
        query_patterns=[
            _pattern(
                pattern_name="generic_a",
                examples=["alpha beta"],
            )
        ],
    )

    diagnostic = result["diagnostic"]
    assert diagnostic["planner_version"] == PLANNER_VERSION
    assert diagnostic["selected_pattern"]["pattern_name"] == "generic_a"
    assert diagnostic["candidates"][0]["criteria"][
        "exact_example_match"
    ] is True


def test_query_plan_autocontido_sem_sql_final() -> None:
    result = build_query_plan(
        context=_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="generic analysis",
    )

    query_plan = result["query_plan"]
    assert query_plan["planner_version"] == PLANNER_VERSION
    assert query_plan["context_version"] == "context-test-v1"
    assert "planning_context" in query_plan
    assert "generated_sql" not in query_plan
    assert query_plan["sql_pattern_metadata"] == "SELECT 1"


def test_promove_dimensao_contextual_para_query_plan() -> None:
    result = build_query_plan(
        context=_dimension_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="total amount por region",
    )

    projection = result["query_plan"]["planning_context"]
    dimensions = projection["detected_dimensions"]
    table_names = {
        table["qualified_name"]
        for table in projection["required_tables"]
    }

    assert result["status"] == "planned"
    assert dimensions[0]["canonical_value"] == "region"
    assert dimensions[0]["target_table"] == "schema_test.dim_region"
    assert dimensions[0]["target_column"] == "region_name"
    assert dimensions[0]["grouping_requested"] is True
    assert "schema_test.dim_region" in table_names
    assert "schema_test.dim_region" in projection["relevant_columns"]


def test_promove_dimensoes_sem_lista_de_negocio_no_python() -> None:
    result = build_query_plan(
        context=_dimension_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="total value por channel",
    )

    projection = result["query_plan"]["planning_context"]
    dimension = projection["detected_dimensions"][0]

    assert dimension["canonical_value"] == "channel"
    assert dimension["target_table"] == "schema_test.dim_channel"
    assert dimension["target_column"] == "channel_name"
    assert "schema_test.dim_channel" in projection["relevant_columns"]


def test_sem_dimensao_nao_cria_grouping() -> None:
    result = build_query_plan(
        context=_dimension_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="total amount in period",
    )

    projection = result["query_plan"]["planning_context"]

    assert projection["detected_dimensions"] == []
    assert projection["diagnostics"]["dimension_diagnostic"] == {
        "grouping_requested": False,
        "matched_terms": [],
        "unresolved_terms": [],
    }


def test_dimensao_inexistente_nao_inventa_coluna() -> None:
    result = build_query_plan(
        context=_dimension_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="total amount por missing thing",
    )

    projection = result["query_plan"]["planning_context"]

    assert projection["detected_dimensions"] == []
    assert projection["diagnostics"]["dimension_diagnostic"][
        "grouping_requested"
    ] is True
    assert projection["diagnostics"]["dimension_diagnostic"][
        "unresolved_terms"
    ] == ["missing thing"]


def test_nome_de_tabela_nao_autoriza_coluna_de_dimensao() -> None:
    result = build_query_plan(
        context=_dimension_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="total amount por territory",
    )

    projection = result["query_plan"]["planning_context"]

    assert projection["detected_dimensions"] == []
    assert projection["diagnostics"]["dimension_diagnostic"][
        "grouping_requested"
    ] is True
    assert projection["diagnostics"]["dimension_diagnostic"][
        "unresolved_terms"
    ] == ["territory"]
    assert "schema_test.dim_territory" not in {
        table["qualified_name"]
        for table in projection["required_tables"]
    }


def test_alias_contextual_explicito_resolve_dimensao_sem_fallback_pk() -> None:
    context = _dimension_context()
    context["entities"].append(
        {
            "entity_type": "dimension",
            "user_term": "territory",
            "canonical_value": "territory",
            "target_table": "schema_test.dim_territory",
            "target_column": "label",
            "sql_filter_hint": None,
            "business_rule": None,
            "priority": 1,
        }
    )

    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="total amount por territory",
    )

    projection = result["query_plan"]["planning_context"]
    dimension = projection["detected_dimensions"][0]

    assert dimension["target_table"] == "schema_test.dim_territory"
    assert dimension["target_column"] == "label"
    assert dimension["source"] == "entity_alias"
    assert dimension["target_column"] not in {"id", "code"}


def test_dimensao_explicita_vence_alias_legado_com_prioridade_menor() -> None:
    context = _dimension_context()
    context["intent_resolution"]["intent_catalog"][0]["business_rule"][
        "intent_catalog"
    ]["rules"][0]["concepts"][0]["terms"].append("por market")
    context["entities"].extend(
        [
            {
                "entity_type": "dimension",
                "user_term": "market",
                "canonical_value": "market",
                "target_table": "schema_test.dim_market",
                "target_column": "market_code",
                "sql_filter_hint": None,
                "business_rule": None,
                "priority": 10,
            },
            {
                "entity_type": "location",
                "user_term": "market",
                "canonical_value": "market",
                "target_table": "schema_test.dim_market",
                "target_column": "market_name",
                "sql_filter_hint": None,
                "business_rule": None,
                "priority": 1,
            },
        ]
    )
    context["table_catalog"].append(
        {
            "schema_name": "schema_test",
            "table_name": "dim_market",
            "table_type": "table",
            "description": "market dimension",
            "grain": None,
            "primary_key": ["market_id"],
            "key_columns": ["market_id", "market_code", "market_name"],
            "metric_columns": [],
            "date_columns": [],
            "join_rules": [{"target_table": "schema_test.table_test"}],
            "ai_hint": None,
            "priority": 1,
            "columns": [
                {"name": "market_id"},
                {"name": "market_code"},
                {"name": "market_name"},
            ],
        }
    )

    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="total amount por market",
    )

    dimension = result["query_plan"]["planning_context"][
        "detected_dimensions"
    ][0]

    assert dimension["canonical_value"] == "market"
    assert dimension["target_table"] == "schema_test.dim_market"
    assert dimension["target_column"] == "market_code"
    assert dimension["priority"] == 10


def test_alias_legado_resolve_dimensao_quando_nao_ha_dimension_explicita() -> None:
    context = _dimension_context()
    context["intent_resolution"]["intent_catalog"][0]["business_rule"][
        "intent_catalog"
    ]["rules"][0]["concepts"][0]["terms"].append("por segment")
    context["entities"].append(
        {
            "entity_type": "classification",
            "user_term": "segment",
            "canonical_value": "segment",
            "target_table": "schema_test.dim_segment",
            "target_column": "segment_name",
            "sql_filter_hint": None,
            "business_rule": None,
            "priority": 1,
        }
    )
    context["table_catalog"].append(
        {
            "schema_name": "schema_test",
            "table_name": "dim_segment",
            "table_type": "table",
            "description": "segment dimension",
            "grain": None,
            "primary_key": ["segment_id"],
            "key_columns": ["segment_id", "segment_name"],
            "metric_columns": [],
            "date_columns": [],
            "join_rules": [{"target_table": "schema_test.table_test"}],
            "ai_hint": None,
            "priority": 1,
            "columns": [
                {"name": "segment_id"},
                {"name": "segment_name"},
            ],
        }
    )

    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="total amount por segment",
    )

    dimension = result["query_plan"]["planning_context"][
        "detected_dimensions"
    ][0]

    assert dimension["canonical_value"] == "segment"
    assert dimension["target_column"] == "segment_name"
    assert dimension["source"] == "entity_alias"


def test_dimension_explicita_sem_match_nao_bloqueia_fallback_legado() -> None:
    context = _dimension_context()
    context["intent_resolution"]["intent_catalog"][0]["business_rule"][
        "intent_catalog"
    ]["rules"][0]["concepts"][0]["terms"].append("por segment")
    context["entities"].extend(
        [
            {
                "entity_type": "dimension",
                "user_term": "market",
                "canonical_value": "market",
                "target_table": "schema_test.dim_market",
                "target_column": "market_code",
                "sql_filter_hint": None,
                "business_rule": None,
                "priority": 1,
            },
            {
                "entity_type": "classification",
                "user_term": "segment",
                "canonical_value": "segment",
                "target_table": "schema_test.dim_segment",
                "target_column": "segment_name",
                "sql_filter_hint": None,
                "business_rule": None,
                "priority": 1,
            },
        ]
    )
    context["table_catalog"].extend(
        [
            {
                "schema_name": "schema_test",
                "table_name": "dim_market",
                "table_type": "table",
                "description": "market dimension",
                "grain": None,
                "primary_key": ["market_id"],
                "key_columns": ["market_id", "market_code"],
                "metric_columns": [],
                "date_columns": [],
                "join_rules": [{"target_table": "schema_test.table_test"}],
                "ai_hint": None,
                "priority": 1,
                "columns": [
                    {"name": "market_id"},
                    {"name": "market_code"},
                ],
            },
            {
                "schema_name": "schema_test",
                "table_name": "dim_segment",
                "table_type": "table",
                "description": "segment dimension",
                "grain": None,
                "primary_key": ["segment_id"],
                "key_columns": ["segment_id", "segment_name"],
                "metric_columns": [],
                "date_columns": [],
                "join_rules": [{"target_table": "schema_test.table_test"}],
                "ai_hint": None,
                "priority": 1,
                "columns": [
                    {"name": "segment_id"},
                    {"name": "segment_name"},
                ],
            },
        ]
    )

    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="total amount por segment",
    )

    dimension = result["query_plan"]["planning_context"][
        "detected_dimensions"
    ][0]

    assert dimension["canonical_value"] == "segment"
    assert dimension["target_column"] == "segment_name"


def main() -> None:
    tests = [
        ("seleciona padrao unico", test_seleciona_padrao_unico),
        ("seleciona exemplo exato", test_seleciona_exemplo_exato),
        (
            "seleciona por similaridade",
            test_seleciona_por_similaridade_deterministica,
        ),
        ("seleciona por prioridade", test_seleciona_por_prioridade),
        (
            "desempate estavel com evidencia",
            test_desempate_estavel_com_evidencia,
        ),
        (
            "rejeita empate sem evidencia",
            test_rejeita_empate_sem_evidencia_semantica,
        ),
        (
            "rejeita intencao sem padrao",
            test_rejeita_intencao_sem_padrao,
        ),
        ("rejeita intencao ausente", test_rejeita_intencao_ausente),
        ("rejeita valor malformado", test_rejeita_valor_malformado),
        (
            "projecao sem mutacao e ordem",
            test_projecao_sem_mutacao_e_ordem_deterministica,
        ),
        (
            "projeta regras por required e applies",
            test_projeta_regras_por_required_e_applies,
        ),
        (
            "rejeita required_rule inexistente",
            test_rejeita_required_rule_inexistente,
        ),
        (
            "rejeita required_table inexistente",
            test_rejeita_required_table_inexistente,
        ),
        (
            "projeta catalogo colunas e joins",
            test_projeta_catalogo_colunas_e_joins,
        ),
        (
            "projeta entidades relevantes",
            test_projeta_entidades_relevantes_e_exclui_intent_definition,
        ),
        ("DRE vazio sem evidencia", test_dre_vazio_sem_evidencia),
        ("diagnostico completo", test_diagnostico_completo),
        (
            "query plan autocontido",
            test_query_plan_autocontido_sem_sql_final,
        ),
        (
            "promove dimensao contextual",
            test_promove_dimensao_contextual_para_query_plan,
        ),
        (
            "promove outra dimensao generica",
            test_promove_dimensoes_sem_lista_de_negocio_no_python,
        ),
        ("sem dimensao sem grouping", test_sem_dimensao_nao_cria_grouping),
        (
            "dimensao inexistente nao inventa",
            test_dimensao_inexistente_nao_inventa_coluna,
        ),
        (
            "nome de tabela nao autoriza coluna",
            test_nome_de_tabela_nao_autoriza_coluna_de_dimensao,
        ),
        (
            "alias contextual resolve dimensao",
            test_alias_contextual_explicito_resolve_dimensao_sem_fallback_pk,
        ),
        (
            "dimensao explicita vence legado",
            test_dimensao_explicita_vence_alias_legado_com_prioridade_menor,
        ),
        (
            "fallback legado preservado",
            test_alias_legado_resolve_dimensao_quando_nao_ha_dimension_explicita,
        ),
        (
            "dimension sem match permite fallback",
            test_dimension_explicita_sem_match_nao_bloqueia_fallback_legado,
        ),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

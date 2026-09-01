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


def _intent_dimension_evidence(
    *,
    term: str,
    matched_tokens: list[str],
) -> dict:
    return {
        "applied": True,
        "intent": "generic_test_intent",
        "best_candidate": {
            "intent_name": "generic_test_intent",
            "score": 120.0,
            "matches": [
                {
                    "pattern": "generic_dimension_rule",
                    "match_details": {
                        "concepts": [
                            {
                                "concept_name": "dimension_grouping",
                                "satisfied": True,
                                "terms": [
                                    {
                                        "term": term,
                                        "normalized_term": term,
                                        "matched": True,
                                        "match_details": {
                                            "semantic_signal": {
                                                "concept_name": (
                                                    "dimension_grouping"
                                                ),
                                                "term": term,
                                                "normalized_term": term,
                                                "source": (
                                                    "intent_catalog_concept"
                                                ),
                                                "confidence": 1.0,
                                                "matched_tokens": (
                                                    matched_tokens
                                                ),
                                            }
                                        },
                                    }
                                ],
                            }
                        ]
                    },
                }
            ],
        },
        "candidates": [],
    }


def _intent_operation_evidence(
    *,
    term: str,
) -> dict:
    return {
        "applied": True,
        "intent": "generic_test_intent",
        "best_candidate": {
            "intent_name": "generic_test_intent",
            "score": 120.0,
            "matches": [
                {
                    "pattern": "generic_operation_rule",
                    "match_details": {
                        "concepts": [
                            {
                                "concept_name": "analytical_operation",
                                "satisfied": True,
                                "terms": [
                                    {
                                        "term": term,
                                        "normalized_term": term,
                                        "matched": True,
                                        "match_details": {
                                            "semantic_signal": {
                                                "concept_name": (
                                                    "analytical_operation"
                                                ),
                                                "term": term,
                                                "normalized_term": term,
                                                "source": (
                                                    "intent_catalog_concept"
                                                ),
                                                "confidence": 1.0,
                                                "matched_tokens": [term],
                                            }
                                        },
                                    }
                                ],
                            }
                        ]
                    },
                }
            ],
        },
        "candidates": [],
    }


def _intent_metric_evidence(
    *,
    term: str,
    operation_term: str | None = None,
) -> dict:
    concepts = [
        {
            "concept_name": "financial_metric",
            "satisfied": True,
            "terms": [
                {
                    "term": term,
                    "normalized_term": term,
                    "matched": True,
                    "match_details": {
                        "semantic_signal": {
                            "concept_name": "financial_metric",
                            "term": term,
                            "normalized_term": term,
                            "source": "intent_catalog_concept",
                            "confidence": 1.0,
                            "matched_tokens": [term],
                        }
                    },
                }
            ],
        }
    ]
    if operation_term is not None:
        concepts.append(
            {
                "concept_name": "analytical_operation",
                "satisfied": True,
                "terms": [
                    {
                        "term": operation_term,
                        "normalized_term": operation_term,
                        "matched": True,
                        "match_details": {
                            "semantic_signal": {
                                "concept_name": "analytical_operation",
                                "term": operation_term,
                                "normalized_term": operation_term,
                                "source": "intent_catalog_concept",
                                "confidence": 1.0,
                                "matched_tokens": [operation_term],
                            }
                        },
                    }
                ],
            }
        )
    return {
        "applied": True,
        "intent": "generic_test_intent",
        "best_candidate": {
            "intent_name": "generic_test_intent",
            "score": 120.0,
            "matches": [
                {
                    "pattern": "generic_metric_rule",
                    "match_details": {"concepts": concepts},
                }
            ],
        },
        "candidates": [],
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


def _operation_context() -> dict:
    context = _dimension_context()
    context["entities"].extend(
        [
            {
                "entity_type": "analytical_operation",
                "user_term": "highest",
                "canonical_value": "ranking",
                "target_table": None,
                "target_column": None,
                "sql_filter_hint": None,
                "business_rule": {
                    "operation": {
                        "operation_type": "ranking",
                        "direction": "descending",
                        "requested_limit": None,
                    }
                },
                "priority": 1,
            },
            {
                "entity_type": "analytical_operation",
                "user_term": "lowest",
                "canonical_value": "ranking",
                "target_table": None,
                "target_column": None,
                "sql_filter_hint": None,
                "business_rule": {
                    "operation": {
                        "operation_type": "ranking",
                        "direction": "ascending",
                        "requested_limit": None,
                    }
                },
                "priority": 1,
            },
        ]
    )
    return context


def _metric_context() -> dict:
    context = _operation_context()
    context["entities"].extend(
        [
            {
                "entity_type": "financial_metric",
                "user_term": "amount",
                "canonical_value": "amount",
                "target_table": "schema_test.fact_metrics",
                "target_column": "measure_value",
                "sql_filter_hint": None,
                "business_rule": {
                    "metric": {
                        "metric_concept": "amount",
                        "target_table": "schema_test.fact_metrics",
                        "target_column": "measure_value",
                    }
                },
                "priority": 1,
            },
            {
                "entity_type": "financial_metric",
                "user_term": "volume",
                "canonical_value": "volume",
                "target_table": "schema_test.fact_metrics",
                "target_column": "volume_value",
                "sql_filter_hint": None,
                "business_rule": {
                    "metric": {
                        "metric_concept": "volume",
                        "target_table": "schema_test.fact_metrics",
                        "target_column": "volume_value",
                    }
                },
                "priority": 1,
            },
        ]
    )
    context["table_catalog"].append(
        {
            "schema_name": "schema_test",
            "table_name": "fact_metrics",
            "table_type": "table",
            "description": "synthetic metrics fact",
            "grain": None,
            "primary_key": ["row_id"],
            "key_columns": ["row_id"],
            "metric_columns": ["measure_value", "volume_value"],
            "date_columns": ["event_date"],
            "join_rules": [],
            "ai_hint": None,
            "priority": 1,
            "columns": [
                {"name": "row_id"},
                {"name": "measure_value"},
                {"name": "volume_value"},
                {"name": "event_date"},
            ],
        }
    )
    return context


def _append_operation_alias(
    context: dict,
    *,
    user_term: str,
    canonical_value: str = "ranking",
    operation_type: str = "ranking",
    direction: str = "descending",
    requested_limit=None,
) -> None:
    context["entities"].append(
        {
            "entity_type": "analytical_operation",
            "user_term": user_term,
            "canonical_value": canonical_value,
            "target_table": None,
            "target_column": None,
            "sql_filter_hint": None,
            "business_rule": {
                "operation": {
                    "operation_type": operation_type,
                    "direction": direction,
                    "requested_limit": requested_limit,
                }
            },
            "priority": 1,
        }
    )


def _append_metric_alias(
    context: dict,
    *,
    user_term: str,
    canonical_value: str = "amount",
    metric_concept: str = "amount",
    target_table: str = "schema_test.fact_metrics",
    target_column: str = "measure_value",
    aggregate=None,
) -> None:
    metric = {
        "metric_concept": metric_concept,
        "target_table": target_table,
        "target_column": target_column,
    }
    if aggregate is not None:
        metric["aggregate"] = aggregate
    context["entities"].append(
        {
            "entity_type": "financial_metric",
            "user_term": user_term,
            "canonical_value": canonical_value,
            "target_table": target_table,
            "target_column": target_column,
            "sql_filter_hint": None,
            "business_rule": {"metric": metric},
            "priority": 1,
        }
    )


def _operation_plan_for_term(
    *,
    context: dict,
    term: str,
) -> dict:
    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question=f"{term} amounts among regions last period",
        intent_resolution_result=_intent_operation_evidence(term=term),
    )
    return result["query_plan"]["planning_context"]


def _metric_plan_for_term(
    *,
    context: dict,
    term: str,
    operation_term: str | None = None,
) -> dict:
    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question=f"{operation_term or ''} {term}".strip(),
        intent_resolution_result=_intent_metric_evidence(
            term=term,
            operation_term=operation_term,
        ),
    )
    return result["query_plan"]["planning_context"]


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
    assert dimensions[0]["source"] == "entity_alias"
    assert dimensions[0]["mapping_source"] == "entity_alias"
    assert dimensions[0]["detection_source"] == "planner_lexical_fallback"
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
    assert dimension["source"] == "entity_alias"
    assert dimension["mapping_source"] == "entity_alias"
    assert dimension["detection_source"] == "planner_lexical_fallback"
    assert "schema_test.dim_channel" in projection["relevant_columns"]


def test_evidence_semantica_do_intent_promove_region_sem_por_literal() -> None:
    result = build_query_plan(
        context=_dimension_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="amount distributed across regions last period",
        intent_resolution_result=_intent_dimension_evidence(
            term="by region",
            matched_tokens=["region"],
        ),
    )

    projection = result["query_plan"]["planning_context"]
    dimension = projection["detected_dimensions"][0]
    diagnostic = projection["diagnostics"]["dimension_diagnostic"]

    assert dimension["canonical_value"] == "region"
    assert dimension["target_table"] == "schema_test.dim_region"
    assert dimension["target_column"] == "region_name"
    assert dimension["source"] == "entity_alias"
    assert dimension["mapping_source"] == "entity_alias"
    assert dimension["detection_source"] == "intent_semantic_evidence"
    assert diagnostic["source"] == "intent_semantic_evidence"
    assert diagnostic["detection_source"] == "intent_semantic_evidence"
    assert diagnostic["fallback_used"] is False


def test_evidence_semantica_do_intent_promove_channel() -> None:
    result = build_query_plan(
        context=_dimension_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="highest amounts among channels last period",
        intent_resolution_result=_intent_dimension_evidence(
            term="by channel",
            matched_tokens=["channel"],
        ),
    )

    dimension = result["query_plan"]["planning_context"][
        "detected_dimensions"
    ][0]

    assert dimension["canonical_value"] == "channel"
    assert dimension["target_table"] == "schema_test.dim_channel"
    assert dimension["target_column"] == "channel_name"
    assert dimension["source"] == "entity_alias"
    assert dimension["mapping_source"] == "entity_alias"
    assert dimension["detection_source"] == "intent_semantic_evidence"


def test_evidence_semantica_explicita_vence_alias_legado() -> None:
    context = _dimension_context()
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
                "entity_type": "classification",
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
        normalized_question="total amount across markets",
        intent_resolution_result=_intent_dimension_evidence(
            term="by market",
            matched_tokens=["market"],
        ),
    )

    dimension = result["query_plan"]["planning_context"][
        "detected_dimensions"
    ][0]

    assert dimension["canonical_value"] == "market"
    assert dimension["target_column"] == "market_code"
    assert dimension["source"] == "entity_alias"
    assert dimension["mapping_source"] == "entity_alias"
    assert dimension["detection_source"] == "intent_semantic_evidence"


def test_evidence_de_outro_conceito_nao_vira_dimensao() -> None:
    evidence = _intent_dimension_evidence(
        term="by region",
        matched_tokens=["region"],
    )
    evidence["best_candidate"]["matches"][0]["match_details"]["concepts"][0][
        "concept_name"
    ] = "financial_metric"

    result = build_query_plan(
        context=_dimension_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="amount distributed across regions last period",
        intent_resolution_result=evidence,
    )

    projection = result["query_plan"]["planning_context"]

    assert projection["detected_dimensions"] == []
    assert projection["diagnostics"]["dimension_diagnostic"]["source"] == (
        "none"
    )


def test_evidence_semantica_incompleta_nao_inventa_dimensao() -> None:
    evidence = _intent_dimension_evidence(
        term="by unknown",
        matched_tokens=[],
    )

    result = build_query_plan(
        context=_dimension_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="amount distributed across regions last period",
        intent_resolution_result=evidence,
    )

    projection = result["query_plan"]["planning_context"]

    assert projection["detected_dimensions"] == []
    assert projection["diagnostics"]["dimension_diagnostic"]["source"] == (
        "none"
    )


def test_evidence_operacional_resolve_ranking_descendente() -> None:
    result = build_query_plan(
        context=_operation_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="highest amounts among regions last period",
        intent_resolution_result=_intent_operation_evidence(
            term="highest",
        ),
    )

    projection = result["query_plan"]["planning_context"]
    operation = projection["analytical_operations"][0]
    diagnostic = projection["diagnostics"][
        "analytical_operation_diagnostic"
    ]

    assert operation["operation_type"] == "ranking"
    assert operation["canonical_value"] == "ranking"
    assert operation["direction"] == "descending"
    assert operation["requested_limit"] is None
    assert operation["detection_source"] == "intent_semantic_evidence"
    assert operation["mapping_source"] == "entity_alias"
    assert diagnostic["source"] == "intent_semantic_evidence"


def test_evidence_operacional_resolve_ranking_ascendente() -> None:
    result = build_query_plan(
        context=_operation_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="lowest amounts among channels last period",
        intent_resolution_result=_intent_operation_evidence(
            term="lowest",
        ),
    )

    operation = result["query_plan"]["planning_context"][
        "analytical_operations"
    ][0]

    assert operation["operation_type"] == "ranking"
    assert operation["direction"] == "ascending"
    assert operation["requested_limit"] is None


def test_evidence_operacional_sem_alias_nao_inventa_operacao() -> None:
    result = build_query_plan(
        context=_operation_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="unknown operation over regions",
        intent_resolution_result=_intent_operation_evidence(
            term="unmapped",
        ),
    )

    projection = result["query_plan"]["planning_context"]

    assert projection["analytical_operations"] == []
    assert projection["diagnostics"]["analytical_operation_diagnostic"][
        "unresolved_terms"
    ] == ["unmapped"]


def test_metadata_operacional_invalida_nao_inventa_operacao() -> None:
    context = _operation_context()
    context["entities"].append(
        {
            "entity_type": "analytical_operation",
            "user_term": "invalid operation",
            "canonical_value": "ranking",
            "target_table": None,
            "target_column": None,
            "sql_filter_hint": None,
            "business_rule": {
                "operation": {
                    "operation_type": "ranking",
                    "direction": "sideways",
                    "requested_limit": None,
                }
            },
            "priority": 1,
        }
    )

    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="invalid operation over regions",
        intent_resolution_result=_intent_operation_evidence(
            term="invalid operation",
        ),
    )

    assert result["query_plan"]["planning_context"][
        "analytical_operations"
    ] == []


def test_operacao_com_canonical_divergente_nao_e_projetada() -> None:
    context = _operation_context()
    _append_operation_alias(
        context,
        user_term="divergent operation",
        canonical_value="different_operation",
        operation_type="ranking",
    )

    projection = _operation_plan_for_term(
        context=context,
        term="divergent operation",
    )

    assert projection["analytical_operations"] == []


def test_requested_limit_bool_nao_e_projetado() -> None:
    for value in (True, False):
        context = _operation_context()
        _append_operation_alias(
            context,
            user_term=f"bool limit {value}",
            requested_limit=value,
        )

        projection = _operation_plan_for_term(
            context=context,
            term=f"bool limit {value}",
        )

        assert projection["analytical_operations"] == []


def test_requested_limit_inteiro_positivo_e_valido() -> None:
    context = _operation_context()
    _append_operation_alias(
        context,
        user_term="top five",
        requested_limit=5,
    )

    projection = _operation_plan_for_term(
        context=context,
        term="top five",
    )
    operation = projection["analytical_operations"][0]

    assert operation["operation_type"] == "ranking"
    assert operation["requested_limit"] == 5


def test_requested_limit_null_e_valido() -> None:
    projection = _operation_plan_for_term(
        context=_operation_context(),
        term="highest",
    )
    operation = projection["analytical_operations"][0]

    assert operation["operation_type"] == "ranking"
    assert operation["requested_limit"] is None


def test_financial_metric_evidence_resolve_planned_metric() -> None:
    projection = _metric_plan_for_term(
        context=_metric_context(),
        term="amount",
    )

    metric = projection["planned_metrics"][0]

    assert metric["metric_concept"] == "amount"
    assert metric["target_table"] == "schema_test.fact_metrics"
    assert metric["target_column"] == "measure_value"
    assert metric["aggregate"] is None
    assert metric["detection_source"] == "intent_semantic_evidence"
    assert metric["mapping_source"] == "entity_alias"
    assert metric["metric_ref"].startswith("metric-")


def test_financial_metric_sem_mapping_nao_inventa_metrica() -> None:
    projection = _metric_plan_for_term(
        context=_metric_context(),
        term="unmapped metric",
    )

    assert projection["planned_metrics"] == []
    assert projection["diagnostics"]["planned_metric_diagnostic"][
        "unresolved_terms"
    ] == ["unmapped metric"]


def test_financial_metric_canonical_inconsistente_rejeita() -> None:
    context = _metric_context()
    _append_metric_alias(
        context,
        user_term="divergent metric",
        canonical_value="amount",
        metric_concept="different",
    )

    projection = _metric_plan_for_term(
        context=context,
        term="divergent metric",
    )

    assert projection["planned_metrics"] == []


def test_financial_metric_target_table_inexistente_rejeita() -> None:
    context = _metric_context()
    _append_metric_alias(
        context,
        user_term="missing table metric",
        target_table="schema_test.missing_fact",
    )

    projection = _metric_plan_for_term(
        context=context,
        term="missing table metric",
    )

    assert projection["planned_metrics"] == []


def test_financial_metric_target_column_fora_de_metric_columns_rejeita() -> None:
    context = _metric_context()
    _append_metric_alias(
        context,
        user_term="invalid column metric",
        target_column="not_metric",
    )

    projection = _metric_plan_for_term(
        context=context,
        term="invalid column metric",
    )

    assert projection["planned_metrics"] == []


def test_financial_metric_com_aggregate_nao_e_projetada() -> None:
    context = _metric_context()
    _append_metric_alias(
        context,
        user_term="aggregate metric",
        aggregate="sum",
    )

    projection = _metric_plan_for_term(
        context=context,
        term="aggregate metric",
    )

    assert projection["planned_metrics"] == []


def test_ranking_recebe_metric_ref_quando_ha_uma_metrica() -> None:
    projection = _metric_plan_for_term(
        context=_metric_context(),
        term="amount",
        operation_term="highest",
    )

    metric = projection["planned_metrics"][0]
    operation = projection["analytical_operations"][0]

    assert operation["metric_ref"] == metric["metric_ref"]
    assert projection["diagnostics"]["analytical_operation_diagnostic"][
        "metric_binding"
    ]["status"] == "bound"


def test_ranking_com_multiplas_metricas_nao_escolhe_arbitrariamente() -> None:
    context = _metric_context()
    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="highest amount and volume",
        intent_resolution_result={
            "applied": True,
            "intent": "generic_test_intent",
            "best_candidate": {
                "intent_name": "generic_test_intent",
                "score": 120.0,
                "matches": [
                    {
                        "match_details": {
                            "concepts": [
                                _intent_metric_evidence(
                                    term="amount"
                                )["best_candidate"]["matches"][0][
                                    "match_details"
                                ]["concepts"][0],
                                _intent_metric_evidence(
                                    term="volume"
                                )["best_candidate"]["matches"][0][
                                    "match_details"
                                ]["concepts"][0],
                                _intent_operation_evidence(
                                    term="highest"
                                )["best_candidate"]["matches"][0][
                                    "match_details"
                                ]["concepts"][0],
                            ]
                        }
                    }
                ],
            },
            "candidates": [],
        },
    )
    projection = result["query_plan"]["planning_context"]

    assert len(projection["planned_metrics"]) == 2
    assert "metric_ref" not in projection["analytical_operations"][0]
    assert projection["diagnostics"]["analytical_operation_diagnostic"][
        "metric_binding"
    ]["status"] == "metric_ambiguous"


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
        "source": "none",
        "fallback_used": False,
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
    assert dimension["mapping_source"] == "entity_alias"
    assert dimension["detection_source"] == "planner_lexical_fallback"
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
    assert dimension["mapping_source"] == "entity_alias"
    assert dimension["detection_source"] == "planner_lexical_fallback"


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
        (
            "evidence semantica promove region",
            test_evidence_semantica_do_intent_promove_region_sem_por_literal,
        ),
        (
            "evidence semantica promove channel",
            test_evidence_semantica_do_intent_promove_channel,
        ),
        (
            "evidence explicita vence legado",
            test_evidence_semantica_explicita_vence_alias_legado,
        ),
        (
            "evidence de outro conceito nao vira dimensao",
            test_evidence_de_outro_conceito_nao_vira_dimensao,
        ),
        (
            "evidence incompleta nao inventa dimensao",
            test_evidence_semantica_incompleta_nao_inventa_dimensao,
        ),
        (
            "evidence operacional ranking desc",
            test_evidence_operacional_resolve_ranking_descendente,
        ),
        (
            "evidence operacional ranking asc",
            test_evidence_operacional_resolve_ranking_ascendente,
        ),
        (
            "evidence operacional sem alias",
            test_evidence_operacional_sem_alias_nao_inventa_operacao,
        ),
        (
            "metadata operacional invalida",
            test_metadata_operacional_invalida_nao_inventa_operacao,
        ),
        (
            "canonical operacional divergente",
            test_operacao_com_canonical_divergente_nao_e_projetada,
        ),
        (
            "requested limit bool invalido",
            test_requested_limit_bool_nao_e_projetado,
        ),
        (
            "requested limit inteiro valido",
            test_requested_limit_inteiro_positivo_e_valido,
        ),
        (
            "requested limit null valido",
            test_requested_limit_null_e_valido,
        ),
        (
            "financial metric evidence",
            test_financial_metric_evidence_resolve_planned_metric,
        ),
        (
            "financial metric sem mapping",
            test_financial_metric_sem_mapping_nao_inventa_metrica,
        ),
        (
            "financial metric canonical inconsistente",
            test_financial_metric_canonical_inconsistente_rejeita,
        ),
        (
            "financial metric target table inexistente",
            test_financial_metric_target_table_inexistente_rejeita,
        ),
        (
            "financial metric target column invalida",
            test_financial_metric_target_column_fora_de_metric_columns_rejeita,
        ),
        (
            "financial metric aggregate ausente",
            test_financial_metric_com_aggregate_nao_e_projetada,
        ),
        (
            "ranking metric ref",
            test_ranking_recebe_metric_ref_quando_ha_uma_metrica,
        ),
        (
            "ranking metric ambiguity",
            test_ranking_com_multiplas_metricas_nao_escolhe_arbitrariamente,
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

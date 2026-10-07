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
    context_concepts: list[str] | None = None,
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
    for concept_name in context_concepts or []:
        concepts.append(
            {
                "concept_name": concept_name,
                "satisfied": True,
                "terms": [
                    {
                        "term": concept_name,
                        "normalized_term": concept_name,
                        "matched": True,
                        "match_details": {
                            "semantic_signal": {
                                "concept_name": concept_name,
                                "term": concept_name,
                                "normalized_term": concept_name,
                                "source": "intent_catalog_concept",
                                "confidence": 1.0,
                                "matched_tokens": [concept_name],
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


def _intent_metric_operation_dimension_evidence(
    *,
    metric_term: str,
    operation_term: str,
    dimension_term: str | None = None,
    dimension_tokens: list[str] | None = None,
    context_concepts: list[str] | None = None,
) -> dict:
    evidence = _intent_metric_evidence(
        term=metric_term,
        operation_term=operation_term,
        context_concepts=context_concepts,
    )
    if dimension_term is not None:
        concepts = evidence["best_candidate"]["matches"][0]["match_details"][
            "concepts"
        ]
        concepts.append(
            {
                "concept_name": "dimension_grouping",
                "satisfied": True,
                "terms": [
                    {
                        "term": dimension_term,
                        "normalized_term": dimension_term,
                        "matched": True,
                        "match_details": {
                            "semantic_signal": {
                                "concept_name": "dimension_grouping",
                                "term": dimension_term,
                                "normalized_term": dimension_term,
                                "source": "intent_catalog_concept",
                                "confidence": 1.0,
                                "matched_tokens": (
                                    dimension_tokens or [dimension_term]
                                ),
                            }
                        },
                    }
                ],
            }
        )
    return evidence


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
    binding_cardinality: dict | None = None,
    output_behavior: str | None = None,
    combination_strategy: str | None = None,
    join_semantics: str | None = None,
) -> None:
    operation = {"operation_type": operation_type}
    if operation_type == "ranking":
        operation["direction"] = direction
        operation["requested_limit"] = requested_limit
    if output_behavior is not None:
        operation["output_behavior"] = output_behavior
    if combination_strategy is not None:
        operation["combination_strategy"] = combination_strategy
    if join_semantics is not None:
        operation["join_semantics"] = join_semantics
    if binding_cardinality is not None:
        operation["binding_cardinality"] = binding_cardinality
    context["entities"].append(
        {
            "entity_type": "analytical_operation",
            "user_term": user_term,
            "canonical_value": canonical_value,
            "target_table": None,
            "target_column": None,
            "sql_filter_hint": None,
            "business_rule": {"operation": operation},
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


def _append_metric_binding(
    context: dict,
    *,
    metric_concept: str = "amount",
    target_table: str = "schema_test.fact_metrics",
    target_column: str = "measure_value",
    when_present: list[str] | None = None,
    when_absent: list[str] | None = None,
    priority: int = 1,
    user_term: str = "binding",
) -> None:
    context["entities"].append(
        {
            "entity_type": "metric_binding",
            "user_term": user_term,
            "canonical_value": metric_concept,
            "target_table": target_table,
            "target_column": target_column,
            "sql_filter_hint": None,
            "business_rule": {
                "metric_binding": {
                    "metric_concept": metric_concept,
                    "target_table": target_table,
                    "target_column": target_column,
                    "when_present": when_present or ["mode_a"],
                    "when_absent": when_absent or [],
                    "aggregate": None,
                }
            },
            "priority": priority,
        }
    )


def _append_metric_table(
    context: dict,
    *,
    table_name: str,
    metric_columns: list[str],
    join_rules: list[dict] | None = None,
) -> None:
    context["table_catalog"].append(
        {
            "schema_name": "schema_test",
            "table_name": table_name,
            "table_type": "table",
            "description": "synthetic binding fact",
            "grain": None,
            "primary_key": ["row_id"],
            "key_columns": ["row_id"],
            "metric_columns": metric_columns,
            "date_columns": ["event_date"],
            "join_rules": join_rules or [],
            "ai_hint": None,
            "priority": 1,
            "columns": [{"name": column} for column in metric_columns],
        }
    )


def _comparison_cardinality() -> dict:
    return {
        "mode": "multiple",
        "minimum": 2,
        "maximum": 2,
        "same_metric_concept": True,
        "distinct_bindings": True,
    }


def _comparison_context(
    *,
    same_target: bool = False,
    reachable_dimension: bool = False,
    join_semantics: str | None = None,
) -> dict:
    context = _metric_context()
    _append_operation_alias(
        context,
        user_term="compare",
        canonical_value="comparison",
        operation_type="comparison",
        binding_cardinality=_comparison_cardinality(),
        output_behavior="side_by_side",
        combination_strategy="aggregate_then_combine",
        join_semantics=join_semantics,
    )
    table_a = "schema_test.fact_a"
    table_b = table_a if same_target else "schema_test.fact_b"
    column_a = "metric_x"
    column_b = "metric_y"
    join_rules = (
        [{"target_table": "schema_test.dim_region"}]
        if reachable_dimension
        else []
    )
    _append_metric_table(
        context,
        table_name="fact_a",
        metric_columns=["metric_x", "metric_y"] if same_target else ["metric_x"],
        join_rules=join_rules,
    )
    if not same_target:
        _append_metric_table(
            context,
            table_name="fact_b",
            metric_columns=["metric_y"],
            join_rules=join_rules,
        )
    _append_metric_binding(
        context,
        metric_concept="amount",
        target_table=table_a,
        target_column=column_a,
        when_present=["mode_a"],
        user_term="binding mode a",
        priority=20,
    )
    _append_metric_binding(
        context,
        metric_concept="amount",
        target_table=table_b,
        target_column=column_b,
        when_present=["mode_b"],
        user_term="binding mode b",
        priority=1,
    )
    return context


def _comparison_projection(
    context: dict,
    *,
    context_concepts: list[str] | None = None,
    dimension: bool = False,
) -> dict:
    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="compare amount",
        intent_resolution_result=_intent_metric_operation_dimension_evidence(
            metric_term="amount",
            operation_term="compare",
            dimension_term="region" if dimension else None,
            dimension_tokens=["region"] if dimension else None,
            context_concepts=context_concepts or ["mode_a", "mode_b"],
        ),
    )
    return result["query_plan"]["planning_context"]


def _comparison_projection_for_operation_terms(
    context: dict,
    *,
    operation_terms: list[str],
) -> dict:
    evidence = _intent_metric_evidence(
        term="amount",
        operation_term=operation_terms[0],
        context_concepts=["mode_a", "mode_b"],
    )
    concepts = evidence["best_candidate"]["matches"][0]["match_details"][
        "concepts"
    ]
    operation_concept = next(
        concept
        for concept in concepts
        if concept.get("concept_name") == "analytical_operation"
    )
    operation_concept["terms"] = [
        {
            "term": term,
            "normalized_term": term,
            "matched": True,
            "match_details": {
                "semantic_signal": {
                    "concept_name": "analytical_operation",
                    "term": term,
                    "normalized_term": term,
                    "source": "intent_catalog_concept",
                    "confidence": 1.0,
                    "matched_tokens": [term],
                }
            },
        }
        for term in operation_terms
    ]

    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="compare amount",
        intent_resolution_result=evidence,
    )
    return result["query_plan"]["planning_context"]


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
    context_concepts: list[str] | None = None,
) -> dict:
    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question=f"{operation_term or ''} {term}".strip(),
        intent_resolution_result=_intent_metric_evidence(
            term=term,
            operation_term=operation_term,
            context_concepts=context_concepts,
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


def test_join_rule_com_target_nao_selecionado_e_removida() -> None:
    context = _context()
    context["table_catalog"][0]["join_rules"] = [
        {
            "source_table": "schema_test.table_test",
            "target_table": "schema_test.table_other",
            "condition": "generic",
        },
        {
            "source_table": "schema_test.table_test",
            "target_table": "schema_test.table_test",
            "condition": "self generic",
        },
    ]

    plan = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="generic analysis",
    )

    join_rules = plan["query_plan"]["planning_context"]["authorized_joins"][0][
        "join_rules"
    ]
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


def test_metric_binding_single_aplica_corretamente() -> None:
    context = _metric_context()
    _append_metric_binding(context, when_present=["mode_a"])

    projection = _metric_plan_for_term(
        context=context,
        term="amount",
        context_concepts=["mode_a"],
    )

    metric = projection["planned_metrics"][0]
    diagnostic = projection["diagnostics"]["planned_metric_diagnostic"]

    assert metric["mapping_source"] == "metric_binding"
    assert metric["target_column"] == "measure_value"
    assert metric["binding_ref"].startswith("binding-")
    assert metric["binding_conditions"]["when_present"] == ["mode_a"]
    assert diagnostic["binding_failures"] == []


def test_metric_binding_nao_aplica_sem_when_present() -> None:
    context = _metric_context()
    _append_metric_binding(context, when_present=["mode_a"])

    projection = _metric_plan_for_term(context=context, term="amount")

    assert projection["planned_metrics"] == []
    failure = projection["diagnostics"]["planned_metric_diagnostic"][
        "binding_failures"
    ][0]["binding_diagnostics"][0]
    assert failure["status"] == "metric_binding_not_applicable"


def test_metric_binding_nao_aplica_com_when_absent_presente() -> None:
    context = _metric_context()
    _append_metric_binding(
        context,
        when_present=["mode_a"],
        when_absent=["mode_b"],
    )

    projection = _metric_plan_for_term(
        context=context,
        term="amount",
        context_concepts=["mode_a", "mode_b"],
    )

    assert projection["planned_metrics"] == []
    failure = projection["diagnostics"]["planned_metric_diagnostic"][
        "binding_failures"
    ][0]["binding_diagnostics"][0]
    assert failure["status"] == "metric_binding_not_applicable"


def test_metric_binding_single_multiplos_targets_falha_fechado() -> None:
    context = _metric_context()
    _append_metric_table(
        context,
        table_name="fact_alternate",
        metric_columns=["alternate_value"],
    )
    _append_metric_binding(
        context,
        user_term="binding a",
        target_column="measure_value",
        when_present=["mode_a"],
        priority=1,
    )
    _append_metric_binding(
        context,
        user_term="binding b",
        target_table="schema_test.fact_alternate",
        target_column="alternate_value",
        when_present=["mode_a"],
        priority=99,
    )

    projection = _metric_plan_for_term(
        context=context,
        term="amount",
        context_concepts=["mode_a"],
    )

    assert projection["planned_metrics"] == []
    failure = projection["diagnostics"]["planned_metric_diagnostic"][
        "binding_failures"
    ][0]["binding_diagnostics"][0]
    assert failure["status"] == "metric_binding_ambiguous"


def test_metric_binding_single_mesmo_target_conditions_diferentes_ambiguous() -> None:
    context = _metric_context()
    _append_metric_binding(
        context,
        user_term="binding a",
        target_column="measure_value",
        when_present=["mode_a"],
    )
    _append_metric_binding(
        context,
        user_term="binding b",
        target_column="measure_value",
        when_present=["mode_b"],
    )

    projection = _metric_plan_for_term(
        context=context,
        term="amount",
        context_concepts=["mode_a", "mode_b"],
    )

    assert projection["planned_metrics"] == []
    failure = projection["diagnostics"]["planned_metric_diagnostic"][
        "binding_failures"
    ][0]["binding_diagnostics"][0]
    assert failure["status"] == "metric_binding_ambiguous"


def test_metric_binding_equivalente_deduplica() -> None:
    context = _metric_context()
    _append_metric_binding(
        context,
        user_term="binding a",
        when_present=["mode_a"],
    )
    _append_metric_binding(
        context,
        user_term="binding b",
        when_present=["mode_a"],
    )

    projection = _metric_plan_for_term(
        context=context,
        term="amount",
        context_concepts=["mode_a"],
    )

    assert len(projection["planned_metrics"]) == 1
    diagnostic = projection["diagnostics"]["planned_metric_diagnostic"]
    assert diagnostic["projected_count"] == 1


def test_metric_binding_multi_min_max_resolve_duas_metricas() -> None:
    context = _metric_context()
    _append_metric_table(
        context,
        table_name="fact_alternate",
        metric_columns=["alternate_value"],
    )
    _append_metric_binding(
        context,
        target_column="measure_value",
        when_present=["mode_a"],
    )
    _append_metric_binding(
        context,
        target_table="schema_test.fact_alternate",
        target_column="alternate_value",
        when_present=["mode_b"],
    )
    _append_operation_alias(
        context,
        user_term="compare",
        binding_cardinality={
            "mode": "multiple",
            "minimum": 2,
            "maximum": 2,
            "same_metric_concept": True,
            "distinct_bindings": True,
        },
    )

    projection = _metric_plan_for_term(
        context=context,
        term="amount",
        operation_term="compare",
        context_concepts=["mode_a", "mode_b"],
    )

    assert len(projection["planned_metrics"]) == 2
    assert {
        metric["target_column"] for metric in projection["planned_metrics"]
    } == {"measure_value", "alternate_value"}
    assert projection["diagnostics"]["planned_metric_diagnostic"][
        "binding_cardinality"
    ]["mode"] == "multiple"


def test_metric_binding_multi_abaixo_do_minimo_falha_fechado() -> None:
    context = _metric_context()
    _append_metric_binding(context, when_present=["mode_a"])
    _append_operation_alias(
        context,
        user_term="compare",
        binding_cardinality={
            "mode": "multiple",
            "minimum": 2,
            "maximum": 2,
            "same_metric_concept": True,
            "distinct_bindings": True,
        },
    )

    projection = _metric_plan_for_term(
        context=context,
        term="amount",
        operation_term="compare",
        context_concepts=["mode_a"],
    )

    assert projection["planned_metrics"] == []
    failure = projection["diagnostics"]["planned_metric_diagnostic"][
        "binding_failures"
    ][0]["binding_diagnostics"][0]
    assert failure["status"] == "metric_binding_below_minimum"


def test_metric_binding_multi_acima_do_maximo_falha_fechado() -> None:
    context = _metric_context()
    _append_metric_table(
        context,
        table_name="fact_alternate",
        metric_columns=["alternate_value"],
    )
    _append_metric_table(
        context,
        table_name="fact_extra",
        metric_columns=["extra_value"],
    )
    _append_metric_binding(
        context,
        target_column="measure_value",
        when_present=["mode_a"],
    )
    _append_metric_binding(
        context,
        target_table="schema_test.fact_alternate",
        target_column="alternate_value",
        when_present=["mode_b"],
    )
    _append_metric_binding(
        context,
        target_table="schema_test.fact_extra",
        target_column="extra_value",
        when_present=["mode_c"],
    )
    _append_operation_alias(
        context,
        user_term="compare",
        binding_cardinality={
            "mode": "multiple",
            "minimum": 1,
            "maximum": 2,
            "same_metric_concept": True,
            "distinct_bindings": True,
        },
    )

    projection = _metric_plan_for_term(
        context=context,
        term="amount",
        operation_term="compare",
        context_concepts=["mode_a", "mode_b", "mode_c"],
    )

    assert projection["planned_metrics"] == []
    failure = projection["diagnostics"]["planned_metric_diagnostic"][
        "binding_failures"
    ][0]["binding_diagnostics"][0]
    assert failure["status"] == "metric_binding_above_maximum"


def test_metric_binding_global_acima_do_maximo_nao_entrega_metricas() -> None:
    context = _metric_context()
    _append_metric_table(
        context,
        table_name="fact_alternate",
        metric_columns=["alternate_value"],
    )
    _append_metric_binding(
        context,
        metric_concept="amount",
        target_column="measure_value",
        when_present=["mode_a"],
    )
    _append_metric_binding(
        context,
        metric_concept="amount",
        target_table="schema_test.fact_alternate",
        target_column="alternate_value",
        when_present=["mode_b"],
    )
    _append_metric_binding(
        context,
        metric_concept="volume",
        target_column="volume_value",
        when_present=["mode_c"],
    )
    _append_operation_alias(
        context,
        user_term="compare",
        binding_cardinality={
            "mode": "multiple",
            "minimum": 1,
            "maximum": 2,
            "same_metric_concept": False,
            "distinct_bindings": True,
        },
    )
    concepts = [
        _intent_metric_evidence(term="amount")["best_candidate"][
            "matches"
        ][0]["match_details"]["concepts"][0],
        _intent_metric_evidence(term="volume")["best_candidate"][
            "matches"
        ][0]["match_details"]["concepts"][0],
        _intent_operation_evidence(term="compare")["best_candidate"][
            "matches"
        ][0]["match_details"]["concepts"][0],
    ]
    concepts.extend(
        {
            "concept_name": concept,
            "satisfied": True,
            "terms": [],
        }
        for concept in ("mode_a", "mode_b", "mode_c")
    )

    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="synthetic multiple metrics",
        intent_resolution_result={
            "applied": True,
            "intent": "generic_test_intent",
            "best_candidate": {
                "intent_name": "generic_test_intent",
                "score": 120.0,
                "matches": [{"match_details": {"concepts": concepts}}],
            },
            "candidates": [],
        },
    )
    projection = result["query_plan"]["planning_context"]

    assert projection["planned_metrics"] == []
    assert projection["diagnostics"]["planned_metric_diagnostic"][
        "binding_failures"
    ][0]["status"] == "metric_binding_above_maximum"


def test_metric_binding_target_invalido_rejeita() -> None:
    context = _metric_context()
    _append_metric_binding(
        context,
        target_column="missing_metric",
        when_present=["mode_a"],
    )

    projection = _metric_plan_for_term(
        context=context,
        term="amount",
        context_concepts=["mode_a"],
    )

    assert projection["planned_metrics"] == []
    failure = projection["diagnostics"]["planned_metric_diagnostic"][
        "binding_failures"
    ][0]["binding_diagnostics"][0]
    assert failure["rejected"][0]["reason"] == "invalid_physical_target"


def test_metric_binding_ref_deterministico() -> None:
    context = _metric_context()
    _append_metric_binding(context, when_present=["mode_a", "mode_b"])

    first = _metric_plan_for_term(
        context=context,
        term="amount",
        context_concepts=["mode_a", "mode_b"],
    )["planned_metrics"][0]
    second = _metric_plan_for_term(
        context=context,
        term="amount",
        context_concepts=["mode_b", "mode_a"],
    )["planned_metrics"][0]

    assert first["binding_ref"] == second["binding_ref"]


def test_metric_binding_semantic_default_satisfaz_when_present() -> None:
    context = _metric_context()
    _append_metric_binding(context, when_present=["mode_default"])
    evidence = _intent_metric_evidence(term="amount")
    evidence["best_candidate"]["matches"][0]["match_details"][
        "concepts"
    ].append(
        {
            "concept_name": "mode_default",
            "satisfied": True,
            "terms": [],
            "semantic_signals": [
                {
                    "concept_name": "mode_default",
                    "source": "semantic_default",
                    "rule_name": "default_rule",
                    "priority": 1,
                    "explicit_vs_default": "default",
                }
            ],
        }
    )

    result = build_query_plan(
        context=context,
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="amount",
        intent_resolution_result=evidence,
    )

    metric = result["query_plan"]["planning_context"]["planned_metrics"][0]
    assert metric["mapping_source"] == "metric_binding"


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


def test_comparison_metadata_e_aceita_pelo_planner() -> None:
    projection = _comparison_projection(_comparison_context())

    operation = projection["analytical_operations"][0]

    assert operation["operation_type"] == "comparison"
    assert operation["canonical_value"] == "comparison"
    assert operation["output_behavior"] == "side_by_side"
    assert operation["combination_strategy"] == "aggregate_then_combine"
    assert operation["binding_cardinality"] == _comparison_cardinality()


def test_comparison_preserva_join_semantics_string_versionada() -> None:
    projection = _comparison_projection(
        _comparison_context(
            join_semantics="preserve_all_operand_categories",
        )
    )

    operation = projection["analytical_operations"][0]

    assert operation["join_semantics"] == "preserve_all_operand_categories"


def test_comparison_sem_join_semantics_nao_inventa_default() -> None:
    projection = _comparison_projection(_comparison_context())

    assert "join_semantics" not in projection["analytical_operations"][0]


def test_comparison_join_semantics_participa_do_dedupe() -> None:
    context = _comparison_context(
        join_semantics="preserve_all_operand_categories",
    )
    _append_operation_alias(
        context,
        user_term="compare differently",
        canonical_value="comparison",
        operation_type="comparison",
        binding_cardinality=_comparison_cardinality(),
        output_behavior="side_by_side",
        combination_strategy="aggregate_then_combine",
        join_semantics="preserve_intersection_only",
    )

    projection = _comparison_projection_for_operation_terms(
        context,
        operation_terms=["compare", "compare differently"],
    )

    join_semantics = {
        operation.get("join_semantics")
        for operation in projection["analytical_operations"]
    }
    assert join_semantics == {
        "preserve_all_operand_categories",
        "preserve_intersection_only",
    }


def test_comparison_join_semantics_tipo_invalido_falha_fechado() -> None:
    context = _comparison_context()
    for entity in context["entities"]:
        if entity.get("user_term") == "compare":
            entity["business_rule"]["operation"]["join_semantics"] = {
                "mode": "preserve_all_operand_categories"
            }

    projection = _comparison_projection(context)

    assert projection["analytical_operations"] == []
    assert projection["diagnostics"]["analytical_operation_diagnostic"][
        "unresolved_terms"
    ] == ["compare"]


def test_comparison_cardinality_multiple_min_max_resolve() -> None:
    projection = _comparison_projection(_comparison_context())

    assert len(projection["planned_metrics"]) == 2
    assert projection["diagnostics"]["planned_metric_diagnostic"][
        "global_binding_status"
    ] == "resolved"
    assert projection["diagnostics"]["analytical_operation_diagnostic"][
        "metric_binding"
    ]["status"] == "bound"


def test_comparison_duas_bindings_distintas_mesmo_metric_concept_passam() -> None:
    projection = _comparison_projection(_comparison_context())

    concepts = {
        metric["metric_concept"] for metric in projection["planned_metrics"]
    }
    binding_refs = {
        metric["binding_ref"] for metric in projection["planned_metrics"]
    }

    assert concepts == {"amount"}
    assert len(binding_refs) == 2


def test_comparison_binding_duplicada_distinct_bindings_falha_fechado() -> None:
    context = _comparison_context()
    for entity in context["entities"]:
        if entity.get("user_term") == "binding mode b":
            metric = entity["business_rule"]["metric_binding"]
            metric["target_table"] = "schema_test.fact_a"
            metric["target_column"] = "metric_x"
            entity["target_table"] = "schema_test.fact_a"
            entity["target_column"] = "metric_x"

    projection = _comparison_projection(context)

    assert projection["planned_metrics"] == []
    assert projection["analytical_operations"][0].get("operand_metric_refs") is None
    assert projection["diagnostics"]["planned_metric_diagnostic"][
        "global_binding_status"
    ] in {
        "metric_binding_ambiguous",
        "metric_binding_below_minimum",
    }


def test_comparison_menos_operandos_que_minimo_falha_fechado() -> None:
    projection = _comparison_projection(
        _comparison_context(),
        context_concepts=["mode_a"],
    )

    assert projection["planned_metrics"] == []
    assert projection["analytical_operations"][0].get("operand_metric_refs") is None
    assert projection["diagnostics"]["planned_metric_diagnostic"][
        "global_binding_status"
    ] == "not_applicable"
    assert projection["diagnostics"]["planned_metric_diagnostic"][
        "invalid_metadata_terms"
    ] == ["amount"]


def test_comparison_mais_operandos_que_maximo_falha_fechado() -> None:
    context = _comparison_context()
    _append_metric_table(context, table_name="fact_c", metric_columns=["metric_z"])
    _append_metric_binding(
        context,
        metric_concept="amount",
        target_table="schema_test.fact_c",
        target_column="metric_z",
        when_present=["mode_c"],
        user_term="binding mode c",
        priority=5,
    )

    projection = _comparison_projection(
        context,
        context_concepts=["mode_a", "mode_b", "mode_c"],
    )

    assert projection["planned_metrics"] == []
    assert projection["analytical_operations"][0].get("operand_metric_refs") is None
    assert projection["diagnostics"]["planned_metric_diagnostic"][
        "global_binding_status"
    ] == "not_applicable"
    assert projection["diagnostics"]["planned_metric_diagnostic"][
        "invalid_metadata_terms"
    ] == ["amount"]


def test_comparison_operand_metric_refs_correspondem_as_metricas_validas() -> None:
    projection = _comparison_projection(_comparison_context())
    operation = projection["analytical_operations"][0]

    metric_refs = {
        metric["metric_ref"] for metric in projection["planned_metrics"]
    }

    assert set(operation["operand_metric_refs"]) == metric_refs
    assert len(operation["operand_metric_refs"]) == len(metric_refs)


def test_comparison_ordem_deterministica_sem_semantica_de_priority() -> None:
    projection = _comparison_projection(_comparison_context())
    operation = projection["analytical_operations"][0]

    assert operation["operand_metric_refs"] == sorted(
        operation["operand_metric_refs"]
    )
    assert [
        metric["metric_ref"] for metric in projection["planned_metrics"]
    ] == sorted(metric["metric_ref"] for metric in projection["planned_metrics"])


def test_comparison_sem_dimensao_e_valida() -> None:
    projection = _comparison_projection(_comparison_context())

    assert projection["detected_dimensions"] == []
    assert projection["analytical_operations"][0]["operand_metric_refs"]
    assert projection["diagnostics"]["analytical_operation_diagnostic"][
        "dimension_compatibility"
    ]["status"] == "passed"


def test_comparison_com_dimensao_alcancavel_por_todos_operandos_e_valida() -> None:
    context = _comparison_context(reachable_dimension=True)
    projection = _comparison_projection(context, dimension=True)

    dimension = projection["detected_dimensions"][0]

    assert dimension["canonical_value"] == "region"
    assert projection["analytical_operations"][0]["operand_metric_refs"]
    assert projection["diagnostics"]["analytical_operation_diagnostic"][
        "dimension_compatibility"
    ]["status"] == "passed"


def test_comparison_com_dimensao_inalcancavel_falha_fechado() -> None:
    projection = _comparison_projection(_comparison_context(), dimension=True)

    assert projection["planned_metrics"] == []
    assert projection["analytical_operations"][0].get("operand_metric_refs") is None
    assert projection["diagnostics"]["analytical_operation_diagnostic"][
        "dimension_compatibility"
    ]["status"] == "failed"


def test_comparison_multiplas_fontes_metricas_true() -> None:
    projection = _comparison_projection(_comparison_context())

    assert projection["analytical_operations"][0][
        "multiple_metric_sources"
    ] is True


def test_comparison_mesma_fonte_metrica_false() -> None:
    projection = _comparison_projection(_comparison_context(same_target=True))

    assert projection["analytical_operations"][0][
        "multiple_metric_sources"
    ] is False


def test_comparison_preserva_regressao_de_ranking() -> None:
    projection = _metric_plan_for_term(
        context=_metric_context(),
        term="amount",
        operation_term="highest",
    )

    operation = projection["analytical_operations"][0]

    assert operation["operation_type"] == "ranking"
    assert operation["direction"] == "descending"
    assert operation["metric_ref"] == projection["planned_metrics"][0][
        "metric_ref"
    ]


def test_contexto_sem_comparison_preserva_fluxo_antigo() -> None:
    projection = _metric_plan_for_term(context=_metric_context(), term="amount")

    assert projection["planned_metrics"]
    assert projection["analytical_operations"] == []


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


def _planned_filter_evidence(*terms: str) -> dict:
    return {
        "applied": True,
        "intent": "generic_test_intent",
        "best_candidate": {
            "intent_name": "generic_test_intent",
            "matches": [
                {
                    "match_details": {
                        "concepts": [
                            {
                                "concept_name": "synthetic_filter_category",
                                "satisfied": True,
                                "terms": [
                                    {
                                        "normalized_term": term,
                                        "matched": True,
                                    }
                                    for term in terms
                                ],
                            }
                        ]
                    }
                }
            ],
        },
        "candidates": [],
    }


def _append_filter_alias(context: dict, term: str, concept: str) -> None:
    context["entities"].append(
        {
            "entity_type": "filter_concept",
            "user_term": term,
            "canonical_value": concept,
            "priority": 1,
        }
    )


def _append_filter_binding(
    context: dict,
    concept: str,
    ref: str,
    **binding_overrides: object,
) -> None:
    binding = {
        "binding_ref": ref,
        "filter_concept": concept,
        "required": True,
        "scope": "query",
        "target_table": "schema_test.table_test",
        "target_column": "value",
        "operator": "equals",
        "value": f"synthetic-{concept}",
        "join_path": [],
    }
    binding.update(binding_overrides)
    context["entities"].append(
        {
            "entity_type": "filter_binding",
            "canonical_value": concept,
            "business_rule": {
                "filter_binding": binding,
            },
        }
    )


def _planned_filters(context: dict, *terms: str) -> tuple[list[dict], dict]:
    projection = project_planning_context(
        context=context,
        intent_name="generic_test_intent",
        normalized_question="synthetic request",
        selected_pattern=_pattern(),
        intent_resolution_result=_planned_filter_evidence(*terms),
    )
    return (
        projection["planned_filters"],
        projection["diagnostics"]["planned_filter_diagnostic"],
    )


def test_planned_filter_categoria_sintetica_a() -> None:
    context = _context()
    _append_filter_alias(context, "class alpha", "concept_alpha")
    _append_filter_binding(context, "concept_alpha", "binding-alpha-v1")

    filters, diagnostic = _planned_filters(context, "class alpha")

    assert filters == [
        {
            "filter_ref": "filter-binding-alpha-v1",
            "filter_concept": "concept_alpha",
            "binding_ref": "binding-alpha-v1",
            "required": True,
            "scope": "query",
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "filter_binding",
            "matched_user_term": "class alpha",
            "provenance": {
                "context_version": "context-test-v1",
                "binding_source": "entity_alias",
            },
        }
    ]
    assert diagnostic["status"] == "resolved"
    for physical_field in (
        "target_table", "target_column", "operator", "value", "join_path"
    ):
        assert physical_field not in filters[0]


def test_planned_filter_sinonimo_preserva_conceito() -> None:
    context = _context()
    _append_filter_alias(context, "class alpha", "concept_alpha")
    _append_filter_alias(context, "alpha synonym", "concept_alpha")
    _append_filter_binding(context, "concept_alpha", "binding-alpha-v1")
    filters, _ = _planned_filters(context, "alpha synonym")
    assert filters[0]["filter_concept"] == "concept_alpha"


def test_planned_filter_categoria_b_vem_do_contexto() -> None:
    context = _context()
    _append_filter_alias(context, "class beta", "concept_beta")
    _append_filter_binding(context, "concept_beta", "binding-beta-v1")
    filters, _ = _planned_filters(context, "class beta")
    assert filters[0]["binding_ref"] == "binding-beta-v1"


def test_planned_filter_termo_generico_nao_inventa_filtro() -> None:
    filters, diagnostic = _planned_filters(_context(), "aggregate amount")
    assert filters == []
    assert diagnostic["status"] == "not_applicable"


def test_planned_filter_conceito_sem_binding_falha_fechado() -> None:
    context = _context()
    _append_filter_alias(context, "class alpha", "concept_alpha")
    filters, diagnostic = _planned_filters(context, "class alpha")
    assert filters == []
    assert diagnostic["unresolved"] == [
        {
            "filter_concept": "concept_alpha",
            "matched_user_term": "class alpha",
            "reason": "binding_not_found",
        }
    ]


def test_planned_filter_binding_invalido_falha_fechado() -> None:
    invalid_fields = {
        "target_table": None,
        "target_column": " ",
        "operator": 7,
        "required": "true",
        "value": float("inf"),
        "join_path": "schema_test.table_test",
    }
    for field, invalid_value in invalid_fields.items():
        context = _context()
        _append_filter_alias(context, "class alpha", "concept_alpha")
        _append_filter_binding(
            context,
            "concept_alpha",
            "binding-alpha-v1",
            **{field: invalid_value},
        )

        filters, diagnostic = _planned_filters(context, "class alpha")

        assert filters == [], field
        assert diagnostic["unresolved"][0]["reason"] == "binding_not_found"

    context = _context()
    _append_filter_alias(context, "class alpha", "concept_alpha")
    _append_filter_binding(context, "concept_alpha", "binding-alpha-v1")
    del context["entities"][-1]["business_rule"]["filter_binding"]["value"]

    filters, diagnostic = _planned_filters(context, "class alpha")

    assert filters == []
    assert diagnostic["unresolved"][0]["reason"] == "binding_not_found"


def test_planned_filter_binding_multi_valor_generico() -> None:
    context = _context()
    _append_filter_alias(context, "class alpha", "concept_alpha")
    _append_filter_binding(
        context,
        "concept_alpha",
        "binding-alpha-v2",
        operator="IN",
        value=["synthetic-a", "synthetic-b"],
    )
    projection = project_planning_context(
        context=context,
        intent_name="generic_test_intent",
        normalized_question="synthetic request",
        selected_pattern=_pattern(),
        intent_resolution_result=_planned_filter_evidence("class alpha"),
    )
    assert projection["planned_filters"][0]["binding_ref"] == "binding-alpha-v2"
    assert projection["resolved_filter_bindings"] == [
        {
            "binding_ref": "binding-alpha-v2",
            "filter_concept": "concept_alpha",
            "target_table": "schema_test.table_test",
            "target_column": "value",
            "operator": "IN",
            "value": ["synthetic-a", "synthetic-b"],
            "join_path": [],
            "required": True,
            "scope": "query",
        }
    ]


def test_planned_filter_binding_multi_valor_invalido_falha_fechado() -> None:
    invalid_values = (
        [],
        ["synthetic-a", 1],
        ["synthetic-a", "synthetic-a"],
        ["synthetic-a", None],
    )
    for value in invalid_values:
        context = _context()
        _append_filter_alias(context, "class alpha", "concept_alpha")
        _append_filter_binding(
            context,
            "concept_alpha",
            "binding-alpha-v2",
            operator="IN",
            value=value,
        )
        filters, diagnostic = _planned_filters(context, "class alpha")
        assert filters == [], value
        assert diagnostic["unresolved"][0]["reason"] == "binding_not_found"

    context = _context()
    _append_filter_alias(context, "class alpha", "concept_alpha")
    _append_filter_binding(
        context,
        "concept_alpha",
        "binding-alpha-v2",
        operator="=",
        value=["synthetic-a", "synthetic-b"],
    )
    filters, diagnostic = _planned_filters(context, "class alpha")
    assert filters == []
    assert diagnostic["unresolved"][0]["reason"] == "binding_not_found"


def test_planned_filter_binding_ref_duplicado_e_ambiguo() -> None:
    context = _context()
    _append_filter_alias(context, "class alpha", "concept_alpha")
    _append_filter_binding(context, "concept_alpha", "binding-alpha-v1")
    _append_filter_binding(
        context,
        "concept_alpha",
        "BINDING-ALPHA-V1",
        value="synthetic-conflict",
    )

    filters, diagnostic = _planned_filters(context, "class alpha")

    assert filters == []
    assert diagnostic["unresolved"][0]["reason"] == "binding_ambiguous"


def test_planned_filters_duas_categorias_ordem_deterministica() -> None:
    context = _context()
    _append_filter_alias(context, "class beta", "concept_beta")
    _append_filter_binding(context, "concept_beta", "binding-beta-v1")
    _append_filter_alias(context, "class alpha", "concept_alpha")
    _append_filter_binding(context, "concept_alpha", "binding-alpha-v1")
    first, _ = _planned_filters(context, "class beta", "class alpha")
    second, _ = _planned_filters(context, "class alpha", "class beta")
    assert first == second
    assert [item["filter_concept"] for item in first] == [
        "concept_alpha", "concept_beta"
    ]


def test_planned_filters_vazio_preserva_compatibilidade() -> None:
    projection = project_planning_context(
        context=_context(),
        intent_name="generic_test_intent",
        normalized_question="generic analysis",
        selected_pattern=_pattern(),
    )
    assert projection["planned_filters"] == []
    assert projection["diagnostics"]["planned_filter_diagnostic"][
        "status"
    ] == "not_applicable"


def main() -> None:
    tests = [
        test_join_rule_com_target_nao_selecionado_e_removida,
        ("planned filter categoria A", test_planned_filter_categoria_sintetica_a),
        ("planned filter sinonimo", test_planned_filter_sinonimo_preserva_conceito),
        ("planned filter categoria B", test_planned_filter_categoria_b_vem_do_contexto),
        ("planned filter termo generico", test_planned_filter_termo_generico_nao_inventa_filtro),
        ("planned filter unresolved", test_planned_filter_conceito_sem_binding_falha_fechado),
        ("planned filter binding invalido", test_planned_filter_binding_invalido_falha_fechado),
        ("planned filter multi valor", test_planned_filter_binding_multi_valor_generico),
        ("planned filter multi valor invalido", test_planned_filter_binding_multi_valor_invalido_falha_fechado),
        ("planned filter binding ambiguo", test_planned_filter_binding_ref_duplicado_e_ambiguo),
        ("planned filters deterministicos", test_planned_filters_duas_categorias_ordem_deterministica),
        ("planned filters vazio", test_planned_filters_vazio_preserva_compatibilidade),
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
            "metric binding single",
            test_metric_binding_single_aplica_corretamente,
        ),
        (
            "metric binding sem when_present",
            test_metric_binding_nao_aplica_sem_when_present,
        ),
        (
            "metric binding bloqueado por when_absent",
            test_metric_binding_nao_aplica_com_when_absent_presente,
        ),
        (
            "metric binding single ambiguo",
            test_metric_binding_single_multiplos_targets_falha_fechado,
        ),
        (
            "metric binding single mesmo target conditions diferentes ambiguo",
            test_metric_binding_single_mesmo_target_conditions_diferentes_ambiguous,
        ),
        (
            "metric binding dedupe equivalente",
            test_metric_binding_equivalente_deduplica,
        ),
        (
            "metric binding multiple",
            test_metric_binding_multi_min_max_resolve_duas_metricas,
        ),
        (
            "metric binding multiple abaixo minimo",
            test_metric_binding_multi_abaixo_do_minimo_falha_fechado,
        ),
        (
            "metric binding multiple acima maximo",
            test_metric_binding_multi_acima_do_maximo_falha_fechado,
        ),
        (
            "metric binding global acima maximo",
            test_metric_binding_global_acima_do_maximo_nao_entrega_metricas,
        ),
        (
            "metric binding target invalido",
            test_metric_binding_target_invalido_rejeita,
        ),
        (
            "metric binding ref deterministico",
            test_metric_binding_ref_deterministico,
        ),
        (
            "metric binding semantic default",
            test_metric_binding_semantic_default_satisfaz_when_present,
        ),
        (
            "ranking metric ref",
            test_ranking_recebe_metric_ref_quando_ha_uma_metrica,
        ),
        (
            "ranking metric ambiguity",
            test_ranking_com_multiplas_metricas_nao_escolhe_arbitrariamente,
        ),
        (
            "comparison metadata",
            test_comparison_metadata_e_aceita_pelo_planner,
        ),
        (
            "comparison join semantics string",
            test_comparison_preserva_join_semantics_string_versionada,
        ),
        (
            "comparison sem join semantics default",
            test_comparison_sem_join_semantics_nao_inventa_default,
        ),
        (
            "comparison join semantics dedupe",
            test_comparison_join_semantics_participa_do_dedupe,
        ),
        (
            "comparison join semantics invalido",
            test_comparison_join_semantics_tipo_invalido_falha_fechado,
        ),
        (
            "comparison cardinality multiple",
            test_comparison_cardinality_multiple_min_max_resolve,
        ),
        (
            "comparison metric concept compartilhado",
            test_comparison_duas_bindings_distintas_mesmo_metric_concept_passam,
        ),
        (
            "comparison binding duplicada fail closed",
            test_comparison_binding_duplicada_distinct_bindings_falha_fechado,
        ),
        (
            "comparison abaixo minimo",
            test_comparison_menos_operandos_que_minimo_falha_fechado,
        ),
        (
            "comparison acima maximo",
            test_comparison_mais_operandos_que_maximo_falha_fechado,
        ),
        (
            "comparison operand refs",
            test_comparison_operand_metric_refs_correspondem_as_metricas_validas,
        ),
        (
            "comparison ordem deterministica",
            test_comparison_ordem_deterministica_sem_semantica_de_priority,
        ),
        (
            "comparison sem dimensao",
            test_comparison_sem_dimensao_e_valida,
        ),
        (
            "comparison dimensao alcancavel",
            test_comparison_com_dimensao_alcancavel_por_todos_operandos_e_valida,
        ),
        (
            "comparison dimensao inalcancavel",
            test_comparison_com_dimensao_inalcancavel_falha_fechado,
        ),
        (
            "comparison multiplas fontes",
            test_comparison_multiplas_fontes_metricas_true,
        ),
        (
            "comparison mesma fonte",
            test_comparison_mesma_fonte_metrica_false,
        ),
        (
            "comparison regressao ranking",
            test_comparison_preserva_regressao_de_ranking,
        ),
        (
            "comparison ausente regressao",
            test_contexto_sem_comparison_preserva_fluxo_antigo,
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

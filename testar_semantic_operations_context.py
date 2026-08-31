from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

from app.domain.context_normalizer import normalize_context_snapshot
from app.domain.intent_resolver import resolve_intent
from app.domain.planner import build_query_plan
from app.domain.search_text import normalize_search_text


SEMANTIC_VERSION = (
    "v2.0-ducklake-query-generator-semantic-operations-v1"
)
GENERIC_INTENT = "metric_total_by_period"
MIGRATION_PATH = (
    Path(__file__).resolve().parent
    / "scripts"
    / "migrations"
    / "002_prepare_semantic_operations_context_v1.sql"
)
MIGRATION_V2_PATH = (
    Path(__file__).resolve().parent
    / "scripts"
    / "migrations"
    / "003_prepare_semantic_operations_context_v2.sql"
)
MIGRATION_V3_PATH = (
    Path(__file__).resolve().parent
    / "scripts"
    / "migrations"
    / "004_prepare_semantic_operations_context_v3.sql"
)
MIGRATION_V4_PATH = (
    Path(__file__).resolve().parent
    / "scripts"
    / "migrations"
    / "005_prepare_semantic_dimensions_context_v4.sql"
)
MIGRATION_V5_PATH = (
    Path(__file__).resolve().parent
    / "scripts"
    / "migrations"
    / "006_prepare_semantic_generalization_context_v5.sql"
)
MIGRATION_V5_DEDUP_PATH = (
    Path(__file__).resolve().parent
    / "scripts"
    / "migrations"
    / "007_prepare_semantic_generalization_context_v5_dedup.sql"
)
MIGRATION_V6_PATH = (
    Path(__file__).resolve().parent
    / "scripts"
    / "migrations"
    / "008_prepare_semantic_analytical_operations_context_v6.sql"
)


def _resolver_config_rule() -> dict:
    return {
        "rule_group": "config",
        "rule_name": "intent_resolver",
        "rule_content": {
            "component": "intent_resolver",
            "minimum_score": 100,
            "ambiguity_margin": 20,
            "applied_confidence": 0.98,
            "fallback_to_previous_intent": False,
            "token_fallback": {"enabled": False},
        },
        "applies_to_intents": [],
        "validation_hint": None,
        "severity": "info",
        "priority": 1,
    }


def _semantic_rule(rule_name: str, intent_name: str) -> dict:
    return {
        "rule_group": "semantic_operations",
        "rule_name": rule_name,
        "rule_content": {
            "source": "versioned_semantic_context",
            "requires": [
                "financial_metric",
                "analytical_operation",
                "period_reference",
            ],
        },
        "applies_to_intents": [intent_name],
        "validation_hint": None,
        "severity": "error",
        "priority": 10,
    }


def _concept(
    concept_name: str,
    terms: list[str],
    *,
    match_mode: str = "contains",
) -> dict:
    return {
        "concept_name": concept_name,
        "terms": terms,
        "match_mode": match_mode,
        "minimum_term_matches": 1,
    }


def _catalog_rule(
    rule_name: str,
    effect: str,
    concepts: list[dict],
    *,
    minimum_concept_matches: int,
    score: float | None = None,
    priority: int = 1,
) -> dict:
    return {
        "rule_name": rule_name,
        "effect": effect,
        "concepts": concepts,
        "minimum_concept_matches": minimum_concept_matches,
        "score": score,
        "priority": priority,
    }


def _generic_metric_definition() -> dict:
    metric_concept = _concept(
        "financial_metric",
        [
            "receita",
            "receitas",
            "faturamento",
            "rol",
            "opex",
            "despesa operacional",
            "despesas operacionais",
            "custo",
            "custos",
        ],
    )
    operation_concept = _concept(
        "analytical_operation",
        [
            "total",
            "quanto",
            "qual foi",
            "quais foram",
            "valor agregado",
            "consolidado",
            "soma",
        ],
    )
    period_concept = _concept(
        "period_reference",
        [
            "ultimo mes",
            "ultimo periodo",
            "mes passado",
            "periodo anterior",
            "periodo passado",
            "no mes",
        ],
    )
    dimension_concept = _concept(
        "dimension_grouping",
        [
            "por marca",
            "por centro de custo",
            "por unidade",
            "por conta",
        ],
    )

    return {
        "entity_type": "intent_definition",
        "user_term": "metric_total_by_period_definition",
        "canonical_value": GENERIC_INTENT,
        "target_table": None,
        "target_column": None,
        "sql_filter_hint": None,
        "business_rule": {
            "intent_catalog": {
                "semantic_description": (
                    "Resolve perguntas analiticas genericas que pedem "
                    "agregacao de uma metrica financeira em periodo."
                ),
                "rules": [
                    _catalog_rule(
                        "metric_period_operation_or_dimension_required",
                        "require",
                        [
                            metric_concept,
                            operation_concept,
                            period_concept,
                            dimension_concept,
                        ],
                        minimum_concept_matches=3,
                        priority=1,
                    ),
                    _catalog_rule(
                        "metric_operation_period_score",
                        "positive_score",
                        [
                            metric_concept,
                            operation_concept,
                            period_concept,
                        ],
                        minimum_concept_matches=3,
                        score=140,
                        priority=2,
                    ),
                    _catalog_rule(
                        "metric_dimension_period_score",
                        "positive_score",
                        [
                            metric_concept,
                            period_concept,
                            dimension_concept,
                        ],
                        minimum_concept_matches=3,
                        score=130,
                        priority=3,
                    ),
                    _catalog_rule(
                        "specialized_responsibility_exclusion",
                        "exclude",
                        [
                            _concept(
                                "responsibility_lookup",
                                [
                                    "responsavel",
                                    "quem responde",
                                    "dono",
                                ],
                            )
                        ],
                        minimum_concept_matches=1,
                        priority=4,
                    ),
                    _catalog_rule(
                        "budget_overrun_exclusion",
                        "exclude",
                        [
                            _concept(
                                "budget_overrun",
                                [
                                    "estouro",
                                    "orcamento",
                                    "orcado",
                                    "realizado",
                                ],
                            )
                        ],
                        minimum_concept_matches=1,
                        priority=5,
                    ),
                ],
            }
        },
        "priority": 40,
    }


def _specialized_signal(
    user_term: str,
    intent_name: str,
    *,
    score: int = 150,
    priority: int = 10,
) -> dict:
    return {
        "entity_type": "intent_signal",
        "user_term": user_term,
        "canonical_value": intent_name,
        "target_table": None,
        "target_column": None,
        "sql_filter_hint": {
            "resolver": {
                "match_mode": "contains",
                "polarity": "positive",
                "score": score,
            }
        },
        "business_rule": None,
        "priority": priority,
    }


def _table(table_name: str, priority: int) -> dict:
    key_columns = []
    extra_columns = []
    if table_name == "gold_centro_custo":
        key_columns = ["sk", "nk_centro_custo"]
        extra_columns = [
            {
                "name": "nk_centro_custo",
                "data_type": "text",
                "nullable": True,
                "description": "Chave de negocio do centro de custo.",
            },
        ]
    elif table_name == "gold_gestor_cc":
        key_columns = ["sk", "nk_centro_custo", "nk_unid_neg"]
    elif table_name == "gold_plano_contas":
        key_columns = ["sk", "nk_conta_contabil"]
        extra_columns = [
            {
                "name": "nk_conta_contabil",
                "data_type": "text",
                "nullable": True,
                "description": "Chave de negocio da conta contabil.",
            },
            {
                "name": "nivel_1_bi",
                "data_type": "text",
                "nullable": True,
                "description": "Grupo DRE de primeiro nivel.",
            },
        ]
    elif table_name == "gold_unidade_negocio":
        key_columns = ["sk", "nk_unide_neg", "nk_base"]
        extra_columns = [
            {
                "name": "marca",
                "data_type": "text",
                "nullable": True,
                "description": "Marca da unidade de negocio.",
            },
            {
                "name": "nk_unide_neg",
                "data_type": "text",
                "nullable": True,
                "description": "Chave de negocio da unidade.",
            },
        ]
    return {
        "table_name": table_name,
        "schema_name": "main_gold",
        "table_type": "table",
        "description": f"{table_name} semantic fixture",
        "grain": {"kind": "fixture"},
        "primary_key": [],
        "key_columns": key_columns,
        "metric_columns": ["valor"],
        "date_columns": ["data_competencia"],
        "join_rules": [],
        "ai_hint": {"usage": "semantic operations fixture"},
        "priority": priority,
        "columns": [
            {
                "name": "valor",
                "data_type": "numeric",
                "nullable": True,
                "description": "Valor contabil.",
            },
            {
                "name": "data_competencia",
                "data_type": "date",
                "nullable": True,
                "description": "Data de competencia.",
            },
        ]
        + extra_columns,
    }


def _raw_context() -> dict:
    return {
        "semantic_agent_version": SEMANTIC_VERSION,
        "semantic_context_source": "unit_test_semantic_context",
        "regras": [
            _resolver_config_rule(),
            _semantic_rule(
                "metric_total_by_period_contract",
                GENERIC_INTENT,
            ),
            _semantic_rule(
                "specialized_intents_remain_preferred",
                "responsavel_centro_custo",
            ),
            _semantic_rule(
                "budget_overrun_contract",
                "estouro_orcamento",
            ),
        ],
        "entidades": [
            _generic_metric_definition(),
            _specialized_signal(
                "responsavel",
                "responsavel_centro_custo",
                priority=1,
            ),
            _specialized_signal(
                "centro de custo",
                "responsavel_centro_custo",
                score=60,
                priority=2,
            ),
            _specialized_signal(
                "estouro de orcamento",
                "estouro_orcamento",
                priority=3,
            ),
            _specialized_signal(
                "orcado vs realizado",
                "orcado_vs_realizado",
                priority=4,
            ),
            {
                "entity_type": "financial_metric_alias",
                "user_term": "faturamento",
                "canonical_value": "receita",
                "target_table": "main_gold.gold_plano_contas",
                "target_column": "nivel_1_bi",
                "sql_filter_hint": {
                    "semantic_role": "financial_metric",
                },
                "business_rule": None,
                "priority": 30,
            },
        ],
        "dre": [
            {
                "dre_code": "ROL",
                "nivel_1_bi": "Receita Operacional Liquida",
                "business_description": "Receita liquida reconhecida.",
                "sign_convention": {"multiplier": 1},
                "category": "receita",
                "is_revenue": True,
                "is_deduction": False,
                "is_cost": False,
                "is_opex": False,
                "is_financial_result": False,
                "sql_filter_hint": {
                    "semantic_metric": "receita",
                    "intent_name": GENERIC_INTENT,
                },
                "sort_order": 1,
            },
            {
                "dre_code": "OPEX",
                "nivel_1_bi": "Despesas Operacionais",
                "business_description": "Opex gerencial.",
                "sign_convention": {"multiplier": -1},
                "category": "opex",
                "is_revenue": False,
                "is_deduction": False,
                "is_cost": False,
                "is_opex": True,
                "is_financial_result": False,
                "sql_filter_hint": {
                    "semantic_metric": "opex",
                    "intent_name": GENERIC_INTENT,
                },
                "sort_order": 2,
            },
            {
                "dre_code": "COST",
                "nivel_1_bi": "Custos",
                "business_description": "Custos operacionais.",
                "sign_convention": {"multiplier": -1},
                "category": "custo",
                "is_revenue": False,
                "is_deduction": False,
                "is_cost": True,
                "is_opex": False,
                "is_financial_result": False,
                "sql_filter_hint": {
                    "semantic_metric": "custo",
                    "intent_name": GENERIC_INTENT,
                },
                "sort_order": 3,
            },
        ],
        "padroes": [
            {
                "intent_name": GENERIC_INTENT,
                "pattern_name": "metric_total_by_period_default",
                "business_question_examples": [
                    "Exemplo documental nao usado pelas perguntas do teste."
                ],
                "required_tables": [
                    "gold_lancamentos_contabeis",
                    "gold_plano_contas",
                ],
                "required_rules": [
                    "metric_total_by_period_contract",
                ],
                "sql_pattern": (
                    "Aggregate one configured financial metric over the "
                    "requested period using only authorized tables."
                ),
                "notes": "Semantic operation pattern, not benchmark lookup.",
                "priority": 50,
            },
            {
                "intent_name": "responsavel_centro_custo",
                "pattern_name": "responsavel_centro_custo_default",
                "business_question_examples": [],
                "required_tables": [
                    "main_gold.gold_centro_custo",
                    "main_gold.gold_gestor_cc",
                ],
                "required_rules": [
                    "specialized_intents_remain_preferred",
                ],
                "sql_pattern": "Resolve cost center owner.",
                "notes": None,
                "priority": 10,
            },
            {
                "intent_name": "estouro_orcamento",
                "pattern_name": "estouro_orcamento_default",
                "business_question_examples": [],
                "required_tables": [
                    "main_gold.gold_orcamento",
                ],
                "required_rules": [
                    "budget_overrun_contract",
                ],
                "sql_pattern": "Resolve budget overrun.",
                "notes": None,
                "priority": 20,
            },
        ],
        "catalogo": [
            _table("gold_lancamentos_contabeis", 1),
            _table("gold_plano_contas", 2),
            _table("gold_centro_custo", 3),
            _table("gold_orcamento", 4),
            _table("gold_gestor_cc", 5),
            _table("gold_unidade_negocio", 6),
        ],
    }


def _context() -> dict:
    return normalize_context_snapshot(_raw_context())


def _context_v4() -> dict:
    raw_context = _raw_context()
    raw_context["semantic_agent_version"] = (
        "v2.0-ducklake-query-generator-semantic-operations-v4"
    )
    raw_context["entidades"].extend(
        [
            {
                "entity_type": "dimension",
                "user_term": "unidade",
                "canonical_value": "unidade",
                "target_table": "main_gold.gold_unidade_negocio",
                "target_column": "nk_unide_neg",
                "sql_filter_hint": None,
                "business_rule": {
                    "source": "versioned_semantic_context",
                    "dimension_mapping": {
                        "evidence": [
                            "gold_unidade_negocio.nk_unide_neg e chave de negocio confirmada"
                        ],
                    },
                },
                "priority": 5,
            },
            {
                "entity_type": "dimension",
                "user_term": "marca",
                "canonical_value": "marca",
                "target_table": "main_gold.gold_unidade_negocio",
                "target_column": "marca",
                "sql_filter_hint": None,
                "business_rule": {
                    "source": "versioned_semantic_context",
                    "dimension_mapping": {
                        "evidence": [
                            "gold_unidade_negocio.marca consta como coluna catalogada"
                        ],
                    },
                },
                "priority": 5,
            },
            {
                "entity_type": "dimension",
                "user_term": "centro de custo",
                "canonical_value": "centro_custo",
                "target_table": "main_gold.gold_centro_custo",
                "target_column": "nk_centro_custo",
                "sql_filter_hint": None,
                "business_rule": {
                    "source": "physical_metadata_confirmed_by_sql_execution_proxy",
                    "dimension_mapping": {
                        "evidence": [
                            "gold_centro_custo.nk_centro_custo existe fisicamente"
                        ],
                    },
                },
                "priority": 5,
            },
            {
                "entity_type": "dimension",
                "user_term": "conta",
                "canonical_value": "conta",
                "target_table": "main_gold.gold_plano_contas",
                "target_column": "nk_conta_contabil",
                "sql_filter_hint": None,
                "business_rule": {
                    "source": "physical_metadata_confirmed_by_sql_execution_proxy",
                    "dimension_mapping": {
                        "evidence": [
                            "gold_plano_contas.nk_conta_contabil existe fisicamente",
                            "nivel_1_bi representa grupo DRE, nao dimensao conta",
                        ],
                    },
                },
                "priority": 5,
            },
        ]
    )
    return normalize_context_snapshot(raw_context)


def _context_v5() -> dict:
    raw_context = _raw_context()
    raw_context["semantic_agent_version"] = (
        "v2.0-ducklake-query-generator-semantic-operations-v5-dedup"
    )
    raw_context["entidades"] = [
        entity
        for entity in raw_context["entidades"]
        if not (
            entity.get("entity_type") == "intent_definition"
            and entity.get("canonical_value") == GENERIC_INTENT
        )
    ]
    raw_context["entidades"].extend(
        _v4_dimension_mappings()
    )
    raw_context["entidades"].append(_generic_metric_definition_v5())
    return normalize_context_snapshot(raw_context)


def _v4_dimension_mappings() -> list[dict]:
    return [
        {
            "entity_type": "dimension",
            "user_term": "unidade",
            "canonical_value": "unidade",
            "target_table": "main_gold.gold_unidade_negocio",
            "target_column": "nk_unide_neg",
            "sql_filter_hint": None,
            "business_rule": {
                "source": "versioned_semantic_context",
                "dimension_mapping": {
                    "evidence": [
                        "gold_unidade_negocio.nk_unide_neg e chave de negocio confirmada"
                    ],
                },
            },
            "priority": 5,
        },
        {
            "entity_type": "dimension",
            "user_term": "marca",
            "canonical_value": "marca",
            "target_table": "main_gold.gold_unidade_negocio",
            "target_column": "marca",
            "sql_filter_hint": None,
            "business_rule": {
                "source": "versioned_semantic_context",
                "dimension_mapping": {
                    "evidence": [
                        "gold_unidade_negocio.marca consta como coluna catalogada"
                    ],
                },
            },
            "priority": 5,
        },
        {
            "entity_type": "dimension",
            "user_term": "centro de custo",
            "canonical_value": "centro_custo",
            "target_table": "main_gold.gold_centro_custo",
            "target_column": "nk_centro_custo",
            "sql_filter_hint": None,
            "business_rule": {
                "source": "physical_metadata_confirmed_by_sql_execution_proxy",
                "dimension_mapping": {
                    "evidence": [
                        "gold_centro_custo.nk_centro_custo existe fisicamente"
                    ],
                },
            },
            "priority": 5,
        },
        {
            "entity_type": "dimension",
            "user_term": "conta",
            "canonical_value": "conta",
            "target_table": "main_gold.gold_plano_contas",
            "target_column": "nk_conta_contabil",
            "sql_filter_hint": None,
            "business_rule": {
                "source": "physical_metadata_confirmed_by_sql_execution_proxy",
                "dimension_mapping": {
                    "evidence": [
                        "gold_plano_contas.nk_conta_contabil existe fisicamente",
                        "nivel_1_bi representa grupo DRE, nao dimensao conta",
                    ],
                },
            },
            "priority": 5,
        },
    ]


def _generic_metric_definition_v5() -> dict:
    metric_concept = _concept(
        "financial_metric",
        [
            "receita",
            "receitas",
            "faturamento",
            "rol",
            "opex",
            "despesa",
            "despesas",
            "despesa operacional",
            "despesas operacionais",
            "gasto",
            "gastos",
            "custo",
            "custos",
            "movimentado",
            "movimentacao",
        ],
    )
    operation_concept = _concept(
        "analytical_operation",
        [
            "total",
            "quanto",
            "qual foi",
            "quais foram",
            "valor agregado",
            "consolidado",
            "soma",
            "distribuido",
            "distribuidos",
            "distribuicao",
            "concentraram",
            "concentrado",
            "concentracao",
            "maiores",
        ],
    )
    period_concept = _concept(
        "period_reference",
        [
            "ultimo mes",
            "ultimo mes fechado",
            "ultimo periodo",
            "ultimo periodo disponivel",
            "mes passado",
            "mes anterior",
            "periodo anterior",
            "periodo passado",
            "no mes",
        ],
    )
    dimension_concept = _concept(
        "dimension_grouping",
        [
            "por marca",
            "por centro de custo",
            "centro de custo",
            "por unidade",
            "unidade",
            "por conta",
            "conta contabil",
        ],
    )

    definition = _generic_metric_definition()
    definition["user_term"] = "metric_total_by_period_generalization_v5"
    definition["business_rule"]["intent_catalog"]["semantic_description"] = (
        "Resolve perguntas analiticas genericas sobre metricas financeiras, "
        "distribuicao, concentracao e movimentacao por periodo e dimensoes "
        "autorizadas pelo contexto."
    )
    rules = definition["business_rule"]["intent_catalog"]["rules"]
    rules[0]["concepts"] = [
        metric_concept,
        operation_concept,
        period_concept,
        dimension_concept,
    ]
    rules[1]["concepts"] = [
        metric_concept,
        operation_concept,
        period_concept,
    ]
    rules[2]["concepts"] = [
        metric_concept,
        period_concept,
        dimension_concept,
    ]
    definition["priority"] = 35
    return definition


def _resolve(question: str, context: dict | None = None) -> dict:
    selected_context = _context() if context is None else context
    return resolve_intent(
        question,
        selected_context["intent_resolution"],
    )


def test_metricas_financeiras_genericas_resolvem_sem_exemplos() -> None:
    context = _context()
    config = context["intent_resolution"]["config"]

    assert config["minimum_score"] == 100.0
    assert config["ambiguity_margin"] == 20.0

    questions = [
        "Quais foram as receitas do ultimo mes?",
        "Qual foi o total de receita no periodo anterior?",
        "Quanto tivemos de receita no mes passado?",
        "Informe o faturamento consolidado do periodo anterior.",
        "Qual o valor agregado de OPEX no mes passado?",
        "Mostre o custo total do periodo anterior.",
        "Mostre a receita por unidade no periodo anterior.",
    ]

    for question in questions:
        result = _resolve(question, context)

        assert result["applied"] is True
        assert result["intent"] == GENERIC_INTENT
        assert result["best_candidate"] is not None
        assert result["best_candidate"]["score"] >= 100.0
        assert result["intent_catalog"][
            "contributed_score_to_selected_intent"
        ] is True


def test_planner_usa_padrao_generico_unico_sem_lookup_de_pergunta() -> None:
    context = _context()
    resolution = _resolve(
        "Quanto tivemos de receita no mes passado?",
        context,
    )

    assert resolution["applied"] is True

    plan_result = build_query_plan(
        context=context,
        intent_name=resolution["intent"],
        intent_confidence=resolution["intent_confidence"],
        normalized_question=resolution["normalized_question"],
    )

    assert plan_result["status"] == "planned"
    assert plan_result["selection_result"]["diagnostic"][
        "decision_reason"
    ] == (
        "single_pattern_selected"
    )
    assert plan_result["query_plan"]["selected_pattern"]["pattern_name"] == (
        "metric_total_by_period_default"
    )
    assert plan_result["projection"]["relevant_dre_mappings"]


def test_planner_continua_sem_dependencia_de_examples() -> None:
    context = _context()
    for pattern in context["query_patterns"]:
        if pattern["intent_name"] == GENERIC_INTENT:
            pattern["business_question_examples"] = []

    resolution = _resolve(
        "Me de o consolidado de faturamento do periodo passado.",
        context,
    )
    plan_result = build_query_plan(
        context=context,
        intent_name=resolution["intent"],
        intent_confidence=resolution["intent_confidence"],
        normalized_question=resolution["normalized_question"],
    )

    assert resolution["applied"] is True
    assert plan_result["status"] == "planned"
    assert plan_result["query_plan"]["selected_pattern"]["pattern_name"] == (
        "metric_total_by_period_default"
    )
    assert plan_result["selection_result"]["diagnostic"]["candidates"][0][
        "examples_count"
    ] == 0


def test_perguntas_adversariais_explicitam_limites_do_modelo() -> None:
    context = _context()
    cases = [
        (
            "Me de o consolidado de faturamento do periodo passado.",
            GENERIC_INTENT,
        ),
        (
            "Quanto somaram os custos no ultimo periodo?",
            GENERIC_INTENT,
        ),
        (
            "Apresente o OPEX consolidado.",
            None,
        ),
        (
            "Mostre a receita por unidade no periodo anterior.",
            GENERIC_INTENT,
        ),
        (
            "Qual conta teve maior despesa no mes passado?",
            None,
        ),
        (
            "Compare receita e OPEX no ultimo mes.",
            None,
        ),
    ]

    for question, expected_intent in cases:
        result = _resolve(question, context)
        if expected_intent is None:
            assert result["applied"] is False
            continue

        assert result["applied"] is True
        assert result["intent"] == expected_intent
        assert result["best_candidate"] is not None
        assert result["best_candidate"]["score"] >= 100.0


def test_intencoes_especializadas_permanecem_estaveis() -> None:
    context = _context()

    responsibility = _resolve(
        "Quem e o responsavel pelo centro de custo Comercial?",
        context,
    )
    budget = _resolve(
        "Qual centro de custo teve maior estouro de orcamento?",
        context,
    )

    assert responsibility["applied"] is True
    assert responsibility["intent"] == "responsavel_centro_custo"
    assert budget["applied"] is True
    assert budget["intent"] == "estouro_orcamento"


def test_pergunta_fora_do_dominio_continua_rejeitada() -> None:
    result = _resolve("Qual e a previsao do tempo para amanha?")

    assert result["applied"] is False
    assert result["reason"] == "minimum_score_not_reached"
    assert result["candidates"] == []


def test_contexto_original_nao_e_mutado_pelo_planejamento() -> None:
    context = _context()
    original = deepcopy(context)
    resolution = _resolve("Mostre o custo total do periodo anterior.", context)

    build_query_plan(
        context=context,
        intent_name=resolution["intent"],
        intent_confidence=resolution["intent_confidence"],
        normalized_question=resolution["normalized_question"],
    )

    assert context == original


def test_migration_usa_tipos_reais_do_contexto_semantico() -> None:
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "FROM public.ai_ducklake_agent_rules source" in sql
    assert "source.is_active = TRUE" in sql
    assert "source.is_allowed = TRUE" in sql
    assert "'[\"metric_total_by_period\"]'::jsonb" in sql
    assert "ARRAY['metric_total_by_period']::text[]" not in sql
    assert "ARRAY[" not in sql
    assert "'[]'::jsonb" in sql
    assert '"gold_lancamentos_contabeis"' in sql
    assert '"gold_plano_contas"' in sql
    assert "main_gold.gold_lancamentos_contabeis" not in sql
    assert "main_gold.gold_plano_contas" not in sql
    assert "COALESCE(sql_filter_hint, '{}'::jsonb)" not in sql
    assert "sql_filter_hint::jsonb" not in sql
    assert "ROLLBACK;" not in sql
    assert sql.rstrip().endswith("COMMIT;")


def test_migration_separa_total_bruto_de_contexto_efetivo() -> None:
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    raw_source_counts = {
        "agent_rules_total": 30,
        "agent_rules_active": 29,
        "entity_aliases_total": 66,
        "entity_aliases_active": 66,
        "dre_mapping_total": 11,
        "dre_mapping_active": 11,
        "sql_patterns_total": 9,
        "sql_patterns_active": 9,
        "table_catalog_total": 9,
        "table_catalog_allowed": 9,
    }

    expected_target_counts = {
        "agent_rules_total": raw_source_counts["agent_rules_active"] + 1,
        "agent_rules_active": raw_source_counts["agent_rules_active"] + 1,
        "entity_aliases_total": raw_source_counts["entity_aliases_active"] + 1,
        "entity_aliases_active": raw_source_counts["entity_aliases_active"] + 1,
        "dre_mapping_total": raw_source_counts["dre_mapping_active"],
        "dre_mapping_active": raw_source_counts["dre_mapping_active"],
        "sql_patterns_total": raw_source_counts["sql_patterns_active"] + 1,
        "sql_patterns_active": raw_source_counts["sql_patterns_active"] + 1,
        "table_catalog_total": raw_source_counts["table_catalog_allowed"],
        "table_catalog_allowed": raw_source_counts["table_catalog_allowed"],
    }

    assert expected_target_counts["agent_rules_total"] == 30
    assert expected_target_counts["agent_rules_active"] == 30
    assert expected_target_counts["entity_aliases_total"] == 67
    assert expected_target_counts["entity_aliases_active"] == 67
    assert expected_target_counts["dre_mapping_total"] == 11
    assert expected_target_counts["dre_mapping_active"] == 11
    assert expected_target_counts["sql_patterns_total"] == 10
    assert expected_target_counts["sql_patterns_active"] == 10
    assert expected_target_counts["table_catalog_total"] == 9
    assert expected_target_counts["table_catalog_allowed"] == 9

    assert sql.count("source.is_active = TRUE") == 4
    assert sql.count("source.is_allowed = TRUE") == 1


def test_migration_v2_preserva_v1_e_copia_somente_contexto_ativo() -> None:
    sql = MIGRATION_V2_PATH.read_text(encoding="utf-8")

    assert "semantic-operations-v1'::text" in sql
    assert "semantic-operations-v2'::text" in sql
    assert sql.count("source.is_active = TRUE") == 4
    assert sql.count("source.is_allowed = TRUE") == 1
    assert "ON CONFLICT DO NOTHING" in sql
    assert "ROLLBACK;" not in sql
    assert sql.rstrip().endswith("COMMIT;")


def test_migration_v2_remove_inducao_de_coluna_responsavel() -> None:
    sql = MIGRATION_V2_PATH.read_text(encoding="utf-8")

    assert "gcc.responsavel" not in sql
    assert "source.target_column = 'responsavel'" in sql
    assert "THEN NULL" in sql
    assert "nao gerar coluna de responsavel" in sql
    assert "coluna fisica confirmada" in sql


def test_migration_v2_preserva_conhecimento_responsavel_da_v1() -> None:
    sql = MIGRATION_V2_PATH.read_text(encoding="utf-8")

    assert "NULLIF(source.rule_content, '')" in sql
    assert "NULLIF(source.validation_hint, '')" in sql
    assert "NULLIF(source.business_rule, '')" in sql
    assert "NULLIF(source.sql_pattern, '')" in sql
    assert "NULLIF(source.notes, '')" in sql
    assert "Regra adicional v2:" in sql
    assert "Hint adicional v2:" in sql
    assert "Orientacao adicional v2:" in sql
    assert "Nota adicional v2:" in sql
    assert "mapeamento fisico de responsavel indisponivel" in sql
    assert "nao projetar coluna inventada" in sql


def test_migration_v2_corrige_unidade_sem_replace_global() -> None:
    sql = MIGRATION_V2_PATH.read_text(encoding="utf-8")

    assert "source.table_name = 'gold_unidade_negocio'" in sql
    assert "un.nk_unide_neg" in sql
    assert "Nao extrapolar nk_unid_neg para gold_unidade_negocio" in sql
    assert "gcc.nk_unid_neg" in sql
    assert "gold_lancamentos_contabeis" not in sql


def test_migration_v2_preserva_notes_e_ai_hint_ao_corrigir_unidade() -> None:
    sql = MIGRATION_V2_PATH.read_text(encoding="utf-8")

    assert "NULLIF(source.notes, '')" in sql
    assert "NULLIF(source.ai_hint, '')" in sql
    assert "Addendum v2:" in sql
    assert "quando gold_unidade_negocio estiver envolvida" in sql
    assert "chave fisica confirmada nesta tabela = nk_unide_neg" in sql
    assert "Nao usar nk_unid_neg nesta tabela" in sql


def test_fixture_preserva_chaves_diferentes_por_tabela() -> None:
    context = _context()
    catalog = {
        item["table_name"]: item
        for item in context["table_catalog"]
    }

    gestor = catalog["gold_gestor_cc"]
    unidade = catalog["gold_unidade_negocio"]

    assert "nk_unid_neg" in gestor["key_columns"]
    assert "responsavel" not in gestor["key_columns"]
    assert "nk_unide_neg" in unidade["key_columns"]
    assert "nk_unid_neg" not in unidade["key_columns"]


def test_responsavel_sem_mapping_fisico_nao_projeta_coluna_inexistente() -> None:
    context = _context()
    resolution = _resolve(
        "Quem e o responsavel pelo centro de custo Comercial?",
        context,
    )
    assert resolution["applied"] is True

    plan_result = build_query_plan(
        context=context,
        intent_name=resolution["intent"],
        intent_confidence=resolution["intent_confidence"],
        normalized_question=resolution["normalized_question"],
    )
    columns = plan_result["query_plan"]["planning_context"]["relevant_columns"]

    assert plan_result["status"] == "planned"
    assert all(
        column.get("name") != "responsavel"
        for table_columns in columns.values()
        for column in table_columns
    )


def test_planner_nao_inventa_coluna_unidade_sem_metadata_explicita() -> None:
    context = _context()
    resolution = _resolve(
        "Mostre os custos por unidade no periodo passado.",
        context,
    )
    assert resolution["applied"] is True
    assert resolution["intent"] == GENERIC_INTENT

    plan_result = build_query_plan(
        context=context,
        intent_name=resolution["intent"],
        intent_confidence=resolution["intent_confidence"],
        normalized_question=resolution["normalized_question"],
    )
    projection = plan_result["query_plan"]["planning_context"]
    tables = {
        table["qualified_name"]
        for table in projection["required_tables"]
    }

    assert plan_result["status"] == "planned"
    assert projection["detected_dimensions"] == []
    assert projection["diagnostics"]["dimension_diagnostic"][
        "grouping_requested"
    ] is True
    assert projection["diagnostics"]["dimension_diagnostic"][
        "unresolved_terms"
    ] == ["unidade"]
    assert "main_gold.gold_unidade_negocio" not in tables


def test_planner_promove_dimensao_marca_com_contexto_versionado() -> None:
    context = _context()
    resolution = _resolve(
        "Qual foi a receita por marca no mes passado?",
        context,
    )
    assert resolution["applied"] is True
    assert resolution["intent"] == GENERIC_INTENT

    plan_result = build_query_plan(
        context=context,
        intent_name=resolution["intent"],
        intent_confidence=resolution["intent_confidence"],
        normalized_question=resolution["normalized_question"],
    )
    projection = plan_result["query_plan"]["planning_context"]
    dimensions = projection["detected_dimensions"]
    tables = {
        table["qualified_name"]
        for table in projection["required_tables"]
    }
    columns = projection["relevant_columns"]["main_gold.gold_unidade_negocio"]

    assert plan_result["status"] == "planned"
    assert dimensions[0]["canonical_value"] == "marca"
    assert dimensions[0]["grouping_requested"] is True
    assert dimensions[0]["target_table"] == "main_gold.gold_unidade_negocio"
    assert dimensions[0]["target_column"] == "marca"
    assert "main_gold.gold_unidade_negocio" in tables
    assert any(column["name"] == "marca" for column in columns)


def test_planner_v4_promove_unidade_por_mapping_explicito() -> None:
    context = _context_v4()
    resolution = _resolve(
        "Mostre os custos por unidade no periodo passado.",
        context,
    )
    assert resolution["applied"] is True
    assert resolution["intent"] == GENERIC_INTENT

    plan_result = build_query_plan(
        context=context,
        intent_name=resolution["intent"],
        intent_confidence=resolution["intent_confidence"],
        normalized_question=resolution["normalized_question"],
    )
    projection = plan_result["query_plan"]["planning_context"]
    dimension = projection["detected_dimensions"][0]
    columns = projection["relevant_columns"]["main_gold.gold_unidade_negocio"]

    assert dimension["canonical_value"] == "unidade"
    assert dimension["target_table"] == "main_gold.gold_unidade_negocio"
    assert dimension["target_column"] == "nk_unide_neg"
    assert dimension["grouping_requested"] is True
    assert dimension["source"] == "entity_alias"
    assert dimension["mapping_source"] == "entity_alias"
    assert dimension["detection_source"] == "planner_lexical_fallback"
    assert dimension["target_column"] != "sk"
    assert any(column["name"] == "nk_unide_neg" for column in columns)


def test_planner_v4_promove_marca_por_mapping_explicito() -> None:
    context = _context_v4()
    resolution = _resolve(
        "Qual foi a receita por marca no mes passado?",
        context,
    )
    assert resolution["applied"] is True
    assert resolution["intent"] == GENERIC_INTENT

    plan_result = build_query_plan(
        context=context,
        intent_name=resolution["intent"],
        intent_confidence=resolution["intent_confidence"],
        normalized_question=resolution["normalized_question"],
    )
    projection = plan_result["query_plan"]["planning_context"]
    dimension = projection["detected_dimensions"][0]

    assert dimension["canonical_value"] == "marca"
    assert dimension["target_table"] == "main_gold.gold_unidade_negocio"
    assert dimension["target_column"] == "marca"
    assert dimension["grouping_requested"] is True
    assert dimension["source"] == "entity_alias"
    assert dimension["mapping_source"] == "entity_alias"
    assert dimension["detection_source"] == "planner_lexical_fallback"


def test_planner_v4_promove_centro_custo_por_mapping_explicito() -> None:
    context = _context_v4()
    resolution = _resolve(
        "Mostre os custos por centro de custo no periodo passado.",
        context,
    )
    assert resolution["applied"] is True
    assert resolution["intent"] == GENERIC_INTENT

    plan_result = build_query_plan(
        context=context,
        intent_name=resolution["intent"],
        intent_confidence=resolution["intent_confidence"],
        normalized_question=resolution["normalized_question"],
    )
    projection = plan_result["query_plan"]["planning_context"]
    dimension = projection["detected_dimensions"][0]
    columns = projection["relevant_columns"]["main_gold.gold_centro_custo"]

    assert dimension["canonical_value"] == "centro_custo"
    assert dimension["target_table"] == "main_gold.gold_centro_custo"
    assert dimension["target_column"] == "nk_centro_custo"
    assert dimension["grouping_requested"] is True
    assert dimension["source"] == "entity_alias"
    assert dimension["mapping_source"] == "entity_alias"
    assert dimension["detection_source"] == "planner_lexical_fallback"
    assert dimension["target_column"] != "sk"
    assert any(column["name"] == "nk_centro_custo" for column in columns)


def test_planner_v4_promove_conta_por_mapping_explicito() -> None:
    context = _context_v4()
    resolution = _resolve(
        "Qual foi o custo por conta no mes passado?",
        context,
    )
    assert resolution["applied"] is True
    assert resolution["intent"] == GENERIC_INTENT

    plan_result = build_query_plan(
        context=context,
        intent_name=resolution["intent"],
        intent_confidence=resolution["intent_confidence"],
        normalized_question=resolution["normalized_question"],
    )
    projection = plan_result["query_plan"]["planning_context"]
    dimension = projection["detected_dimensions"][0]
    columns = projection["relevant_columns"]["main_gold.gold_plano_contas"]

    assert dimension["canonical_value"] == "conta"
    assert dimension["target_table"] == "main_gold.gold_plano_contas"
    assert dimension["target_column"] == "nk_conta_contabil"
    assert dimension["grouping_requested"] is True
    assert dimension["source"] == "entity_alias"
    assert dimension["mapping_source"] == "entity_alias"
    assert dimension["detection_source"] == "planner_lexical_fallback"
    assert dimension["target_column"] not in {"sk", "nivel_1_bi", "nk_conta"}
    assert any(column["name"] == "nk_conta_contabil" for column in columns)


def _assert_v5_dimension(
    question: str,
    *,
    canonical_value: str,
    target_table: str,
    target_column: str,
) -> None:
    context = _context_v5()
    resolution = _resolve(question, context)

    assert resolution["applied"] is True
    assert resolution["intent"] == GENERIC_INTENT
    assert resolution["best_candidate"]["score"] >= 100.0

    plan_result = build_query_plan(
        context=context,
        intent_name=resolution["intent"],
        intent_confidence=resolution["intent_confidence"],
        normalized_question=resolution["normalized_question"],
        intent_resolution_result=resolution,
    )
    projection = plan_result["query_plan"]["planning_context"]
    dimensions = projection["detected_dimensions"]

    assert plan_result["status"] == "planned"
    assert dimensions
    assert dimensions[0]["canonical_value"] == canonical_value
    assert dimensions[0]["target_table"] == target_table
    assert dimensions[0]["target_column"] == target_column
    assert dimensions[0]["detection_source"] == "intent_semantic_evidence"
    assert dimensions[0]["mapping_source"] == "entity_alias"
    assert dimensions[0]["source"] == "entity_alias"
    assert dimensions[0]["grouping_requested"] is True


def test_contexto_v5_resolve_gap_a_gastos_distribuidos_unidades() -> None:
    _assert_v5_dimension(
        "Como os gastos ficaram distribuidos entre as unidades no ultimo mes fechado?",
        canonical_value="unidade",
        target_table="main_gold.gold_unidade_negocio",
        target_column="nk_unide_neg",
    )


def test_contexto_v5_resolve_gap_c_despesas_concentracao_centro_custo() -> None:
    _assert_v5_dimension(
        "Quais centros de custo concentraram mais despesas no mes anterior?",
        canonical_value="centro_custo",
        target_table="main_gold.gold_centro_custo",
        target_column="nk_centro_custo",
    )


def test_contexto_v5_c_reconhece_operacao_mas_query_plan_nao_modela_ranking() -> None:
    context = _context_v5()
    resolution = _resolve(
        "Quais centros de custo concentraram mais despesas no mes anterior?",
        context,
    )
    evaluation = resolution["intent_catalog"]["evaluations"][0]
    matched = {
        concept["concept_name"]: [
            term["term"]
            for rule in evaluation["rules"]
            for concept in rule["concepts"]
            if concept["satisfied"]
            for term in concept["terms"]
            if term["matched"]
        ]
        for rule in evaluation["rules"]
        for concept in rule["concepts"]
        if concept["satisfied"]
    }

    plan_result = build_query_plan(
        context=context,
        intent_name=resolution["intent"],
        intent_confidence=resolution["intent_confidence"],
        normalized_question=resolution["normalized_question"],
        intent_resolution_result=resolution,
    )
    query_plan = plan_result["query_plan"]
    projection = query_plan["planning_context"]

    assert "analytical_operation" in matched
    assert any(
        term in matched["analytical_operation"]
        for term in ("concentraram", "maiores")
    )
    assert projection["detected_dimensions"][0]["canonical_value"] == (
        "centro_custo"
    )
    assert "ranking" not in query_plan
    assert "ranking" not in projection
    assert "ordering" not in projection


def test_contexto_v5_resolve_gap_d_movimentado_conta_contabil() -> None:
    _assert_v5_dimension(
        "Mostre o total movimentado por conta contabil no ultimo periodo disponivel.",
        canonical_value="conta",
        target_table="main_gold.gold_plano_contas",
        target_column="nk_conta_contabil",
    )


def test_contexto_v5_generaliza_sem_lookup_das_perguntas_b32() -> None:
    cases = [
        (
            "Distribuicao de gasto entre unidades no mes anterior.",
            "unidade",
            "main_gold.gold_unidade_negocio",
            "nk_unide_neg",
        ),
        (
            "Liste as despesas concentradas por centro de custo no periodo passado.",
            "centro_custo",
            "main_gold.gold_centro_custo",
            "nk_centro_custo",
        ),
        (
            "Qual movimentacao consolidada por conta contabil no ultimo mes?",
            "conta",
            "main_gold.gold_plano_contas",
            "nk_conta_contabil",
        ),
    ]
    for question, canonical_value, target_table, target_column in cases:
        _assert_v5_dimension(
            question,
            canonical_value=canonical_value,
            target_table=target_table,
            target_column=target_column,
        )


def test_migration_v5_deriva_de_v4_e_preserva_contexto_ativo() -> None:
    sql = MIGRATION_V5_DEDUP_PATH.read_text(encoding="utf-8")

    assert "semantic-operations-v4'::text" in sql
    assert "semantic-operations-v5-dedup'::text" in sql
    assert sql.count("source.is_active = TRUE") == 4
    assert sql.count("source.is_allowed = TRUE") == 1
    agent_rules_copy = sql.split(
        "FROM public.ai_ducklake_agent_rules source", 1
    )[1].split("ON CONFLICT DO NOTHING;", 1)[0]
    entity_alias_copy = sql.split(
        "FROM public.ai_ducklake_entity_aliases source", 1
    )[1].split("ON CONFLICT DO NOTHING;", 1)[0]
    assert "source.entity_type" not in agent_rules_copy
    assert "source.canonical_value" not in agent_rules_copy
    assert "source.entity_type = 'intent_definition'" in entity_alias_copy
    assert "source.canonical_value = 'metric_total_by_period'" in (
        entity_alias_copy
    )
    assert "ON CONFLICT DO NOTHING" in sql
    assert "ROLLBACK;" not in sql
    assert sql.rstrip().endswith("COMMIT;")


def test_migration_v5_adiciona_vocabulario_semantico_generalizavel() -> None:
    sql = MIGRATION_V5_DEDUP_PATH.read_text(encoding="utf-8")

    assert "'metric_total_by_period_generalization_v5_dedup'" in sql
    assert '"gastos"' in sql
    assert '"despesas"' in sql
    assert '"movimentado"' in sql
    assert '"distribuicao"' in sql
    assert '"movimentacao",' not in sql
    assert '"distribuição"' not in sql
    assert '"concentraram"' in sql
    assert '"concentração"' not in sql
    assert '"movimentação"' not in sql
    assert '"ultimo mes fechado"' in sql
    assert '"ultimo periodo disponivel"' in sql
    assert "expected_sql" not in sql
    assert "generated_sql" not in sql
    assert "ai_ducklake_benchmarks" not in sql
    assert "Como os gastos ficaram" not in sql
    assert "Quais centros de custo concentraram" not in sql
    assert "Mostre o total movimentado" not in sql


def test_contexto_v5_nao_tem_duplicatas_pos_normalizacao() -> None:
    context = _context_v5()
    catalog = context["intent_resolution"]["intent_catalog"]
    assert len(catalog) == 1

    for rule in catalog[0]["rules"]:
        for concept in rule["concepts"]:
            normalized_terms = [
                normalize_search_text(term)
                for term in concept["terms"]
            ]
            assert len(normalized_terms) == len(set(normalized_terms))


def _v6_operation_entries() -> list[dict]:
    sql = MIGRATION_V6_PATH.read_text(encoding="utf-8")
    values_block = sql.rsplit(
        "INSERT INTO public.ai_ducklake_entity_aliases", 1
    )[1].split("ON CONFLICT DO NOTHING;", 1)[0]
    entries: list[dict] = []
    for match in re.finditer(
        r"\(\s*"
        r"'(?P<agent_version>[^']+)',\s*"
        r"'(?P<entity_type>analytical_operation)',\s*"
        r"'(?P<user_term>[^']+)',\s*"
        r"'(?P<canonical_value>[^']+)',\s*"
        r"NULL,\s*NULL,\s*NULL,\s*"
        r"'(?P<business_rule>\{[^']+\})',\s*"
        r"(?P<priority>\d+),\s*TRUE\s*"
        r"\)",
        values_block,
        re.MULTILINE,
    ):
        entries.append(
            {
                "entity_type": match.group("entity_type"),
                "user_term": match.group("user_term"),
                "canonical_value": match.group("canonical_value"),
                "business_rule": match.group("business_rule"),
            }
        )
    return entries


def _operation_by_term(user_term: str) -> dict | None:
    normalized = normalize_search_text(user_term)
    for entry in _v6_operation_entries():
        if normalize_search_text(entry["user_term"]) == normalized:
            return entry
    return None


def test_migration_v6_deriva_de_v5_dedup_e_preserva_contexto() -> None:
    sql = MIGRATION_V6_PATH.read_text(encoding="utf-8")

    assert "semantic-operations-v5-dedup'::text" in sql
    assert "semantic-operations-v6'::text" in sql
    assert sql.count("source.is_active = TRUE") == 4
    assert sql.count("source.is_allowed = TRUE") == 1
    entity_alias_copy = sql.split(
        "FROM public.ai_ducklake_entity_aliases source", 1
    )[1].split("ON CONFLICT DO NOTHING;", 1)[0]
    assert "source.entity_type = 'intent_definition'" not in (
        entity_alias_copy
    )
    assert "source.canonical_value = 'metric_total_by_period'" not in (
        entity_alias_copy
    )
    assert "'metric_total_by_period_generalization_v6'" not in sql
    assert "ON CONFLICT DO NOTHING" in sql
    assert "ROLLBACK;" not in sql
    assert sql.rstrip().endswith("COMMIT;")


def test_migration_v6_adiciona_operacoes_analiticas_versionadas() -> None:
    sql = MIGRATION_V6_PATH.read_text(encoding="utf-8")

    assert "'analytical_operation'" in sql
    assert "'ranking'" in sql
    assert '"operation_type":"ranking"' in sql
    assert '"direction":"descending"' in sql
    assert '"direction":"ascending"' in sql
    assert '"requested_limit":null' in sql
    assert "expected_sql" not in sql
    assert "generated_sql" not in sql
    assert "ai_ducklake_benchmarks" not in sql
    assert "Quais centros de custo concentraram" not in sql


def test_contexto_v6_operacoes_nao_duplicam_termos_normalizados() -> None:
    normalized_terms = [
        normalize_search_text(entry["user_term"])
        for entry in _v6_operation_entries()
    ]

    assert normalized_terms
    assert len(normalized_terms) == len(set(normalized_terms))


def test_contexto_v6_resolve_ranking_descendente_por_metadata() -> None:
    entries = _v6_operation_entries()
    assert entries
    descending_count = 0
    for entry in entries:
        operation = json.loads(entry["business_rule"])["operation"]
        assert entry["canonical_value"] == "ranking"
        assert operation["operation_type"] == "ranking"
        assert operation["direction"] in {"ascending", "descending"}
        assert operation["requested_limit"] is None
        if operation["direction"] == "descending":
            descending_count += 1

    assert descending_count >= 1


def test_contexto_v6_resolve_ranking_ascendente_por_metadata() -> None:
    ascending_count = 0
    for entry in _v6_operation_entries():
        operation = json.loads(entry["business_rule"])["operation"]
        if operation["direction"] == "ascending":
            ascending_count += 1

    assert ascending_count >= 1


def test_contexto_v6_termo_desconhecido_nao_inventa_operacao() -> None:
    assert _operation_by_term("operacao desconhecida") is None


def test_business_question_examples_nao_sao_base_da_v2() -> None:
    sql = MIGRATION_V2_PATH.read_text(encoding="utf-8")

    assert "business_question_examples" in sql
    assert "INSERT INTO public.ai_ducklake_sql_patterns" in sql
    assert "VALUES (" not in sql


def test_migration_v3_deriva_de_v2_sem_alterar_v2() -> None:
    sql = MIGRATION_V3_PATH.read_text(encoding="utf-8")

    assert "semantic-operations-v2'::text" in sql
    assert "semantic-operations-v3'::text" in sql
    assert sql.count("source.is_active = TRUE") == 4
    assert sql.count("source.is_allowed = TRUE") == 1
    assert "ON CONFLICT DO NOTHING" in sql
    assert "ROLLBACK;" not in sql
    assert sql.rstrip().endswith("COMMIT;")


def test_migration_v3_neutraliza_coluna_fisica_responsavel_sem_perder_semantica() -> None:
    sql = MIGRATION_V3_PATH.read_text(encoding="utf-8")

    assert "source.intent_name = 'responsavel_centro_custo'" in sql
    assert "source.rule_group = 'responsavel_centro_custo'" in sql
    assert "source.target_column = 'responsavel'" in sql
    assert "THEN NULL" in sql
    assert "regexp_replace(" in sql
    assert "mapeamento fisico de responsavel indisponivel" in sql
    assert "responsavel continua como conceito semantico cadastral" in sql
    assert "preservar centro de custo, unidade, joins e filtros cadastrais" in sql
    assert "nao projetar nem filtrar coluna fisica de responsavel" in sql


def test_migration_v3_corrige_sk_unid_neg_somente_em_gold_unidade_negocio() -> None:
    sql = MIGRATION_V3_PATH.read_text(encoding="utf-8")

    assert "source.table_name = 'gold_unidade_negocio'" in sql
    assert "gold_unidade_negocio.sk e chave tecnica confirmada" in sql
    assert "gold_unidade_negocio.nk_unide_neg e chave de negocio confirmada" in sql
    assert "gold_unidade_negocio.sk_unid_neg" in sql
    assert "gold_unidade_negocio.nk_unid_neg" in sql
    assert "source.table_name = 'gold_lancamentos_contabeis'" not in sql
    assert "replace(source.ai_hint, 'sk_unid_neg'" not in sql
    assert "replace(source.ai_hint, 'nk_unid_neg'" not in sql


def test_migration_v4_deriva_de_v3_e_copia_somente_contexto_ativo() -> None:
    sql = MIGRATION_V4_PATH.read_text(encoding="utf-8")

    assert "semantic-operations-v3'::text" in sql
    assert "semantic-operations-v4'::text" in sql
    assert sql.count("source.is_active = TRUE") == 4
    assert sql.count("source.is_allowed = TRUE") == 1
    assert "ON CONFLICT DO NOTHING" in sql
    assert "ROLLBACK;" not in sql
    assert sql.rstrip().endswith("COMMIT;")


def test_migration_v4_adiciona_mapeamentos_explicitos_de_dimensao() -> None:
    sql = MIGRATION_V4_PATH.read_text(encoding="utf-8")

    assert "'dimension'" in sql
    assert "'unidade'" in sql
    assert "'main_gold.gold_unidade_negocio'" in sql
    assert "'nk_unide_neg'" in sql
    assert "'marca'" in sql
    assert "'centro de custo'" in sql
    assert "'centro_custo'" in sql
    assert "'main_gold.gold_centro_custo'" in sql
    assert "'nk_centro_custo'" in sql
    assert "'conta'" in sql
    assert "'main_gold.gold_plano_contas'" in sql
    assert "'nk_conta_contabil'" in sql
    assert "'nk_conta'" not in sql
    assert "'nivel_1_bi'" not in sql
    assert "dimension_mapping" in sql
    assert "gold_unidade_negocio.sk e chave tecnica, nao dimensao de negocio" in sql
    assert "nivel_1_bi representa grupo DRE, nao dimensao conta" in sql
    assert "business_question_examples" in sql
    assert "VALUES (" not in sql
    assert "ai_ducklake_benchmarks" not in sql
    assert "generated_sql" not in sql
    assert "expected_sql" not in sql


def main() -> None:
    tests = [
        (
            "metricas genericas resolvem",
            test_metricas_financeiras_genericas_resolvem_sem_exemplos,
        ),
        (
            "planner generico unico",
            test_planner_usa_padrao_generico_unico_sem_lookup_de_pergunta,
        ),
        (
            "planner sem examples",
            test_planner_continua_sem_dependencia_de_examples,
        ),
        (
            "perguntas adversariais",
            test_perguntas_adversariais_explicitam_limites_do_modelo,
        ),
        (
            "regressao especializadas",
            test_intencoes_especializadas_permanecem_estaveis,
        ),
        (
            "fora do dominio rejeitada",
            test_pergunta_fora_do_dominio_continua_rejeitada,
        ),
        (
            "planejamento sem mutacao",
            test_contexto_original_nao_e_mutado_pelo_planejamento,
        ),
        (
            "migration tipos reais",
            test_migration_usa_tipos_reais_do_contexto_semantico,
        ),
        (
            "migration counts efetivos",
            test_migration_separa_total_bruto_de_contexto_efetivo,
        ),
        (
            "migration v2 ativa",
            test_migration_v2_preserva_v1_e_copia_somente_contexto_ativo,
        ),
        (
            "migration v2 responsavel",
            test_migration_v2_remove_inducao_de_coluna_responsavel,
        ),
        (
            "migration v2 preserva responsavel",
            test_migration_v2_preserva_conhecimento_responsavel_da_v1,
        ),
        (
            "migration v2 unidade",
            test_migration_v2_corrige_unidade_sem_replace_global,
        ),
        (
            "migration v2 preserva unidade",
            test_migration_v2_preserva_notes_e_ai_hint_ao_corrigir_unidade,
        ),
        (
            "chaves por tabela",
            test_fixture_preserva_chaves_diferentes_por_tabela,
        ),
        (
            "responsavel sem mapping",
            test_responsavel_sem_mapping_fisico_nao_projeta_coluna_inexistente,
        ),
        (
            "planner nao inventa unidade",
            test_planner_nao_inventa_coluna_unidade_sem_metadata_explicita,
        ),
        (
            "planner promove marca",
            test_planner_promove_dimensao_marca_com_contexto_versionado,
        ),
        (
            "planner v4 promove unidade",
            test_planner_v4_promove_unidade_por_mapping_explicito,
        ),
        (
            "planner v4 promove marca",
            test_planner_v4_promove_marca_por_mapping_explicito,
        ),
        (
            "planner v4 promove centro custo",
            test_planner_v4_promove_centro_custo_por_mapping_explicito,
        ),
        (
            "planner v4 promove conta",
            test_planner_v4_promove_conta_por_mapping_explicito,
        ),
        (
            "contexto v5 gap A",
            test_contexto_v5_resolve_gap_a_gastos_distribuidos_unidades,
        ),
        (
            "contexto v5 gap C",
            test_contexto_v5_resolve_gap_c_despesas_concentracao_centro_custo,
        ),
        (
            "contexto v5 ranking diagnostico",
            test_contexto_v5_c_reconhece_operacao_mas_query_plan_nao_modela_ranking,
        ),
        (
            "contexto v5 gap D",
            test_contexto_v5_resolve_gap_d_movimentado_conta_contabil,
        ),
        (
            "contexto v5 generalizacao",
            test_contexto_v5_generaliza_sem_lookup_das_perguntas_b32,
        ),
        (
            "examples nao base v2",
            test_business_question_examples_nao_sao_base_da_v2,
        ),
        (
            "migration v3 ativa",
            test_migration_v3_deriva_de_v2_sem_alterar_v2,
        ),
        (
            "migration v3 responsavel",
            test_migration_v3_neutraliza_coluna_fisica_responsavel_sem_perder_semantica,
        ),
        (
            "migration v3 unidade",
            test_migration_v3_corrige_sk_unid_neg_somente_em_gold_unidade_negocio,
        ),
        (
            "migration v4 ativa",
            test_migration_v4_deriva_de_v3_e_copia_somente_contexto_ativo,
        ),
        (
            "migration v4 dimensoes",
            test_migration_v4_adiciona_mapeamentos_explicitos_de_dimensao,
        ),
        (
            "migration v5 ativa",
            test_migration_v5_deriva_de_v4_e_preserva_contexto_ativo,
        ),
        (
            "migration v5 vocabulario",
            test_migration_v5_adiciona_vocabulario_semantico_generalizavel,
        ),
        (
            "contexto v5 sem duplicatas",
            test_contexto_v5_nao_tem_duplicatas_pos_normalizacao,
        ),
        (
            "migration v6 deriva v5 dedup",
            test_migration_v6_deriva_de_v5_dedup_e_preserva_contexto,
        ),
        (
            "migration v6 analytical operations",
            test_migration_v6_adiciona_operacoes_analiticas_versionadas,
        ),
        (
            "contexto v6 operacoes sem duplicatas",
            test_contexto_v6_operacoes_nao_duplicam_termos_normalizados,
        ),
        (
            "contexto v6 ranking desc",
            test_contexto_v6_resolve_ranking_descendente_por_metadata,
        ),
        (
            "contexto v6 ranking asc",
            test_contexto_v6_resolve_ranking_ascendente_por_metadata,
        ),
        (
            "contexto v6 termo desconhecido",
            test_contexto_v6_termo_desconhecido_nao_inventa_operacao,
        ),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

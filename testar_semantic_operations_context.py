from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from app.domain.context_normalizer import normalize_context_snapshot
from app.domain.intent_resolver import resolve_intent
from app.domain.planner import build_query_plan


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
    if table_name == "gold_gestor_cc":
        key_columns = ["sk", "nk_centro_custo", "nk_unid_neg"]
    elif table_name == "gold_unidade_negocio":
        key_columns = ["sk", "nk_unide_neg", "nk_base"]
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
        ],
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


def test_migration_v2_corrige_unidade_sem_replace_global() -> None:
    sql = MIGRATION_V2_PATH.read_text(encoding="utf-8")

    assert "source.table_name = 'gold_unidade_negocio'" in sql
    assert "un.nk_unide_neg" in sql
    assert "Nao extrapolar nk_unid_neg para gold_unidade_negocio" in sql
    assert "gcc.nk_unid_neg" in sql
    assert "gold_lancamentos_contabeis" not in sql


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


def test_business_question_examples_nao_sao_base_da_v2() -> None:
    sql = MIGRATION_V2_PATH.read_text(encoding="utf-8")

    assert "business_question_examples" in sql
    assert "INSERT INTO public.ai_ducklake_sql_patterns" in sql
    assert "VALUES (" not in sql


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
            "migration v2 unidade",
            test_migration_v2_corrige_unidade_sem_replace_global,
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
            "examples nao base v2",
            test_business_question_examples_nao_sao_base_da_v2,
        ),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

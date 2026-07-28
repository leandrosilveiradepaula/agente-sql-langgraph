from copy import deepcopy

from app.domain.context_normalizer import normalize_context_snapshot
from app.domain.context_validator import validate_context_snapshot


def _intent_definition() -> dict:
    return {
        "entity_type": "intent_definition",
        "user_term": "generic_definition",
        "canonical_value": "intent_test",
        "target_table": None,
        "target_column": None,
        "sql_filter_hint": None,
        "business_rule": {
            "intent_catalog": {
                "semantic_description": (
                    "Definição semântica genérica para validação."
                ),
                "rules": [
                    {
                        "rule_name": "required_rule",
                        "effect": "require",
                        "concepts": [
                            {
                                "concept_name": "first_concept",
                                "terms": ["alpha", "alpha synonym"],
                                "match_mode": "contains",
                                "minimum_term_matches": 1,
                            },
                            {
                                "concept_name": "second_concept",
                                "terms": ["beta"],
                                "match_mode": "all_tokens",
                                "minimum_term_matches": 1,
                            },
                        ],
                        "minimum_concept_matches": 2,
                        "score": None,
                        "priority": 1,
                    },
                    {
                        "rule_name": "score_rule",
                        "effect": "positive_score",
                        "concepts": [
                            {
                                "concept_name": "score_concept",
                                "terms": ["gamma"],
                                "match_mode": "contains",
                                "minimum_term_matches": 1,
                            }
                        ],
                        "minimum_concept_matches": 1,
                        "score": 120,
                        "priority": 2,
                    },
                ],
            }
        },
        "priority": 2,
    }


def _raw_snapshot() -> dict:
    return {
        "semantic_agent_version": "context-validator-test-v3",
        "semantic_context_source": (
            "postgres_versioned_semantic_context"
        ),
        "regras": [
            {
                "rule_group": "config",
                "rule_name": "resolver",
                "rule_content": {
                    "component": "intent_resolver",
                    "minimum_score": 100,
                    "ambiguity_margin": 20,
                    "applied_confidence": 0.98,
                    "fallback_to_previous_intent": True,
                    "token_fallback": {
                        "enabled": True,
                        "apply_to_polarities": ["positive"],
                        "apply_to_match_modes": ["contains"],
                        "ignored_tokens": [],
                        "minimum_pattern_tokens": 2,
                        "minimum_matched_tokens": 2,
                        "minimum_pattern_coverage": 1.0,
                        "maximum_unmatched_pattern_tokens": 0,
                        "allow_prefix_equivalence": True,
                        "minimum_prefix_length": 6,
                        "minimum_prefix_ratio": 0.85,
                    },
                },
                "applies_to_intents": [],
                "validation_hint": None,
                "severity": "info",
                "priority": 1,
            },
            {
                "rule_group": "general",
                "rule_name": "rule_test",
                "rule_content": {"enabled": True},
                "applies_to_intents": ["intent_test"],
                "validation_hint": None,
                "severity": "error",
                "priority": 2,
            },
        ],
        "entidades": [
            {
                "entity_type": "intent_signal",
                "user_term": "generic analysis",
                "canonical_value": "intent_test",
                "target_table": None,
                "target_column": None,
                "sql_filter_hint": {
                    "resolver": {
                        "match_mode": "contains",
                        "polarity": "positive",
                        "score": 120,
                    }
                },
                "business_rule": None,
                "priority": 1,
            },
            _intent_definition(),
        ],
        "dre": [],
        "padroes": [
            {
                "intent_name": "intent_test",
                "pattern_name": "pattern_test",
                "business_question_examples": [],
                "required_tables": ["schema_test.table_test"],
                "required_rules": ["rule_test"],
                "sql_pattern": "SELECT 1",
                "notes": None,
                "priority": 1,
            }
        ],
        "catalogo": [
            {
                "table_name": "table_test",
                "schema_name": "schema_test",
                "table_type": "table",
                "description": None,
                "grain": None,
                "primary_key": ["id"],
                "key_columns": ["id"],
                "metric_columns": ["value"],
                "date_columns": ["event_date"],
                "join_rules": [],
                "ai_hint": None,
                "priority": 1,
            }
        ],
        "context_counts": {
            "regras": 2,
            "entidades": 2,
            "dre": 0,
            "padroes": 1,
            "catalogo": 1,
        },
    }


def _valid_snapshot() -> dict:
    return normalize_context_snapshot(_raw_snapshot())


def _error_codes(result: dict) -> set[str]:
    return {item["code"] for item in result["errors"]}


def test_aceita_snapshot_valido() -> None:
    result = validate_context_snapshot(_valid_snapshot())

    assert result["status"] == "valid"
    assert result["errors"] == []
    assert result["warnings"] == []


def test_aceita_catalogo_ausente() -> None:
    raw = _raw_snapshot()
    raw["entidades"] = raw["entidades"][:1]
    raw["context_counts"]["entidades"] = 1
    snapshot = normalize_context_snapshot(raw)

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "valid"
    assert snapshot["intent_resolution"]["intent_catalog"] == []


def test_aceita_token_fallback_desabilitado() -> None:
    snapshot = _valid_snapshot()
    snapshot["intent_resolution"]["config"][
        "token_fallback"
    ] = {"enabled": False}

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "valid"
    assert result["errors"] == []


def test_rejeita_catalogo_vazio() -> None:
    snapshot = _valid_snapshot()
    snapshot["table_catalog"] = []
    snapshot["tables"] = []
    snapshot["allowed_schemas"] = []
    snapshot["counts"]["table_catalog"] = 0

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "invalid"
    assert "TABLE_CATALOG_EMPTY" in _error_codes(result)


def test_rejeita_tabela_duplicada() -> None:
    snapshot = _valid_snapshot()
    duplicate = deepcopy(snapshot["table_catalog"][0])
    snapshot["table_catalog"].append(duplicate)
    snapshot["counts"]["table_catalog"] = 2

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "invalid"
    assert "TABLE_CATALOG_DUPLICATE" in _error_codes(result)


def test_rejeita_tabela_requerida_desconhecida() -> None:
    snapshot = _valid_snapshot()
    snapshot["query_patterns"][0]["required_tables"] = [
        "schema_test.unknown_table"
    ]

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "invalid"
    assert "REQUIRED_TABLE_NOT_ALLOWED" in _error_codes(result)


def test_rejeita_referencia_de_tabela_ambigua() -> None:
    raw = _raw_snapshot()
    raw["catalogo"].append(
        {
            **deepcopy(raw["catalogo"][0]),
            "schema_name": "second_schema",
        }
    )
    raw["padroes"][0]["required_tables"] = ["table_test"]
    raw["context_counts"]["catalogo"] = 2
    snapshot = normalize_context_snapshot(raw)

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "invalid"
    assert "REQUIRED_TABLE_AMBIGUOUS" in _error_codes(result)


def test_rejeita_sinal_com_intencao_inexistente() -> None:
    snapshot = _valid_snapshot()
    snapshot["intent_resolution"]["signals"][0][
        "intent_name"
    ] = "unknown_intent"

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "invalid"
    assert "INTENT_SIGNAL_UNKNOWN_INTENT" in _error_codes(result)


def test_rejeita_configuracao_principal_incompleta() -> None:
    snapshot = _valid_snapshot()
    del snapshot["intent_resolution"]["config"][
        "ambiguity_margin"
    ]

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "invalid"
    assert (
        "INTENT_RESOLVER_AMBIGUITY_MARGIN_INVALID"
        in _error_codes(result)
    )


def test_rejeita_confianca_fora_do_intervalo() -> None:
    snapshot = _valid_snapshot()
    snapshot["intent_resolution"]["config"][
        "applied_confidence"
    ] = 1.1

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "invalid"
    assert (
        "INTENT_RESOLVER_CONFIDENCE_INVALID"
        in _error_codes(result)
    )


def test_rejeita_match_mode_desconhecido() -> None:
    snapshot = _valid_snapshot()
    snapshot["intent_resolution"]["signals"][0][
        "match_mode"
    ] = "unknown_mode"

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "invalid"
    assert (
        "INTENT_SIGNAL_MATCH_MODE_INVALID"
        in _error_codes(result)
    )


def test_rejeita_polaridade_desconhecida() -> None:
    snapshot = _valid_snapshot()
    snapshot["intent_resolution"]["signals"][0][
        "polarity"
    ] = "neutral"

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "invalid"
    assert (
        "INTENT_SIGNAL_POLARITY_INVALID"
        in _error_codes(result)
    )


def test_rejeita_score_negativo() -> None:
    snapshot = _valid_snapshot()
    snapshot["intent_resolution"]["signals"][0]["score"] = -1

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "invalid"
    assert "INTENT_SIGNAL_SCORE_INVALID" in _error_codes(result)


def test_rejeita_token_fallback_incompleto() -> None:
    snapshot = _valid_snapshot()
    snapshot["intent_resolution"]["config"][
        "token_fallback"
    ] = {
        "enabled": True,
        "apply_to_polarities": ["positive"],
        "apply_to_match_modes": ["contains"],
    }

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "invalid"
    codes = _error_codes(result)
    assert (
        "INTENT_TOKEN_FALLBACK_MINIMUM_PATTERN_TOKENS_INVALID"
        in codes
    )
    assert "INTENT_TOKEN_FALLBACK_COVERAGE_INVALID" in codes


def test_rejeita_token_fallback_com_valores_nao_suportados() -> None:
    snapshot = _valid_snapshot()
    token_fallback = snapshot["intent_resolution"]["config"][
        "token_fallback"
    ]
    token_fallback["apply_to_polarities"] = ["neutral"]
    token_fallback["apply_to_match_modes"] = ["semantic"]
    token_fallback["minimum_pattern_coverage"] = 1.5

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "invalid"
    codes = _error_codes(result)
    assert "INTENT_TOKEN_FALLBACK_POLARITIES_INVALID" in codes
    assert "INTENT_TOKEN_FALLBACK_MATCH_MODES_INVALID" in codes
    assert "INTENT_TOKEN_FALLBACK_COVERAGE_INVALID" in codes


def test_rejeita_definicao_com_intencao_inexistente() -> None:
    raw = _raw_snapshot()
    raw["entidades"][1]["canonical_value"] = "unknown_intent"
    snapshot = normalize_context_snapshot(raw)

    result = validate_context_snapshot(snapshot)

    codes = _error_codes(result)
    assert result["status"] == "invalid"
    assert "INTENT_DEFINITION_UNKNOWN_INTENT" in codes
    assert "INTENT_CATALOG_UNKNOWN_INTENT" in codes


def test_rejeita_definicao_duplicada() -> None:
    raw = _raw_snapshot()
    duplicate = deepcopy(raw["entidades"][1])
    duplicate["user_term"] = "second_definition"
    duplicate["priority"] = 3
    raw["entidades"].append(duplicate)
    raw["context_counts"]["entidades"] = 3
    snapshot = normalize_context_snapshot(raw)

    result = validate_context_snapshot(snapshot)

    codes = _error_codes(result)
    assert result["status"] == "invalid"
    assert "INTENT_DEFINITION_DUPLICATE" in codes
    assert "INTENT_CATALOG_DUPLICATE" in codes


def test_rejeita_alvo_fisico_e_resolver_na_definicao() -> None:
    raw = _raw_snapshot()
    definition = raw["entidades"][1]
    definition["target_table"] = "schema_test.table_test"
    definition["sql_filter_hint"] = {
        "resolver": {
            "match_mode": "contains",
            "polarity": "positive",
            "score": 100,
        }
    }
    snapshot = normalize_context_snapshot(raw)

    result = validate_context_snapshot(snapshot)

    codes = _error_codes(result)
    assert result["status"] == "invalid"
    assert "INTENT_DEFINITION_PHYSICAL_TARGET_INVALID" in codes
    assert "INTENT_DEFINITION_RESOLVER_HINT_FORBIDDEN" in codes


def test_rejeita_payload_e_descricao_invalidos() -> None:
    raw = _raw_snapshot()
    raw["entidades"][1]["business_rule"] = None
    snapshot = normalize_context_snapshot(raw)

    result = validate_context_snapshot(snapshot)

    codes = _error_codes(result)
    assert result["status"] == "invalid"
    assert "INTENT_DEFINITION_BUSINESS_RULE_INVALID" in codes
    assert "INTENT_CATALOG_DESCRIPTION_REQUIRED" in codes
    assert "INTENT_CATALOG_RULES_INVALID" in codes


def test_rejeita_regras_e_conceitos_duplicados() -> None:
    snapshot = _valid_snapshot()
    entry = snapshot["intent_resolution"]["intent_catalog"][0]
    duplicate_rule = deepcopy(entry["rules"][0])
    duplicate_rule["priority"] = 3
    entry["rules"].append(duplicate_rule)
    duplicate_concept = deepcopy(entry["rules"][0]["concepts"][0])
    entry["rules"][0]["concepts"].append(duplicate_concept)
    entry["rules"][0]["minimum_concept_matches"] = 2

    result = validate_context_snapshot(snapshot)

    codes = _error_codes(result)
    assert result["status"] == "invalid"
    assert "INTENT_CATALOG_RULE_DUPLICATE" in codes
    assert "INTENT_CATALOG_CONCEPT_DUPLICATE" in codes


def test_rejeita_termos_duplicados_apos_normalizacao() -> None:
    snapshot = _valid_snapshot()
    concept = snapshot["intent_resolution"]["intent_catalog"][0][
        "rules"
    ][0]["concepts"][0]
    concept["terms"] = ["Álpha", "alpha"]
    concept["normalized_terms"] = ["alpha", "alpha"]
    concept["minimum_term_matches"] = 1

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "invalid"
    assert "INTENT_CATALOG_TERM_DUPLICATE" in _error_codes(result)


def test_rejeita_normalizacao_e_match_mode_invalidos() -> None:
    snapshot = _valid_snapshot()
    concept = snapshot["intent_resolution"]["intent_catalog"][0][
        "rules"
    ][0]["concepts"][0]
    concept["match_mode"] = "semantic"
    concept["normalized_terms"][0] = "wrong"

    result = validate_context_snapshot(snapshot)

    codes = _error_codes(result)
    assert result["status"] == "invalid"
    assert "INTENT_CATALOG_MATCH_MODE_INVALID" in codes
    assert "INTENT_CATALOG_TERM_NORMALIZATION_INVALID" in codes


def test_rejeita_minimos_fora_do_intervalo() -> None:
    snapshot = _valid_snapshot()
    rule = snapshot["intent_resolution"]["intent_catalog"][0][
        "rules"
    ][0]
    rule["minimum_concept_matches"] = 99
    rule["concepts"][0]["minimum_term_matches"] = 99

    result = validate_context_snapshot(snapshot)

    codes = _error_codes(result)
    assert result["status"] == "invalid"
    assert "INTENT_CATALOG_MINIMUM_CONCEPT_MATCHES_INVALID" in codes
    assert "INTENT_CATALOG_MINIMUM_TERM_MATCHES_INVALID" in codes


def test_rejeita_efeito_e_score_invalidos() -> None:
    snapshot = _valid_snapshot()
    rules = snapshot["intent_resolution"]["intent_catalog"][0][
        "rules"
    ]
    rules[0]["effect"] = "unknown_effect"
    rules[1]["score"] = None

    result = validate_context_snapshot(snapshot)

    codes = _error_codes(result)
    assert result["status"] == "invalid"
    assert "INTENT_CATALOG_RULE_EFFECT_INVALID" in codes
    assert "INTENT_CATALOG_RULE_SCORE_INVALID" in codes


def test_rejeita_score_em_regra_require() -> None:
    snapshot = _valid_snapshot()
    rule = snapshot["intent_resolution"]["intent_catalog"][0][
        "rules"
    ][0]
    rule["score"] = 10

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "invalid"
    assert "INTENT_CATALOG_RULE_SCORE_FORBIDDEN" in _error_codes(
        result
    )


def test_rejeita_projecao_ausente_e_orfa() -> None:
    snapshot = _valid_snapshot()
    original = deepcopy(
        snapshot["intent_resolution"]["intent_catalog"][0]
    )
    snapshot["intent_resolution"]["intent_catalog"] = []

    missing_result = validate_context_snapshot(snapshot)
    assert "INTENT_CATALOG_PROJECTION_MISSING" in _error_codes(
        missing_result
    )

    raw = _raw_snapshot()
    raw["entidades"] = raw["entidades"][:1]
    raw["context_counts"]["entidades"] = 1
    orphan_snapshot = normalize_context_snapshot(raw)
    orphan_snapshot["intent_resolution"]["intent_catalog"] = [
        original
    ]

    orphan_result = validate_context_snapshot(orphan_snapshot)
    assert "INTENT_CATALOG_ORPHAN_ENTRY" in _error_codes(
        orphan_result
    )


def test_rejeita_nomes_obrigatorios_da_definicao() -> None:
    raw = _raw_snapshot()
    definition = raw["entidades"][1]
    definition["user_term"] = ""
    definition["canonical_value"] = ""
    snapshot = normalize_context_snapshot(raw)

    result = validate_context_snapshot(snapshot)

    codes = _error_codes(result)
    assert result["status"] == "invalid"
    assert "INTENT_DEFINITION_NAME_REQUIRED" in codes
    assert "INTENT_DEFINITION_INTENT_REQUIRED" in codes
    assert "INTENT_CATALOG_DEFINITION_NAME_REQUIRED" in codes
    assert "INTENT_CATALOG_INTENT_REQUIRED" in codes


def test_rejeita_prioridades_invalidas_do_catalogo() -> None:
    snapshot = _valid_snapshot()
    entry = snapshot["intent_resolution"]["intent_catalog"][0]
    entry["priority"] = -1
    entry["rules"][0]["priority"] = float("inf")

    result = validate_context_snapshot(snapshot)

    codes = _error_codes(result)
    assert result["status"] == "invalid"
    assert "INTENT_CATALOG_PRIORITY_INVALID" in codes
    assert "INTENT_CATALOG_RULE_PRIORITY_INVALID" in codes


def test_rejeita_catalogo_canonico_ausente() -> None:
    snapshot = _valid_snapshot()
    del snapshot["intent_resolution"]["intent_catalog"]

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "invalid"
    assert "INTENT_CATALOG_INVALID" in _error_codes(result)


def test_rejeita_contagem_inconsistente() -> None:
    snapshot = _valid_snapshot()
    snapshot["counts"]["rules"] = 99

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "invalid"
    assert "CONTEXT_COUNT_MISMATCH" in _error_codes(result)


def main() -> None:
    tests = [
        ("aceita snapshot válido", test_aceita_snapshot_valido),
        ("aceita catálogo ausente", test_aceita_catalogo_ausente),
        (
            "aceita token fallback desabilitado",
            test_aceita_token_fallback_desabilitado,
        ),
        ("rejeita catálogo vazio", test_rejeita_catalogo_vazio),
        ("rejeita tabela duplicada", test_rejeita_tabela_duplicada),
        (
            "rejeita tabela requerida desconhecida",
            test_rejeita_tabela_requerida_desconhecida,
        ),
        (
            "rejeita referência de tabela ambígua",
            test_rejeita_referencia_de_tabela_ambigua,
        ),
        (
            "rejeita sinal com intenção inexistente",
            test_rejeita_sinal_com_intencao_inexistente,
        ),
        (
            "rejeita configuração principal incompleta",
            test_rejeita_configuracao_principal_incompleta,
        ),
        (
            "rejeita confiança fora do intervalo",
            test_rejeita_confianca_fora_do_intervalo,
        ),
        (
            "rejeita match mode desconhecido",
            test_rejeita_match_mode_desconhecido,
        ),
        (
            "rejeita polaridade desconhecida",
            test_rejeita_polaridade_desconhecida,
        ),
        ("rejeita score negativo", test_rejeita_score_negativo),
        (
            "rejeita token fallback incompleto",
            test_rejeita_token_fallback_incompleto,
        ),
        (
            "rejeita token fallback com valores não suportados",
            test_rejeita_token_fallback_com_valores_nao_suportados,
        ),
        (
            "rejeita definição com intenção inexistente",
            test_rejeita_definicao_com_intencao_inexistente,
        ),
        (
            "rejeita definição duplicada",
            test_rejeita_definicao_duplicada,
        ),
        (
            "rejeita alvo físico e resolver na definição",
            test_rejeita_alvo_fisico_e_resolver_na_definicao,
        ),
        (
            "rejeita payload e descrição inválidos",
            test_rejeita_payload_e_descricao_invalidos,
        ),
        (
            "rejeita regras e conceitos duplicados",
            test_rejeita_regras_e_conceitos_duplicados,
        ),
        (
            "rejeita termos duplicados após normalização",
            test_rejeita_termos_duplicados_apos_normalizacao,
        ),
        (
            "rejeita normalização e match mode inválidos",
            test_rejeita_normalizacao_e_match_mode_invalidos,
        ),
        (
            "rejeita mínimos fora do intervalo",
            test_rejeita_minimos_fora_do_intervalo,
        ),
        (
            "rejeita efeito e score inválidos",
            test_rejeita_efeito_e_score_invalidos,
        ),
        (
            "rejeita score em regra require",
            test_rejeita_score_em_regra_require,
        ),
        (
            "rejeita projeção ausente e órfã",
            test_rejeita_projecao_ausente_e_orfa,
        ),
        (
            "rejeita nomes obrigatórios da definição",
            test_rejeita_nomes_obrigatorios_da_definicao,
        ),
        (
            "rejeita prioridades inválidas do catálogo",
            test_rejeita_prioridades_invalidas_do_catalogo,
        ),
        (
            "rejeita catálogo canônico ausente",
            test_rejeita_catalogo_canonico_ausente,
        ),
        (
            "rejeita contagem inconsistente",
            test_rejeita_contagem_inconsistente,
        ),
    ]

    for index, (name, test_function) in enumerate(
        tests,
        start=1,
    ):
        test_function()
        print(f"TESTE {index} — {name}: OK")


if __name__ == "__main__":
    main()

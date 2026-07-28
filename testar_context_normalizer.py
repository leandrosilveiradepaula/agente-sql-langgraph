from copy import deepcopy

from app.domain.context_normalizer import (
    ContextNormalizationError,
    normalize_context_snapshot,
)


def _intent_definition() -> dict:
    return {
        "entity_type": "intent_definition",
        "user_term": "generic_definition",
        "canonical_value": "generic_test_intent",
        "target_table": None,
        "target_column": None,
        "sql_filter_hint": None,
        "business_rule": {
            "intent_catalog": {
                "semantic_description": (
                    "  Definição semântica genérica para teste.  "
                ),
                "rules": [
                    {
                        "rule_name": "zeta_optional_score",
                        "effect": "POSITIVE_SCORE",
                        "concepts": [
                            {
                                "concept_name": "second_concept",
                                "terms": [
                                    "Álpha",
                                    "alpha synonym",
                                ],
                                "match_mode": "CONTAINS",
                                "minimum_term_matches": "1",
                            }
                        ],
                        "minimum_concept_matches": "1",
                        "score": "120",
                        "priority": "2",
                    },
                    {
                        "rule_name": "alpha_required_rule",
                        "effect": "REQUIRE",
                        "concepts": [
                            {
                                "concept_name": "regex_concept",
                                "terms": [r"^Código\s+[A-Z]{2}$"],
                                "match_mode": "REGEX",
                                "minimum_term_matches": "1",
                            },
                            {
                                "concept_name": "first_concept",
                                "terms": [
                                    " Beta ",
                                    "alpha",
                                ],
                                "match_mode": "ALL_TOKENS",
                                "minimum_term_matches": "1",
                            },
                        ],
                        "minimum_concept_matches": "2",
                        "score": None,
                        "priority": "1",
                    },
                ],
            }
        },
        "priority": "3",
    }


def _raw_snapshot() -> dict:
    return {
        "semantic_agent_version": "context-test-v3",
        "semantic_context_source": (
            "postgres_versioned_semantic_context"
        ),
        "regras": [
            {
                "rule_group": "config",
                "rule_name": "resolver",
                "rule_content": (
                    '{"component":"intent_resolver",'
                    '"minimum_score":"100",'
                    '"ambiguity_margin":"20",'
                    '"applied_confidence":"0,98",'
                    '"fallback_to_previous_intent":"true",'
                    '"token_fallback":{'
                    '"enabled":"true",'
                    '"apply_to_polarities":["positive"],'
                    '"apply_to_match_modes":["contains"],'
                    '"ignored_tokens":["De","de","COM"],'
                    '"minimum_pattern_tokens":"2",'
                    '"minimum_matched_tokens":"2",'
                    '"minimum_pattern_coverage":"1",'
                    '"maximum_unmatched_pattern_tokens":"0",'
                    '"allow_prefix_equivalence":"true",'
                    '"minimum_prefix_length":"6",'
                    '"minimum_prefix_ratio":"0,85"}}'
                ),
                "applies_to_intents": "[]",
                "validation_hint": None,
                "severity": "info",
                "priority": "1",
            },
            {
                "rule_group": "general",
                "rule_name": "generic_test_rule",
                "rule_content": {"enabled": True},
                "applies_to_intents": '["generic_test_intent"]',
                "validation_hint": {"required": True},
                "severity": "error",
                "priority": 2,
            },
        ],
        "entidades": [
            {
                "entity_type": "intent_signal",
                "user_term": "Análise,   genérica!!!",
                "canonical_value": "generic_test_intent",
                "target_table": None,
                "target_column": None,
                "sql_filter_hint": (
                    '{"resolver":{"match_mode":"CONTAINS",'
                    '"polarity":"POSITIVE","score":"120"}}'
                ),
                "business_rule": None,
                "priority": 5,
            },
            {
                "entity_type": "intent_signal",
                "user_term": r"^Código\s+[A-Z]{2}$",
                "canonical_value": "generic_test_intent",
                "target_table": None,
                "target_column": None,
                "sql_filter_hint": {
                    "resolver": {
                        "match_mode": "regex",
                        "polarity": "negative",
                        "score": 30,
                    }
                },
                "business_rule": None,
                "priority": 6,
            },
            _intent_definition(),
        ],
        "dre": [
            {
                "dre_code": "01",
                "nivel_1_bi": "Grupo teste",
                "business_description": "Descrição",
                "sign_convention": {"multiplier": 1},
                "category": "categoria",
                "is_revenue": "true",
                "is_deduction": False,
                "is_cost": 0,
                "is_opex": 1,
                "is_financial_result": "false",
                "sql_filter_hint": None,
                "sort_order": "1",
            }
        ],
        "padroes": [
            {
                "intent_name": "generic_test_intent",
                "pattern_name": "generic_test_pattern",
                "business_question_examples": (
                    '["Exemplo apenas documental"]'
                ),
                "required_tables": (
                    '["schema_test.table_test"]'
                ),
                "required_rules": '["generic_test_rule"]',
                "sql_pattern": "SELECT 1",
                "notes": None,
                "priority": "1",
            }
        ],
        "catalogo": [
            {
                "table_name": "table_test",
                "schema_name": "schema_test",
                "table_type": "table",
                "description": None,
                "grain": "uma linha por teste",
                "primary_key": '["id"]',
                "key_columns": '["id"]',
                "metric_columns": '["value"]',
                "date_columns": '["event_date"]',
                "join_rules": "[]",
                "ai_hint": {"usage": "test"},
                "priority": 1,
            }
        ],
        "context_counts": {
            "regras": 2,
            "entidades": 3,
            "dre": 1,
            "padroes": 1,
            "catalogo": 1,
        },
    }


def test_normaliza_snapshot_fisico() -> None:
    snapshot = normalize_context_snapshot(_raw_snapshot())

    assert snapshot["version"] == "context-test-v3"
    assert snapshot["source"] == (
        "postgres_versioned_semantic_context"
    )
    assert snapshot["counts"]["rules"] == 2
    assert snapshot["counts"]["entities"] == 3
    assert snapshot["allowed_schemas"] == ["schema_test"]

    raw_component_config = snapshot["component_configs"][
        "intent_resolver"
    ]
    assert raw_component_config["minimum_score"] == "100"

    resolver_config = snapshot["intent_resolution"]["config"]
    assert resolver_config["component"] == "intent_resolver"
    assert resolver_config["minimum_score"] == 100.0
    assert resolver_config["ambiguity_margin"] == 20.0
    assert resolver_config["applied_confidence"] == 0.98
    assert resolver_config["fallback_to_previous_intent"] is True

    token_fallback = resolver_config["token_fallback"]
    assert token_fallback["enabled"] is True
    assert token_fallback["apply_to_polarities"] == [
        "positive"
    ]
    assert token_fallback["apply_to_match_modes"] == [
        "contains"
    ]
    assert token_fallback["ignored_tokens"] == [
        "com",
        "de",
    ]
    assert token_fallback["minimum_pattern_tokens"] == 2
    assert token_fallback["minimum_matched_tokens"] == 2
    assert token_fallback["minimum_pattern_coverage"] == 1.0
    assert token_fallback[
        "maximum_unmatched_pattern_tokens"
    ] == 0
    assert token_fallback["allow_prefix_equivalence"] is True
    assert token_fallback["minimum_prefix_length"] == 6
    assert token_fallback["minimum_prefix_ratio"] == 0.85

    signals = snapshot["intent_resolution"]["signals"]
    assert len(signals) == 2

    direct_signal = signals[0]
    assert direct_signal["intent_name"] == "generic_test_intent"
    assert direct_signal["raw_pattern"] == (
        "Análise,   genérica!!!"
    )
    assert direct_signal["normalized_pattern"] == (
        "analise generica"
    )
    assert direct_signal["match_mode"] == "contains"
    assert direct_signal["polarity"] == "positive"
    assert direct_signal["score"] == 120.0

    intent_catalog = snapshot["intent_resolution"][
        "intent_catalog"
    ]
    assert len(intent_catalog) == 1
    entry = intent_catalog[0]
    assert entry["intent_name"] == "generic_test_intent"
    assert entry["definition_name"] == "generic_definition"
    assert entry["semantic_description"] == (
        "Definição semântica genérica para teste."
    )
    assert entry["priority"] == 3.0

    assert [rule["rule_name"] for rule in entry["rules"]] == [
        "alpha_required_rule",
        "zeta_optional_score",
    ]
    required_rule = entry["rules"][0]
    assert required_rule["effect"] == "require"
    assert required_rule["minimum_concept_matches"] == 2
    assert required_rule["score"] is None
    assert [
        concept["concept_name"]
        for concept in required_rule["concepts"]
    ] == ["first_concept", "regex_concept"]

    first_concept = required_rule["concepts"][0]
    assert first_concept["match_mode"] == "all_tokens"
    assert first_concept["terms"] == ["alpha", "Beta"]
    assert first_concept["normalized_terms"] == [
        "alpha",
        "beta",
    ]

    regex_concept = required_rule["concepts"][1]
    expected_regex = r"^Código\s+[A-Z]{2}$"
    assert regex_concept["terms"] == [expected_regex]
    assert regex_concept["normalized_terms"] == [expected_regex]

    assert snapshot["tables"][0]["schema"] == "schema_test"
    assert snapshot["tables"][0]["name"] == "table_test"
    assert (
        snapshot["aliases"]["Análise,   genérica!!!"]
        == "generic_test_intent"
    )
    assert "generic_definition" not in snapshot["aliases"]
    assert len(snapshot["fingerprint"]) == 64


def test_preserva_padrao_regex_bruto() -> None:
    snapshot = normalize_context_snapshot(_raw_snapshot())
    signals = snapshot["intent_resolution"]["signals"]

    regex_signal = next(
        signal
        for signal in signals
        if signal["match_mode"] == "regex"
    )

    expected_pattern = r"^Código\s+[A-Z]{2}$"
    assert regex_signal["raw_pattern"] == expected_pattern
    assert regex_signal["normalized_pattern"] == expected_pattern
    assert regex_signal["polarity"] == "negative"


def test_intent_definition_fica_isolada_de_sinais_e_aliases() -> None:
    raw = _raw_snapshot()
    definition = raw["entidades"][2]
    definition["sql_filter_hint"] = {
        "resolver": {
            "match_mode": "contains",
            "polarity": "positive",
            "score": 999,
        }
    }

    snapshot = normalize_context_snapshot(raw)

    assert len(snapshot["intent_resolution"]["signals"]) == 2
    assert "generic_definition" not in snapshot["aliases"]
    assert len(snapshot["intent_resolution"]["intent_catalog"]) == 1


def test_catalogo_ausente_resulta_em_lista_vazia() -> None:
    raw = _raw_snapshot()
    raw["entidades"] = raw["entidades"][:2]
    raw["context_counts"]["entidades"] = 2

    snapshot = normalize_context_snapshot(raw)

    assert snapshot["intent_resolution"]["intent_catalog"] == []


def test_fingerprint_independe_da_ordem_das_colecoes() -> None:
    first = _raw_snapshot()
    second = deepcopy(first)
    second["regras"] = list(reversed(second["regras"]))
    second["entidades"] = list(reversed(second["entidades"]))
    rules = second["entidades"][0].get("business_rule")
    if isinstance(rules, dict) and isinstance(
        rules.get("intent_catalog"), dict
    ):
        catalog_rules = rules["intent_catalog"].get("rules")
        if isinstance(catalog_rules, list):
            rules["intent_catalog"]["rules"] = list(
                reversed(catalog_rules)
            )

    first_snapshot = normalize_context_snapshot(first)
    second_snapshot = normalize_context_snapshot(second)

    assert (
        first_snapshot["fingerprint"]
        == second_snapshot["fingerprint"]
    )


def test_fingerprint_muda_quando_catalogo_muda() -> None:
    first = _raw_snapshot()
    second = deepcopy(first)
    second["entidades"][2]["business_rule"]["intent_catalog"][
        "semantic_description"
    ] = "Outra descrição semântica genérica."

    first_snapshot = normalize_context_snapshot(first)
    second_snapshot = normalize_context_snapshot(second)

    assert (
        first_snapshot["fingerprint"]
        != second_snapshot["fingerprint"]
    )


def test_rejeita_colecao_com_formato_invalido() -> None:
    raw = _raw_snapshot()
    raw["regras"] = {"rule_name": "nao_e_lista"}

    try:
        normalize_context_snapshot(raw)
    except ContextNormalizationError as exc:
        assert exc.field_name == "regras"
        assert "lista JSON" in exc.message
    else:
        raise AssertionError(
            "Era esperado ContextNormalizationError."
        )


def main() -> None:
    tests = [
        (
            "normaliza snapshot físico e catálogo semântico",
            test_normaliza_snapshot_fisico,
        ),
        (
            "preserva padrão regex bruto",
            test_preserva_padrao_regex_bruto,
        ),
        (
            "isola intent_definition de sinais e aliases",
            test_intent_definition_fica_isolada_de_sinais_e_aliases,
        ),
        (
            "projeta catálogo ausente como lista vazia",
            test_catalogo_ausente_resulta_em_lista_vazia,
        ),
        (
            "fingerprint independe da ordem das coleções",
            test_fingerprint_independe_da_ordem_das_colecoes,
        ),
        (
            "fingerprint inclui conteúdo do catálogo",
            test_fingerprint_muda_quando_catalogo_muda,
        ),
        (
            "rejeita coleção inválida",
            test_rejeita_colecao_com_formato_invalido,
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

from copy import deepcopy

from app.domain.context_normalizer import (
    ContextNormalizationError,
    normalize_context_snapshot,
)


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
            "entidades": 2,
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
    assert snapshot["counts"]["entities"] == 2
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

    assert snapshot["tables"][0]["schema"] == "schema_test"
    assert snapshot["tables"][0]["name"] == "table_test"
    assert (
        snapshot["aliases"]["Análise,   genérica!!!"]
        == "generic_test_intent"
    )
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


def test_fingerprint_independe_da_ordem_das_colecoes() -> None:
    first = _raw_snapshot()
    second = deepcopy(first)
    second["regras"] = list(reversed(second["regras"]))
    second["entidades"] = list(reversed(second["entidades"]))

    first_snapshot = normalize_context_snapshot(first)
    second_snapshot = normalize_context_snapshot(second)

    assert (
        first_snapshot["fingerprint"]
        == second_snapshot["fingerprint"]
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
            "normaliza snapshot físico e configuração do resolvedor",
            test_normaliza_snapshot_fisico,
        ),
        (
            "preserva padrão regex bruto",
            test_preserva_padrao_regex_bruto,
        ),
        (
            "fingerprint independe da ordem das coleções",
            test_fingerprint_independe_da_ordem_das_colecoes,
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

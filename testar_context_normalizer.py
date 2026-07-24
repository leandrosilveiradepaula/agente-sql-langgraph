from copy import deepcopy

from app.domain.context_normalizer import (
    ContextNormalizationError,
    normalize_context_snapshot,
)


def _raw_snapshot() -> dict:
    return {
        "semantic_agent_version": "context-test-v2",
        "semantic_context_source": (
            "postgres_versioned_semantic_context"
        ),
        "regras": [
            {
                "rule_group": "config",
                "rule_name": "resolver",
                "rule_content": (
                    '{"component":"intent_resolver",'
                    '"minimum_score":100}'
                ),
                "applies_to_intents": "[]",
                "validation_hint": None,
                "severity": "info",
                "priority": "1",
            },
            {
                "rule_group": "financeiro",
                "rule_name": "regra_teste",
                "rule_content": {"enabled": True},
                "applies_to_intents": '["intent_teste"]',
                "validation_hint": {"required": True},
                "severity": "error",
                "priority": 2,
            },
        ],
        "entidades": [
            {
                "entity_type": "intent_signal",
                "user_term": "Gestão   do orçamento",
                "canonical_value": "intent_teste",
                "target_table": None,
                "target_column": None,
                "sql_filter_hint": (
                    '{"resolver":{"match_mode":"contains",'
                    '"polarity":"positive","score":120}}'
                ),
                "business_rule": None,
                "priority": 5,
            }
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
                "intent_name": "intent_teste",
                "pattern_name": "padrao_teste",
                "business_question_examples": (
                    '["Exemplo apenas documental"]'
                ),
                "required_tables": (
                    '["schema_teste.tabela_teste"]'
                ),
                "required_rules": '["regra_teste"]',
                "sql_pattern": "SELECT 1",
                "notes": None,
                "priority": "1",
            }
        ],
        "catalogo": [
            {
                "table_name": "tabela_teste",
                "schema_name": "schema_teste",
                "table_type": "table",
                "description": None,
                "grain": "uma linha por teste",
                "primary_key": '["id"]',
                "key_columns": '["id"]',
                "metric_columns": '["valor"]',
                "date_columns": '["data"]',
                "join_rules": "[]",
                "ai_hint": {"usage": "test"},
                "priority": 1,
            }
        ],
        "context_counts": {
            "regras": 2,
            "entidades": 1,
            "dre": 1,
            "padroes": 1,
            "catalogo": 1,
        },
    }


def test_normaliza_snapshot_fisico() -> None:
    snapshot = normalize_context_snapshot(_raw_snapshot())

    assert snapshot["version"] == "context-test-v2"
    assert snapshot["source"] == (
        "postgres_versioned_semantic_context"
    )
    assert snapshot["counts"]["rules"] == 2
    assert snapshot["allowed_schemas"] == ["schema_teste"]
    assert (
        snapshot["component_configs"]["intent_resolver"][
            "minimum_score"
        ]
        == 100
    )

    signals = snapshot["intent_resolution"]["signals"]
    assert len(signals) == 1
    assert signals[0]["intent_name"] == "intent_teste"
    assert signals[0]["raw_pattern"] == (
        "Gestão   do orçamento"
    )
    assert signals[0]["normalized_pattern"] == (
        "gestao do orcamento"
    )
    assert signals[0]["score"] == 120.0

    assert snapshot["tables"][0]["schema"] == "schema_teste"
    assert snapshot["tables"][0]["name"] == "tabela_teste"
    assert (
        snapshot["aliases"]["Gestão   do orçamento"]
        == "intent_teste"
    )
    assert len(snapshot["fingerprint"]) == 64


def test_fingerprint_independe_da_ordem_das_colecoes() -> None:
    first = _raw_snapshot()
    second = deepcopy(first)
    second["regras"] = list(reversed(second["regras"]))

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
            "normaliza snapshot físico",
            test_normaliza_snapshot_fisico,
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

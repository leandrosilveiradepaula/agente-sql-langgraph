from copy import deepcopy

from app.domain.context_normalizer import normalize_context_snapshot
from app.domain.context_validator import validate_context_snapshot


def _raw_snapshot() -> dict:
    return {
        "semantic_agent_version": "context-validator-test-v1",
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
                "user_term": "budget management",
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
            }
        ],
        "dre": [],
        "padroes": [
            {
                "intent_name": "intent_test",
                "pattern_name": "pattern_test",
                "business_question_examples": [],
                "required_tables": [
                    "schema_test.table_test"
                ],
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
            "entidades": 1,
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


def test_rejeita_contagem_inconsistente() -> None:
    snapshot = _valid_snapshot()
    snapshot["counts"]["rules"] = 99

    result = validate_context_snapshot(snapshot)

    assert result["status"] == "invalid"
    assert "CONTEXT_COUNT_MISMATCH" in _error_codes(result)


def main() -> None:
    tests = [
        ("aceita snapshot válido", test_aceita_snapshot_valido),
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

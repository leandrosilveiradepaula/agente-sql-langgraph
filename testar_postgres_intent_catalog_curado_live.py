from __future__ import annotations

from copy import deepcopy

from validar_postgres_intent_catalog_curado_live import _reconcile_definitions


def _definition(*, user_term: str = "generic definition") -> dict:
    return {
        "entity_type": "intent_definition",
        "user_term": user_term,
        "canonical_value": "generic_intent",
        "target_table": None,
        "target_column": None,
        "sql_filter_hint": None,
        "business_rule": {
            "intent_catalog": {
                "semantic_description": "Generic semantic definition.",
                "rules": [
                    {
                        "rule_name": "generic_score",
                        "effect": "positive_score",
                        "minimum_concept_matches": 1,
                        "score": 120,
                        "priority": 1,
                        "concepts": [
                            {
                                "concept_name": "generic_concept",
                                "match_mode": "contains",
                                "minimum_term_matches": 1,
                                "terms": ["generic"],
                            }
                        ],
                    }
                ],
            }
        },
        "priority": 1,
    }


def _snapshot(entities: list[dict]) -> dict:
    return {
        "entidades": deepcopy(entities),
        "context_counts": {"entidades": len(entities)},
    }


def test_reconcile_sobrepoe_apenas_definicao_ausente() -> None:
    definition = _definition()

    snapshot, diagnostic = _reconcile_definitions(
        _snapshot([]),
        [definition],
    )

    assert snapshot["entidades"] == [definition]
    assert snapshot["context_counts"]["entidades"] == 1
    assert diagnostic == {
        "persisted_equivalent": 0,
        "overlaid_in_memory": 1,
    }


def test_reconcile_reutiliza_definicao_persistida_equivalente() -> None:
    definition = _definition()

    snapshot, diagnostic = _reconcile_definitions(
        _snapshot([definition]),
        [definition],
    )

    assert snapshot["entidades"] == [definition]
    assert snapshot["context_counts"]["entidades"] == 1
    assert diagnostic == {
        "persisted_equivalent": 1,
        "overlaid_in_memory": 0,
    }


def test_reconcile_rejeita_definicao_persistida_divergente() -> None:
    local = _definition()
    persisted = _definition()
    persisted["business_rule"]["intent_catalog"]["rules"][0]["score"] = 121

    try:
        _reconcile_definitions(_snapshot([persisted]), [local])
    except ValueError as error:
        assert "divergente" in str(error)
    else:
        raise AssertionError("definicao divergente deveria falhar")


def test_reconcile_rejeita_duplicata_persistida() -> None:
    definition = _definition()
    duplicate = deepcopy(definition)

    try:
        _reconcile_definitions(
            _snapshot([definition, duplicate]),
            [definition],
        )
    except ValueError as error:
        assert "duplicadas" in str(error)
    else:
        raise AssertionError("duplicata persistida deveria falhar")


def main() -> None:
    tests = [
        ("overlay somente ausente", test_reconcile_sobrepoe_apenas_definicao_ausente),
        (
            "reutiliza persisted equivalente",
            test_reconcile_reutiliza_definicao_persistida_equivalente,
        ),
        (
            "rejeita persisted divergente",
            test_reconcile_rejeita_definicao_persistida_divergente,
        ),
        (
            "rejeita duplicata persisted",
            test_reconcile_rejeita_duplicata_persistida,
        ),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

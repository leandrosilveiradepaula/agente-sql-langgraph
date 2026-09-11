from __future__ import annotations

from copy import deepcopy

from app.adapters.testing.fake_sql_generator import FakeSqlGenerator
from app.domain.context_normalizer import normalize_context_snapshot
from app.domain.context_validator import validate_context_snapshot
from app.domain.intent_resolver import resolve_intent
from app.domain.planner import build_query_plan
from app.domain.sql_contract import run_sql_contract_gate
from app.domain.sql_generation import build_sql_generation_request


CONCEPT = "category_alpha"
BINDING_REF = "binding-category-alpha-v1"
TABLE = "synthetic.records"
COLUMN = "category_code"
VALUE = "alpha-value"


def _raw_context(*, binding: dict | None = None, aliases: list[str] | None = None) -> dict:
    configured_aliases = aliases or ["alpha class", "primary group"]
    entities = [
        {
            "entity_type": "intent_signal",
            "user_term": "synthetic report",
            "canonical_value": "synthetic_intent",
            "sql_filter_hint": {
                "resolver": {
                    "match_mode": "contains",
                    "polarity": "positive",
                    "score": 120,
                }
            },
            "priority": 1,
        },
        {
            "entity_type": "intent_definition",
            "user_term": "synthetic definition",
            "canonical_value": "synthetic_intent",
            "business_rule": {
                "intent_catalog": {
                    "semantic_description": "Synthetic offline intent.",
                    "rules": [{
                        "rule_name": "configured_filter_evidence",
                        "effect": "positive_score",
                        "concepts": [{
                            "concept_name": CONCEPT,
                            "terms": configured_aliases,
                            "match_mode": "contains",
                            "minimum_term_matches": 1,
                        }],
                        "minimum_concept_matches": 1,
                        "score": 120,
                        "priority": 1,
                    }],
                }
            },
            "priority": 1,
        },
        *[
            {
                "entity_type": "filter_concept",
                "user_term": term,
                "canonical_value": CONCEPT,
                "priority": index + 1,
            }
            for index, term in enumerate(configured_aliases)
        ],
    ]
    if binding is not None:
        entities.append({
            "entity_type": "filter_binding",
            "canonical_value": CONCEPT,
            "business_rule": {"filter_binding": binding},
            "priority": 1,
        })
    return {
        "semantic_agent_version": "synthetic-context-v1",
        "semantic_context_source": "offline-versioned-fixture",
        "rules": [
            {
                "rule_group": "configuration",
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
                "severity": "info",
                "priority": 1,
            },
            {
                "rule_group": "generic",
                "rule_name": "synthetic_read_rule",
                "rule_content": {"enabled": True},
                "applies_to_intents": ["synthetic_intent"],
                "severity": "error",
                "priority": 2,
            },
        ],
        "entities": entities,
        "dre_mappings": [],
        "query_patterns": [{
            "intent_name": "synthetic_intent",
            "pattern_name": "synthetic_projection",
            "business_question_examples": [],
            "required_tables": [TABLE],
            "required_rules": ["synthetic_read_rule"],
            "sql_pattern": "",
            "notes": "No question or SQL lookup.",
            "priority": 1,
        }],
        "table_catalog": [{
            "schema_name": "synthetic",
            "table_name": "records",
            "table_type": "table",
            "description": "Synthetic records.",
            "grain": {"kind": "synthetic"},
            "primary_key": ["id"],
            "key_columns": ["id", COLUMN],
            "metric_columns": [],
            "date_columns": [],
            "join_rules": [],
            "ai_hint": None,
            "priority": 1,
            "columns": [
                {"name": "id", "data_type": "integer", "nullable": False},
                {"name": COLUMN, "data_type": "text", "nullable": False},
            ],
        }],
    }


def _binding(**overrides: object) -> dict:
    result = {
        "binding_ref": BINDING_REF,
        "filter_concept": CONCEPT,
        "required": True,
        "scope": "where",
        "target_table": TABLE,
        "target_column": COLUMN,
        "operator": "=",
        "value": VALUE,
        "join_path": [],
    }
    result.update(overrides)
    return result


def _plan(question: str, raw_context: dict) -> dict:
    context = normalize_context_snapshot(raw_context)
    validation = validate_context_snapshot(context)
    assert validation["status"] == "valid", validation
    evidence = resolve_intent(question, context["intent_resolution"])
    assert evidence["applied"] is True
    result = build_query_plan(
        context=context,
        intent_name=evidence["intent"],
        intent_confidence=evidence["intent_confidence"],
        normalized_question=question,
        intent_resolution_result=evidence,
    )
    assert result["status"] == "planned", result
    assert result["query_plan"] is not None
    return result["query_plan"]


def test_fluxo_offline_usa_obrigacao_semantica_e_binding_separado() -> None:
    raw_context = _raw_context(binding=_binding())
    plans = [
        _plan(question, raw_context)
        for question in (
            "synthetic report for alpha class",
            "synthetic report about primary group",
        )
    ]
    for plan in plans:
        planning = plan["planning_context"]
        assert len(planning["planned_filters"]) == 1
        obligation = planning["planned_filters"][0]
        assert obligation["filter_concept"] == CONCEPT
        assert obligation["binding_ref"] == BINDING_REF
        assert not ({"target_table", "target_column", "operator", "value"} & obligation.keys())
        assert planning["resolved_filter_bindings"] == [_binding()]

        request = build_sql_generation_request(plan)
        assert request["generation_context"]["planned_filters"] == [obligation]
        assert request["generation_context"]["filter_bindings"] == [_binding()]
        assert "sql_filter_hint" not in obligation
        assert "sql_filter_hint" not in request["generation_context"]["filter_bindings"][0]
        assert not ({"expected_sql", "golden_answer", "benchmark"} & request.keys())

        generator = FakeSqlGenerator(
            f"SELECT id FROM {TABLE} WHERE {COLUMN} = '{VALUE}'"
        )
        generated = generator.generate(request)["output_text"]
        approved, _ = run_sql_contract_gate(current_sql=generated, query_plan=plan)
        rejected, _ = run_sql_contract_gate(
            current_sql=f"SELECT id FROM {TABLE}", query_plan=plan
        )
        assert approved["status"] == "approved"
        assert rejected["status"] == "rejected"

    assert plans[0]["planning_context"]["planned_filters"][0]["filter_concept"] == (
        plans[1]["planning_context"]["planned_filters"][0]["filter_concept"]
    )


def test_binding_ausente_ambiguo_invalido_e_divergente_falha_fechado() -> None:
    cases = []
    cases.append(_raw_context(binding=None))
    ambiguous = _raw_context(binding=_binding())
    ambiguous["entities"].append(deepcopy(ambiguous["entities"][-1]))
    cases.append(ambiguous)
    invalid = _binding()
    del invalid["target_column"]
    cases.append(_raw_context(binding=invalid))
    cases.append(_raw_context(binding=_binding(filter_concept="category_beta")))

    for raw_context in cases:
        plan = _plan("synthetic report for alpha class", raw_context)
        planning = plan["planning_context"]
        assert planning["planned_filters"] == []
        assert planning["resolved_filter_bindings"] == []
        assert planning["diagnostics"]["planned_filter_diagnostic"]["status"] == "unresolved"


def test_sem_filtro_configurado_preserva_compatibilidade() -> None:
    plan = _plan(
        "synthetic report without configured category",
        _raw_context(binding=_binding()),
    )
    assert plan["planning_context"]["planned_filters"] == []
    request = build_sql_generation_request(plan)
    assert request["generation_context"]["planned_filters"] == []
    assert request["generation_context"]["filter_bindings"] == []


def main() -> None:
    tests = [
        test_fluxo_offline_usa_obrigacao_semantica_e_binding_separado,
        test_binding_ausente_ambiguo_invalido_e_divergente_falha_fechado,
        test_sem_filtro_configurado_preserva_compatibilidade,
    ]
    for test in tests:
        test()
        print(f"OK: {test.__name__}")
    print("TODOS OS TESTES DE PLANNED FILTERS E2E PASSARAM")


if __name__ == "__main__":
    main()

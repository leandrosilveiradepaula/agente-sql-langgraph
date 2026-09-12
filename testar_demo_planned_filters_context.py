from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from app.adapters.testing.fake_sql_generator import FakeSqlGenerator
from app.domain.context_normalizer import normalize_context_snapshot
from app.domain.context_validator import validate_context_snapshot
from app.domain.intent_resolver import resolve_intent
from app.domain.planner import build_query_plan
from app.domain.sql_contract import run_sql_contract_gate
from app.domain.sql_generation import build_sql_generation_request


DELTA_PATH = Path("semantic_context/demo_planned_filters_v8.delta.json")
EVIDENCE_PATH = Path(
    "semantic_context/evidence/demo_revenue_filter_binding_v1.json"
)
INTENT = "demo_financial_filter"
SOURCE_TABLE = "demo_lakehouse.gold_lancamentos_contabeis"
TARGET_TABLE = "demo_lakehouse.gold_plano_contas"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_delta() -> dict[str, Any]:
    return _load(DELTA_PATH)


def _revenue_binding() -> dict[str, Any]:
    binding = deepcopy(_load_delta()["filter_bindings"][0])
    binding.pop("evidence_ref", None)
    return binding


def _raw_context(*, binding_mode: str = "complete") -> dict[str, Any]:
    delta = _load_delta()
    evidence = _load(EVIDENCE_PATH)
    entities: list[dict[str, Any]] = [
        {
            "entity_type": "intent_signal",
            "user_term": "relatorio",
            "canonical_value": INTENT,
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
            "user_term": "demo financial filter definition",
            "canonical_value": INTENT,
            "business_rule": {
                "intent_catalog": {
                    "semantic_description": "Offline DEMO filter validation.",
                    "rules": [
                        {
                            "rule_name": f"configured_{concept['filter_concept']}",
                            "effect": "positive_score",
                            "concepts": [
                                {
                                    "concept_name": concept["filter_concept"],
                                    "terms": list(concept["aliases"]),
                                    "match_mode": "contains",
                                    "minimum_term_matches": 1,
                                }
                            ],
                            "minimum_concept_matches": 1,
                            "score": 120,
                            "priority": index + 1,
                        }
                        for index, concept in enumerate(delta["filter_concepts"])
                    ],
                }
            },
            "priority": 1,
        },
        *[
            {
                "entity_type": "filter_concept",
                "user_term": alias,
                "canonical_value": concept["filter_concept"],
                "priority": index + 1,
            }
            for concept in delta["filter_concepts"]
            for index, alias in enumerate(concept["aliases"])
        ],
        *[
            {
                "entity_type": "intent_signal",
                "user_term": term,
                "canonical_value": INTENT,
                "sql_filter_hint": {
                    "resolver": {
                        "match_mode": "exact",
                        "polarity": "negative",
                        "score": 500,
                    }
                },
                "priority": 1,
            }
            for term in evidence["unsupported_aliases"]
        ],
    ]

    if binding_mode != "missing":
        binding = _revenue_binding()
        if binding_mode == "incomplete":
            binding.pop("target_column")
        entities.append(
            {
                "entity_type": "filter_binding",
                "canonical_value": binding["filter_concept"],
                "business_rule": {"filter_binding": binding},
                "priority": 1,
            }
        )
        if binding_mode == "ambiguous":
            entities.append(deepcopy(entities[-1]))

    return {
        "semantic_agent_version": delta["target_context_version"],
        "semantic_context_source": "offline-versioned-demo-artifact",
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
                "rule_name": "demo_read_rule",
                "rule_content": {"enabled": True},
                "applies_to_intents": [INTENT],
                "severity": "error",
                "priority": 2,
            },
        ],
        "entities": entities,
        "dre_mappings": [],
        "query_patterns": [
            {
                "intent_name": INTENT,
                "pattern_name": "demo_filter_projection",
                "business_question_examples": [],
                "required_tables": [SOURCE_TABLE, TARGET_TABLE],
                "required_rules": ["demo_read_rule"],
                "sql_pattern": "",
                "notes": "Offline harness only; no question-to-SQL lookup.",
                "priority": 1,
            }
        ],
        "table_catalog": [
            {
                "schema_name": "demo_lakehouse",
                "table_name": "gold_lancamentos_contabeis",
                "table_type": "table",
                "description": "Offline projection of DEMO realized source.",
                "grain": {"kind": "offline-demo"},
                "primary_key": ["id"],
                "key_columns": ["id", "nk_conta"],
                "metric_columns": ["valor"],
                "date_columns": [],
                "join_rules": [{"target_table": TARGET_TABLE}],
                "ai_hint": None,
                "priority": 1,
                "columns": [
                    {"name": "id", "data_type": "integer", "nullable": False},
                    {"name": "nk_conta", "data_type": "text", "nullable": False},
                    {"name": "valor", "data_type": "numeric", "nullable": True},
                ],
            },
            {
                "schema_name": "demo_lakehouse",
                "table_name": "gold_plano_contas",
                "table_type": "table",
                "description": "Offline projection of DEMO account plan.",
                "grain": {"kind": "offline-demo"},
                "primary_key": ["nk_conta"],
                "key_columns": ["nk_conta", "grupo_contabil"],
                "metric_columns": [],
                "date_columns": [],
                "join_rules": [{"target_table": SOURCE_TABLE}],
                "ai_hint": None,
                "priority": 1,
                "columns": [
                    {"name": "nk_conta", "data_type": "text", "nullable": False},
                    {"name": "grupo_contabil", "data_type": "text", "nullable": False},
                ],
            },
        ],
    }


def _resolve(question: str, raw_context: dict[str, Any]) -> tuple[dict, dict]:
    context = normalize_context_snapshot(raw_context)
    validation = validate_context_snapshot(context)
    assert validation["status"] == "valid", validation
    evidence = resolve_intent(question, context["intent_resolution"])
    return context, evidence


def _plan(question: str, raw_context: dict[str, Any]) -> dict[str, Any]:
    context, evidence = _resolve(question, raw_context)
    assert evidence["applied"] is True, evidence
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


def _assert_forbidden_request_keys_absent(value: Any) -> None:
    forbidden = {
        "sql_filter_hint",
        "benchmark",
        "benchmark_id",
        "benchmark_mode",
        "golden_answer",
        "expected_sql",
    }
    if isinstance(value, dict):
        assert not forbidden.intersection(value.keys()), value
        for child in value.values():
            _assert_forbidden_request_keys_absent(child)
    elif isinstance(value, list):
        for child in value:
            _assert_forbidden_request_keys_absent(child)


def test_delta_e_versionado_e_nao_aplicavel_automaticamente() -> None:
    delta = _load_delta()
    assert delta["contract"] == "semantic-context-delta/v1"
    assert delta["source_context_version"] == "v7-planned-metrics"
    assert delta["target_context_version"] == "v8-planned-filters"
    assert delta["source_context_version"] != delta["target_context_version"]
    assert delta["environment"] == "DEMO"
    assert delta["automatic_apply"] is False
    assert delta["activation"]["allowed"] is False

    gaps = {item["scope"]: item for item in delta["gaps"]}
    assert gaps["dre_receita"]["status"] == "RESOLVED_WITH_VERSIONED_EVIDENCE"
    assert gaps["dre_receita"]["activation_allowed"] is False
    for concept in ("dre_custos", "dre_despesas_operacionais"):
        assert gaps[concept]["status"] == "BLOCKING_FAIL_CLOSED"
        assert gaps[concept]["activation_allowed"] is False


def test_receita_e_semantica_e_binding_e_separado() -> None:
    delta = _load_delta()
    revenue = next(
        item for item in delta["filter_concepts"]
        if item["filter_concept"] == "dre_receita"
    )
    assert revenue["aliases"] == ["receita", "receitas"]
    physical_fields = {
        "target_table", "target_column", "operator", "value", "scope",
        "join_path", "binding_ref",
    }
    assert not physical_fields.intersection(revenue)

    binding = delta["filter_bindings"][0]
    evidence = _load(EVIDENCE_PATH)
    assert binding["binding_ref"] == "demo-dre-receita-v1"
    assert binding["scope"] == "where"
    assert evidence["supports"]["scope"] == "where"
    assert evidence["collection_mode"] == "read_only"
    assert evidence["external_write_performed"] is False
    assert evidence["authorizes_apply"] is False
    assert set(evidence["unsupported_aliases"]) == {
        "receita operacional liquida",
        "receita operacional líquida",
    }


def test_pipeline_real_do_delta_resolve_aliases_e_separa_binding() -> None:
    raw_context = _raw_context()
    plans = [
        _plan(question, raw_context)
        for question in ("relatorio receita", "relatorio receitas")
    ]
    expected_binding = _revenue_binding()

    for plan in plans:
        planning = plan["planning_context"]
        assert len(planning["planned_filters"]) == 1
        obligation = planning["planned_filters"][0]
        assert obligation["filter_concept"] == "dre_receita"
        assert obligation["binding_ref"] == "demo-dre-receita-v1"
        assert obligation["scope"] == "where"
        assert not ({"target_table", "target_column", "operator", "value", "join_path"} & obligation.keys())
        assert planning["resolved_filter_bindings"] == [expected_binding]

        request = build_sql_generation_request(plan)
        assert request["generation_context"]["planned_filters"] == [obligation]
        assert request["generation_context"]["filter_bindings"] == [expected_binding]
        _assert_forbidden_request_keys_absent(request)

    assert plans[0]["planning_context"]["planned_filters"][0]["filter_concept"] == plans[1]["planning_context"]["planned_filters"][0]["filter_concept"]
    assert plans[0]["planning_context"]["planned_filters"][0]["binding_ref"] == plans[1]["planning_context"]["planned_filters"][0]["binding_ref"]


def test_contract_gate_aprova_filtro_e_join_e_rejeita_divergencias() -> None:
    plan = _plan("relatorio receita", _raw_context())
    correct_sql = (
        "SELECT lc.valor FROM demo_lakehouse.gold_lancamentos_contabeis lc "
        "JOIN demo_lakehouse.gold_plano_contas pc ON lc.nk_conta = pc.nk_conta "
        "WHERE pc.grupo_contabil = 'Receita'"
    )
    request = build_sql_generation_request(plan)
    generated = FakeSqlGenerator(correct_sql).generate(request)["output_text"]
    approved, _ = run_sql_contract_gate(current_sql=generated, query_plan=plan)
    assert approved["status"] == "approved", approved

    invalid_sqls = [
        (
            "SELECT lc.valor FROM demo_lakehouse.gold_lancamentos_contabeis lc "
            "JOIN demo_lakehouse.gold_plano_contas pc ON lc.nk_conta = pc.nk_conta"
        ),
        (
            "SELECT lc.valor FROM demo_lakehouse.gold_lancamentos_contabeis lc "
            "JOIN demo_lakehouse.gold_plano_contas pc ON lc.nk_conta = pc.nk_conta "
            "WHERE pc.nk_conta = 'Receita'"
        ),
        (
            "SELECT lc.valor FROM demo_lakehouse.gold_lancamentos_contabeis lc "
            "JOIN demo_lakehouse.gold_plano_contas pc ON lc.nk_conta = pc.nk_conta "
            "WHERE pc.grupo_contabil <> 'Receita'"
        ),
        (
            "SELECT lc.valor FROM demo_lakehouse.gold_lancamentos_contabeis lc "
            "JOIN demo_lakehouse.gold_plano_contas pc ON lc.nk_conta = pc.nk_conta "
            "WHERE pc.grupo_contabil = 'Outra'"
        ),
        (
            "SELECT lc.valor FROM demo_lakehouse.gold_lancamentos_contabeis lc "
            "JOIN demo_lakehouse.gold_plano_contas pc ON lc.nk_conta = pc.grupo_contabil "
            "WHERE pc.grupo_contabil = 'Receita'"
        ),
    ]
    for sql in invalid_sqls:
        rejected, _ = run_sql_contract_gate(current_sql=sql, query_plan=plan)
        assert rejected["status"] == "rejected", (sql, rejected)


def test_binding_ausente_incompleto_ambiguo_e_outros_conceitos_falham_fechado() -> None:
    for mode in ("missing", "incomplete", "ambiguous"):
        plan = _plan("relatorio receita", _raw_context(binding_mode=mode))
        planning = plan["planning_context"]
        assert planning["planned_filters"] == []
        assert planning["resolved_filter_bindings"] == []
        assert planning["diagnostics"]["planned_filter_diagnostic"]["status"] == "unresolved"

    for question, concept in (
        ("relatorio custos", "dre_custos"),
        ("relatorio despesas operacionais", "dre_despesas_operacionais"),
    ):
        plan = _plan(question, _raw_context())
        planning = plan["planning_context"]
        assert planning["planned_filters"] == []
        assert planning["resolved_filter_bindings"] == []
        diagnostic = planning["diagnostics"]["planned_filter_diagnostic"]
        assert diagnostic["status"] == "unresolved"
        assert diagnostic["unresolved"][0]["filter_concept"] == concept
        assert diagnostic["unresolved"][0]["reason"] == "binding_not_found"


def test_termo_nao_sustentado_nao_vira_receita_silenciosamente() -> None:
    for question in (
        "receita operacional liquida",
        "receita operacional líquida",
    ):
        _, evidence = _resolve(question, _raw_context())
        assert evidence["applied"] is False, evidence


def test_evidencia_transitional_nao_vira_contrato() -> None:
    delta = _load_delta()
    inventory = {item["field"]: item for item in delta["transitional_inventory"]}
    assert inventory["sql_filter_hint"]["allowed_use"] == "migration_inventory_only"
    assert inventory["sql_filter_hint"]["forbidden_use"] == "filter_binding_contract"
    assert inventory["nivel_1_bi"]["forbidden_use"] == "inferred_target_column"
    serialized_contract = json.dumps(
        delta["filter_concepts"] + delta["filter_bindings"], sort_keys=True
    )
    assert "sql_filter_hint" not in serialized_contract
    assert "nivel_1_bi" not in serialized_contract


def test_rollback_nao_remove_dados() -> None:
    rollback = _load_delta()["rollback"]
    assert "v7-planned-metrics" in rollback["action"]
    assert rollback["delete_data"] is False


def main() -> None:
    tests = [
        test_delta_e_versionado_e_nao_aplicavel_automaticamente,
        test_receita_e_semantica_e_binding_e_separado,
        test_pipeline_real_do_delta_resolve_aliases_e_separa_binding,
        test_contract_gate_aprova_filtro_e_join_e_rejeita_divergencias,
        test_binding_ausente_incompleto_ambiguo_e_outros_conceitos_falham_fechado,
        test_termo_nao_sustentado_nao_vira_receita_silenciosamente,
        test_evidencia_transitional_nao_vira_contrato,
        test_rollback_nao_remove_dados,
    ]
    for test in tests:
        test()
        print(f"OK: {test.__name__}")
    print("TODOS OS TESTES DEMO PLANNED FILTERS PASSARAM")


if __name__ == "__main__":
    main()

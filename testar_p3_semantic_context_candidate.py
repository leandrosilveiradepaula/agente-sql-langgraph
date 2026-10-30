"""Offline P3 -> canonical-context candidate contract, including portability.

The fixture values are abstract semantic labels.  They are not benchmarks,
financial SQL, client names, or generator inputs beyond their declared context.
"""
from __future__ import annotations

from hashlib import sha256
import json

from app.domain.context_validator import validate_context_snapshot
from app.domain.intent_resolver import resolve_intent
from app.domain.planner import build_query_plan
from app.graph.nodes.contract_gate import contract_gate
from app.graph.nodes.generate_sql import create_generate_sql_node
from app.graph.nodes.security_gate import security_gate
from app.adapters.testing.fake_sql_generator import FakeSqlGenerator
from scripts.operations.p3_semantic_context_candidate import CandidateBlocked, build_candidate


def _review(schema: str = "scope_alpha") -> dict:
    table = "ledger" if schema == "scope_alpha" else "events"
    identifier = "record_id" if schema == "scope_alpha" else "event_key"
    measure = "measure_value" if schema == "scope_alpha" else "amount_value"
    period = "period_day" if schema == "scope_alpha" else "observed_on"
    raw = {
        "semantic_agent_version": "candidate-" + schema,
        "semantic_context_source": "p3-approved-external-contract",
        "regras": [{"rule_group": "config", "rule_name": "resolver", "rule_content": {"component": "intent_resolver", "minimum_score": 1, "ambiguity_margin": 0, "applied_confidence": 1, "fallback_to_previous_intent": False}, "applies_to_intents": [], "validation_hint": None, "severity": "info", "priority": 1}],
        "entidades": [
            {"entity_type": "intent_signal", "user_term": "unseen inquiry", "canonical_value": "aggregate_measure", "target_table": None, "target_column": None, "sql_filter_hint": {"resolver": {"match_mode": "contains", "polarity": "positive", "score": 2}}, "business_rule": None, "priority": 1},
            {"entity_type": "intent_definition", "user_term": "definition", "canonical_value": "aggregate_measure", "target_table": None, "target_column": None, "sql_filter_hint": None, "business_rule": {"intent_catalog": {"semantic_description": "externally approved definition", "rules": [{"rule_name": "metric_mode", "effect": "positive_score", "concepts": [{"concept_name": "metric_mode", "terms": ["unseen inquiry"], "match_mode": "contains", "minimum_term_matches": 1}], "minimum_concept_matches": 1, "score": 2, "priority": 1}]}}, "priority": 2},
            {"entity_type": "metric_binding", "user_term": "measure", "canonical_value": "approved_measure", "target_table": schema + "." + table, "target_column": measure, "sql_filter_hint": None, "business_rule": {"metric_binding": {"metric_concept": "approved_measure", "target_table": schema + "." + table, "target_column": measure, "when_present": ["metric_mode"], "when_absent": [], "aggregate": None}}, "priority": 3},
        ],
        "dre": [],
        "padroes": [{"intent_name": "aggregate_measure", "pattern_name": "approved_aggregate", "business_question_examples": [], "required_tables": [schema + "." + table], "required_rules": [], "sql_pattern": None, "notes": None, "priority": 1}],
        "catalogo": [{"schema_name": schema, "table_name": table, "table_type": "table", "description": None, "grain": "externally approved grain", "primary_key": [identifier], "key_columns": [identifier], "metric_columns": [measure], "date_columns": [period], "join_rules": [], "ai_hint": None, "priority": 1, "columns": [{"name": identifier, "data_type": "uuid"}, {"name": measure, "data_type": "numeric"}, {"name": period, "data_type": "date"}]}],
        "context_counts": {"regras": 1, "entidades": 3, "dre": 0, "padroes": 1, "catalogo": 1},
    }
    tables = [{"schema": schema, "table": table, "columns": [{"name": identifier, "postgres_type": "uuid"}, {"name": measure, "postgres_type": "numeric"}, {"name": period, "postgres_type": "date"}]}]
    tables[0]["columns"].sort(key=lambda item: item["name"])
    fingerprint = sha256(json.dumps(tables, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    return {"contract": "p3-semantic-mapping-review-v1", "status": "APPROVED", "organization_id": "external-organization-reference", "accounting_approval": {"status": "APPROVED", "reference": "external-approved-definition"}, "can_import_into_semantic_catalog": False, "can_execute_financial_sql": False, "source": {"schema": schema, "physical_fingerprint": fingerprint}, "tables": tables, "semantic_context": raw}


def test_portable_approved_candidates_pass_real_context_contract() -> None:
    for schema in ("scope_alpha", "scope_beta"):
        prepared = build_candidate(_review(schema))
        snapshot = prepared["candidate"]
        assert validate_context_snapshot(snapshot)["status"] == "valid"
        assert snapshot["allowed_schemas"] == [schema]
        assert prepared["activation_authorized"] is False
        assert prepared["financial_sql_executed"] is False


def test_incomplete_or_drifted_mapping_fails_closed() -> None:
    review = _review()
    review["status"] = "UNAPPROVED_DRAFT"
    try:
        build_candidate(review)
    except CandidateBlocked as error:
        assert str(error) == "NEEDS_BUSINESS_APPROVAL"
    else:
        raise AssertionError("unapproved review was accepted")
    review = _review()
    review["semantic_context"]["catalogo"][0]["columns"][1]["name"] = "not_physical"
    try:
        build_candidate(review)
    except CandidateBlocked as error:
        assert str(error) == "CANDIDATE_CATALOG_PHYSICAL_MISMATCH"
    else:
        raise AssertionError("physical drift was accepted")


def test_unseen_question_plans_then_simulated_sql_is_gated_without_execution() -> None:
    snapshot = build_candidate(_review())["candidate"]
    resolution = resolve_intent("an unseen inquiry about measure", snapshot["intent_resolution"])
    assert resolution["applied"] is True
    plan = build_query_plan(context=snapshot, intent_name=resolution["intent"], intent_confidence=resolution["intent_confidence"], normalized_question=resolution["normalized_question"], intent_resolution_result=resolution)
    assert plan["status"] == "planned"
    sql = "SELECT SUM(measure_value) FROM scope_alpha.ledger"
    query_plan = plan["query_plan"]
    assert query_plan is not None
    generated = create_generate_sql_node(FakeSqlGenerator(sql))({"query_plan": query_plan, "errors": []})
    secured = security_gate({**generated, "query_plan": query_plan, "errors": []})
    contracted = contract_gate({**generated, **secured, "query_plan": query_plan, "errors": []})
    assert generated["sql_generation_result"]["status"] == "generated"
    assert secured["security_result"]["status"] == "approved"
    assert contracted["contract_result"]["status"] == "approved"
    assert "execution_result" not in contracted


if __name__ == "__main__":
    for test in (test_portable_approved_candidates_pass_real_context_contract, test_incomplete_or_drifted_mapping_fails_closed, test_unseen_question_plans_then_simulated_sql_is_gated_without_execution):
        test()
        print("TEST:", test.__name__, "PASS")

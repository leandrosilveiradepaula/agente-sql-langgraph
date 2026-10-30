"""Offline P3 -> canonical-context candidate contract, including portability.

The fixture values are abstract semantic labels.  They are not benchmarks,
financial SQL, client names, or generator inputs beyond their declared context.
"""
from __future__ import annotations

from hashlib import sha256
from copy import deepcopy
import hmac
import json

from app.domain.context_validator import validate_context_snapshot
from app.domain.intent_resolver import resolve_intent
from app.domain.planner import build_query_plan
from app.graph.nodes.contract_gate import contract_gate
from app.graph.nodes.generate_sql import create_generate_sql_node
from app.graph.nodes.security_gate import security_gate
from app.adapters.testing.fake_sql_generator import FakeSqlGenerator
from scripts.operations.p3_semantic_context_candidate import CandidateBlocked, build_candidate, _physical_fingerprint
from scripts.operations.p3_semantic_mapping_review_readonly import create_review


def _review(schema: str = "scope_alpha", with_dre: bool = False) -> dict:
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
    raw["dre"] = ([{"dre_code": "synthetic", "nivel_1_bi": "Synthetic category", "business_description": "synthetic", "sign_convention": {"test": True}, "category": "synthetic", "sort_order": 1}] if with_dre else [])
    raw["context_counts"]["dre"] = len(raw["dre"])
    policy = {"database": "synthetic_database", "role_name": "synthetic_reader", "schema": schema, "relations": [table]}
    baseline = create_review(policy, [(schema, table, identifier, "uuid"), (schema, table, measure, "numeric"), (schema, table, period, "date")], "original-v1")
    review = deepcopy(baseline)
    review.update({"status": "APPROVED", "candidate_version": raw["semantic_agent_version"],
                   "organization_id": "tenant-" + schema, "review_evidence": {"reviewer": "independent-reviewer", "source_definition_ref": "synthetic-proof", "review_timestamp": "2026-01-01T00:00:00Z"},
                   "accounting_approval": {"status": "APPROVED", "reference": "synthetic-proof"},
                   "intent_definitions": [{"name": "aggregate_measure"}], "entity_aliases": [], "business_rules": [],
                   "semantic_context": raw})
    review["tables"][0].update({"grain": "reviewed grain", "primary_key": identifier, "key_columns": [identifier],
        "metric_bindings": [{"column": measure, "aggregation": "sum", "concept": "approved_measure", "sign_convention": "approved", "evidence": "synthetic-proof"}],
        "dimension_bindings": [], "date_bindings": [{"column": period, "reference": "reviewed period", "evidence": "synthetic-proof"}],
        "join_bindings": [], "dre_mappings": [{"evidence": "synthetic-proof"}] if with_dre else [], "business_evidence": "synthetic-proof"})
    return review, baseline



_TEST_KEY = sha256(b"offline-test-only-not-a-production-approval").digest()


def _receipt(review: dict) -> dict:
    evidence = review["review_evidence"]
    claims = {
        "contract": "p3-accounting-approval-v1", "decision": "APPROVED",
        "review_sha256": sha256(json.dumps(review, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest(),
        "physical_fingerprint": review["source"]["physical_fingerprint"],
        "organization_id": review["organization_id"],
        "candidate_version": review["candidate_version"],
        "reviewer_id": evidence["reviewer"], "approved_at": evidence["review_timestamp"],
        "evidence_ref": evidence["source_definition_ref"],
    }
    signature = hmac.new(_TEST_KEY, json.dumps(claims, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(), sha256).hexdigest()
    return {"claims": claims, "hmac_sha256": signature}


def _prepare(review: dict, baseline: dict, receipt: dict | None = None) -> dict:
    return build_candidate(review, trusted_baseline=baseline, approval_receipt=receipt or _receipt(review), approval_verification_key=_TEST_KEY)


def _blocked(expected: str, review: dict, baseline: dict, receipt: dict | None = None) -> None:
    try:
        _prepare(review, baseline, receipt)
    except CandidateBlocked as error:
        assert str(error) == expected, (str(error), expected)
    else:
        raise AssertionError("unapproved candidate accepted")


def test_two_tenants_and_dre_optional() -> None:
    seen = []
    for schema, with_dre in (("scope_alpha", True), ("scope_beta", False)):
        review, baseline = _review(schema, with_dre)
        prepared = _prepare(review, baseline)
        snapshot = prepared["candidate"]
        assert validate_context_snapshot(snapshot)["status"] == "valid"
        assert snapshot["allowed_schemas"] == [schema]
        assert len(snapshot["dre_mappings"]) == int(with_dre)
        assert prepared["activation_authorized"] is False
        assert prepared["financial_sql_executed"] is False
        resolution = resolve_intent("an unseen inquiry about measure", snapshot["intent_resolution"])
        assert resolution["applied"] is True
        plan = build_query_plan(context=snapshot, intent_name=resolution["intent"], intent_confidence=resolution["intent_confidence"], normalized_question=resolution["normalized_question"], intent_resolution_result=resolution)
        assert plan["status"] == "planned"
        seen.append(prepared)
    assert seen[0]["organization_id"] != seen[1]["organization_id"]
    assert seen[0]["candidate_version"] != seen[1]["candidate_version"]
    assert seen[0]["tenant_binding_fingerprint"] != seen[1]["tenant_binding_fingerprint"]


def test_forged_approval_and_physical_drift() -> None:
    review, baseline = _review()
    changed = deepcopy(review)
    changed["status"] = "UNAPPROVED_DRAFT"
    _blocked("NEEDS_BUSINESS_APPROVAL", changed, baseline)
    try:
        build_candidate(review, trusted_baseline=baseline)
    except CandidateBlocked as err:
        assert str(err) == "P3_INDEPENDENT_APPROVAL_REQUIRED"
    else:
        raise AssertionError("missing receipt accepted")
    changed = deepcopy(review)
    changed["tables"][0]["columns"][0]["name"] = "invented"
    changed["source"]["physical_fingerprint"] = _physical_fingerprint(changed)
    _blocked("SOURCE_OR_PHYSICAL_FINGERPRINT_DRIFT", changed, baseline)
    changed = deepcopy(review)
    changed["semantic_context"]["catalogo"][0]["columns"][0]["name"] = "invented"
    _blocked("CANDIDATE_CATALOG_PHYSICAL_MISMATCH", changed, baseline)
    changed = deepcopy(review)
    changed["semantic_context"]["padroes"][0]["notes"] = "unapproved modification"
    _blocked("P3_APPROVAL_SCOPE_MISMATCH", changed, baseline, _receipt(review))
    changed_receipt = _receipt(review)
    changed_receipt["hmac_sha256"] = "0" * 64
    _blocked("P3_APPROVAL_SIGNATURE_INVALID", review, baseline, changed_receipt)


def test_version_tenant_fanout_ambiguity() -> None:
    review, baseline = _review()
    changed = deepcopy(review)
    changed["organization_id"] = "different-tenant"
    _blocked("P3_APPROVAL_SCOPE_MISMATCH", changed, baseline, _receipt(review))
    changed = deepcopy(review)
    changed["semantic_context"]["semantic_agent_version"] = "different-version"
    _blocked("SEMANTIC_VERSION_MISMATCH", changed, baseline)
    changed = deepcopy(review)
    table = changed["tables"][0]
    table["join_bindings"] = [{"from_column": table["primary_key"], "to_table": table["table"],
                               "to_column": table["primary_key"], "cardinality": "one_to_many", "evidence": "synthetic-proof"}]
    _blocked("P3_SEMANTIC_REVIEW_INCOMPLETE", changed, baseline)
    snapshot = _prepare(review, baseline)["candidate"]
    ambiguous = resolve_intent("not a recognized question", snapshot["intent_resolution"])
    assert ambiguous["applied"] is False


def test_fake_sql_gates_without_execution() -> None:
    review, baseline = _review()
    snapshot = _prepare(review, baseline)["candidate"]
    resolution = resolve_intent("an unseen inquiry about measure", snapshot["intent_resolution"])
    plan = build_query_plan(context=snapshot, intent_name=resolution["intent"], intent_confidence=resolution["intent_confidence"], normalized_question=resolution["normalized_question"], intent_resolution_result=resolution)
    assert plan["status"] == "planned"
    query_plan = plan["query_plan"]
    assert query_plan is not None
    generated = create_generate_sql_node(FakeSqlGenerator("SELECT SUM(measure_value) FROM scope_alpha.ledger"))({"query_plan": query_plan, "errors": []})
    secured = security_gate({**generated, "query_plan": query_plan, "errors": []})
    contracted = contract_gate({**generated, **secured, "query_plan": query_plan, "errors": []})
    assert generated["sql_generation_result"]["status"] == "generated"
    assert secured["security_result"]["status"] == "approved"
    assert contracted["contract_result"]["status"] == "approved"
    assert "execution_result" not in contracted


if __name__ == "__main__":
    for test in (test_two_tenants_and_dre_optional, test_forged_approval_and_physical_drift,
                 test_version_tenant_fanout_ambiguity, test_fake_sql_gates_without_execution):
        test()
        print("TEST:", test.__name__, "PASS")

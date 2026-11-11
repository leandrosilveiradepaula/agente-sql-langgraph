"""Offline-only preflight for semantic catalog role migration.

No network, private benchmark, SQL generation or financial execution.
"""
from __future__ import annotations

from copy import deepcopy

from app.domain.context_normalizer import normalize_context_snapshot
from app.domain.semantic_role_migration import (
    SemanticRoleMigrationRefused,
    audit_role_migration_questions,
    prepare_role_migration,
)
from testar_context_normalizer import _raw_snapshot


def _prepare(raw=None, roles=None, version="context-test-v4"):
    if raw is None:
        raw = _raw_snapshot()
    if roles is None:
        roles = {"grouping": ["first_concept"]}
    return prepare_role_migration(
        raw, candidate_version=version, role_bindings=roles,
        expected_source_fingerprint=normalize_context_snapshot(raw)["fingerprint"],
    )


def _refuses(code, fn):
    try:
        fn()
    except SemanticRoleMigrationRefused as exc:
        assert str(exc) == code, (code, str(exc))
    else:
        raise AssertionError("expected refusal: " + code)


def test_prepares_versioned_candidate_without_mutating_source() -> None:
    original = _raw_snapshot()
    before = deepcopy(original)
    result = _prepare(original)
    assert original == before
    assert result["status"] == "PREPARED_NOT_ACTIVATED"
    assert result["source"]["version"] == "context-test-v3"
    assert result["candidate"]["version"] == "context-test-v4"
    assert result["candidate"]["fingerprint"] != result["source"]["fingerprint"]
    assert result["candidate"]["intent_resolution"]["config"]["concept_roles"] == {
        "grouping": ["first_concept"]
    }
    assert result["source"]["intent_resolution"]["config"].get("concept_roles") is None
    assert result["candidate_raw"]["semantic_agent_version"] == "context-test-v4"
    assert result["candidate_raw"] != original
    _refuses(
        "source_fingerprint_mismatch",
        lambda: prepare_role_migration(
            original, candidate_version="context-test-v4",
            role_bindings={"grouping": ["first_concept"]},
            expected_source_fingerprint="0" * 64,
        ),
    )


def test_reports_only_aggregates_and_never_leaks_questions_or_sql() -> None:
    staged = _prepare()
    questions = [
        "Análise genérica",
        "unrelated question",
        "codigo ab beta alpha",
    ]
    result = audit_role_migration_questions(staged, questions)
    assert result["status"] in ("NO_DETECTED_DRIFT", "REVIEW_REQUIRED")
    assert result["question_count"] == 3
    assert result["provider_calls"] == 0
    assert result["sql_generated"] is False
    assert result["sql_executed"] is False
    assert result["automated_activation_authorized"] is False
    rendered = repr(result).lower()
    for text in ("análise genérica", "unrelated question", "codigo ab", "select"):
        assert text not in rendered
    assert result["candidate_fingerprint"] != result["source_fingerprint"]
    assert result["planned_to_rejected"] >= 0
    assert result["rejected_to_planned"] >= 0
    assert result["planned_projection_changes"] >= 0
    assert isinstance(result["rejection_code_counts"], dict)
    assert isinstance(result["changed_projection_field_counts"], dict)


def test_rejects_unmapped_concepts_and_duplicate_roles() -> None:
    _refuses(
        "candidate_context_invalid",
        lambda: _prepare(roles={"grouping": ["unmapped_concept"]}),
    )
    _refuses(
        "role_bindings_invalid",
        lambda: _prepare(roles={"grouping": ["first_concept", "first_concept"]}),
    )


def test_refuses_same_version_and_missing_resolver_rule() -> None:
    _refuses("version_not_advanced", lambda: _prepare(version="context-test-v3"))
    raw = _raw_snapshot()
    raw["regras"] = [
        rule for rule in raw["regras"]
        if rule.get("rule_name") != "resolver"
    ]
    raw["context_counts"]["regras"] = len(raw["regras"])
    _refuses("source_context_invalid", lambda: _prepare(raw))


def test_rejects_bad_questions_and_unprepared_candidates() -> None:
    staged = _prepare()
    for questions in ([], [" "], [123], ["x" * 16001], ["x"] * 501):
        _refuses(
            "questions_invalid",
            lambda questions=questions: audit_role_migration_questions(
                staged, questions,
            ),
        )
    _refuses(
        "unprepared_candidate",
        lambda: audit_role_migration_questions({"status": "not_prepared"}, ["q"]),
    )


def test_two_different_tenant_contexts_reuse_same_migration_engine() -> None:
    a = _raw_snapshot()
    b = deepcopy(a)
    b["semantic_agent_version"] = "another-tenant-v1"
    b["semantic_context_source"] = "another_tenant_versioned_catalog"
    b["catalogo"][0]["schema_name"] = "ledger_other"
    b["padroes"][0]["required_tables"] = '["ledger_other.table_test"]'
    b["entidades"][-1]["business_rule"]["intent_catalog"]["rules"][1]["concepts"][0][
        "concept_name"
    ] = "client_specific_measure"
    x = _prepare(a, roles={"grouping": ["first_concept"]}, version="context-test-v4")
    y = _prepare(
        b,
        roles={"metric": ["client_specific_measure"]},
        version="another-tenant-v2",
    )
    assert x["candidate"]["fingerprint"] != y["candidate"]["fingerprint"]
    assert x["candidate"]["intent_resolution"]["config"]["concept_roles"] != (
        y["candidate"]["intent_resolution"]["config"]["concept_roles"]
    )
    for staged in (x, y):
        report = audit_role_migration_questions(staged, ["a question about the data"])
        assert report["question_count"] == 1
        assert report["automated_activation_authorized"] is False



def test_audit_classifies_plan_loss_and_planned_projection_changes() -> None:
    from unittest.mock import patch

    staged = _prepare()
    calls = iter([
        {"status": "planned", "query_plan": {"planning_context": {
            "planned_metrics": [{"metric_ref": "ref-a"}],
            "detected_dimensions": [], "analytical_operations": [],
            "authorized_joins": [],
        }}},
        {"status": "rejected", "error_code": "PLANNING_ANALYTICAL_BINDING_INCOMPLETE"},
        {"status": "planned", "query_plan": {"planning_context": {
            "planned_metrics": [{"metric_ref": "ref-a"}],
            "detected_dimensions": [], "analytical_operations": [],
            "authorized_joins": [],
        }}},
        {"status": "planned", "query_plan": {"planning_context": {
            "planned_metrics": [{"metric_ref": "ref-a"}],
            "detected_dimensions": [], "analytical_operations": [{"operation_type": "aggregation"}],
            "authorized_joins": [],
        }}},
    ])
    from app.domain import semantic_role_migration as migration

    with patch.object(migration, "_safe_plan", side_effect=lambda *args: next(calls)):
        result = audit_role_migration_questions(
            staged, ["synthetic first question", "synthetic second question"],
        )
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["intent_decisions_changed"] == 0
    assert result["planning_projections_changed"] == 2
    assert result["planned_to_rejected"] == 1
    assert result["planned_projection_changes"] == 1
    assert result["rejected_to_planned"] == 0
    assert result["rejection_code_counts"] == {
        "PLANNING_ANALYTICAL_BINDING_INCOMPLETE": 1
    }
    assert result["changed_projection_field_counts"] == {
        "analytical_operations": 1,
    }
    assert result["automated_activation_authorized"] is False
    assert "synthetic first question" not in repr(result)


if __name__ == "__main__":
    import inspect
    tests = sorted(
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and inspect.isfunction(fn)
    )
    for name, fn in tests:
        fn()
        print("PASS " + name)
    print("SEMANTIC_ROLE_MIGRATION_TESTS=" + str(len(tests)))

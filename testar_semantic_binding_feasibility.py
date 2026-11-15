"""Conditional binding route feasibility, without business-specific shortcuts."""
from __future__ import annotations

from copy import deepcopy

from app.domain.semantic_binding_feasibility import binding_route_feasibility
from app.domain.planner import (
    _binding_ref,
    _default_binding_cardinality,
    _metric_binding_rule,
    _resolve_metric_bindings,
)
from testar_planner import _append_metric_binding, _metric_context


def _binding(
    *,
    concept: str = "tenant_metric",
    table: str = "tenant_schema.entry_a",
    column: str = "value",
    present: list[str] | None = None,
    absent: list[str] | None = None,
) -> dict:
    return {
        "metric_concept": concept,
        "target_table": table,
        "target_column": column,
        "when_present": ["mode_a"] if present is None else present,
        "when_absent": [] if absent is None else absent,
    }


def _cardinality(*, minimum: int = 2, same: bool = True) -> dict:
    return {
        "mode": "multiple",
        "minimum": minimum,
        "maximum": minimum,
        "same_metric_concept": same,
        "distinct_bindings": True,
    }


def test_feasible_two_distinct_physical_operands():
    bindings = [
        _binding(table="schema_one.cash_rows", present=["mode_a"]),
        _binding(table="schema_one.budget_rows", present=["mode_b"]),
    ]
    assert binding_route_feasibility(
        bindings=bindings, cardinality=_cardinality(),
    ) == "possible"
    changed = deepcopy(bindings)
    for record in changed:
        record["target_table"] = record["target_table"].replace(
            "schema_one", "unrelated_client"
        )
        record["metric_concept"] = "foreign_measure"
    assert binding_route_feasibility(
        bindings=changed, cardinality=_cardinality(),
    ) == "possible"


def test_mutually_exclusive_predicates_cannot_form_one_comparison():
    bindings = [
        _binding(present=["mode_a"]),
        _binding(table="tenant_schema.entry_b", present=["mode_b"],
                 absent=["MODE_A"]),
    ]
    assert binding_route_feasibility(
        bindings=bindings, cardinality=_cardinality(),
    ) == "impossible"


def test_duplicate_metric_target_is_not_two_operands_even_with_distinct_aliases():
    bindings = [
        _binding(present=["mode_a"]),
        _binding(present=["mode_b"]),
    ]
    assert binding_route_feasibility(
        bindings=bindings, cardinality=_cardinality(),
    ) == "impossible"


def test_same_metric_concept_is_tenant_configured_not_assumed():
    bindings = [
        _binding(concept="metric_x"),
        _binding(concept="metric_y", table="tenant_schema.entry_b"),
    ]
    assert binding_route_feasibility(
        bindings=bindings, cardinality=_cardinality(same=True),
    ) == "impossible"
    assert binding_route_feasibility(
        bindings=bindings, cardinality=_cardinality(same=False),
    ) == "possible"


def test_no_binding_route_does_not_claim_no_other_metric_path():
    assert binding_route_feasibility(
        bindings=[], cardinality=_cardinality(),
    ) == "not_configured"
    assert binding_route_feasibility(
        bindings=[], cardinality=_default_binding_cardinality(),
    ) == "not_applicable"


def test_excessive_combination_space_is_indeterminate_not_impossible():
    bindings = [
        _binding(
            table="tenant_schema.table_" + str(i),
            present=["mode_" + str(i)],
            absent=["mode_" + str(j) for j in range(50) if j != i],
        )
        for i in range(50)
    ]
    assert binding_route_feasibility(
        bindings=bindings, cardinality=_cardinality(minimum=5),
    ) == "indeterminate"


def test_case_insensitive_context_matches_declared_predicate():
    context = _metric_context()
    _append_metric_binding(
        context, when_present=["MODE_A"], when_absent=["Mode_B"],
    )
    resolved, diagnosis = _resolve_metric_bindings(
        context=context,
        metric_concept="amount",
        matched_user_term="amount",
        binding_context_concepts=[{"concept_name": "mode_a"}],
        cardinality=_default_binding_cardinality(),
    )
    assert len(resolved) == 1, diagnosis
    blocked, diagnostic = _resolve_metric_bindings(
        context=context,
        metric_concept="amount",
        matched_user_term="amount",
        binding_context_concepts=[
            {"concept_name": "mode_a"},
            {"concept_name": "mode_b"},
        ],
        cardinality=_default_binding_cardinality(),
    )
    assert blocked == []
    assert diagnostic["rejected"][0]["reason"] == "when_absent_present"


def test_contradictory_condition_rejected_independent_of_case():
    entity = {
        "metric_binding": {
            "metric_concept": "m",
            "target_table": "s.t",
            "target_column": "x",
            "when_present": ["Mode_A"],
            "when_absent": ["mode_a"],
            "required_filter_concepts": [],
            "aggregate": None,
        }
    }
    assert _metric_binding_rule(entity) is None


def test_equivalent_predicates_have_stable_binding_reference():
    identity = {
        "metric_concept": "metric_a",
        "target_table": "test.table",
        "target_column": "value",
    }
    left = _binding_ref(
        **identity, when_present=["MODE_A"], when_absent=["MODE_B"],
    )
    right = _binding_ref(
        **identity, when_present=["mode_a"], when_absent=["mode_b"],
    )
    assert left == right


if __name__ == "__main__":
    tests = sorted((n, v) for n, v in globals().items()
                   if n.startswith("test_") and callable(v))
    for name, fn in tests:
        fn()
        print("PASS " + name)
    print("SEMANTIC_BINDING_FEASIBILITY_TESTS=" + str(len(tests)))

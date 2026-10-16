from __future__ import annotations

from app.domain.planner import _project_temporal_series, build_query_plan
from testar_planner import _synthetic_temporal_context, _pattern


def project(
    bindings, *, dates=None, strategy="configured_metric_source_date",
    source_table="schema_test.table_test", question="Show monthly totals",
    reference_selection=None,
):
    context = _synthetic_temporal_context()
    cfg = context["component_configs"]["temporal_planning"]
    cfg["date_binding_strategy"] = strategy
    cfg["date_bindings"] = bindings
    if reference_selection is not None:
        cfg["reference_selection"] = reference_selection
    table = dict(context["table_catalog"][0])
    table["qualified_name"] = source_table
    table["date_columns"] = dates if dates is not None else [
        "event_date", "created_at",
    ]
    table["columns"] = list(table["columns"]) + [
        {"name": "created_at", "data_type": "timestamp"},
    ]
    return _project_temporal_series(
        context=context,
        intent_name="generic_test_intent",
        normalized_question=question,
        planned_metrics=[{
            "metric_ref": "synthetic-ref",
            "metric_concept": "measure",
            "target_table": source_table,
            "target_column": "value",
        }],
        required_tables=[table],
        intent_resolution_result=None,
    )


def binding(column="event_date", *, concept="measure", table="schema_test.table_test"):
    return {
        "metric_concept": concept,
        "target_table": table,
        "target_column": column,
    }


def test_explicit_date_bindings() -> None:
    series, diagnostic = project([binding()])
    assert diagnostic["status"] == "resolved", diagnostic
    assert series["date_column"] == "event_date"
    assert series["mapping_source"] == "component_configs.temporal_planning.date_bindings"

    for bindings, expected in [
        ([], "date_bindings_missing_or_invalid"),
        ([binding(), binding("created_at")], "date_binding_ambiguous"),
        ([binding("not_in_catalog")], "date_binding_not_in_catalog"),
        ([binding(concept="other")], "date_binding_not_found"),
        ([binding(table="schema_test.other")], "date_binding_not_found"),
        ([{"metric_concept": "measure"}], "date_bindings_missing_or_invalid"),
    ]:
        series, diagnostic = project(bindings)
        assert series is None
        assert expected in diagnostic["issues"], (expected, diagnostic)


def test_same_metric_concept_selects_the_correct_source_date() -> None:
    # Synthetic metric sources can share a concept without sharing time columns.
    # Binding order must not influence selection.
    declared = [
        binding("created_at", table="schema_test.second_source"),
        binding("event_date", table="schema_test.first_source"),
    ]
    for source, column in (
        ("schema_test.first_source", "event_date"),
        ("schema_test.second_source", "created_at"),
    ):
        for configured in (declared, list(reversed(declared))):
            series, diagnostic = project(
                configured, source_table=source,
            )
            assert diagnostic["status"] == "resolved", diagnostic
            assert series["date_table"] == source
            assert series["date_column"] == column
            assert series["mapping_source"] == (
                "component_configs.temporal_planning.date_bindings"
            )

    # A request for an unconfigured third metric source must not fall back
    # to a date binding declared for another source.
    series, diagnostic = project(
        declared, source_table="schema_test.unconfigured_source"
    )
    assert series is None
    assert "date_binding_not_found" in diagnostic["issues"]


def test_explicit_reference_never_silently_uses_default_date() -> None:
    """Structural test: names and terms are generic synthetic metadata."""
    selection = {
        "default_reference": "period_A",
        "references": [
            {"reference": "period_A", "terms": ["transaction period"]},
            {"reference": "period_B", "terms": ["posting date"]},
        ],
    }
    baseline = [binding("event_date")]
    for question in (
        "Show monthly totals",
        "Show monthly totals by transaction period",
    ):
        series, diagnostic = project(
            baseline, question=question, reference_selection=selection
        )
        assert diagnostic["status"] == "resolved", diagnostic
        assert series["date_column"] == "event_date"

    for question, code in (
        ("Show monthly totals by posting date", "temporal_reference_not_configured"),
        (
            "Show monthly totals by transaction period and posting date",
            "temporal_reference_ambiguous",
        ),
    ):
        series, diagnostic = project(
            baseline, question=question, reference_selection=selection
        )
        assert series is None
        assert diagnostic["status"] == "incomplete"
        assert code in diagnostic["issues"], diagnostic

    # An additional reference becomes resolvable by versioning a separate
    # authorized binding, with no code changes or lookup of entire questions.
    configured = {
        **selection,
        "references": [
            selection["references"][0],
            {
                **selection["references"][1],
                "date_bindings": [binding("created_at")],
            },
        ],
    }
    for entries in (
        configured["references"], list(reversed(configured["references"]))
    ):
        series, diagnostic = project(
            baseline,
            question="Show monthly totals by posting date",
            reference_selection={**configured, "references": entries},
        )
        assert diagnostic["status"] == "resolved", diagnostic
        assert series["date_column"] == "created_at"
        assert series["mapping_source"] == (
            "component_configs.temporal_planning.reference_selection"
        )

    series, diagnostic = project(
        baseline,
        question="Show monthly totals by posting date",
        reference_selection={
            **configured,
            "references": [
                configured["references"][0],
                {
                    **configured["references"][1],
                    "date_bindings": [binding("created_at", concept="other")],
                },
            ],
        },
    )
    assert series is None
    assert "date_binding_not_found" in diagnostic["issues"]


def test_temporal_reference_metadata_fails_closed() -> None:
    baseline = [binding("event_date")]
    cases = [
        {"default_reference": "a", "references": []},
        {
            "default_reference": "missing",
            "references": [{"reference": "other", "terms": ["keyword"]}],
        },
        {
            "default_reference": "one",
            "references": [
                {"reference": "one", "terms": ["overlap"]},
                {"reference": "two", "terms": ["overlap"]},
            ],
        },
        {"default_reference": "one", "references": [
            {"reference": "one", "terms": ["one"], "date_bindings": [binding()]}
        ]},
    ]
    for selection in cases:
        series, diagnostic = project(
            baseline, reference_selection=selection
        )
        assert series is None
        assert "temporal_reference_metadata_invalid" in diagnostic["issues"]


def test_explicit_alternative_rejected_outside_temporal_intent() -> None:
    """Other intents must not silently replace an explicit date reference."""
    context = _synthetic_temporal_context()
    other = _pattern(pattern_name="independent_intent_pattern")
    other["intent_name"] = "independent_intent"
    context["query_patterns"].append(other)
    reference = {
        "default_reference": "financial_period",
        "references": [
            {"reference": "financial_period", "terms": ["by period"]},
            {"reference": "event_date", "terms": ["by posting date"]},
        ],
    }
    cfg = context["component_configs"]["temporal_planning"]
    cfg["date_binding_strategy"] = "configured_metric_source_date"
    cfg["date_bindings"] = [binding()]
    cfg["reference_selection"] = reference

    # Test intent is absent from configured required_intents. Even if this
    # intent could produce a query, named alternate references are unsafe.
    for question in (
        "Show value by posting date",
        "Show a ranking of value by posting date",
        "Compare amount by posting date",
        "Show value by period and by posting date",
    ):
        plan = build_query_plan(
            context=context,
            intent_name="independent_intent",
            intent_confidence=0.95,
            normalized_question=question,
        )
        assert plan["status"] == "rejected", (question, plan)
        assert plan["error_code"] == "PLANNING_TEMPORAL_REFERENCE_UNSUPPORTED"
        assert plan["query_plan"] is None
        assert plan["projection"] is None

    # Even when a date binding is configured for the alternative, it is not
    # automatically applied by intents with no temporal projector.
    cfg["reference_selection"] = {
        **reference,
        "references": [
            reference["references"][0],
            {
                **reference["references"][1],
                "date_bindings": [binding("event_date")],
            },
        ],
    }
    plan = build_query_plan(
        context=context,
        intent_name="independent_intent",
        intent_confidence=0.95,
        normalized_question="Show value by posting date",
    )
    assert plan["status"] == "rejected"
    assert plan["error_code"] == "PLANNING_TEMPORAL_REFERENCE_UNSUPPORTED"

    # The gate is semantic rather than unconditional: unrelated questions
    # and the configured default date do not trigger this rejection.
    for question in ("Show value by period", "Show value across teams"):
        plan = build_query_plan(
            context=context,
            intent_name="independent_intent",
            intent_confidence=0.95,
            normalized_question=question,
        )
        assert plan["error_code"] != "PLANNING_TEMPORAL_REFERENCE_UNSUPPORTED"


def test_cross_intent_reference_gate_is_context_driven() -> None:
    from app.domain.planner import _cross_intent_temporal_reference_issue

    context = _synthetic_temporal_context()
    cfg = context["component_configs"]["temporal_planning"]
    cfg["reference_selection"] = {
        "default_reference": "alpha",
        "references": [
            {"reference": "alpha", "terms": ["time alpha"]},
            {"reference": "beta", "terms": ["time beta"]},
        ],
    }

    # The gate uses only configured terms and applies to new phrasings.
    for question in (
        "Results by time beta",
        "Breakdown OF values with time beta",
    ):
        issue = _cross_intent_temporal_reference_issue(
            context=context,
            intent_name="unconfigured_intent",
            normalized_question=question,
        )
        assert issue == "temporal_reference_not_configured"

    assert _cross_intent_temporal_reference_issue(
        context=context,
        intent_name="unconfigured_intent",
        normalized_question="Results by time alpha",
    ) is None
    assert _cross_intent_temporal_reference_issue(
        context=context,
        intent_name="generic_test_intent",
        normalized_question="Results by time beta",
    ) is None
    context["component_configs"].pop("temporal_planning")
    assert _cross_intent_temporal_reference_issue(
        context=context,
        intent_name="unconfigured_intent",
        normalized_question="Results by time beta",
    ) is None


def test_legacy_strategy_remains_unchanged() -> None:
    series, diagnostic = project([], strategy="unique_metric_source_catalog_date")
    assert series is None
    assert "ambiguous_date_columns" in diagnostic["issues"]

    series, diagnostic = project(
        [], strategy="unique_metric_source_catalog_date", dates=["event_date"]
    )
    assert diagnostic["status"] == "resolved", diagnostic
    assert series["date_column"] == "event_date"


if __name__ == "__main__":
    test_explicit_date_bindings()
    test_same_metric_concept_selects_the_correct_source_date()
    test_explicit_reference_never_silently_uses_default_date()
    test_temporal_reference_metadata_fails_closed()
    test_explicit_alternative_rejected_outside_temporal_intent()
    test_cross_intent_reference_gate_is_context_driven()
    test_legacy_strategy_remains_unchanged()
    print("EXPLICIT_TEMPORAL_BINDING=PASS")

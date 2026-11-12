"""Novel, generic multi-source metric compositions across different tenants.

These are independent synthetic financial-schema fixtures, not the 63
historical n8n questions and not G5 accounting claims. No DB/LLM/SQL execute.
The test drives the real intent resolver, planner and SQL request builder.
"""
from __future__ import annotations

from copy import deepcopy

from app.domain.context_normalizer import (
    ContextNormalizationError, normalize_context_snapshot,
)
from app.domain.context_validator import validate_context_snapshot
from app.domain.intent_resolver import resolve_intent
from app.domain.planner import build_query_plan
from app.domain.metric_source_composition import (
    MetricSourceCompositionError, project_metric_source_composition,
)
from app.domain.sql_generation import (
    SqlGenerationInputError, build_sql_generation_request,
)
from app.adapters.postgres.metric_source_composition_sql import (
    PostgresCompositionSqlError, build_postgres_metric_source_sql,
)
from app.domain.sql_security import run_sql_security_gate
from app.domain.sql_contract import run_sql_contract_gate
from testar_planned_filters_e2e import _raw_context


def _tenant(
    schema: str, first: str, second: str,
    value_a: str, value_b: str, *, version: str,
) -> dict:
    raw = _raw_context()
    raw["semantic_agent_version"] = version
    raw["semantic_context_source"] = "synthetic-multi-source-accounting"
    original = raw["table_catalog"][0]
    first_table = deepcopy(original)
    first_table["schema_name"] = schema
    first_table["table_name"] = first
    first_table["description"] = "First fact stream, test-only"
    first_table["metric_columns"] = [value_a]
    first_table["columns"] = [
        {"name": "event_id", "data_type": "integer", "nullable": False},
        {"name": value_a, "data_type": "numeric", "nullable": False},
        {"name": "zone_code", "data_type": "text", "nullable": False},
        {"name": "flag", "data_type": "text", "nullable": False},
    ]
    first_table["primary_key"] = ["event_id"]
    first_table["key_columns"] = ["event_id"]
    second_table = deepcopy(first_table)
    second_table["table_name"] = second
    second_table["description"] = "Second independent fact stream, test-only"
    second_table["metric_columns"] = [value_b]
    second_table["columns"][1]["name"] = value_b
    raw["table_catalog"] = [first_table, second_table]
    one, two = f"{schema}.{first}", f"{schema}.{second}"
    raw["query_patterns"][0]["required_tables"] = [one, two]
    raw["metric_source_compositions"] = [{
        "composition_ref": "approved-stream-aggregation",
        "intent_name": "synthetic_intent",
        "metric_ref": "net_metric",
        "strategy": "union_all_then_aggregate",
        "source_use": "APPROVED_SEMANTIC_MAPPING",
        "accounting_definition_attested": True,
        "sources": [
            {
                "source_ref": "A",
                "target_table": one,
                "value_column": value_a,
                "grain_ref": "fact_grain_A",
                "sign_multiplier": 1,
                "dimension_columns": {"region": "zone_code"},
                "source_filters": [
                    {"column": "flag", "operator": "=", "value": "approved"}
                ],
            },
            {
                "source_ref": "B",
                "target_table": two,
                "value_column": value_b,
                "grain_ref": "fact_grain_B",
                "sign_multiplier": -1,
                "dimension_columns": {"region": "zone_code"},
                "source_filters": [
                    {"column": "flag", "operator": "IN",
                     "value": ["approved", "verified"]}
                ],
            },
        ],
    }]
    return raw


def fixture_a() -> dict:
    return _tenant(
        "funding", "inflows", "outflows",
        "gross_units", "released_units", version="fin-tenant-1-v4"
    )


def fixture_b() -> dict:
    return _tenant(
        "warehouse_ledger", "book_a", "book_b",
        "charge_amount", "credit_total", version="ops-tenant-2-v9"
    )


def _plan(raw: dict):
    context = normalize_context_snapshot(raw)
    validation = validate_context_snapshot(context)
    assert validation["status"] == "valid", validation
    question = "synthetic report about two combined streams"
    intent = resolve_intent(question, context["intent_resolution"])
    assert intent["applied"], intent
    result = build_query_plan(
        context=context,
        intent_name=intent["intent"],
        intent_confidence=intent["intent_confidence"],
        normalized_question=question,
        intent_resolution_result=intent,
    )
    return context, result


def test_two_unrelated_tenants_plan_and_send_dynamic_structural_composition():
    first, second = fixture_a(), fixture_b()
    contexts = []
    requests = []
    for data in (first, second):
        ctx, plan = _plan(data)
        assert plan["status"] == "planned", plan
        context = plan["query_plan"]["planning_context"]
        comp = context["metric_source_composition"]
        assert comp["strategy"] == "union_all_then_aggregate"
        assert comp["metric_ref"] == "net_metric"
        assert comp["sources"][0]["grain_ref"] == "fact_grain_A"
        assert comp["sources"][1]["sign_multiplier"] == -1
        assert context["planned_metrics"] == []
        assert context["planned_filters"] == []
        assert not context["relevant_dre_mappings"]
        req = build_sql_generation_request(plan["query_plan"])
        forwarded = req["generation_context"]["metric_source_composition"]
        assert forwarded == comp
        assert any(
            ins["name"] == "multi_source_metric_composition"
            for ins in req["instructions"]
        )
        assert req["generation_context"]["authorized_tables"]
        assert "sql_pattern" not in str(req["generation_context"]["pattern_metadata"])
        contexts.append(ctx)
        requests.append(req)
    assert contexts[0]["fingerprint"] != contexts[1]["fingerprint"]
    assert requests[0]["generation_context"]["metric_source_composition"] != (
        requests[1]["generation_context"]["metric_source_composition"]
    )


def test_sign_flip_changes_context_fingerprint_not_code():
    raw = fixture_a()
    old = normalize_context_snapshot(raw)["fingerprint"]
    raw["metric_source_compositions"][0]["sources"][1]["sign_multiplier"] = 1
    new = normalize_context_snapshot(raw)["fingerprint"]
    assert old != new


def test_missing_physical_table_or_measure_rejected_pre_planning():
    for kind in ("table", "column", "metric_column", "grain", "negative_sign"):
        raw = fixture_a()
        source = raw["metric_source_compositions"][0]["sources"][1]
        if kind == "table":
            source["target_table"] = "unapproved.private"
        elif kind == "column":
            source["value_column"] = "missing"
        elif kind == "metric_column":
            raw["table_catalog"][1]["metric_columns"] = []
        elif kind == "grain":
            source["grain_ref"] = ""
        elif kind == "negative_sign":
            source["sign_multiplier"] = -9
        try:
            normalize_context_snapshot(raw)
        except ContextNormalizationError:
            pass
        else:
            raise AssertionError(kind)


def test_no_verified_accounting_meaning_or_unsafe_definition_rejected():
    for kind in ("approval", "status", "extra", "duplicate", "sql"):
        raw = fixture_a()
        definition = raw["metric_source_compositions"][0]
        if kind == "approval":
            definition["accounting_definition_attested"] = False
        elif kind == "status":
            definition["source_use"] = "EVALUATION_ONLY"
        elif kind == "extra":
            definition["historical_sql"] = "SELECT * FROM unapproved"
        elif kind == "duplicate":
            definition["sources"][1]["source_ref"] = "A"
        elif kind == "sql":
            definition["sources"][0]["sql_pattern"] = "SELECT ..."
        try:
            normalize_context_snapshot(raw)
        except ContextNormalizationError:
            pass
        else:
            raise AssertionError(kind)


def test_unauthorized_filter_and_group_column_rejected():
    for kind in ("filter", "operator", "dimension", "empty_in"):
        raw = fixture_b()
        source = raw["metric_source_compositions"][0]["sources"][1]
        if kind == "filter":
            source["source_filters"][0]["column"] = "private_amount"
        elif kind == "operator":
            source["source_filters"][0]["operator"] = "DROP"
        elif kind == "dimension":
            source["dimension_columns"]["region"] = "missing_column"
        else:
            source["source_filters"][0]["value"] = []
        try:
            normalize_context_snapshot(raw)
        except ContextNormalizationError:
            pass
        else:
            raise AssertionError(kind)


def test_missing_required_source_table_rejected_before_provider():
    raw = fixture_a()
    raw["query_patterns"][0]["required_tables"] = ["funding.inflows"]
    _, result = _plan(raw)
    assert result["status"] == "rejected", result
    assert result["error_code"] == "PLANNING_METRIC_COMPOSITION_INVALID"


def test_unmatched_requested_grouping_fails_closed():
    raw = fixture_a()
    snapshot = normalize_context_snapshot(raw)
    definitions = snapshot["metric_source_compositions"]
    required = [
        {"qualified_name": "funding.inflows"},
        {"qualified_name": "funding.outflows"},
    ]
    try:
        project_metric_source_composition(
            definitions=definitions,
            intent_name="synthetic_intent",
            required_tables=required,
            detected_dimensions=[{
                "canonical_value": "unknown_region",
                "grouping_requested": True,
            }],
            planned_metrics=[], planned_filters=[],
            analytical_operations=[], temporal_series=None,
        )
    except MetricSourceCompositionError:
        pass
    else:
        raise AssertionError("Unknown grouping silently discarded")


def test_conflicting_metric_or_filter_or_comparison_rejected():
    raw = fixture_a()
    snapshot = normalize_context_snapshot(raw)
    definitions = snapshot["metric_source_compositions"]
    common = dict(
        definitions=definitions,
        intent_name="synthetic_intent",
        required_tables=[
            {"qualified_name": "funding.inflows"},
            {"qualified_name": "funding.outflows"},
        ],
        detected_dimensions=[],
    )
    for override in (
        {"planned_metrics": [{"metric_ref": "standalone"}]},
        {"planned_filters": [{"filter_ref": "mandatory"}]},
        {"analytical_operations": [{"operation_type": "comparison"}]},
        {"temporal_series": {"time_grain": "month"}},
    ):
        options = dict(
            planned_metrics=[], planned_filters=[],
            analytical_operations=[], temporal_series=None, **common
        )
        options.update(override)
        try:
            project_metric_source_composition(**options)
        except MetricSourceCompositionError:
            pass
        else:
            raise AssertionError(f"Unsupported combination accepted: {override}")


def test_modified_query_plan_rejected_before_sql_provider():
    raw = fixture_a()
    _, result = _plan(raw)
    assert result["status"] == "planned", result
    for case in ("table", "metric", "filter", "dim"):
        plan = deepcopy(result["query_plan"])
        comp = plan["planning_context"]["metric_source_composition"]
        if case == "table":
            comp["sources"][0]["target_table"] = "other.private"
        elif case == "metric":
            comp["sources"][0]["value_column"] = "private"
        elif case == "filter":
            comp["sources"][0]["source_filters"][0]["column"] = "private"
        else:
            comp["grouping_dimensions"] = [{
                "canonical_value": "region",
                "source_bindings": [{"source_ref": "A",
                    "target_table": "funding.inflows",
                    "target_column": "private"}],
            }]
        try:
            build_sql_generation_request(plan)
        except SqlGenerationInputError:
            pass
        else:
            raise AssertionError(f"Unauthorized provider input accepted: {case}")


def test_legacy_snapshots_without_compositions_keep_old_fingerprint():
    raw = _raw_context()
    ctx = normalize_context_snapshot(raw)
    assert "metric_source_compositions" not in ctx
    assert ctx["fingerprint"] == normalize_context_snapshot(deepcopy(raw))["fingerprint"]



def test_generated_postgres_sql_has_dynamic_sources_and_no_raw_fact_join():
    for raw in (fixture_a(), fixture_b()):
        _, result = _plan(raw)
        assert result["status"] == "planned"
        plan = result["query_plan"]
        req = build_sql_generation_request(plan)
        sql = build_postgres_metric_source_sql(req)
        print("GENERATED_READ_ONLY_SQL_SHA256", __import__("hashlib").sha256(
            sql.encode()).hexdigest())
        assert "UNION ALL" in sql
        assert "JOIN" not in sql
        assert 'SUM("measure_value") AS "metric_value"' in sql
        assert sql.startswith('WITH "combined_sources" AS (')
        assert raw["metric_source_compositions"][0]["sources"][0]["value_column"] in sql
        assert raw["metric_source_compositions"][0]["sources"][1]["value_column"] in sql
        security, analysis = run_sql_security_gate(
            current_sql=sql, query_plan=plan,
        )
        assert security["status"] == "approved", security["errors"]
        contract, _ = run_sql_contract_gate(
            current_sql=sql, query_plan=plan, analysis=analysis,
        )
        assert contract["status"] == "approved", contract["errors"]


def test_compiler_fails_closed_on_unconfigured_source_and_escaped_literals():
    raw = fixture_a()
    _, planned = _plan(raw)
    req = build_sql_generation_request(planned["query_plan"])
    changed = deepcopy(req)
    changed["generation_context"]["metric_source_composition"]["sources"][0][
        "target_table"
    ] = "other.private"
    try:
        build_postgres_metric_source_sql(changed)
    except PostgresCompositionSqlError:
        pass
    else:
        raise AssertionError("Unapproved source included")

    escaped = deepcopy(req)
    escaped["generation_context"]["metric_source_composition"]["sources"][0][
        "source_filters"
    ][0]["value"] = "O'Brien"
    sql = build_postgres_metric_source_sql(escaped)
    assert "'O''Brien'" in sql
    assert "O'Brien" not in sql

def main() -> None:
    tests = sorted(
        (name, obj) for name, obj in globals().items()
        if name.startswith("test_") and callable(obj)
    )
    for name, test in tests:
        test()
        print("PASS", name)
    print("TOTAL_TESTS", len(tests))


if __name__ == "__main__":
    main()

from __future__ import annotations

"""Read-only, business-agnostic metadata preflight for a semantic candidate.

This is not a physical database inspection or authorization to activate.
Expected SQL, benchmark fixtures, LLM providers and SQL executors are absent.
"""

import argparse
import json
import os
from collections.abc import Mapping
from typing import Any

from app.adapters.postgres.context_repository import PostgresContextRepository
from app.domain.context_validator import validate_context_snapshot


_SUPPORTED_DATE_STRATEGIES = {
    "unique_metric_source_catalog_date",
    "configured_metric_source_date",
}


def _names(value: Any) -> set[str]:
    """Read declared catalog names only; never infer a column from a hint."""
    items = value if isinstance(value, list) else [value]
    names: set[str] = set()
    for item in items:
        name = item.get("name") if isinstance(item, Mapping) else item
        if isinstance(name, str) and name.strip():
            names.add(name.strip().casefold())
    return names


def _tables(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for table in snapshot.get("table_catalog", []):
        if not isinstance(table, Mapping):
            continue
        schema, name = table.get("schema_name"), table.get("table_name")
        if isinstance(schema, str) and isinstance(name, str):
            if schema.strip() and name.strip():
                result[f"{schema.strip()}.{name.strip()}".casefold()] = table
    return result


def _allowed_filter_columns(table: Mapping[str, Any]) -> set[str]:
    allowed = set()
    for key in ("columns", "primary_key", "key_columns", "metric_columns", "date_columns"):
        allowed.update(_names(table.get(key)))
    hint = table.get("ai_hint")
    if isinstance(hint, Mapping):
        allowed.update(_names(hint.get("authorized_filter_columns")))
    return allowed


def _entity_binding(entity: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    rule = entity.get("business_rule")
    candidate = rule.get(key) if isinstance(rule, Mapping) else None
    return candidate if isinstance(candidate, Mapping) else None


def evaluate_candidate_readiness(
    snapshot: Mapping[str, Any],
    *,
    simulate_temporal_strategy: str | None = None,
) -> dict[str, Any]:
    """Check metadata consistency without choosing finance rules or issuing SQL."""
    if simulate_temporal_strategy is not None and (
        simulate_temporal_strategy not in _SUPPORTED_DATE_STRATEGIES
    ):
        raise ValueError("unsupported temporal strategy")

    config_container = snapshot.get("component_configs")
    config_container = config_container if isinstance(config_container, Mapping) else {}
    temporal = config_container.get("temporal_planning")
    temporal = temporal if isinstance(temporal, Mapping) else {}
    strategy = (
        simulate_temporal_strategy
        if simulate_temporal_strategy is not None
        else temporal.get("date_binding_strategy")
    )
    source = "simulation" if simulate_temporal_strategy is not None else "versioned"
    catalog = _tables(snapshot)
    entities = snapshot.get("entities", [])
    entities = entities if isinstance(entities, list) else []
    filter_bindings: dict[str, list[Mapping[str, Any]]] = {}
    metrics: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    issues: list[dict[str, str]] = []
    checks: list[dict[str, Any]] = []

    def block(code: str, *, concept: str = "", table: str = "") -> None:
        issues.append({"code": code, "concept": concept, "table": table})

    for entity in entities:
        if not isinstance(entity, Mapping):
            continue
        kind = str(entity.get("entity_type", "")).casefold()
        if kind == "filter_binding":
            binding = _entity_binding(entity, "filter_binding")
            if binding is None:
                continue
            concept = str(binding.get("filter_concept", "")).strip()
            if concept:
                filter_bindings.setdefault(concept.casefold(), []).append(binding)
            target = str(binding.get("target_table", "")).strip()
            column = str(binding.get("target_column", "")).strip()
            table = catalog.get(target.casefold())
            if table is None:
                block("FILTER_TABLE_NOT_IN_CATALOG", concept=concept, table=target)
            elif not column or column.casefold() not in _allowed_filter_columns(table):
                block("FILTER_COLUMN_NOT_AUTHORIZED", concept=concept, table=target)
        elif kind == "metric_binding":
            binding = _entity_binding(entity, "metric_binding")
            if binding is not None:
                metrics.append((entity, binding))

    if strategy is not None and strategy not in _SUPPORTED_DATE_STRATEGIES:
        block("TEMPORAL_STRATEGY_UNSUPPORTED")
    if strategy is not None and not metrics:
        block("METRIC_BINDINGS_MISSING")

    date_bindings = temporal.get("date_bindings")
    date_bindings = date_bindings if isinstance(date_bindings, list) else []
    for entity, binding in metrics:
        concept = str(binding.get("metric_concept") or entity.get("canonical_value") or "").strip()
        target = str(binding.get("target_table") or entity.get("target_table") or "").strip()
        metric_col = str(binding.get("target_column") or entity.get("target_column") or "").strip()
        table = catalog.get(target.casefold())
        status = "metadata_resolved"
        dates: set[str] = set()

        if table is None:
            block("METRIC_TABLE_NOT_IN_CATALOG", concept=concept, table=target)
            status = "blocked"
        else:
            if not metric_col or metric_col.casefold() not in _names(table.get("metric_columns")):
                block("METRIC_COLUMN_NOT_AUTHORIZED", concept=concept, table=target)
                status = "blocked"
            dates = _names(table.get("date_columns"))

        required = binding.get("required_filter_concepts", [])
        if isinstance(required, list):
            for value in required:
                if not isinstance(value, str) or not value.strip():
                    block("REQUIRED_FILTER_CONCEPT_INVALID", concept=concept, table=target)
                    status = "blocked"
                    continue
                matches = filter_bindings.get(value.strip().casefold(), [])
                if len(matches) != 1 or matches[0].get("required") is not True:
                    block("REQUIRED_FILTER_BINDING_MISSING_OR_AMBIGUOUS", concept=concept, table=target)
                    status = "blocked"

        if table is not None and strategy == "unique_metric_source_catalog_date":
            if len(dates) != 1:
                block(
                    "TEMPORAL_DATE_AMBIGUOUS" if dates else "TEMPORAL_DATE_MISSING",
                    concept=concept, table=target,
                )
                status = "blocked"
            elif _names(table.get("columns")) and not dates <= _names(table.get("columns")):
                block("TEMPORAL_DATE_NOT_IN_COLUMNS", concept=concept, table=target)
                status = "blocked"
        elif table is not None and strategy == "configured_metric_source_date":
            matches = [
                item for item in date_bindings
                if isinstance(item, Mapping)
                and str(item.get("metric_concept", "")).strip().casefold() == concept.casefold()
                and str(item.get("target_table", "")).strip().casefold() == target.casefold()
            ]
            if len(matches) != 1:
                block("TEMPORAL_EXPLICIT_BINDING_MISSING_OR_AMBIGUOUS", concept=concept, table=target)
                status = "blocked"
            else:
                chosen = str(matches[0].get("target_column", "")).strip().casefold()
                if (
                    not chosen or chosen not in dates
                    or (_names(table.get("columns")) and chosen not in _names(table.get("columns")))
                ):
                    block("TEMPORAL_DATE_NOT_AUTHORIZED", concept=concept, table=target)
                    status = "blocked"

        checks.append({
            "kind": "metric_source_metadata",
            "concept": concept,
            "table": target,
            "date_candidates": sorted(dates),
            "status": status,
        })

    issues.sort(key=lambda x: (x["code"], x["concept"].casefold(), x["table"].casefold()))
    checks.sort(key=lambda x: (x["concept"].casefold(), x["table"].casefold()))
    result_status = (
        "blocked" if issues else
        "not_applicable" if strategy is None else
        "checks_passed"
    )
    return {
        "context_version": str(snapshot.get("version", "")),
        "context_fingerprint": str(snapshot.get("fingerprint", "")),
        "status": result_status,
        "temporal_strategy": strategy,
        "temporal_strategy_source": source,
        "metric_bindings_checked": len(metrics),
        "filter_bindings_checked": sum(map(len, filter_bindings.values())),
        "checks": checks,
        "blocking_issues": issues,
        "physical_schema_verified": False,
        "finance_semantics_verified": False,
        "activation_authorized": False,
        "llm_calls": 0,
        "real_sql_execution": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--simulate-temporal-strategy", choices=sorted(_SUPPORTED_DATE_STRATEGIES))
    args = parser.parse_args()

    if os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") != "false":
        print("ABORTED: real SQL execution must be disabled.")
        return 3

    try:
        repo = PostgresContextRepository(
            dsn=os.environ["CONTEXT_POSTGRES_DSN"],
            semantic_agent_version=args.version,
            context_schema=os.environ.get("POSTGRES_CONTEXT_SCHEMA", "semantic_context"),
        )
        snapshot = repo.load_active_context(user_profile="runtime_validation")
        if snapshot.get("version") != args.version:
            print("ABORTED: unexpected context version.")
            return 4
        if args.expected_fingerprint and snapshot.get("fingerprint") != args.expected_fingerprint:
            print("ABORTED: context fingerprint mismatch.")
            return 4
        validation = validate_context_snapshot(snapshot)
        report = evaluate_candidate_readiness(
            snapshot, simulate_temporal_strategy=args.simulate_temporal_strategy
        )
        report["structural_validation_status"] = validation.get("status")
        report["structural_error_codes"] = sorted({
            str(item.get("code", "unknown")) for item in validation.get("errors", [])
        })
        if validation.get("status") != "valid":
            report["status"] = "blocked"
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
        return 1 if report["status"] == "blocked" else 0
    except Exception as exc:
        # Database errors can include DSNs; report only the exception type.
        print("READINESS_ERROR_TYPE:", type(exc).__name__)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

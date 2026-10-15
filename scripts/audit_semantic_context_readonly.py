from __future__ import annotations

"""Read-only, business-agnostic semantic context inventory for Shadow.

No LLM, benchmark, SQL execution, evidence writes or context migrations.
The user supplies the semantic term being inspected; this file contains
no finance-specific entities, physical table names or expected answers.
"""

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping
from typing import Any

from app.adapters.postgres.context_repository import PostgresContextRepository
from app.domain.context_validator import validate_context_snapshot
from app.domain.search_text import normalize_search_text


_SENSITIVE_FIELDS = (
    "authorization", "password", "secret", "token", "api_key",
    "apikey", "dsn", "credential", "cookie",
)


def _safe_metadata(value: Any, *, depth: int = 0) -> Any:
    """Limit output and remove credential-looking metadata keys."""
    if depth > 6:
        return "<max_depth>"
    if isinstance(value, Mapping):
        return {
            str(key): (
                "<redacted>"
                if any(piece in str(key).casefold() for piece in _SENSITIVE_FIELDS)
                else _safe_metadata(child, depth=depth + 1)
            )
            for key, child in list(value.items())[:40]
        }
    if isinstance(value, list):
        return [_safe_metadata(item, depth=depth + 1) for item in value[:40]]
    if isinstance(value, str):
        return value[:600]
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(type(value).__name__)


def inventory(snapshot: Mapping[str, Any], *, term: str | None = None) -> dict[str, Any]:
    entities = snapshot.get("entities") or []
    dre = snapshot.get("dre_mappings") or []
    tables = snapshot.get("table_catalog") or []
    if not all(isinstance(group, list) for group in (entities, dre, tables)):
        raise ValueError("invalid context collections")

    counter = Counter(
        str(item.get("entity_type", "unknown"))
        for item in entities if isinstance(item, Mapping)
    )
    metrics = []
    bindings = []
    filter_bindings = []
    for entity in entities:
        if not isinstance(entity, Mapping):
            continue
        kind = entity.get("entity_type")
        rule = entity.get("business_rule")
        rule = rule if isinstance(rule, Mapping) else {}
        base = {
            "term": entity.get("user_term"),
            "concept": entity.get("canonical_value"),
            "table": entity.get("target_table"),
            "column": entity.get("target_column"),
        }
        if kind == "financial_metric":
            metrics.append({
                **base, "metric": _safe_metadata(rule.get("metric")),
            })
        elif kind == "metric_binding":
            bindings.append({
                **base, "binding": _safe_metadata(rule.get("metric_binding")),
            })
        elif kind == "filter_binding":
            filter_bindings.append({
                **base, "binding": _safe_metadata(rule.get("filter_binding")),
            })

    revenue_mappings = []
    for item in dre:
        if not isinstance(item, Mapping) or item.get("is_revenue") is not True:
            continue
        revenue_mappings.append({
            "dre_code": item.get("dre_code"),
            "nivel_1_bi": item.get("nivel_1_bi"),
            "category": item.get("category"),
            "description": item.get("business_description"),
            "sign_convention": _safe_metadata(item.get("sign_convention")),
            "sql_filter_hint": _safe_metadata(item.get("sql_filter_hint")),
        })

    catalogue = [
        {
            "table": "{}.{}".format(
                item.get("schema_name", ""), item.get("table_name", "")
            ),
            "metric_columns": _safe_metadata(item.get("metric_columns")),
            "date_columns": _safe_metadata(item.get("date_columns")),
            "join_rules": _safe_metadata(item.get("join_rules")),
        }
        for item in tables if isinstance(item, Mapping)
    ]
    config = snapshot.get("component_configs") or {}
    config = config if isinstance(config, Mapping) else {}
    key = normalize_search_text(term) if term else None
    exact_metrics = [
        metric for metric in metrics
        if key and normalize_search_text(str(metric.get("term") or "")) == key
    ]
    concepts = {
        str(metric.get("concept") or "").casefold()
        for metric in exact_metrics
    }
    exact_bindings = [
        binding for binding in bindings
        if str(binding.get("concept") or "").casefold() in concepts
    ]
    validation = validate_context_snapshot(snapshot)
    return {
        "context_version": snapshot.get("version"),
        "fingerprint": snapshot.get("fingerprint"),
        "context_validation": {
            "status": validation.get("status"),
            "error_codes": sorted({
                str(error.get("code", "unknown"))
                for error in validation.get("errors", [])
            }),
        },
        "entity_type_counts": dict(sorted(counter.items())),
        "metric_alias_count": len(metrics),
        "metric_aliases": metrics[:100],
        "metric_binding_count": len(bindings),
        "metric_bindings": bindings[:100],
        "filter_binding_count": len(filter_bindings),
        "filter_bindings": filter_bindings[:60],
        "revenue_dre_mapping_count": len(revenue_mappings),
        "revenue_dre_mappings": revenue_mappings[:60],
        "catalogue": catalogue[:50],
        "component_names": sorted(str(item) for item in config),
        "temporal_planning": _safe_metadata(config.get("temporal_planning")),
        "term_probe": {
            "term": term,
            "matching_metric_aliases": exact_metrics,
            "matching_metric_bindings": exact_bindings,
            "status": (
                "not_requested" if not key
                else "no_exact_metric_alias" if not exact_metrics
                else "metric_binding_missing" if not exact_bindings
                else "candidate_bindings_present"
            ),
        },
        "truncation_policy": {
            "metric_aliases": 100, "metric_bindings": 100,
            "filter_bindings": 60, "revenue_dre_mappings": 60,
            "catalogue": 50,
        },
        "llm_calls": 0,
        "real_sql_execution": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--term")
    args = parser.parse_args()

    if os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") != "false":
        print("ABORTED: real SQL execution must be disabled.")
        return 3
    try:
        repo = PostgresContextRepository(
            dsn=os.environ["CONTEXT_POSTGRES_DSN"],
            semantic_agent_version=args.version,
            context_schema=os.environ.get(
                "POSTGRES_CONTEXT_SCHEMA", "semantic_context"
            ),
        )
        snapshot = repo.load_active_context(user_profile="runtime_validation")
        if snapshot.get("version") != args.version:
            print("ABORTED: unexpected semantic context version.")
            return 4
        print(json.dumps(
            inventory(snapshot, term=args.term),
            ensure_ascii=False, indent=2, sort_keys=True, default=str
        ))
        return 0
    except Exception as exc:
        # Do not reveal raw DSNs, database errors, or runtime configuration.
        print("AUDIT_ERROR_TYPE=" + type(exc).__name__)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Generic, approved-by-context multi-source *metric* composition contract.

Only structural operations live here. Tenant-specific measures, source facts,
signs, grains, dimensions, and predicates are provided by versioned catalog
data, never inferred from words in the question or from historic SQL.

This opt-in feature is isolated from the legacy runtime. Catalog approval
claims do not replace an independently approved tenant/fingerprint or an
accountant's verification of real source records.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

_REFERENCE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_COLUMN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_STRATEGY = "union_all_then_aggregate"
_PROVENANCE = "APPROVED_SEMANTIC_MAPPING"
_COMPOSITION_KEYS = {
    "composition_ref", "intent_name", "metric_ref", "strategy",
    "source_use", "accounting_definition_attested", "sources",
}
_SOURCE_KEYS = {
    "source_ref", "target_table", "value_column", "grain_ref",
    "sign_multiplier", "dimension_columns", "source_filters",
}
_FILTER_KEYS = {"column", "operator", "value"}
_FILTER_OPS = {"=", "<>", ">", ">=", "<", "<=", "IN", "NOT IN"}


class MetricSourceCompositionError(ValueError):
    """An unapproved, physically unsafe or ambiguous composition."""


def _valid_ref(value: object) -> bool:
    return isinstance(value, str) and _REFERENCE.fullmatch(value) is not None


def _valid_column(value: object) -> bool:
    return isinstance(value, str) and _COLUMN.fullmatch(value) is not None


def _safe_scalar(value: object) -> bool:
    return (
        (isinstance(value, (str, int, float, bool)) or value is None)
        and not isinstance(value, complex)
        and (not isinstance(value, str) or len(value) <= 250)
        and (not isinstance(value, float) or (
            value == value and value not in (float("inf"), float("-inf"))
        ))
    )


def _source_filter(raw: object, columns: set[str]) -> dict[str, Any]:
    if not isinstance(raw, Mapping) or set(raw) != _FILTER_KEYS:
        raise MetricSourceCompositionError("COMPOSITION_FILTER_INVALID")
    col, op, value = raw["column"], raw["operator"], raw["value"]
    if not _valid_column(col) or col.casefold() not in columns:
        raise MetricSourceCompositionError("COMPOSITION_FILTER_COLUMN_UNKNOWN")
    if op not in _FILTER_OPS:
        raise MetricSourceCompositionError("COMPOSITION_FILTER_OPERATOR_INVALID")
    if op in ("IN", "NOT IN"):
        if (
            not isinstance(value, list)
            or not 1 <= len(value) <= 50
            or not all(_safe_scalar(v) and v is not None for v in value)
        ):
            raise MetricSourceCompositionError("COMPOSITION_FILTER_VALUES_INVALID")
    elif not _safe_scalar(value) or value is None:
        raise MetricSourceCompositionError("COMPOSITION_FILTER_VALUE_INVALID")
    return {"column": col, "operator": op, "value": deepcopy(value)}


def normalize_metric_source_compositions(
    raw: object, table_catalog: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Validate and canonicalize versioned fact-stream union definitions.

    All physical target columns must be present in the *same* approved
    catalog. No universal accounting schema or DRE is assumed.
    """
    if not isinstance(raw, list) or len(raw) > 128:
        raise MetricSourceCompositionError("COMPOSITIONS_NOT_LIST")
    table_index: dict[str, Mapping[str, Any]] = {}
    for table in table_catalog:
        if not isinstance(table, Mapping):
            raise MetricSourceCompositionError("COMPOSITION_CATALOG_INVALID")
        schema, name = table.get("schema_name"), table.get("table_name")
        if not _valid_column(schema) or not _valid_column(name):
            raise MetricSourceCompositionError("COMPOSITION_CATALOG_INVALID")
        qualified = f"{schema}.{name}".casefold()
        if qualified in table_index:
            raise MetricSourceCompositionError("COMPOSITION_CATALOG_AMBIGUOUS")
        table_index[qualified] = table

    output = []
    intents: set[str] = set()
    for raw_item in raw:
        if not isinstance(raw_item, Mapping) or set(raw_item) != _COMPOSITION_KEYS:
            raise MetricSourceCompositionError("COMPOSITION_DEFINITION_INVALID")
        identity = raw_item.get("composition_ref")
        intent = raw_item.get("intent_name")
        metric_ref = raw_item.get("metric_ref")
        if (
            not all(_valid_ref(v) for v in (identity, intent, metric_ref))
            or intent.casefold() in intents
            or raw_item.get("strategy") != _STRATEGY
            or raw_item.get("source_use") != _PROVENANCE
            or raw_item.get("accounting_definition_attested") is not True
        ):
            raise MetricSourceCompositionError("COMPOSITION_UNAPPROVED_OR_AMBIGUOUS")
        intents.add(intent.casefold())
        raw_sources = raw_item.get("sources")
        if not isinstance(raw_sources, list) or not 2 <= len(raw_sources) <= 24:
            raise MetricSourceCompositionError("COMPOSITION_SOURCE_COUNT_INVALID")
        sources = []
        seen_refs: set[str] = set()
        seen_tables: set[str] = set()
        for source in raw_sources:
            if not isinstance(source, Mapping) or set(source) != _SOURCE_KEYS:
                raise MetricSourceCompositionError("COMPOSITION_SOURCE_INVALID")
            source_ref = source.get("source_ref")
            table_ref = source.get("target_table")
            value_column = source.get("value_column")
            grain = source.get("grain_ref")
            if (
                not all(_valid_ref(v) for v in (source_ref, grain))
                or not isinstance(table_ref, str)
                or table_ref.casefold() not in table_index
                or not _valid_column(value_column)
                or source_ref.casefold() in seen_refs
                or table_ref.casefold() in seen_tables
            ):
                raise MetricSourceCompositionError("COMPOSITION_SOURCE_UNRESOLVED")
            seen_refs.add(source_ref.casefold())
            seen_tables.add(table_ref.casefold())
            table = table_index[table_ref.casefold()]
            declared_columns = table.get("columns", [])
            if not isinstance(declared_columns, list):
                raise MetricSourceCompositionError("COMPOSITION_COLUMNS_MISSING")
            available = {
                str(col.get("name", "")).casefold()
                for col in declared_columns if isinstance(col, Mapping)
            }
            metric_columns = table.get("metric_columns", [])
            if not isinstance(metric_columns, list) or (
                value_column.casefold() not in {
                    str(col).casefold() for col in metric_columns
                }
            ) or value_column.casefold() not in available:
                raise MetricSourceCompositionError("COMPOSITION_METRIC_NOT_AUTHORIZED")
            sign = source.get("sign_multiplier")
            if type(sign) is not int or sign not in (-1, 1):
                raise MetricSourceCompositionError("COMPOSITION_SIGN_UNATTESTED")
            raw_dimensions = source.get("dimension_columns")
            if not isinstance(raw_dimensions, Mapping) or len(raw_dimensions) > 32:
                raise MetricSourceCompositionError("COMPOSITION_DIMENSIONS_INVALID")
            dimensions = {}
            for concept, column in raw_dimensions.items():
                if (
                    not _valid_ref(concept)
                    or not _valid_column(column)
                    or column.casefold() not in available
                ):
                    raise MetricSourceCompositionError(
                        "COMPOSITION_DIMENSION_UNAUTHORIZED"
                    )
                if concept.casefold() in {x.casefold() for x in dimensions}:
                    raise MetricSourceCompositionError("COMPOSITION_DIMENSION_DUPLICATED")
                dimensions[concept] = column
            raw_filters = source.get("source_filters")
            if not isinstance(raw_filters, list) or len(raw_filters) > 32:
                raise MetricSourceCompositionError("COMPOSITION_FILTERS_INVALID")
            filters = [_source_filter(f, available) for f in raw_filters]
            sources.append({
                "source_ref": source_ref,
                "target_table": table_ref,
                "value_column": value_column,
                "grain_ref": grain,
                "sign_multiplier": sign,
                "dimension_columns": dict(sorted(
                    dimensions.items(), key=lambda p: p[0].casefold()
                )),
                "source_filters": sorted(
                    filters, key=lambda f: (
                        f["column"].casefold(), f["operator"], str(f["value"])
                    ),
                ),
            })
        output.append({
            "composition_ref": identity,
            "intent_name": intent,
            "metric_ref": metric_ref,
            "strategy": _STRATEGY,
            "source_use": _PROVENANCE,
            "accounting_definition_attested": True,
            "sources": sorted(
                sources, key=lambda x: x["source_ref"].casefold()
            ),
        })
    return sorted(output, key=lambda c: c["intent_name"].casefold())


def project_metric_source_composition(
    *,
    definitions: object,
    intent_name: str,
    required_tables: list[Mapping[str, Any]],
    detected_dimensions: list[Mapping[str, Any]],
    planned_metrics: list[Mapping[str, Any]],
    planned_filters: list[Mapping[str, Any]],
    analytical_operations: list[Mapping[str, Any]],
    temporal_series: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(definitions, list):
        raise MetricSourceCompositionError("COMPOSITIONS_INVALID")
    matches = [
        item for item in definitions
        if isinstance(item, Mapping)
        and item.get("intent_name", "").casefold() == intent_name.casefold()
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise MetricSourceCompositionError("COMPOSITION_INTENT_AMBIGUOUS")
    source = matches[0]
    # No silent dropping of filters, measures, comparisons or time-series.
    # Multi-source support will expand only with explicit grain mapping.
    if planned_metrics or planned_filters or analytical_operations or temporal_series:
        raise MetricSourceCompositionError("COMPOSITION_OPERATION_CONFLICT")
    authorized_tables = {
        str(table.get("qualified_name", "")).casefold()
        for table in required_tables if isinstance(table, Mapping)
    }
    for fact in source["sources"]:
        if fact["target_table"].casefold() not in authorized_tables:
            raise MetricSourceCompositionError("COMPOSITION_SOURCE_NOT_SELECTED")

    requested_dimensions = [
        dim for dim in detected_dimensions
        if isinstance(dim, Mapping) and dim.get("grouping_requested") is True
    ]
    seen: set[str] = set()
    selected = []
    for dim in requested_dimensions:
        concept = dim.get("canonical_value")
        if not _valid_ref(concept) or concept.casefold() in seen:
            raise MetricSourceCompositionError("COMPOSITION_GROUPING_AMBIGUOUS")
        seen.add(concept.casefold())
        bindings = []
        for fact in source["sources"]:
            value = next((
                col for key, col in fact["dimension_columns"].items()
                if key.casefold() == concept.casefold()
            ), None)
            if value is None:
                raise MetricSourceCompositionError("COMPOSITION_GROUPING_INCOMPLETE")
            bindings.append({
                "source_ref": fact["source_ref"],
                "target_table": fact["target_table"],
                "target_column": value,
            })
        selected.append({
            "canonical_value": concept,
            "source_bindings": bindings,
        })
    return {
        "composition_ref": source["composition_ref"],
        "metric_ref": source["metric_ref"],
        "strategy": source["strategy"],
        "source_use": source["source_use"],
        "sources": [
            {key: deepcopy(value) for key, value in fact.items()
             if key != "dimension_columns"}
            for fact in source["sources"]
        ],
        "grouping_dimensions": sorted(
            selected, key=lambda d: d["canonical_value"].casefold()
        ),
    }

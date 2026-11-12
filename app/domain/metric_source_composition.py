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
from decimal import Decimal, InvalidOperation
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from app.domain.search_text import normalize_search_text

_REFERENCE = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,127}$")
_COLUMN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_STRATEGY = "union_all_then_aggregate"
_PROVENANCE = "APPROVED_SEMANTIC_MAPPING"
_COMPOSITION_KEYS = {
    "composition_ref", "intent_name", "metric_ref", "strategy",
    "source_use", "accounting_definition_attested", "sources",
}
_RANKING_KEYS = {"terms", "default_limit", "maximum_limit"}
_RANKING_TERM_KEYS = {"term", "direction"}
_RANKING_DIRECTIONS = {"ascending", "descending"}
_RANKING_OPERATIONAL_CEILING = 100

_WEIGHTED_CALCULATION_KEYS = {"operation", "terms"}
_WEIGHTED_TERM_KEYS = {"source_ref", "coefficient"}
_WEIGHT_DECIMAL = re.compile(r"^-?(?:0|[1-9][0-9]{0,5})(?:\.[0-9]{1,6})?$")
_WEIGHT_ABSOLUTE_LIMIT = Decimal("1000000")

_CALCULATION_KEYS = {
    "operation", "numerator_source_refs", "denominator_source_refs",
    "scale", "zero_denominator",
}
_TEMPORAL_GRAINS = {"day", "week", "month", "quarter", "year"}
_NUMERIC_TYPES = {"numeric", "decimal", "smallint", "integer", "bigint"}
_TEMPORAL_KEYS = {"require_explicit_grain", "granularities", "source_dates"}
_TEMPORAL_OPTIONAL_KEYS = {"unhandled_period_terms", "period_year", "period_year_range"}
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
        and (not isinstance(value, str) or (
            len(value) <= 250
            and all(ord(character) >= 32 for character in value)
        ))
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



def _approved_source_ratio(
    raw: object, source_refs: set[str],
) -> dict[str, Any]:
    """Versioned generic ratio of SUMs over source streams.

    No business metric, sign, account, DRE, SQL expression, currency, or
    particular client can be embedded as code. The approved tenant snapshot
    supplies every operand, inclusion and scale. All streams must contribute
    to at least one operand to prevent silently dropping financial facts.
    """
    if not isinstance(raw, Mapping) or set(raw) != _CALCULATION_KEYS:
        raise MetricSourceCompositionError("COMPOSITION_CALCULATION_INVALID")
    if (
        raw.get("operation") != "ratio_of_sums"
        or raw.get("zero_denominator") != "null"
        or type(raw.get("scale")) is not int
        or not 1 <= raw["scale"] <= 10000
    ):
        raise MetricSourceCompositionError("COMPOSITION_CALCULATION_NOT_ATTESTED")
    normalized = {}
    for key in ("numerator_source_refs", "denominator_source_refs"):
        refs = raw[key]
        if not isinstance(refs, list) or not 1 <= len(refs) <= 24:
            raise MetricSourceCompositionError("COMPOSITION_OPERANDS_INVALID")
        chosen = set()
        for ref in refs:
            if (
                not _valid_ref(ref)
                or ref.casefold() not in source_refs
                or ref.casefold() in chosen
            ):
                raise MetricSourceCompositionError("COMPOSITION_OPERAND_NOT_BOUND")
            chosen.add(ref.casefold())
        normalized[key] = chosen
    if (
        normalized["numerator_source_refs"]
        | normalized["denominator_source_refs"]
    ) != source_refs:
        raise MetricSourceCompositionError("COMPOSITION_UNUSED_SOURCE")
    return {
        "operation": "ratio_of_sums",
        "numerator_source_refs": sorted(normalized["numerator_source_refs"]),
        "denominator_source_refs": sorted(normalized["denominator_source_refs"]),
        "scale": raw["scale"],
        "zero_denominator": "null",
    }




def _approved_source_calculation(
    raw: object, source_refs: set[str],
) -> dict[str, Any]:
    """Arithmetic DSL; all client accounting signs and weights are tenant data.

    Every authorized source participates once, with a coefficient explicitly
    attested in the versioned context; no source has a built-in business role.
    """
    if not isinstance(raw, Mapping):
        raise MetricSourceCompositionError("COMPOSITION_CALCULATION_INVALID")
    if raw.get("operation") != "weighted_sum_of_sums":
        return _approved_source_ratio(raw, source_refs)
    if set(raw) != _WEIGHTED_CALCULATION_KEYS:
        raise MetricSourceCompositionError("COMPOSITION_WEIGHTED_DEFINITION_INVALID")
    terms = raw.get("terms")
    if not isinstance(terms, list) or not 2 <= len(terms) <= 24:
        raise MetricSourceCompositionError("COMPOSITION_WEIGHTED_TERMS_INVALID")
    result = []
    seen: set[str] = set()
    for term in terms:
        if not isinstance(term, Mapping) or set(term) != _WEIGHTED_TERM_KEYS:
            raise MetricSourceCompositionError("COMPOSITION_WEIGHTED_TERM_INVALID")
        ref, coefficient = term.get("source_ref"), term.get("coefficient")
        if (
            not _valid_ref(ref)
            or ref.casefold() not in source_refs
            or ref.casefold() in seen
            or not isinstance(coefficient, str)
            or _WEIGHT_DECIMAL.fullmatch(coefficient) is None
        ):
            raise MetricSourceCompositionError("COMPOSITION_WEIGHTED_BINDING_INVALID")
        try:
            numeric = Decimal(coefficient)
        except InvalidOperation:
            raise MetricSourceCompositionError("COMPOSITION_WEIGHTED_COEFFICIENT_INVALID") from None
        if not numeric.is_finite() or numeric == 0 or abs(numeric) > _WEIGHT_ABSOLUTE_LIMIT:
            raise MetricSourceCompositionError("COMPOSITION_WEIGHTED_COEFFICIENT_INVALID")
        seen.add(ref.casefold())
        canonical = format(numeric.normalize(), "f")
        result.append({"source_ref": ref.casefold(), "coefficient": canonical})
    if seen != source_refs:
        raise MetricSourceCompositionError("COMPOSITION_UNUSED_SOURCE")
    return {
        "operation": "weighted_sum_of_sums",
        "terms": sorted(result, key=lambda item: item["source_ref"]),
    }


def _normalize_ranking_policy(raw: object) -> dict[str, Any]:
    """Versioned tenant-owned ranking terms, not hardcoded NL→SQL phrases."""
    if not isinstance(raw, Mapping) or set(raw) != _RANKING_KEYS:
        raise MetricSourceCompositionError("COMPOSITION_RANKING_INVALID")
    default_limit = raw.get("default_limit")
    maximum_limit = raw.get("maximum_limit")
    if (
        type(default_limit) is not int
        or type(maximum_limit) is not int
        or not 1 <= default_limit <= maximum_limit <= _RANKING_OPERATIONAL_CEILING
    ):
        raise MetricSourceCompositionError("COMPOSITION_RANKING_LIMIT_INVALID")
    terms = raw.get("terms")
    if not isinstance(terms, list) or not 1 <= len(terms) <= 16:
        raise MetricSourceCompositionError("COMPOSITION_RANKING_TERMS_INVALID")
    result = []
    seen = set()
    for raw_term in terms:
        if not isinstance(raw_term, Mapping) or set(raw_term) != _RANKING_TERM_KEYS:
            raise MetricSourceCompositionError("COMPOSITION_RANKING_TERM_INVALID")
        word = raw_term.get("term")
        direction = raw_term.get("direction")
        if (
            not isinstance(word, str) or not 1 <= len(word.strip()) <= 64
            or any(ord(ch) < 32 for ch in word)
            or not all(ch.isalpha() or ch in " -_" for ch in word)
            or direction not in _RANKING_DIRECTIONS
        ):
            raise MetricSourceCompositionError("COMPOSITION_RANKING_TERM_INVALID")
        normalized = normalize_search_text(word)
        if not normalized or normalized in seen:
            raise MetricSourceCompositionError("COMPOSITION_RANKING_TERM_AMBIGUOUS")
        seen.add(normalized)
        result.append({"term": normalized, "direction": direction})
    return {
        "terms": sorted(result, key=lambda v:v["term"]),
        "default_limit": default_limit,
        "maximum_limit": maximum_limit,
    }


def _select_ranking(
    policy: object,
    normalized_question: str,
    *,
    has_group: bool,
) -> dict[str, Any] | None:
    if policy is None:
        return None
    if not isinstance(policy, Mapping) or not isinstance(normalized_question, str):
        raise MetricSourceCompositionError("COMPOSITION_RANKING_INVALID")
    # Normalization removes minus/plus signs. Reject signed quantities before
    # normalization instead of silently treating "-5" as a valid "5".
    if re.search(r"(?<!\w)[+-]\s*[0-9]", normalized_question):
        raise MetricSourceCompositionError("COMPOSITION_RANKING_SIGNED_NUMBER_UNBOUND")
    question = normalize_search_text(normalized_question)
    matches = []
    for entry in policy["terms"]:
        term = entry["term"]
        for match in re.finditer(
            r"(?<!\w)" + re.escape(term) + r"(?!\w)", question
        ):
            matches.append((match, entry))
    if not matches:
        return None
    if len(matches) != 1:
        raise MetricSourceCompositionError("COMPOSITION_RANKING_AMBIGUOUS")
    if not has_group:
        raise MetricSourceCompositionError("COMPOSITION_RANKING_NO_GROUP")
    match, entry = matches[0]
    remainder = question[match.end():]
    specified = re.match(r"\s+([0-9]+)", remainder)
    if specified and (
        len(specified.group(1)) > 5
        or re.match(r"\s+[0-9]+", remainder[specified.end():])
    ):
        raise MetricSourceCompositionError("COMPOSITION_RANKING_LIMIT_UNBOUND")
    limit = int(specified.group(1)) if specified else policy["default_limit"]
    if not 1 <= limit <= policy["maximum_limit"]:
        raise MetricSourceCompositionError("COMPOSITION_RANKING_LIMIT_EXCEEDED")
    return {
        "direction": entry["direction"],
        "limit": limit,
        "maximum_limit": policy["maximum_limit"],
        "source_use": _PROVENANCE,
    }


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
        if (
            not isinstance(raw_item, Mapping)
            or not _COMPOSITION_KEYS <= set(raw_item)
            or set(raw_item) - _COMPOSITION_KEYS - {"temporal", "calculation", "ranking"}
        ):
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
            numeric_col = next((
                col for col in declared_columns
                if isinstance(col, Mapping)
                and str(col.get("name", "")).casefold() == value_column.casefold()
            ), None)
            if (
                not isinstance(numeric_col, Mapping)
                or str(numeric_col.get("data_type", "")).casefold()
                not in _NUMERIC_TYPES
            ):
                raise MetricSourceCompositionError("COMPOSITION_METRIC_TYPE_UNSAFE")
            declared_grain = table.get("grain")
            if (
                not isinstance(declared_grain, Mapping)
                or declared_grain.get("grain_ref") != grain
            ):
                raise MetricSourceCompositionError("COMPOSITION_GRAIN_UNATTESTED")
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
        temporal = None
        if "temporal" in raw_item:
            temporal = _normalize_composition_temporal(
                raw_item["temporal"], sources, table_index
            )
        calculation = None
        if "calculation" in raw_item:
            calculation = _approved_source_calculation(
                raw_item["calculation"],
                {source["source_ref"].casefold() for source in sources},
            )
        ranking = None
        if "ranking" in raw_item:
            ranking = _normalize_ranking_policy(raw_item["ranking"])
        output.append({
            **({"ranking": ranking} if ranking is not None else {}),
            **({"calculation": calculation} if calculation is not None else {}),
            **({"temporal": temporal} if temporal is not None else {}),
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
    normalized_question: str = "",
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
    temporal_grouping = _select_composition_temporal(
        source.get("temporal"), normalized_question
    )
    result_ranking = _select_ranking(
        source.get("ranking"), normalized_question,
        has_group=bool(selected) or temporal_grouping is not None,
    )
    return {
        **({"result_ranking": result_ranking} if result_ranking is not None else {}),
        **(
            {"calculation": deepcopy(source["calculation"])}
            if "calculation" in source else {}
        ),
        **(
            {"temporal_grouping": temporal_grouping}
            if temporal_grouping is not None else {}
        ),
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


def validate_projected_metric_composition(
    value: object,
    *,
    authorized_tables: list[Mapping[str, Any]],
    catalog_columns: Mapping[str, Any],
) -> dict[str, Any]:
    """Second, pre-provider boundary: reject altered plans and missing ACL."""
    expected = {
        "composition_ref", "metric_ref", "strategy", "source_use",
        "sources", "grouping_dimensions",
    }
    if (
        not isinstance(value, Mapping)
        or not expected <= set(value)
        or set(value) - expected - {"temporal_grouping", "calculation", "result_ranking"}
    ):
        raise MetricSourceCompositionError("COMPOSITION_PROVIDER_CONTRACT_INVALID")
    if (
        not _valid_ref(value.get("composition_ref"))
        or not _valid_ref(value.get("metric_ref"))
        or value.get("strategy") != _STRATEGY
        or value.get("source_use") != _PROVENANCE
    ):
        raise MetricSourceCompositionError("COMPOSITION_PROVIDER_UNAPPROVED")
    sources = value.get("sources")
    dimensions = value.get("grouping_dimensions")
    if (
        not isinstance(sources, list)
        or not 2 <= len(sources) <= 24
        or not isinstance(dimensions, list)
        or len(dimensions) > 32
    ):
        raise MetricSourceCompositionError("COMPOSITION_PROVIDER_SOURCES_INVALID")
    allowed = {
        str(table.get("qualified_name", "")).casefold()
        for table in authorized_tables if isinstance(table, Mapping)
    }
    table_index = {
        str(item.get("qualified_name", "")).casefold(): item
        for item in authorized_tables if isinstance(item, Mapping)
    }
    unique_refs: set[str] = set()
    ref_to_table: dict[str, str] = {}
    for source in sources:
        if not isinstance(source, Mapping) or set(source) != (
            _SOURCE_KEYS - {"dimension_columns"}
        ):
            raise MetricSourceCompositionError("COMPOSITION_PROVIDER_SOURCE_INVALID")
        ref = source.get("source_ref")
        table = source.get("target_table")
        col = source.get("value_column")
        if (
            not _valid_ref(ref)
            or ref.casefold() in unique_refs
            or not isinstance(table, str)
            or table.casefold() not in allowed
            or not _valid_column(col)
            or not _valid_ref(source.get("grain_ref"))
            or type(source.get("sign_multiplier")) is not int
            or source["sign_multiplier"] not in (-1, 1)
        ):
            raise MetricSourceCompositionError("COMPOSITION_PROVIDER_BINDING_INVALID")
        unique_refs.add(ref.casefold())
        ref_to_table[ref.casefold()] = table.casefold()
        visible = {
            str(item.get("name", "")).casefold()
            for item in catalog_columns.get(table, [])
            if isinstance(item, Mapping)
        }
        if col.casefold() not in visible:
            raise MetricSourceCompositionError("COMPOSITION_PROVIDER_COLUMN_UNAUTHORIZED")
        declared = table_index.get(table.casefold(), {})
        declared_measures = declared.get("metric_columns", [])
        declared_grain = declared.get("grain")
        if (
            not isinstance(declared_measures, list)
            or col.casefold() not in {
                str(item).casefold() for item in declared_measures
            }
            or not isinstance(declared_grain, Mapping)
            or declared_grain.get("grain_ref") != source["grain_ref"]
        ):
            raise MetricSourceCompositionError("COMPOSITION_PROVIDER_GRAIN_OR_METRIC_UNAUTHORIZED")
        column_definitions = catalog_columns.get(table, [])
        if (
            not isinstance(column_definitions, list)
            or not any(
                isinstance(item, Mapping)
                and str(item.get("name", "")).casefold() == col.casefold()
                and str(item.get("data_type", "")).casefold()
                in _NUMERIC_TYPES
                for item in column_definitions
            )
        ):
            raise MetricSourceCompositionError("COMPOSITION_PROVIDER_METRIC_TYPE_INVALID")
        filters = source.get("source_filters")
        if not isinstance(filters, list) or len(filters) > 32:
            raise MetricSourceCompositionError("COMPOSITION_PROVIDER_FILTERS_INVALID")
        for predicate in filters:
            _source_filter(predicate, visible)
    if "calculation" in value:
        approved_calculation = _approved_source_calculation(
            value["calculation"], unique_refs,
        )
        if value["calculation"] != approved_calculation:
            raise MetricSourceCompositionError("COMPOSITION_CALCULATION_NOT_CANONICAL")
    if "result_ranking" in value:
        ranking = value["result_ranking"]
        if (
            not isinstance(ranking, Mapping)
            or set(ranking) != {"direction", "limit", "maximum_limit", "source_use"}
            or ranking.get("direction") not in _RANKING_DIRECTIONS
            or ranking.get("source_use") != _PROVENANCE
            or type(ranking.get("limit")) is not int
            or type(ranking.get("maximum_limit")) is not int
            or not 1 <= ranking["limit"] <= ranking["maximum_limit"] <= _RANKING_OPERATIONAL_CEILING
            or (not dimensions and "temporal_grouping" not in value)
        ):
            raise MetricSourceCompositionError("COMPOSITION_PROVIDER_RANKING_INVALID")
    if len(set(ref_to_table.values())) != len(ref_to_table):
        raise MetricSourceCompositionError("COMPOSITION_PROVIDER_DUPLICATE_FACT")
    seen_dims: set[str] = set()
    for dimension in dimensions:
        if not isinstance(dimension, Mapping) or set(dimension) != {
            "canonical_value", "source_bindings",
        }:
            raise MetricSourceCompositionError("COMPOSITION_PROVIDER_GROUPING_INVALID")
        concept = dimension.get("canonical_value")
        if not _valid_ref(concept) or concept.casefold() in seen_dims:
            raise MetricSourceCompositionError("COMPOSITION_PROVIDER_GROUPING_AMBIGUOUS")
        seen_dims.add(concept.casefold())
        bindings = dimension.get("source_bindings")
        if not isinstance(bindings, list) or len(bindings) != len(sources):
            raise MetricSourceCompositionError("COMPOSITION_PROVIDER_GROUPING_INCOMPLETE")
        present: set[str] = set()
        for binding in bindings:
            if not isinstance(binding, Mapping) or set(binding) != {
                "source_ref", "target_table", "target_column",
            }:
                raise MetricSourceCompositionError("COMPOSITION_PROVIDER_GROUPING_INVALID")
            ref = binding.get("source_ref")
            table = binding.get("target_table")
            col = binding.get("target_column")
            if (
                not _valid_ref(ref)
                or ref.casefold() not in ref_to_table
                or ref.casefold() in present
                or not isinstance(table, str)
                or table.casefold() != ref_to_table[ref.casefold()]
                or not _valid_column(col)
            ):
                raise MetricSourceCompositionError("COMPOSITION_PROVIDER_GROUPING_INVALID")
            present.add(ref.casefold())
            visible = {
                str(item.get("name", "")).casefold()
                for item in catalog_columns.get(table, [])
                if isinstance(item, Mapping)
            }
            if col.casefold() not in visible:
                raise MetricSourceCompositionError(
                    "COMPOSITION_PROVIDER_GROUP_COLUMN_UNAUTHORIZED"
                )
        if present != unique_refs:
            raise MetricSourceCompositionError("COMPOSITION_PROVIDER_GROUPING_INCOMPLETE")
    if "temporal_grouping" in value:
        temporal = value["temporal_grouping"]
        if (
            not isinstance(temporal, Mapping)
            or not {"grain", "source_bindings"} <= set(temporal)
            or set(temporal) - {"grain", "source_bindings", "period_year", "period_year_range"}
            or (
                "period_year" in temporal and (
                    type(temporal["period_year"]) is not int
                    or not 1 <= temporal["period_year"] <= 9998
                )
            )
            or ("period_year" in temporal and "period_year_range" in temporal)
            or (
                "period_year_range" in temporal and (
                    not isinstance(temporal["period_year_range"], Mapping)
                    or set(temporal["period_year_range"]) != {"start_year", "end_year"}
                    or type(temporal["period_year_range"].get("start_year")) is not int
                    or type(temporal["period_year_range"].get("end_year")) is not int
                    or not 1 <= temporal["period_year_range"]["start_year"]
                    <= temporal["period_year_range"]["end_year"] <= 9998
                    or (
                        temporal["period_year_range"]["end_year"]
                        - temporal["period_year_range"]["start_year"] + 1
                    ) > 100
                )
            )
            or temporal.get("grain") not in _TEMPORAL_GRAINS
            or not isinstance(temporal.get("source_bindings"), list)
            or len(temporal["source_bindings"]) != len(sources)
        ):
            raise MetricSourceCompositionError("COMPOSITION_PROVIDER_TEMPORAL_INVALID")
        dates: set[str] = set()
        allowed_by_table = {
            str(table.get("qualified_name", "")).casefold(): table
            for table in authorized_tables if isinstance(table, Mapping)
        }
        for binding in temporal["source_bindings"]:
            if not isinstance(binding, Mapping) or set(binding) != {
                "source_ref", "target_table", "target_column"
            }:
                raise MetricSourceCompositionError("COMPOSITION_PROVIDER_DATE_INVALID")
            ref = binding.get("source_ref")
            table = binding.get("target_table")
            col = binding.get("target_column")
            if (
                not _valid_ref(ref)
                or ref.casefold() not in ref_to_table
                or ref.casefold() in dates
                or not isinstance(table, str)
                or table.casefold() != ref_to_table[ref.casefold()]
                or not _valid_column(col)
            ):
                raise MetricSourceCompositionError("COMPOSITION_PROVIDER_DATE_INVALID")
            dates.add(ref.casefold())
            declared = allowed_by_table.get(table.casefold(), {})
            date_fields = declared.get("date_columns", [])
            if not isinstance(date_fields, list) or col.casefold() not in {
                str(item if isinstance(item, str) else item.get("name", "")).casefold()
                for item in date_fields
                if isinstance(item, (str, Mapping))
            }:
                raise MetricSourceCompositionError("COMPOSITION_PROVIDER_DATE_NOT_CATALOGED")
            columns = catalog_columns.get(table, [])
            if not isinstance(columns, list) or not any(
                isinstance(item, Mapping)
                and str(item.get("name", "")).casefold() == col.casefold()
                and str(item.get("data_type", "")).casefold() == "date"
                for item in columns
            ):
                raise MetricSourceCompositionError("COMPOSITION_PROVIDER_DATE_TYPE_INVALID")
        if dates != unique_refs:
            raise MetricSourceCompositionError("COMPOSITION_PROVIDER_DATES_INCOMPLETE")
    return deepcopy(dict(value))




def _normalize_calendar_range_policy(raw: object) -> dict[str, Any]:
    """Accept only explicit, versioned calendar-range language and safety bounds."""
    if (
        not isinstance(raw, Mapping)
        or set(raw) != {"calendar_range_attested", "max_span_years", "phrases"}
        or raw["calendar_range_attested"] is not True
        or type(raw["max_span_years"]) is not int
        or not 1 <= raw["max_span_years"] <= 100
        or not isinstance(raw["phrases"], list)
        or not 1 <= len(raw["phrases"]) <= 16
    ):
        raise MetricSourceCompositionError("COMPOSITION_YEAR_RANGE_POLICY_INVALID")
    phrases = []
    unique = set()
    for item in raw["phrases"]:
        if not isinstance(item, Mapping) or set(item) != {"prefix", "separator"}:
            raise MetricSourceCompositionError("COMPOSITION_YEAR_RANGE_PHRASE_INVALID")
        tokens = []
        for key in ("prefix", "separator"):
            value = item[key]
            if (
                not isinstance(value, str) or not value.strip() or len(value) > 80
                or any(ord(char) < 32 for char in value)
            ):
                raise MetricSourceCompositionError("COMPOSITION_YEAR_RANGE_PHRASE_INVALID")
            normalized = normalize_search_text(value)
            if (
                not normalized or len(normalized.split()) > 6
                or not all(char.isalpha() or char == " " for char in normalized)
            ):
                raise MetricSourceCompositionError("COMPOSITION_YEAR_RANGE_PHRASE_INVALID")
            tokens.append(normalized)
        pair = tuple(tokens)
        if pair in unique:
            raise MetricSourceCompositionError("COMPOSITION_YEAR_RANGE_PHRASE_DUPLICATED")
        unique.add(pair)
        phrases.append({"prefix": pair[0], "separator": pair[1]})
    return {
        "calendar_range_attested": True,
        "max_span_years": raw["max_span_years"],
        "phrases": sorted(phrases, key=lambda x: (x["prefix"], x["separator"])),
    }

def _normalize_composition_temporal(
    raw: object,
    sources: list[dict[str, Any]],
    table_index: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Bind all calendar dates to the catalog; refuse implicit timezone casts."""
    if (
        not isinstance(raw, Mapping)
        or not _TEMPORAL_KEYS <= set(raw)
        or set(raw) - _TEMPORAL_KEYS - _TEMPORAL_OPTIONAL_KEYS
    ):
        raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_INVALID")
    if type(raw.get("require_explicit_grain")) is not bool:
        raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_REQUIRED_FLAG_INVALID")
    raw_grains = raw.get("granularities")
    if not isinstance(raw_grains, list) or not 1 <= len(raw_grains) <= 5:
        raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_GRAINS_INVALID")
    seen_grains: set[str] = set()
    term_to_grain: dict[str, str] = {}
    grains = []
    for item in raw_grains:
        if not isinstance(item, Mapping) or set(item) != {"grain", "terms"}:
            raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_GRAIN_INVALID")
        grain, terms = item["grain"], item["terms"]
        if (
            grain not in _TEMPORAL_GRAINS
            or grain in seen_grains
            or not isinstance(terms, list)
            or not 1 <= len(terms) <= 32
        ):
            raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_GRAIN_INVALID")
        seen_grains.add(grain)
        normalized_terms = []
        for term in terms:
            if not isinstance(term, str) or not term.strip() or len(term) > 80:
                raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_TERM_INVALID")
            if any(ord(c) < 32 for c in term):
                raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_TERM_INVALID")
            normalized = normalize_search_text(term)
            if (
                not normalized
                or normalized in term_to_grain
            ):
                raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_TERM_AMBIGUOUS")
            term_to_grain[normalized] = grain
            normalized_terms.append(normalized)
        grains.append({
            "grain": grain,
            "terms": sorted(normalized_terms),
        })
    period_year = None
    if "period_year" in raw:
        year_policy = raw["period_year"]
        if (
            not isinstance(year_policy, Mapping)
            or set(year_policy) != {
                "calendar_year_attested", "allow_bare_year",
                "require_year", "year_terms"
            }
            or year_policy["calendar_year_attested"] is not True
            or type(year_policy["allow_bare_year"]) is not bool
            or type(year_policy["require_year"]) is not bool
            or not isinstance(year_policy["year_terms"], list)
            or not 1 <= len(year_policy["year_terms"]) <= 32
        ):
            raise MetricSourceCompositionError("COMPOSITION_YEAR_POLICY_INVALID")
        prefixes = set()
        for item in year_policy["year_terms"]:
            if (
                not isinstance(item, str)
                or not item.strip()
                or len(item) > 80
                or any(ord(char) < 32 for char in item)
            ):
                raise MetricSourceCompositionError("COMPOSITION_YEAR_TERM_INVALID")
            normalized = normalize_search_text(item)
            if not normalized or normalized in prefixes:
                raise MetricSourceCompositionError("COMPOSITION_YEAR_TERM_INVALID")
            prefixes.add(normalized)
        period_year = {
            "calendar_year_attested": True,
            "allow_bare_year": year_policy["allow_bare_year"],
            "require_year": year_policy["require_year"],
            "year_terms": sorted(prefixes),
        }
    year_range = None
    if "period_year_range" in raw:
        year_range = _normalize_calendar_range_policy(raw["period_year_range"])
    raw_periods = raw.get("unhandled_period_terms", [])
    if not isinstance(raw_periods, list) or len(raw_periods) > 64:
        raise MetricSourceCompositionError("COMPOSITION_UNHANDLED_PERIODS_INVALID")
    period_terms = set()
    for raw_term in raw_periods:
        if (
            not isinstance(raw_term, str)
            or not raw_term.strip()
            or len(raw_term) > 80
            or any(ord(ch) < 32 for ch in raw_term)
        ):
            raise MetricSourceCompositionError("COMPOSITION_UNHANDLED_PERIOD_INVALID")
        term = normalize_search_text(raw_term)
        if (
            not term or term in period_terms or term in term_to_grain
            or (
                year_range is not None
                and term in {p["prefix"] for p in year_range["phrases"]}
            )
        ):
            raise MetricSourceCompositionError("COMPOSITION_UNHANDLED_PERIOD_AMBIGUOUS")
        period_terms.add(term)
    bindings = raw.get("source_dates")
    if not isinstance(bindings, list) or len(bindings) != len(sources):
        raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_DATES_INCOMPLETE")
    by_ref = {source["source_ref"].casefold(): source for source in sources}
    seen_refs: set[str] = set()
    parsed = []
    for binding in bindings:
        if not isinstance(binding, Mapping) or set(binding) != {
            "source_ref", "target_column"
        }:
            raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_DATE_INVALID")
        ref, col = binding["source_ref"], binding["target_column"]
        if (
            not _valid_ref(ref)
            or ref.casefold() not in by_ref
            or ref.casefold() in seen_refs
            or not _valid_column(col)
        ):
            raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_DATE_INVALID")
        seen_refs.add(ref.casefold())
        fact = by_ref[ref.casefold()]
        table = table_index[fact["target_table"].casefold()]
        date_fields = table.get("date_columns", [])
        if not isinstance(date_fields, list) or col.casefold() not in {
            str(item if isinstance(item, str) else item.get("name", "")).casefold()
            for item in date_fields if isinstance(item, (str, Mapping))
        }:
            raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_DATE_NOT_ALLOWED")
        metadata = table.get("columns", [])
        # Only DATE is accepted until tenant timezone/coercion semantics
        # are explicitly validated. TIMESTAMPTZ would change months by zone.
        if not isinstance(metadata, list) or not any(
            isinstance(item, Mapping)
            and str(item.get("name", "")).casefold() == col.casefold()
            and str(item.get("data_type", "")).casefold() == "date"
            for item in metadata
        ):
            raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_DATE_TYPE_INVALID")
        parsed.append({
            "source_ref": fact["source_ref"],
            "target_table": fact["target_table"],
            "target_column": col,
        })
    if seen_refs != set(by_ref):
        raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_DATES_INCOMPLETE")
    return {
        "require_explicit_grain": raw["require_explicit_grain"],
        "granularities": sorted(grains, key=lambda x: x["grain"]),
        "source_dates": sorted(parsed, key=lambda x: x["source_ref"].casefold()),
        "unhandled_period_terms": sorted(period_terms),
        **({"period_year": period_year} if period_year is not None else {}),
        **({"period_year_range": year_range} if year_range is not None else {}),
    }


def _select_composition_temporal(
    temporal: object, question: str,
) -> dict[str, Any] | None:
    if temporal is None:
        return None
    if not isinstance(temporal, Mapping) or not isinstance(question, str):
        raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_INVALID")
    # Normalization strips punctuation. Reject date-like text *before* that,
    # otherwise an unhandled exact date could be mistaken for its calendar year.
    if re.search(
        r"(?<!\w)(?:[0-9]{4}[-/.][0-9]{1,2}(?:[-/.][0-9]{1,2})?"
        r"|[0-9]{1,2}[-/.][0-9]{1,2}[-/.][0-9]{4})(?!\w)",
        question,
    ):
        raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_DATE_UNBOUND")
    normalized = normalize_search_text(question)
    year_pattern = r"(?<!\w)[0-9]{4}(?!\w)"
    year_hits = list(re.finditer(year_pattern, normalized))
    year = None
    year_range = None
    range_policy = temporal.get("period_year_range")
    if isinstance(range_policy, Mapping):
        matches = []
        for phrase in range_policy["phrases"]:
            pattern = (
                r"(?<!\w)" + re.escape(phrase["prefix"])
                + r"\s+([0-9]{4})\s+"
                + re.escape(phrase["separator"])
                + r"\s+([0-9]{4})(?!\w)"
            )
            matches.extend(re.finditer(pattern, normalized))
        if matches:
            # Exactly two references in one approved expression: no partial
            # consumption of a third period, another interval or nested text.
            if len(matches) != 1 or len(year_hits) != 2:
                raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_YEAR_AMBIGUOUS")
            match = matches[0]
            if any(
                not (match.start() <= hit.start() < match.end())
                for hit in year_hits
            ):
                raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_YEAR_AMBIGUOUS")
            first, last = int(match.group(1)), int(match.group(2))
            if (
                not 1 <= first <= last <= 9998
                or last - first + 1 > range_policy["max_span_years"]
            ):
                raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_YEAR_RANGE_INVALID")
            year_range = {"start_year": first, "end_year": last}
    if year_range is None:
        if len(year_hits) > 1:
            raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_YEAR_AMBIGUOUS")
        if year_hits:
            policy = temporal.get("period_year")
            year = int(year_hits[0].group())
            if (
                not isinstance(policy, Mapping)
                or policy.get("calendar_year_attested") is not True
                or not 1 <= year <= 9998
            ):
                raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_PERIOD_UNBOUND")
            if not policy["allow_bare_year"] and not any(
                re.search(
                    r"(?<!\w)" + re.escape(term) + r"\s+"
                    + str(year) + r"(?!\w)", normalized,
                )
                for term in policy["year_terms"]
            ):
                raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_YEAR_UNSCOPED")
        elif (
            isinstance(temporal.get("period_year"), Mapping)
            and temporal["period_year"]["require_year"]
        ):
            raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_YEAR_REQUIRED")
    if any(
        re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", normalized)
        for term in temporal["unhandled_period_terms"]
    ):
        raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_PERIOD_UNBOUND")
    matches = {
        item["grain"] for item in temporal["granularities"]
        if any(
            re.search(r"(?<!\w)" + re.escape(term) + r"(?!\w)", normalized)
            for term in item["terms"]
        )
    }
    if len(matches) > 1:
        raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_GRAIN_AMBIGUOUS")
    if not matches:
        if temporal["require_explicit_grain"] or year is not None or year_range is not None:
            raise MetricSourceCompositionError("COMPOSITION_TEMPORAL_GRAIN_REQUIRED")
        return None
    return {
        "grain": next(iter(matches)),
        "source_bindings": deepcopy(temporal["source_dates"]),
        **({"period_year": year} if year is not None else {}),
        **({"period_year_range": year_range} if year_range is not None else {}),
    }

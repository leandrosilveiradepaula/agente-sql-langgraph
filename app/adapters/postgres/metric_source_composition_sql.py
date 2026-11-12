"""Generate-only PostgreSQL witness for a versioned multi-source metric plan.

A small structural SQL adapter, not an LLM answer lookup. The query is built
solely from the independently validated, tenant-pinned metric composition
contract. No client table name, accounting formula, alias, category or sign
convention is embedded here. It is not wired into the official provider or
any SQL executor; security/contract gates still decide whether output is safe.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.domain.metric_source_composition import (
    MetricSourceCompositionError,
    validate_projected_metric_composition,
)

class PostgresCompositionSqlError(ValueError):
    """Do not issue a SQL string when source contracts are uncertain."""


def _ident(value: str) -> str:
    if not isinstance(value, str) or not value or (
        not (value[0].isalpha() or value[0] == "_")
        or not all(letter.isascii() and (
            letter.isalnum() or letter == "_"
        ) for letter in value)
    ):
        raise PostgresCompositionSqlError("UNSAFE_POSTGRES_IDENTIFIER")
    return '"' + value.replace('"', '""') + '"'


def _table(value: str) -> str:
    if not isinstance(value, str) or value.count(".") != 1:
        raise PostgresCompositionSqlError("INVALID_POSTGRES_QUALIFIED_TABLE")
    return ".".join(_ident(segment) for segment in value.split("."))


def _literal(value: object) -> str:
    if value is None:
        raise PostgresCompositionSqlError("NULL_LITERAL_NOT_ATTESTED")
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise PostgresCompositionSqlError("UNSAFE_NUMERIC_LITERAL")
        return repr(value)
    if isinstance(value, str):
        if any(ord(ch) < 32 for ch in value) or len(value) > 250:
            raise PostgresCompositionSqlError("UNSAFE_FILTER_LITERAL")
        return "'" + value.replace("'", "''") + "'"
    raise PostgresCompositionSqlError("UNSUPPORTED_FILTER_LITERAL")


def _predicate(entry: Mapping[str, Any], table_alias: str) -> str:
    column = _ident(table_alias) + "." + _ident(entry["column"])
    op = entry["operator"]
    if op not in ("=", "<>", "<", "<=", ">", ">=", "IN", "NOT IN"):
        raise PostgresCompositionSqlError("UNAUTHORIZED_FILTER_OPERATOR")
    value = entry["value"]
    if op in ("IN", "NOT IN"):
        if not isinstance(value, list) or not value:
            raise PostgresCompositionSqlError("UNAUTHORIZED_FILTER_VALUES")
        rendered = ", ".join(_literal(item) for item in value)
        return f"{column} {op} ({rendered})"
    return f"{column} {op} {_literal(value)}"


def build_postgres_metric_source_sql(request: Mapping[str, Any]) -> str:
    """Render a single read-only SELECT from approved physical references.

    Only one numeric measure plus requested group columns per stream.
    SUM happens after UNION ALL. Does not join two raw fact streams and does
    not invent metric definitions, missing periods, joins or source filters.
    """
    if not isinstance(request, Mapping):
        raise PostgresCompositionSqlError("GENERATION_REQUEST_INVALID")
    context = request.get("generation_context")
    if not isinstance(context, Mapping):
        raise PostgresCompositionSqlError("GENERATION_CONTEXT_INVALID")
    definition = context.get("metric_source_composition")
    if definition is None:
        raise PostgresCompositionSqlError("COMPOSITION_NOT_REQUESTED")
    try:
        value = validate_projected_metric_composition(
            definition,
            authorized_tables=context["authorized_tables"],
            catalog_columns=context["catalog_columns"],
        )
    except (KeyError, TypeError, MetricSourceCompositionError):
        raise PostgresCompositionSqlError("COMPOSITION_SOURCE_UNAUTHORIZED") from None
    dimensions = value["grouping_dimensions"]
    temporal = value.get("temporal_grouping")
    calculation = value.get("calculation")
    aliases = [f"group_{index+1}" for index in range(len(dimensions))]
    subqueries = []
    for source_index, source in enumerate(value["sources"], 1):
        table_alias = f"source_{source_index}"
        columns = []
        date_column = None
        if temporal is not None:
            date_bindings = [
                item for item in temporal["source_bindings"]
                if item["source_ref"] == source["source_ref"]
            ]
            if len(date_bindings) != 1:
                raise PostgresCompositionSqlError("DATE_NOT_BOUND")
            date_column = _ident(date_bindings[0]["target_column"])
            grain = temporal["grain"]
            if grain not in ("day", "week", "month", "quarter", "year"):
                raise PostgresCompositionSqlError("DATE_GRAIN_UNAUTHORIZED")
            columns.append(
                f'date_trunc(\'{grain}\', '
                f'{_ident(table_alias)}.{date_column}) AS "time_bucket"'
            )
        for index, dim in enumerate(dimensions):
            matching = [
                binding for binding in dim["source_bindings"]
                if binding["source_ref"] == source["source_ref"]
            ]
            if len(matching) != 1:
                raise PostgresCompositionSqlError("GROUPING_NOT_BOUND")
            columns.append(
                f'{_ident(table_alias)}.{_ident(matching[0]["target_column"])} AS {_ident(aliases[index])}'
            )
        if calculation is not None:
            columns.append(
                _literal(source["source_ref"].casefold()) + ' AS "source_ref"'
            )
        val = _ident(source["value_column"])
        multiplier = source["sign_multiplier"]
        columns.append(
            f'({_ident(table_alias)}.{val} * {multiplier}) AS "measure_value"'
        )
        subquery = (
            "SELECT " + ", ".join(columns) + "\n"
            + "FROM " + _table(source["target_table"])
            + " AS " + _ident(table_alias)
        )
        filters = source["source_filters"]
        predicates = []
        if temporal is not None and (
            "period_year" in temporal or "period_year_range" in temporal
        ):
            if date_column is None:
                raise PostgresCompositionSqlError("CALENDAR_YEAR_UNAUTHORIZED")
            if "period_year_range" in temporal:
                bounds = temporal["period_year_range"]
                start_year, end_year = bounds["start_year"], bounds["end_year"]
            else:
                start_year = end_year = temporal["period_year"]
            if (
                type(start_year) is not int or type(end_year) is not int
                or not 1 <= start_year <= end_year <= 9998
                or end_year - start_year + 1 > 100
            ):
                raise PostgresCompositionSqlError("CALENDAR_YEAR_UNAUTHORIZED")
            qualified_date = f'{_ident(table_alias)}.{date_column}'
            predicates.extend((
                f"{qualified_date} >= '{start_year:04d}-01-01'",
                f"{qualified_date} < '{end_year + 1:04d}-01-01'",
            ))
        predicates.extend(_predicate(f, table_alias) for f in filters)
        if predicates:
            subquery += "\nWHERE " + " AND ".join(predicates)
        subqueries.append(subquery)
    outer = (
        ['"time_bucket"'] if temporal is not None else []
    ) + [f'"{name}"' for name in aliases]
    if calculation is None:
        outer.append('SUM("measure_value") AS "metric_value"')
    else:
        def operand(key: str) -> str:
            refs = calculation[key]
            includes = ", ".join(_literal(ref) for ref in refs)
            return (
                'SUM(CASE WHEN "source_ref" IN (' + includes
                + ') THEN "measure_value" ELSE 0 END)'
            )
        numerator = operand("numerator_source_refs")
        denominator = operand("denominator_source_refs")
        # Both operands are summed at the requested grouping grain BEFORE
        # dividing. No row-wise ratios, and no divide-by-zero exception.
        outer.append(
            '(' + numerator + ' * ' + str(calculation["scale"])
            + ' / NULLIF(' + denominator + ', 0)) AS "metric_value"'
        )
    sql = (
        'WITH "combined_sources" AS (\n'
        + "\nUNION ALL\n".join(subqueries)
        + "\n)\nSELECT " + ", ".join(outer)
        + '\nFROM "combined_sources"'
    )
    group_aliases = (["time_bucket"] if temporal is not None else []) + aliases
    if group_aliases:
        sql += "\nGROUP BY " + ", ".join(f'"{alias}"' for alias in group_aliases)
    result_ranking = value.get("result_ranking")
    if result_ranking is not None:
        direction = "DESC" if result_ranking["direction"] == "descending" else "ASC"
        # Stable tie-breakers are derived from authorized projected grouping,
        # not arbitrary user SQL or copied business-specific ranking rules.
        ties = [f'"{alias}" ASC NULLS LAST' for alias in group_aliases]
        sql += (
            '\nORDER BY "metric_value" ' + direction + " NULLS LAST"
            + (", " + ", ".join(ties) if ties else "")
            + "\nLIMIT " + str(result_ranking["limit"])
        )
    return sql

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
    aliases = [f"group_{index+1}" for index in range(len(dimensions))]
    subqueries = []
    for source_index, source in enumerate(value["sources"], 1):
        table_alias = f"source_{source_index}"
        columns = []
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
        if filters:
            subquery += "\nWHERE " + " AND ".join(
                _predicate(f, table_alias) for f in filters
            )
        subqueries.append(subquery)
    outer = [f'"{name}"' for name in aliases]
    outer.append('SUM("measure_value") AS "metric_value"')
    sql = (
        'WITH "combined_sources" AS (\n'
        + "\nUNION ALL\n".join(subqueries)
        + "\n)\nSELECT " + ", ".join(outer)
        + '\nFROM "combined_sources"'
    )
    if aliases:
        sql += "\nGROUP BY " + ", ".join(f'"{alias}"' for alias in aliases)
    return sql

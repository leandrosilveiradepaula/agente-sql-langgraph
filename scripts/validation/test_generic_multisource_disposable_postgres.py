#!/usr/bin/env python3
"""SQL dialect and numeric witness on *disposable, synthetic* PostgreSQL only.

Never targets a tenant database, production, a financial executor, LLM or
benchmark material. The tested SQL is generated from novel questions and
versioned synthetic semantic catalogs, not stored expected SQL.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
from copy import deepcopy
from decimal import Decimal

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.errors import InsufficientPrivilege

from app.adapters.postgres.metric_source_composition_sql import (
    build_postgres_metric_source_sql,
)
from app.domain.metric_source_composition import project_metric_source_composition
from app.domain.sql_contract import run_sql_contract_gate
from app.domain.sql_generation import build_sql_generation_request
from app.domain.sql_security import run_sql_security_gate
from testar_metric_source_composition_e2e import (
    _plan, fixture_a, fixture_b, fixture_calendar_range, fixture_attested_ratio,
)

EXPECTED_ENV = {
    "CI": "true",
    "GITHUB_ACTIONS": "true",
    "COMPOSITION_DISPOSABLE_POSTGRES_TEST": "true",
    "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "false",
    "PGHOST": "127.0.0.1",
    "PGPORT": "5432",
    "PGDATABASE": "synthetic_ci",
    "PGUSER": "synthetic_ci",
}


def _guard() -> str:
    if any(os.environ.get(key) != value for key, value in EXPECTED_ENV.items()):
        raise RuntimeError("COMPOSITION_DISPOSABLE_POSTGRES_ONLY")
    if not os.environ.get("PGPASSWORD"):
        raise RuntimeError("COMPOSITION_TEST_CREDENTIAL_MISSING")
    return make_conninfo(
        "", host=EXPECTED_ENV["PGHOST"], port=EXPECTED_ENV["PGPORT"],
        dbname=EXPECTED_ENV["PGDATABASE"], user=EXPECTED_ENV["PGUSER"],
        connect_timeout=5,
    )


def _query(raw: dict, question: str, *, grouped: bool = False) -> str:
    snapshot, result = _plan(raw, question)
    assert result["status"] == "planned", result.get("error_code")
    plan = deepcopy(result["query_plan"])
    assert snapshot["fingerprint"]
    if grouped:
        context = plan["planning_context"]
        first = raw["metric_source_compositions"][0]["sources"][0]
        dimension = {
            "canonical_value": "region",
            "target_table": first["target_table"],
            "target_column": "zone_code",
            "grouping_requested": True,
            "source": "semantic_alias",
        }
        context["detected_dimensions"] = [dimension]
        context["metric_source_composition"] = project_metric_source_composition(
            definitions=snapshot["metric_source_compositions"],
            intent_name="synthetic_intent",
            required_tables=context["required_tables"],
            detected_dimensions=[dimension],
            planned_metrics=[], planned_filters=[],
            analytical_operations=[], temporal_series=None,
            normalized_question=question,
        )
    generated = build_postgres_metric_source_sql(
        build_sql_generation_request(plan)
    )
    security, analysis = run_sql_security_gate(
        current_sql=generated, query_plan=plan,
    )
    contract, _ = run_sql_contract_gate(
        current_sql=generated, query_plan=plan, analysis=analysis,
    )
    assert security["status"] == "approved", security["errors"]
    assert contract["status"] == "approved", contract["errors"]
    return generated


def _create_fixture(conn: psycopg.Connection, raw: dict, role: str) -> None:
    sources = raw["metric_source_compositions"][0]["sources"]
    dates = {
        item["source_ref"]: item["target_column"]
        for item in raw["metric_source_compositions"][0]["temporal"]["source_dates"]
    }
    schema = sources[0]["target_table"].split(".")[0]
    with conn.cursor() as cur:
        cur.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        cur.execute(sql.SQL("CREATE ROLE {} NOLOGIN").format(sql.Identifier(role)))
        cur.execute(
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                sql.Identifier(schema), sql.Identifier(role)
            )
        )
        for source in sources:
            fact_schema, table = source["target_table"].split(".")
            assert fact_schema == schema
            measure, day = source["value_column"], dates[source["source_ref"]]
            cur.execute(
                sql.SQL(
                    "CREATE TABLE {}.{} ({} NUMERIC, zone_code TEXT, "
                    "flag TEXT, {} DATE)"
                ).format(
                    sql.Identifier(schema), sql.Identifier(table),
                    sql.Identifier(measure), sql.Identifier(day),
                )
            )
            cur.execute(
                sql.SQL("GRANT SELECT ON {}.{} TO {}").format(
                    sql.Identifier(schema), sql.Identifier(table),
                    sql.Identifier(role),
                )
            )
            positive = source["sign_multiplier"] == 1
            rows = [
                (1000 if positive else 100, "north", "approved", "2024-05-01"),
                (130 if positive else 30, "north", "approved", "2025-02-09"),
                (40 if positive else 15, "north", "approved", "2025-08-10"),
                (80 if positive else 10, "north", "approved", "2026-01-08"),
                (15 if positive else 5, "north", "approved", "2026-02-05"),
                (11 if positive else 3, "west",
                 "approved" if positive else "verified", "2026-01-12"),
                (1000 if positive else 100, "north", "approved", "2027-01-05"),
                (999, "north", "blocked", "2026-01-25"),
            ]
            cur.executemany(
                sql.SQL("INSERT INTO {}.{} ({}, zone_code, flag, {}) "
                        "VALUES (%s, %s, %s, %s)").format(
                    sql.Identifier(schema), sql.Identifier(table),
                    sql.Identifier(measure), sql.Identifier(day),
                ),
                rows,
            )


def _readonly_query(conn: psycopg.Connection, role: str, generated: str):
    # This is a separate SELECT-only role; it cannot create/write even if
    # a regression accidentally sends another statement.
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
        try:
            cur.execute("BEGIN READ ONLY")
            try:
                cur.execute(generated)
                return cur.fetchall()
            finally:
                cur.execute("ROLLBACK")
        finally:
            cur.execute("RESET ROLE")


def _forbidden_cross_tenant(
    conn: psycopg.Connection, role: str, other_tenant_sql: str
) -> None:
    with conn.cursor() as cur:
        cur.execute(sql.SQL("SET ROLE {}").format(sql.Identifier(role)))
        try:
            cur.execute("BEGIN READ ONLY")
            try:
                try:
                    cur.execute(other_tenant_sql)
                except InsufficientPrivilege:
                    pass
                else:
                    raise AssertionError("CROSS_TENANT_PHYSICAL_ACL_MISSING")
            finally:
                cur.execute("ROLLBACK")
        finally:
            cur.execute("RESET ROLE")


def _actual(rows) -> list[tuple[str, Decimal]]:
    return sorted((str(record[0].date()), record[-1]) for record in rows)


def main() -> None:
    dsn = _guard()
    first, second = fixture_calendar_range(fixture_a()), fixture_calendar_range(fixture_b())
    cases = (("ci_reader_test_a", first), ("ci_reader_test_b", second))
    # All tables/roles live in the CI service database, which is discarded
    # after the job; neither project databases nor human finance SQL are used.
    with psycopg.connect(dsn) as setup:
        for role, raw in cases:
            _create_fixture(setup, raw, role)
    queries = []
    with psycopg.connect(dsn, autocommit=True) as connection:
        for role, raw in cases:
            monthly = _query(raw, "synthetic report monthly between 2025 and 2026")
            annual = _query(raw, "synthetic report per year in 2026")
            grouped = _query(raw, "synthetic report monthly between 2025 and 2026", grouped=True)
            assert _actual(_readonly_query(connection, role, monthly)) == [
                ("2025-02-01", Decimal(100)),
                ("2025-08-01", Decimal(25)),
                ("2026-01-01", Decimal(78)),
                ("2026-02-01", Decimal(10)),
            ]
            assert _actual(_readonly_query(connection, role, annual)) == [
                ("2026-01-01", Decimal(88))
            ]
            grouped_rows = sorted(
                (str(day.date()), region, value)
                for day, region, value
                in _readonly_query(connection, role, grouped)
            )
            assert grouped_rows == [
                ("2025-02-01", "north", Decimal(100)),
                ("2025-08-01", "north", Decimal(25)),
                ("2026-01-01", "north", Decimal(70)),
                ("2026-01-01", "west", Decimal(8)),
                ("2026-02-01", "north", Decimal(10)),
            ], grouped_rows
            ratio_sql = _query(
                fixture_attested_ratio(raw),
                "synthetic report monthly between 2025 and 2026",
            )
            ratio_rows = _actual(_readonly_query(connection, role, ratio_sql))
            assert [row[0] for row in ratio_rows] == [
                "2025-02-01", "2025-08-01", "2026-01-01", "2026-02-01"
            ]
            # Assert aggregates-before-divide, not a mean of row ratios.
            assert [
                (value.quantize(Decimal("0.001")))
                for _, value in ratio_rows
            ] == [
                Decimal("76.923"), Decimal("62.500"),
                Decimal("85.714"), Decimal("66.667"),
            ], ratio_rows
            # Deliberately introduce a group containing only a denominator-
            # absent stream in this disposable database. A missing approved
            # denominator must be NULL, never a fabricated zero or infinity.
            other = raw["metric_source_compositions"][0]["sources"][1]
            date_binding = next(
                item["target_column"]
                for item in raw["metric_source_compositions"][0]["temporal"]["source_dates"]
                if item["source_ref"] == other["source_ref"]
            )
            schema, table = other["target_table"].split(".")
            with psycopg.connect(dsn) as privileged:
                with privileged.cursor() as cur:
                    cur.execute(
                        sql.SQL(
                            "INSERT INTO {}.{} ({}, zone_code, flag, {}) "
                            "VALUES (%s, %s, %s, %s)"
                        ).format(
                            sql.Identifier(schema), sql.Identifier(table),
                            sql.Identifier(other["value_column"]),
                            sql.Identifier(date_binding),
                        ),
                        (20, "denominator_absent", "approved", "2026-03-05"),
                    )
            grouped_ratio_sql = _query(
                fixture_attested_ratio(raw),
                "synthetic report monthly between 2025 and 2026",
                grouped=True,
            )
            guarded_rows = _readonly_query(
                connection, role, grouped_ratio_sql
            )
            assert [
                row for row in guarded_rows
                if row[1] == "denominator_absent"
            ][0][-1] is None
            queries.append((role, monthly))
        assert queries[0][1] != queries[1][1]
        _forbidden_cross_tenant(connection, queries[0][0], queries[1][1])
        _forbidden_cross_tenant(connection, queries[1][0], queries[0][1])
    print("DISPOSABLE_POSTGRES_COMPOSITION=PASS")
    print("TENANT_CONTEXTS=2")
    print("READONLY_GENERATED_SELECTS=10")
    print("ZERO_DENOMINATOR_RETURNS_NULL=PASS")
    print("ATTESTED_GENERIC_RATIO_OF_SUMS=PASS")
    print("CROSS_TENANT_ACL_REJECTIONS=2")
    print("CUSTOMER_FINANCIAL_SQL_EXECUTED=false")


if __name__ == "__main__":
    main()

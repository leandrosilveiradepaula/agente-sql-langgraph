"""Onboarding metadata reader: real PostgreSQL SQL shape, fake driver."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.adapters.postgres.physical_catalog_reader import (
    PhysicalCatalogReadError,
    PostgresPhysicalCatalogReader,
)

DSN = "postgresql://invalid.test/schema_only"


class FakeCursor:
    def __init__(self, rows: Any) -> None:
        self.rows = rows
        self.executed: list[tuple[str, Any]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def execute(self, query: str, params: Any = None) -> None:
        self.executed.append((query, deepcopy(params)))

    def fetchall(self) -> Any:
        return deepcopy(self.rows)


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, *args: object) -> bool:
        return False

    def cursor(self) -> FakeCursor:
        return self._cursor


class FakeConnect:
    def __init__(self, rows: Any) -> None:
        self.cursor = FakeCursor(rows)
        self.calls = 0

    def __call__(self, dsn: str, **kwargs: Any) -> FakeConnection:
        self.calls += 1
        assert dsn == DSN
        return FakeConnection(self.cursor)


def make_rows(schema: str, table: str, columns: list[str]) -> list[dict]:
    return [
        {
            "table_schema": schema,
            "table_name": table,
            "column_name": col,
        }
        for col in columns
    ]


def test_same_reader_contract_for_unrelated_schemas() -> None:
    for schema, table, columns in [
        ("ledger_private", "journal_entries", ["pk", "minor_amount", "at"]),
        ("ops_scope", "activity_facts", ["row_id", "unit_count", "date_key"]),
    ]:
        fake = FakeConnect(make_rows(schema, table, columns))
        reader = PostgresPhysicalCatalogReader(
            dsn=DSN, allowed_schemas=[schema], connect=fake
        )
        result = reader.inspect()
        assert result == [{
            "schema_name": schema,
            "table_name": table,
            "columns": sorted(columns),
        }]
        assert fake.calls == 1
        assert fake.cursor.executed[0][0] == "SET TRANSACTION READ ONLY"
        select_sql, params = fake.cursor.executed[1]
        assert select_sql.lstrip().startswith("SELECT ")
        assert "information_schema.columns" in select_sql
        assert "ANY(%(allowed_schemas)s::text[])" in select_sql
        assert params == {"allowed_schemas": [schema]}
        assert table not in select_sql
        assert schema not in select_sql


def test_authorization_is_not_inferred_from_user_question() -> None:
    for schemas in (
        [], ["pg_catalog"], ["information_schema"], ["public.foo"],
        ["public", "public"], ["x;DROP"],
    ):
        fake = FakeConnect([])
        try:
            PostgresPhysicalCatalogReader(
                dsn=DSN, allowed_schemas=schemas, connect=fake
            )
        except ValueError:
            assert fake.calls == 0
        else:
            raise AssertionError(f"Unsafe schemas accepted: {schemas}")


def test_untrusted_or_duplicated_metadata_fails_closed() -> None:
    for rows in (
        [],
        make_rows("unallowed", "tab", ["col"]),
        make_rows("tenant_s", "tab", ["col"]) * 2,
        make_rows("tenant_s", "tab;DROP", ["col"]),
    ):
        fake = FakeConnect(rows)
        reader = PostgresPhysicalCatalogReader(
            dsn=DSN, allowed_schemas=["tenant_s"], connect=fake
        )
        try:
            reader.inspect()
        except PhysicalCatalogReadError:
            pass
        else:
            raise AssertionError("Untrusted metadata was accepted")


def test_preflight_pipeline_uses_inspected_physical_columns() -> None:
    from testar_tenant_semantic_readiness import candidate
    from app.domain.tenant_semantic_readiness import (
        assess_tenant_semantic_candidate,
    )
    value = candidate(tenant="first", version="v1")
    item = value["physical_catalog"][0]
    fake = FakeConnect(make_rows(
        item["schema_name"], item["table_name"], item["columns"]
    ))
    physical = PostgresPhysicalCatalogReader(
        dsn=DSN,
        allowed_schemas=[item["schema_name"]],
        connect=fake,
    ).inspect()
    value["physical_catalog"] = physical
    report = assess_tenant_semantic_candidate(**value)
    assert report["status"].startswith("PHYSICALLY_CONSISTENT")
    assert report["approved_for_sql_generation"] is False


if __name__ == "__main__":
    cases = sorted(
        (name, test) for name, test in globals().items()
        if name.startswith("test_") and callable(test)
    )
    for name, test in cases:
        test()
        print("PASS", name)
    print("TOTAL_TESTS", len(cases))

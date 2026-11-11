"""Canonical catalog selection and isolation tests; fake PostgreSQL only."""
from __future__ import annotations

from copy import deepcopy

from app.adapters.postgres.canonical_context_repository import (
    CanonicalContextRepository,
)
from app.config.postgres_context import (
    load_postgres_context_runtime_config,
    RuntimeConfigError,
)
from app.bootstrap import create_postgres_context_repository
from app.domain.context_normalizer import normalize_context_snapshot
from app.ports.context_repository import ContextRepositoryError
from testar_postgres_context_repository import (
    FakeConnect,
    _physical_snapshot,
)

DSN = "postgresql://test.invalid/semantic_catalog"


def client_raw(*, tenant: str, version: str, alternate: bool = False) -> dict:
    payload = deepcopy(_physical_snapshot())
    payload["tenant_id"] = tenant
    payload["semantic_agent_version"] = version
    payload["source_approval_status"] = "APPROVED"
    payload["historical_evaluation_sql_excluded"] = True
    if alternate:
        payload["catalogo"][0]["schema_name"] = "tenant_b_data"
        payload["catalogo"][0]["table_name"] = "delivery_fact_records"
        payload["catalogo"][0]["key_columns"] = ["delivery_row_id"]
        payload["catalogo"][0]["primary_key"] = ["delivery_row_id"]
        payload["catalogo"][0]["metric_columns"] = ["delivered_units"]
        payload["padroes"][0]["required_tables"] = [
            "tenant_b_data.delivery_fact_records"
        ]
    else:
        payload["catalogo"][0]["schema_name"] = "tenant_a_data"
        payload["catalogo"][0]["table_name"] = "settlement_values"
        payload["catalogo"][0]["key_columns"] = ["batch_id"]
        payload["catalogo"][0]["primary_key"] = ["batch_id"]
        payload["catalogo"][0]["metric_columns"] = ["amount_minor_units"]
        payload["padroes"][0]["required_tables"] = [
            "tenant_a_data.settlement_values"
        ]
    return payload


def make_repo(
    payload: dict,
    *,
    tenant: str,
    version: str,
    connect: FakeConnect | None = None,
    fingerprint: str | None = None,
) -> tuple[CanonicalContextRepository, FakeConnect]:
    fake = connect or FakeConnect(row={
        "snapshot_payload": payload, "matching_rows": 1,
    })
    pinned = fingerprint or normalize_context_snapshot(payload)["fingerprint"]
    repo = CanonicalContextRepository(
        dsn=DSN, tenant_id=tenant,
        semantic_agent_version=version,
        expected_context_fingerprint=pinned,
        context_schema="catalog_private",
        context_table="versioned_context_documents",
        connect=fake,
    )
    return repo, fake


def denied(repo: CanonicalContextRepository, code: str) -> None:
    try:
        repo.load_active_context(user_profile="user")
    except ContextRepositoryError as error:
        assert code in str(error), str(error)
    else:
        raise AssertionError("Insecure tenant context was accepted")


def test_two_materially_different_clients_same_engine() -> None:
    results = []
    for tenant, version, alternate in (
        ("tenant-one", "release-1", False),
        ("tenant-two", "release-2", True),
    ):
        payload = client_raw(
            tenant=tenant, version=version, alternate=alternate
        )
        repo, fake = make_repo(payload, tenant=tenant, version=version)
        result = repo.load_active_context(user_profile="admin")
        assert result["version"] == version
        assert result["allowed_schemas"] == [
            "tenant_b_data" if alternate else "tenant_a_data"
        ]
        assert fake.cursor.executed_parameters == {
            "tenant_id": tenant,
            "agent_version": version,
        }
        assert "tenant_b_data" not in fake.cursor.executed_query
        assert "tenant_a_data" not in fake.cursor.executed_query
        assert "WHERE tenant_id =" in fake.cursor.executed_query
        assert "is_approved = TRUE" in fake.cursor.executed_query
        results.append(result["fingerprint"])
    assert results[0] != results[1]


def test_cross_tenant_payload_rejected_even_if_database_row_matches() -> None:
    source = client_raw(tenant="not-this-one", version="release-1")
    repo, _ = make_repo(
        source, tenant="request-tenant", version="release-1",
        fingerprint=normalize_context_snapshot(source)["fingerprint"],
    )
    denied(repo, "Proveniência")


def test_cross_version_payload_rejected() -> None:
    source = client_raw(tenant="tenant-one", version="release-1")
    repo, _ = make_repo(
        source, tenant="tenant-one", version="release-2",
    )
    denied(repo, "Proveniência")


def test_unapproved_context_or_benchmark_provenance_rejected() -> None:
    for key, invalid in (
        ("source_approval_status", "PENDING"),
        ("historical_evaluation_sql_excluded", False),
    ):
        source = client_raw(tenant="tenant-one", version="release-1")
        source[key] = invalid
        repo, _ = make_repo(
            source, tenant="tenant-one", version="release-1",
        )
        denied(repo, "Proveniência")


def test_multiple_or_missing_context_versions_rejected() -> None:
    source = client_raw(tenant="tenant-one", version="release-1")
    for row in (None, {"snapshot_payload": source, "matching_rows": 2}):
        fake = FakeConnect(row=row)
        repo, _ = make_repo(
            source, tenant="tenant-one", version="release-1",
            connect=fake,
        )
        denied(repo, "Versão semântica única")


def test_modified_financial_schema_fingerprint_rejected() -> None:
    source = client_raw(tenant="tenant-one", version="release-1")
    original = normalize_context_snapshot(source)["fingerprint"]
    source["catalogo"][0]["table_name"] = "different_data"
    repo, _ = make_repo(
        source, tenant="tenant-one", version="release-1",
        fingerprint=original,
    )
    denied(repo, "Fingerprint")


def test_identifier_injection_and_missing_pin_fail_before_connection() -> None:
    source = client_raw(tenant="tenant-one", version="release-1")
    for field, value in (
        ("context_table", "versioned_context;DROP TABLE x"),
        ("context_schema", "private.other"),
        ("tenant_id", "hello there"),
    ):
        kwargs = {
            "dsn": DSN,
            "tenant_id": "tenant-one",
            "semantic_agent_version": "release-1",
            "expected_context_fingerprint": normalize_context_snapshot(source)["fingerprint"],
            "context_schema": "catalog_private",
            "context_table": "versioned_context_documents",
        }
        kwargs[field] = value
        try:
            CanonicalContextRepository(**kwargs)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Invalid {field} was accepted")
    try:
        CanonicalContextRepository(
            dsn=DSN, tenant_id="tenant-one",
            semantic_agent_version="release-1",
            expected_context_fingerprint=None,
            context_schema="catalog_private",
            context_table="versioned_context_documents",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Unpinned context was accepted")


def test_runtime_config_and_bootstrap_are_fail_closed() -> None:
    source = client_raw(tenant="tenant-one", version="release-1")
    env = {
        "POSTGRES_DSN": DSN,
        "SEMANTIC_AGENT_VERSION": "release-1",
        "POSTGRES_CONTEXT_SOURCE_MODE": "canonical_snapshot",
        "POSTGRES_CONTEXT_SCHEMA": "catalog_private",
        "POSTGRES_CANONICAL_CONTEXT_TABLE": "versioned_context_documents",
        "CONTEXT_TENANT_ID": "tenant-one",
        "SEMANTIC_CONTEXT_EXPECTED_FINGERPRINT": normalize_context_snapshot(source)["fingerprint"],
    }
    config = load_postgres_context_runtime_config(env)
    assert config.context_source_mode == "canonical_snapshot"
    assert config.tenant_id == "tenant-one"
    assert config.canonical_context_table == "versioned_context_documents"
    assert isinstance(create_postgres_context_repository(config), CanonicalContextRepository)

    for key in (
        "CONTEXT_TENANT_ID",
        "POSTGRES_CANONICAL_CONTEXT_TABLE",
        "SEMANTIC_CONTEXT_EXPECTED_FINGERPRINT",
    ):
        unsafe = dict(env)
        del unsafe[key]
        try:
            load_postgres_context_runtime_config(unsafe)
        except RuntimeConfigError:
            pass
        else:
            raise AssertionError(f"Missing {key} was accepted")

    unsafe = dict(env)
    unsafe["POSTGRES_CONTEXT_SOURCE_MODE"] = "untrusted_mode"
    try:
        load_postgres_context_runtime_config(unsafe)
    except RuntimeConfigError:
        pass
    else:
        raise AssertionError("Unknown context source accepted")


if __name__ == "__main__":
    tests = sorted(
        (name, value) for name, value in globals().items()
        if name.startswith("test_") and callable(value)
    )
    for name, test in tests:
        test()
        print("PASS", name)
    print("TOTAL_TESTS", len(tests))

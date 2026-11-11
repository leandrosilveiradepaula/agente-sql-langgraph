"""Two unrelated customer schemas and fail-closed metadata preflight."""
from __future__ import annotations

from copy import deepcopy

from app.domain.customer_context_readiness import (
    assess_customer_semantic_candidate,
)
from testar_canonical_context_repository import client_raw


def candidate(*, tenant: str, version: str, other: bool = False) -> dict:
    data = client_raw(tenant=tenant, version=version, alternate=other)
    row = data["catalogo"][0]
    return {
        "raw_context": data,
        "tenant_id": tenant,
        "semantic_version": version,
        "physical_catalog": [{
            "schema_name": row["schema_name"],
            "table_name": row["table_name"],
            "columns": sorted(set(
                row["primary_key"] + row["key_columns"] +
                row["metric_columns"] + row["date_columns"]
            )),
        }],
        "metadata_readonly_attested": True,
    }


def test_two_distinct_clients_can_pass_physical_review_without_hardcodes() -> None:
    reports = []
    for t, v, other in (
        ("first-client", "v4", False),
        ("second-client", "v9", True),
    ):
        report = assess_customer_semantic_candidate(
            **candidate(tenant=t, version=v, other=other)
        )
        assert report["status"] == (
            "PHYSICALLY_CONSISTENT_REQUIRES_BUSINESS_APPROVAL"
        )
        assert report["semantic_table_count"] == 1
        assert report["verified_semantic_tables"] == 1
        assert report["issues"] == []
        assert report["financial_meanings_attested"] is False
        assert report["approved_for_sql_generation"] is False
        assert report["approved_for_real_sql_execution"] is False
        reports.append(report)
    assert reports[0]["context_fingerprint"] != reports[1]["context_fingerprint"]


def test_unmapped_column_never_inferred_from_similar_name() -> None:
    values = candidate(tenant="first", version="v1")
    values["physical_catalog"][0]["columns"].remove("amount_minor_units")
    result = assess_customer_semantic_candidate(**values)
    assert result["status"] == "REJECTED"
    assert any(x["code"] == "PHYSICAL_COLUMN_NOT_FOUND" for x in result["issues"])
    assert "amount_minor_units" not in str(result)
    assert result["approved_for_sql_generation"] is False


def test_missing_table_fails_closed_with_no_schema_disclosure() -> None:
    values = candidate(tenant="first", version="v1")
    values["physical_catalog"][0]["table_name"] = "other_object"
    result = assess_customer_semantic_candidate(**values)
    assert result["verified_semantic_tables"] == 0
    assert result["status"] == "REJECTED"
    assert any(x["code"] == "PHYSICAL_TABLE_NOT_FOUND" for x in result["issues"])
    assert "other_object" not in str(result)


def test_duplicate_or_injected_physical_catalog_fails_closed() -> None:
    for mode in ("duplicate_table", "duplicate_column", "inject_schema"):
        values = candidate(tenant="first", version="v1")
        if mode == "duplicate_table":
            values["physical_catalog"].append(
                deepcopy(values["physical_catalog"][0])
            )
        elif mode == "duplicate_column":
            values["physical_catalog"][0]["columns"].append(
                values["physical_catalog"][0]["columns"][0]
            )
        else:
            values["physical_catalog"][0]["schema_name"] = "schema;DELETE"
        try:
            assess_customer_semantic_candidate(**values)
        except ValueError:
            pass
        else:
            raise AssertionError("Unsafe metadata was accepted")


def test_no_attestation_or_version_mismatch_fails_closed() -> None:
    for field, value in (
        ("metadata_readonly_attested", False),
        ("semantic_version", "wrong-version"),
        ("tenant_id", "other-tenant"),
    ):
        values = candidate(tenant="first", version="v1")
        values[field] = value
        try:
            assess_customer_semantic_candidate(**values)
        except ValueError:
            pass
        else:
            raise AssertionError("Untrusted provenance was accepted")


def test_dre_is_optional_to_generic_physical_review() -> None:
    values = candidate(tenant="first", version="v1")
    values["raw_context"]["dre"] = []
    result = assess_customer_semantic_candidate(**values)
    assert result["status"].startswith("PHYSICALLY_CONSISTENT")
    assert result["approved_for_sql_generation"] is False


if __name__ == "__main__":
    tests = sorted(
        (name, value) for name, value in globals().items()
        if name.startswith("test_") and callable(value)
    )
    for name, test in tests:
        test()
        print("PASS", name)
    print("TOTAL_TESTS", len(tests))

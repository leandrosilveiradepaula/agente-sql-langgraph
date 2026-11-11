"""Regression tests for generic n8n + G5 source inventory; no network."""
from __future__ import annotations

import json
import hashlib
from copy import deepcopy

from scripts.operations.legacy_migration_source_crosswalk_offline import (
    LegacyMigrationInventoryRefused,
    build_legacy_migration_inventory,
)


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def fixtures(prefix: str, *, other: bool = False) -> dict:
    source_collection = "source_semantic_records_" + prefix
    sql_collection = "historic_sql_records_" + prefix
    tablename = "payroll_ledger" if not other else "delivery_facts"
    column = "processed_amount" if not other else "quantity_units"
    version = sha(prefix + "-version")
    record = sha(prefix + "-record")
    nodes = [
        {
            "id": prefix + "-start",
            "name": "Start " + prefix,
            "type": "n8n-nodes-base.webhook",
            "parameters": {"path": "private-" + prefix},
        },
        {
            "id": prefix + "-source",
            "name": "Read " + prefix,
            "type": "n8n-nodes-base.postgres",
            "parameters": {
                "query": "SELECT " + column + " FROM " + tablename
            },
            "credentials": {"postgres": {"id": "never-output-this"}},
        },
        {
            "id": prefix + "-end",
            "name": "Respond " + prefix,
            "type": "n8n-nodes-base.respondToWebhook",
            "parameters": {},
        },
    ]
    workflow = {
        "id": prefix + "-id",
        "active": True,
        "versionId": prefix + "-v1",
        "activeVersionId": prefix + "-v1",
        "nodes": nodes,
        "connections": {
            nodes[0]["name"]: {"main": [[{
                "node": nodes[1]["name"], "type": "main", "index": 0,
            }]]},
            nodes[1]["name"]: {"main": [[{
                "node": nodes[2]["name"], "type": "main", "index": 0,
            }]]},
        },
    }
    return {
        "workflow": workflow,
        "workflow_source_sha256": sha(json.dumps(workflow, sort_keys=True)),
        "inventory": {
            "context_activated": False,
            "sql_patterns_classification": "EVALUATION_ONLY_NOT_GENERATOR_INPUT",
            "source_collections": [
                {"name": source_collection, "rows": 1, "use": "CONTEXT_REVIEW_ONLY"},
                {"name": sql_collection, "rows": 1, "use": "EVALUATION_ONLY"},
            ],
        },
        "lineage": {
            "mapped_context_approved": False,
            "source_row_count": 2,
            "source_archive_sha256": sha(prefix + "-archive"),
        },
        "hints": {
            "approved_for_context_activation": False,
            "approved_for_financial_sql": False,
            "candidates": [{
                "source_version_sha256": version,
                "source_record_sha256": record,
                "collection": source_collection,
                "source_table_ref": tablename,
                "source_column_ref": column,
            }],
        },
        "manifest": {
            "approved_for_generation": False,
            "approved_for_import": False,
            "sql_pattern_rows_excluded": 1,
            "versions": [{"source_version_sha256": version,
                          "row_counts": {source_collection: 1}}],
        },
    }


def denied(args: dict, code: str) -> None:
    try:
        build_legacy_migration_inventory(**args)
    except LegacyMigrationInventoryRefused as exc:
        assert str(exc) == code, (str(exc), code)
        return
    raise AssertionError("A contaminated source was incorrectly accepted")


def test_two_different_tenants_without_code_special_cases() -> None:
    for prefix, different in (("alpha", False), ("beta", True)):
        args = fixtures(prefix, other=different)
        report = build_legacy_migration_inventory(**args)
        assert report["counts"]["nodes"] == 3
        assert report["counts"]["edges"] == 2
        assert report["counts"]["nodes_on_webhook_to_response_path"] == 3
        assert report["counts"]["textual_reference_links"] == 1
        assert report["counts"]["g5_identifier_hints"] == 1
        assert report["nodes"][1]["query_shape"] == "READ_STATEMENT"
        assert report["nodes"][1]["has_credential_reference"] is True
        assert report["business_mapping_approved"] is False
        assert report["financial_sql_executed"] is False
        serialized = json.dumps(report)
        for sensitive in (
            "never-output-this",
            "SELECT", "processed_amount", "quantity_units",
            "payroll_ledger", "delivery_facts", "private-" + prefix,
        ):
            assert sensitive not in serialized, sensitive


def test_unpublished_or_inactive_workflow_fails_closed() -> None:
    for change in (
        {"active": False},
        {"activeVersionId": "different"},
        {"versionId": None},
    ):
        args = fixtures("alpha")
        args["workflow"].update(change)
        denied(args, "PUBLISHED_WORKFLOW_NOT_VERIFIED")


def test_broken_topology_fails_closed() -> None:
    args = fixtures("alpha")
    args["workflow"]["connections"]["Start alpha"]["main"][0][0][
        "node"
    ] = "missing"
    denied(args, "WORKFLOW_DANGLING_CONNECTION")


def test_untrusted_g5_and_pattern_leaks_fail_closed() -> None:
    for mutate, code in (
        (lambda a: a["manifest"].update(approved_for_generation=True),
         "SOURCE_APPROVAL_BOUNDARY_INVALID"),
        (lambda a: a["manifest"].update(sql_pattern_rows_excluded=0),
         "HISTORICAL_SQL_EXCLUSION_COUNT_INVALID"),
        (lambda a: a["hints"]["candidates"][0].update(
            source_version_sha256=sha("other-version")
        ), "CANDIDATE_PROVENANCE_INVALID"),
        (lambda a: a["lineage"].update(source_row_count=99),
         "SOURCE_ROW_COUNT_MISMATCH"),
    ):
        args = fixtures("beta", other=True)
        mutate(args)
        denied(args, code)


def test_no_inference_from_absence_or_similar_words() -> None:
    args = fixtures("tenant_scope_three")
    args["hints"]["candidates"][0]["source_table_ref"] = "unrelated_dataset"
    args["hints"]["candidates"][0]["source_column_ref"] = "unknown_column"
    report = build_legacy_migration_inventory(**args)
    assert report["counts"]["textual_reference_links"] == 0
    assert report["counts"]["nodes_with_textual_reference"] == 0
    assert all(not node["candidate_source_record_links"]
               for node in report["nodes"])


if __name__ == "__main__":
    tests = sorted(
        (name, func) for name, func in globals().items()
        if name.startswith("test_") and callable(func)
    )
    for name, func in tests:
        func()
        print("PASS", name)
    print("TESTS", len(tests))

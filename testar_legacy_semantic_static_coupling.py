"""Synthetic multi-tenant static evidence cases, no financial SQL or n8n I/O."""
from __future__ import annotations

import json

from scripts.operations.legacy_semantic_static_coupling_offline import (
    LegacyAuditBlocked,
    audit_legacy_semantic_coupling,
)


def fixture(*, ledger: str = "cash_settlements", schema: str = "source"):
    version = "a" * 64
    wf = {
        "active": True,
        "versionId": "published",
        "activeVersionId": "published",
        "nodes": [
            {
                "name": "Read Context",
                "type": "n8n-nodes-base.postgres",
                "parameters": {
                    "query": (
                        "SELECT * FROM "+schema+".versioned_rules "
                        "WHERE agent_version='fixed-legacy-version';"
                        "SELECT * FROM "+schema+".historical_examples "
                        "WHERE agent_version='fixed-legacy-version';"
                    )
                },
            },
            {
                "name": "Plan",
                "type": "n8n-nodes-base.code",
                "parameters": {
                    "jsCode": (
                        "const SOURCES = {\\n"
                        "  facts: '"+ledger+"',\\n"
                        "  dims: 'dimension_table'\\n"
                        "};\\n"
                    ).replace("\\n", "\n")
                },
            },
        ],
    }
    manifest = {
        "approved_for_generation": False,
        "versions": [{"source_version_sha256": version}],
    }
    inventory = {
        "sql_patterns_classification": (
            "EVALUATION_ONLY_NOT_GENERATOR_INPUT"
        ),
        "source_collections": [
            {
                "name": "versioned_rules",
                "use": "SOURCE_SEMANTIC_REVIEW_ONLY",
            },
            {
                "name": "historical_examples",
                "use": "EVALUATION_ONLY",
            },
        ],
    }
    hints = {
        "candidates": [
            {
                "source_version_sha256": version,
                "source_table_ref": ledger,
                "candidate_status": "AMBIGUOUS_TABLE_NAME",
            }
        ]
    }
    return {
        "workflow": wf, "source_manifest": manifest,
        "source_inventory": inventory, "source_hints": hints,
    }


def test_detects_legacy_fixed_semantic_version_and_evaluation_input():
    data = audit_legacy_semantic_coupling(**fixture())
    assert data["node_count"] == 2
    assert data["fixed_source_version_nodes"][0]["selector_count"] == 2
    assert not data["fixed_source_version_nodes"][0][
        "has_explicit_tenant_column_reference"
    ]
    assert len(data["evaluation_only_sources_read_by_legacy"]) == 1
    assert data["evaluation_only_sources_read_by_legacy"][0][
        "collections"
    ] == ["historical_examples"]
    assert "fixed-legacy-version" not in json.dumps(data)


def test_same_auditor_on_materially_different_client_structures():
    a = audit_legacy_semantic_coupling(**fixture())
    b = audit_legacy_semantic_coupling(
        **fixture(ledger="delivery_fact_rows", schema="other_schema")
    )
    for report in (a, b):
        assert report["static_object_map_count"] == 1
        assert report["static_binding_candidate_count"] == 2
        assert report["static_bindings_with_textual_g5_hints"] == 1
        binding = report["nodes"][1]["static_object_maps"][0]["bindings"][0]
        assert binding["source_hint_count"] == 1
        assert binding["source_version_count"] == 1
        assert binding["candidate_status_counts"] == {
            "AMBIGUOUS_TABLE_NAME": 1
        }
        assert not binding["accounting_equivalence_approved"]
    assert a["nodes"][1]["static_object_maps"] != b["nodes"][1]["static_object_maps"]


def test_multiple_versions_keep_ambiguous_status_unapproved():
    values = fixture()
    other = "b" * 64
    values["source_manifest"]["versions"].append(
        {"source_version_sha256": other}
    )
    values["source_hints"]["candidates"].append({
        "source_version_sha256": other,
        "source_table_ref": "cash_settlements",
        "candidate_status": "COLUMN_UNRESOLVED",
    })
    report = audit_legacy_semantic_coupling(**values)
    binding = report["nodes"][1]["static_object_maps"][0]["bindings"][0]
    assert binding["source_version_count"] == 2
    assert binding["source_hint_count"] == 2
    assert binding["candidate_status_counts"] == {
        "AMBIGUOUS_TABLE_NAME": 1,
        "COLUMN_UNRESOLVED": 1,
    }
    assert report["business_mappings_approved"] is False


def test_no_historical_source_read_does_not_infer_clean_business_rules():
    values = fixture()
    values["workflow"]["nodes"][0]["parameters"]["query"] = (
        "SELECT * FROM source.versioned_rules WHERE tenant_id = 'foo'"
    )
    report = audit_legacy_semantic_coupling(**values)
    assert report["evaluation_only_sources_read_by_legacy"] == []
    assert report["fixed_source_version_nodes"] == []
    assert report["business_mappings_approved"] is False


def test_unapproved_or_missing_manifest_refused():
    for problem in ("approved", "missing", "version_mismatch"):
        values = fixture()
        if problem == "approved":
            values["source_manifest"]["approved_for_generation"] = True
        elif problem == "missing":
            values["source_inventory"]["sql_patterns_classification"] = None
        else:
            values["source_hints"]["candidates"][0][
                "source_version_sha256"
            ] = "c" * 64
        try:
            audit_legacy_semantic_coupling(**values)
        except LegacyAuditBlocked:
            pass
        else:
            raise AssertionError(problem)


def test_unpublished_or_malformed_workflow_refused():
    for problem in ("inactive", "unpublished", "duplicate"):
        values = fixture()
        if problem == "inactive":
            values["workflow"]["active"] = False
        elif problem == "unpublished":
            values["workflow"]["activeVersionId"] = "different"
        else:
            values["workflow"]["nodes"][1]["name"] = "Read Context"
        try:
            audit_legacy_semantic_coupling(**values)
        except LegacyAuditBlocked:
            pass
        else:
            raise AssertionError(problem)


def test_business_text_not_exported_in_report():
    source = fixture(ledger="private_ledger_xo")
    report = audit_legacy_semantic_coupling(**source)
    text = json.dumps(report, sort_keys=True)
    assert "private_ledger_xo" not in text
    assert "SELECT *" not in text
    assert "fixed-legacy-version" not in text
    assert not report["contains_raw_legacy_queries_or_js_or_alias_values"]
    assert report["financial_sql_executed"] is False


def test_can_handle_no_physical_hints():
    x = fixture()
    x["source_hints"]["candidates"] = []
    r = audit_legacy_semantic_coupling(**x)
    assert r["static_bindings_with_textual_g5_hints"] == 0
    assert r["business_mappings_approved"] is False


if __name__ == "__main__":
    cases = [
        (name, test)
        for name, test in sorted(globals().items())
        if name.startswith("test_") and callable(test)
    ]
    for name, test in cases:
        test()
        print("PASS", name)
    print("TOTAL_TESTS", len(cases))

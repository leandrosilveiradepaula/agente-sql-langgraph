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
                "use": "CONTEXT_REVIEW_ONLY",
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




def test_if_gate_cannot_infer_human_approval_from_validator_success():
    values = fixture()
    wf = values["workflow"]
    wf["nodes"][1]["parameters"]["jsCode"] += (
        "\nconst aprovado = errors.length === 0;\n"
    )
    wf["nodes"].append({
        "name": "Gate",
        "type": "n8n-nodes-base.if",
        "parameters": {
            "conditions": {
                "conditions": [{
                    "leftValue": "={{ $json.aprovado === true }}",
                }],
            },
        },
    })
    wf["connections"] = {
        "Plan": {"main": [[{"node": "Gate", "type": "main", "index": 0}]]}
    }
    result = audit_legacy_semantic_coupling(**values)
    assert len(result["if_gate_signals"]) == 1
    gate = result["if_gate_signals"][0]
    assert gate["ordinal"] == 3
    assert gate["direct_source_code_ordinals"] == [2]
    assert gate["gate_classification"] == "ERROR_COUNT_TECHNICAL_VALIDATION_ONLY"
    assert gate["human_approval_verified"] is False


def test_if_gate_with_unknown_parent_does_not_certify_human_approval():
    values = fixture()
    values["workflow"]["nodes"].append({
        "name": "Unknown Approval",
        "type": "n8n-nodes-base.if",
        "parameters": {
            "conditions": {
                "conditions": [{"leftValue": "={{ $json.approved === true }}"}],
            }
        },
    })
    result = audit_legacy_semantic_coupling(**values)
    gate = result["if_gate_signals"][0]
    assert gate["gate_classification"] == "SIGNAL_PROVENANCE_NOT_ESTABLISHED"
    assert gate["human_approval_verified"] is False



def _pin_fixture_to_active_manifest(values: dict) -> str:
    import hashlib
    pinned = hashlib.sha256(b"fixed-legacy-version").hexdigest()
    values["source_manifest"]["versions"][0]["source_version_sha256"] = pinned
    values["source_hints"]["candidates"][0]["source_version_sha256"] = pinned
    values["source_manifest"]["versions"][0].update({
        "row_counts": {"versioned_rules": 2},
        "identifier_hints_count": 1,
        "sealed_and_roundtrip_verified": True,
    })
    return pinned


def test_reconcile_exact_legacy_version_to_sealed_manifest_without_decrypting():
    values = fixture()
    version = _pin_fixture_to_active_manifest(values)
    report = audit_legacy_semantic_coupling(**values)
    scoped = report["pinned_source_version_reconciliation"]
    assert scoped["status"] == "PINNED_VERSION_MATCHES_SEALED_G5"
    assert scoped["matching_source_version_sha256"] == version
    assert scoped["matching_manifest_row_counts"] == {"versioned_rules": 2}
    assert scoped["matching_manifest_identifier_hint_count"] == 1
    assert scoped["seal_roundtrip_reported_by_manifest"] is True
    mapping = scoped["selected_version_binding_evidence"][0]
    assert mapping["binding_count"] == 2
    assert mapping["bindings_with_textual_hints"] == 1
    assert mapping["accounting_equivalence_approved"] is False
    assert scoped["source_plaintext_reviewed"] is False
    assert scoped["ready_for_generation"] is False


def test_missing_pinned_version_does_not_silently_substitute_another_version():
    report = audit_legacy_semantic_coupling(**fixture())
    scoped = report["pinned_source_version_reconciliation"]
    assert scoped["status"] == "PINNED_VERSION_NOT_IN_G5_MANIFEST"
    assert scoped["matching_source_version_sha256"] is None
    assert scoped["matching_manifest_row_counts"] == {}
    assert scoped["selected_version_binding_evidence"] == []


def test_multiple_workflow_version_literals_are_never_merged():
    values = fixture()
    _pin_fixture_to_active_manifest(values)
    source = values["workflow"]["nodes"][0]["parameters"]["query"]
    values["workflow"]["nodes"][0]["parameters"]["query"] = source.replace(
        "WHERE agent_version='fixed-legacy-version';",
        "WHERE agent_version='fixed-legacy-version';",
        1,
    ).replace(
        "SELECT * FROM source.historical_examples "
        "WHERE agent_version='fixed-legacy-version';",
        "SELECT * FROM source.historical_examples "
        "WHERE agent_version='second-version';",
    )
    report = audit_legacy_semantic_coupling(**values)
    scoped = report["pinned_source_version_reconciliation"]
    assert scoped["status"] == "MULTIPLE_PINNED_VERSIONS_REQUIRE_REVIEW"
    assert scoped["matching_source_version_sha256"] is None


def test_version_scoped_counts_do_not_mix_old_alias_records():
    values = fixture()
    pinned = _pin_fixture_to_active_manifest(values)
    extra = "b" * 64
    values["source_manifest"]["versions"].append({
        "source_version_sha256": extra,
        "row_counts": {"versioned_rules": 100},
    })
    values["source_hints"]["candidates"].append({
        "source_version_sha256": extra,
        "source_table_ref": "cash_settlements",
        "candidate_status": "COLUMN_UNRESOLVED",
    })
    report = audit_legacy_semantic_coupling(**values)
    scoped = report["pinned_source_version_reconciliation"]
    assert scoped["matching_source_version_sha256"] == pinned
    assert scoped["matching_manifest_row_counts"] == {"versioned_rules": 2}
    assert scoped["matching_manifest_identifier_hint_count"] == 1
    match = scoped["selected_version_binding_evidence"][0]
    assert match["candidate_status_counts"] == {
        "AMBIGUOUS_TABLE_NAME": 1
    }


def test_unknown_or_negative_manifest_counts_fail_closed():
    for rows in ({"untrusted_collection": 1}, {"versioned_rules": -1},
                 {"versioned_rules": "2"}):
        values = fixture()
        _pin_fixture_to_active_manifest(values)
        values["source_manifest"]["versions"][0]["row_counts"] = rows
        try:
            audit_legacy_semantic_coupling(**values)
        except LegacyAuditBlocked:
            pass
        else:
            raise AssertionError("Invalid source row count accepted")


def test_no_version_selector_never_approves_unpinned_context():
    values = fixture()
    values["workflow"]["nodes"][0]["parameters"]["query"] = (
        "SELECT * FROM source.versioned_rules WHERE tenant_id='tenant-1'"
    )
    report = audit_legacy_semantic_coupling(**values)
    scoped = report["pinned_source_version_reconciliation"]
    assert scoped["status"] == "NO_LEGACY_VERSION_SELECTOR"
    assert scoped["ready_for_generation"] is False

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

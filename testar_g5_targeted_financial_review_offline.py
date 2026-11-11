"""No-decryption synthetic tests of targeted G5 financial review safety."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.operations.g5_targeted_financial_review_offline import (
    ReviewBlocked,
    select_verified_seal,
    verify_decrypted_packet,
    write_private_once,
)


def fixture(version: str = "f" * 64, alternate: bool = False):
    source = "value_events" if alternate else "ledger_records"
    record = {
        "source_row_sha256": "d" * 64,
        "source_fields_unreviewed": {
            "metric_identity": "some_metric",
            "target_source": source,
        },
    }
    packet = {
        "origin": {"source_version_sha256": version},
        "status": "QUARANTINED_SOURCE_EVIDENCE_UNAPPROVED",
        "financial_semantics_equivalence": "NOT_ATTESTED",
        "can_import_into_semantic_catalog": False,
        "can_use_as_llm_or_planner_context": False,
        "can_execute_financial_sql": False,
        "historical_sql_patterns_excluded": True,
        "row_counts": {"semantic_rules": 1},
        "collections": {"semantic_rules": [record]},
    }
    raw = json.dumps(packet, sort_keys=True).encode()
    seal = {
        "source_version_sha256": version,
        "file": f"source-version-{version}.json.gpg",
        "ciphertext_sha256": "e" * 64,
        "plaintext_sha256": hashlib.sha256(raw).hexdigest(),
        "row_counts": {"semantic_rules": 1},
        "sealed_and_roundtrip_verified": True,
    }
    manifest = {
        "approved_for_generation": False,
        "approved_for_import": False,
        "financial_sql_executed": False,
        "context_activated": False,
        "versions": [seal],
    }
    return raw, seal, manifest


def denied(function, *args):
    try:
        function(*args)
    except ReviewBlocked:
        return
    raise AssertionError("Invalid unapproved data accepted")


def test_distinct_tenant_schemas_are_reviewed_with_same_structural_contract():
    for other in (False, True):
        raw, seal, manifest = fixture(alternate=other)
        assert select_verified_seal(manifest, seal["source_version_sha256"]) == seal
        packet, result = verify_decrypted_packet(raw, seal)
        assert result["status"] == "INTEGRITY_VERIFIED_FINANCIAL_MEANING_UNAPPROVED"
        assert result["source_row_count"] == 1
        assert result["ready_for_generator"] is False
        assert result["benchmark_inputs_included"] is False
        assert packet["collections"]["semantic_rules"][0]["source_fields_unreviewed"]


def test_manifest_cannot_be_preapproved_or_select_wrong_version():
    raw, seal, manifest = fixture()
    manifest["approved_for_generation"] = True
    denied(select_verified_seal, manifest, seal["source_version_sha256"])
    manifest["approved_for_generation"] = False
    denied(select_verified_seal, manifest, "b" * 64)


def test_tampered_payload_digest_and_versions_are_rejected():
    raw, seal, _ = fixture()
    denied(verify_decrypted_packet, raw + b" ", seal)
    forged = json.loads(raw)
    forged["origin"]["source_version_sha256"] = "b" * 64
    changed = json.dumps(forged, sort_keys=True).encode()
    badseal = dict(seal, plaintext_sha256=hashlib.sha256(changed).hexdigest())
    denied(verify_decrypted_packet, changed, badseal)


def test_historical_sql_and_active_context_flags_fail_closed():
    raw, seal, _ = fixture()
    for key, other in (
        ("historical_sql_patterns_excluded", False),
        ("can_use_as_llm_or_planner_context", True),
        ("can_execute_financial_sql", True),
    ):
        packet = json.loads(raw)
        packet[key] = other
        data = json.dumps(packet, sort_keys=True).encode()
        modified = dict(seal, plaintext_sha256=hashlib.sha256(data).hexdigest())
        denied(verify_decrypted_packet, data, modified)


def test_row_counts_and_source_row_digest_must_match():
    raw, seal, _ = fixture()
    packet = json.loads(raw)
    packet["collections"]["semantic_rules"].append(
        packet["collections"]["semantic_rules"][0]
    )
    data = json.dumps(packet, sort_keys=True).encode()
    modified = dict(seal, plaintext_sha256=hashlib.sha256(data).hexdigest())
    denied(verify_decrypted_packet, data, modified)


def test_private_review_creation_is_exclusive_and_permissions_restrictive():
    with TemporaryDirectory() as directory:
        root = Path(directory)
        output = root / "test-review.json"
        write_private_once(output, b'{"ok":true}\n')
        assert output.read_bytes() == b'{"ok":true}\n'
        assert output.stat().st_mode & 0o077 == 0
        denied(write_private_once, output, b"overwritten")


def test_no_raw_business_values_in_sanitized_report():
    raw, seal, _ = fixture()
    _, report = verify_decrypted_packet(raw, seal)
    view = json.dumps(report, sort_keys=True)
    assert "some_metric" not in view
    assert "ledger_records" not in view
    assert "source_row_sha256" not in view


if __name__ == "__main__":
    all_tests = sorted(
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    )
    for name, fn in all_tests:
        fn()
        print("PASS", name)
    print("TOTAL_TESTS", len(all_tests))

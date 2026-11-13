"""No-decryption synthetic tests of targeted G5 financial review safety."""
from __future__ import annotations

import hashlib
import json
import os
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
        "contract": "g5-private-source-review-manifest-v1",
        "status": "ENCRYPTED_NOT_APPROVED",
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
        if os.name != "posix":
            # Windows CI must fail closed: cannot prove POSIX 0600.
            denied(write_private_once, output, b'{"ok":true}\n')
            assert not output.exists()
            return
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


def test_real_entrypoint_preserves_original_plaintext_digest_for_crosswalk():
    """A reserialized JSON is NOT the original G5 sealed payload."""
    from unittest.mock import patch
    import scripts.operations.g5_targeted_financial_review_offline as module
    from scripts.operations.g5_financial_crosswalk_review import draft, source_ids

    class SyntheticTTY:
        def isatty(self):
            return True

    for alternate in (False, True):
        raw, seal, manifest = fixture(alternate=alternate)
        # Synthetic input varies only the source object, never uses financial SQL.
        cipher_content = b"synthetic encrypted fixture only"
        seal["ciphertext_sha256"] = hashlib.sha256(cipher_content).hexdigest()
        with TemporaryDirectory() as temp:
            root = Path(temp)
            encrypted = root / seal["file"]
            encrypted.write_bytes(cipher_content)
            encrypted.chmod(0o600)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest))
            manifest_path.chmod(0o600)
            out = root / "private"
            with (
                patch.object(module.sys, "stdin", SyntheticTTY()),
                patch.object(module.getpass, "getpass",
                             return_value="synthetic-test-only"),
                patch.object(module, "decrypt_local_gpg", return_value=raw),
            ):
                result = module.main([
                    "--manifest", str(manifest_path),
                    "--version-sha256", seal["source_version_sha256"],
                    "--output-dir", str(out),
                ])
            if os.name != "posix":
                # The real endpoint must fail closed on Windows, even when
                # a mocked TTY/passphrase/decryptor is supplied. Separately
                # verify the immutable source digest on every platform.
                assert result == 2
                assert not out.exists()
                packet, report = verify_decrypted_packet(raw, seal)
                assert report["packet_plaintext_sha256"] == seal["plaintext_sha256"]
                assert len(source_ids(packet)) == 1
                continue
            assert result == 0
            assert out.stat().st_mode & 0o077 == 0
            persisted = out / "unapproved-source-packet.json"
            assert persisted.stat().st_mode & 0o077 == 0
            assert persisted.read_bytes() == raw
            packet, report = verify_decrypted_packet(
                persisted.read_bytes(), seal,
            )
            saved_report = json.loads(
                (out / "sanitized-review-evidence.json").read_bytes()
            )
            assert saved_report == report
            review = json.loads(
                (out / "financial-crosswalk-review-draft.json").read_bytes()
            )
            assert review == draft(packet, report["packet_plaintext_sha256"])
            assert len(source_ids(packet)) == len(review["rows"]) == 1
            assert review["accounting_approved"] is False
            assert review["ready_for_generation"] is False
            # Original formatter re-encoded with extra separators/newline;
            # it must not be accepted as the original sealed source bytes.
            reformatted = (
                json.dumps(packet, sort_keys=True, ensure_ascii=True).encode()
                + b"\n"
            )
            assert reformatted != raw
            denied(verify_decrypted_packet, reformatted, seal)


if __name__ == "__main__":
    all_tests = sorted(
        (name, fn) for name, fn in globals().items()
        if name.startswith("test_") and callable(fn)
    )
    for name, fn in all_tests:
        fn()
        print("PASS", name)
    print("TOTAL_TESTS", len(all_tests))

"""Privacy and fail-closed proofs for real G5 reviewer dossier entrypoint.

Synthetic values only; no customer's business fields, SQL, or benchmark rows.
"""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import stat
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.operations.g5_financial_crosswalk_review import FinancialReviewBlocked, draft
from scripts.operations.g5_private_financial_review_dossier import (
    build, main, render_html, review_rows,
)
from scripts.operations.g5_targeted_financial_review_offline import (
    ReviewBlocked, verify_decrypted_packet,
)
from testar_g5_targeted_financial_review_offline import fixture


def _private_files(folder: Path, *, alternate=False, hint=False, n=1):
    data, seal, manifest = fixture(alternate=alternate)
    packet = json.loads(data)
    if n > 1:
        base = packet["collections"]["semantic_rules"][0]
        packet["collections"]["semantic_rules"] = [
            {
                "source_row_sha256": format(i + 1, "064x"),
                "source_fields_unreviewed": {
                    **base["source_fields_unreviewed"],
                    "synthetic_sequence": str(i),
                },
            }
            for i in range(n)
        ]
        packet["row_counts"]["semantic_rules"] = n
        seal["row_counts"]["semantic_rules"] = n
    packet["collections"]["semantic_rules"][0]["source_fields_unreviewed"][
        "synthetic_sensitive_text"
    ] = "<script>PRIVATE-SENTINEL</script> & business"
    if hint:
        first = packet["collections"]["semantic_rules"][0]
        packet["physical_identifier_hints_unapproved"] = [
            {
                "collection": "semantic_rules",
                "source_record_sha256": first["source_row_sha256"],
                "candidate_status": "AMBIGUOUS_TABLE_NAME",
                "column_status": "COLUMN_UNRESOLVED",
            }
        ]
    # Deliberately non-standard serialization to prove byte integrity.
    data = (json.dumps(packet, sort_keys=False, separators=(",", ":")) + "\n").encode()
    seal["plaintext_sha256"] = hashlib.sha256(data).hexdigest()
    manifest["versions"][0]["plaintext_sha256"] = seal["plaintext_sha256"]
    manifest["versions"][0]["row_counts"] = dict(seal["row_counts"])
    folder.chmod(0o700)
    manifest_path = folder / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    manifest_path.chmod(0o600)
    packet_path = folder / "unapproved-source-packet.json"
    packet_path.write_bytes(data)
    packet_path.chmod(0o600)
    review_path = folder / "financial-crosswalk-review-draft.json"
    review_path.write_text(json.dumps(draft(packet, seal["plaintext_sha256"])))
    review_path.chmod(0o600)
    return packet, seal, manifest_path, packet_path, review_path


def _denied(fn):
    try:
        fn()
    except (FinancialReviewBlocked, ReviewBlocked, ValueError):
        return
    raise AssertionError("Unsafe G5 dossier operation was accepted")


def test_two_different_context_shapes_render_privately_and_escape_html():
    if os.name != "posix":
        return  # Private 0600/0700 dossier is POSIX-only; safe skip on Windows.
    for alternate in (False, True):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            _, seal, manifest, packet, review = _private_files(
                root, alternate=alternate, hint=True,
            )
            target = root / "reviewer-private.html"
            stats = build(
                manifest_path=manifest,
                version_sha256=seal["source_version_sha256"],
                packet_path=packet, review_path=review, output_path=target,
            )
            assert stats == {
                "records": 1,
                "physical_hint_rows": 1,
                "ambiguous_physical_tables": 1,
                "unresolved_physical_columns": 1,
            }
            assert stat.S_IMODE(target.stat().st_mode) == 0o600
            data = target.read_text()
            assert "PRIVATE-SENTINEL" in data
            assert "<script>PRIVATE-SENTINEL</script>" not in data
            assert "&lt;script&gt;PRIVATE-SENTINEL&lt;/script&gt;" in data
            assert "default-src 'none'" in data
            assert "Classificação: UNRESOLVED" in data
            assert "NÃO APROVADO" in data
            assert len(data) < 100_000


def test_complete_77_row_review_matrix_is_read_only_and_private():
    if os.name != "posix":
        return  # Private 0600/0700 dossier is POSIX-only; safe skip on Windows.
    with TemporaryDirectory() as folder:
        root = Path(folder)
        _, seal, manifest, packet, review = _private_files(root, n=77)
        stats = build(
            manifest_path=manifest,
            version_sha256=seal["source_version_sha256"],
            packet_path=packet, review_path=review,
            output_path=root / "private.html",
        )
        assert stats["records"] == 77
        page = (root / "private.html").read_text()
        assert page.count("<section>") == 77
        assert page.count("UNRESOLVED") == 77
        assert "0 APROVAÇÕES CONTÁBEIS" in page


def test_draft_cannot_be_reclassified_or_approved_by_dossier():
    if os.name != "posix":
        return  # Private 0600/0700 dossier is POSIX-only; safe skip on Windows.
    with TemporaryDirectory() as folder:
        root = Path(folder)
        _, seal, manifest, packet, review = _private_files(root)
        changed = json.loads(review.read_text())
        changed["rows"][0]["classification"] = "STRUCTURAL"
        review.write_text(json.dumps(changed))
        _denied(lambda: build(
            manifest_path=manifest,
            version_sha256=seal["source_version_sha256"],
            packet_path=packet, review_path=review,
            output_path=root / "never.html",
        ))
        assert not (root / "never.html").exists()


def test_tampered_sealed_plaintext_never_generates_dossier():
    if os.name != "posix":
        return  # Private 0600/0700 dossier is POSIX-only; safe skip on Windows.
    with TemporaryDirectory() as folder:
        root = Path(folder)
        _, seal, manifest, packet, review = _private_files(root)
        packet.write_bytes(packet.read_bytes() + b" ")
        _denied(lambda: build(
            manifest_path=manifest,
            version_sha256=seal["source_version_sha256"],
            packet_path=packet, review_path=review,
            output_path=root / "never.html",
        ))
        assert not (root / "never.html").exists()


def test_path_and_file_permissions_are_enforced():
    if os.name != "posix":
        return  # Private 0600/0700 dossier is POSIX-only; safe skip on Windows.
    with TemporaryDirectory() as folder:
        root = Path(folder)
        _, seal, manifest, packet, review = _private_files(root)
        packet.chmod(0o644)
        _denied(lambda: build(
            manifest_path=manifest,
            version_sha256=seal["source_version_sha256"],
            packet_path=packet, review_path=review,
            output_path=root / "never.html",
        ))
        packet.chmod(0o600)
        outside = root.parent / ("not-private-" + root.name + ".html")
        _denied(lambda: build(
            manifest_path=manifest,
            version_sha256=seal["source_version_sha256"],
            packet_path=packet, review_path=review,
            output_path=outside,
        ))
        assert not outside.exists()


def test_hint_provenance_cannot_be_missing_or_duplicated():
    for reason in ("unknown", "duplicated"):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            packet, seal, _, _, _ = _private_files(root, hint=True)
            p = json.loads(json.dumps(packet))
            if reason == "unknown":
                p["physical_identifier_hints_unapproved"][0][
                    "source_record_sha256"
                ] = "a" * 64
            else:
                p["physical_identifier_hints_unapproved"].append(
                    dict(p["physical_identifier_hints_unapproved"][0])
                )
            _denied(lambda: review_rows(
                p, draft(p, seal["plaintext_sha256"]),
                seal["plaintext_sha256"],
            ))


def test_cli_stdout_never_contains_private_values():
    if os.name != "posix":
        return  # Private 0600/0700 dossier is POSIX-only; safe skip on Windows.
    with TemporaryDirectory() as folder:
        root = Path(folder)
        _, seal, manifest, packet, review = _private_files(root, hint=True)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main([
                "--manifest", str(manifest),
                "--version-sha256", seal["source_version_sha256"],
                "--packet-file", str(packet),
                "--review-file", str(review),
                "--output-html", str(root / "private.html"),
            ])
        assert rc == 0
        assert "G5_PRIVATE_REVIEW_DOSSIER=PASS" in out.getvalue()
        for secret in ("PRIVATE-SENTINEL", "some_metric", "ledger_records"):
            assert secret not in out.getvalue()


def test_non_posix_dossier_is_not_supported():
    if os.name == "posix":
        return
    with TemporaryDirectory() as folder:
        root = Path(folder)
        _, seal, manifest, packet, review = _private_files(root)
        _denied(lambda: build(
            manifest_path=manifest,
            version_sha256=seal["source_version_sha256"],
            packet_path=packet, review_path=review,
            output_path=root / "not-supported.html",
        ))


def main_tests():
    tests = sorted(
        (name, value) for name, value in globals().items()
        if name.startswith("test_") and callable(value)
    )
    for name, function in tests:
        function()
        print("PASS", name)
    print("TOTAL_TESTS", len(tests))


if __name__ == "__main__":
    main_tests()

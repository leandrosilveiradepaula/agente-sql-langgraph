"""Offline, synthetic integrity tests for the root-only P3 custody transfer."""
from __future__ import annotations

import hashlib
import json
import os
import stat
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.operations.g5_financial_crosswalk_review import FinancialReviewBlocked
from scripts.operations.g5_preserve_p3_custody_offline import main, preserve
from scripts.operations.g5_targeted_financial_review_offline import ReviewBlocked
from testar_g5_targeted_financial_review_offline import fixture


def source(*, root: Path, alternate: bool = False):
    raw, seal, manifest = fixture(alternate=alternate)
    packet = json.loads(raw)
    table = "values_source" if alternate else "records_source"
    schema = "tenant_b" if alternate else "tenant_a"
    physical = {
        "contract": "p3-metadata-snapshot-v1",
        "database": "synthetic_offline",
        "role_name": "readonly_synthetic",
        "context_version": "synthetic-v1",
        "context": [],
        "physical": [[schema, table, "metric_amount", "numeric"]],
        "grants": [],
        "identity": [str(i) for i in range(14)],
        "sql_executed": False,
        "llm_calls": 0,
    }
    p3_bytes = (json.dumps(physical, separators=(",", ":"), sort_keys=True) + "\n").encode()
    packet["origin"]["p3_snapshot_sha256"] = hashlib.sha256(p3_bytes).hexdigest()
    raw = json.dumps(packet, sort_keys=True).encode()
    seal["plaintext_sha256"] = hashlib.sha256(raw).hexdigest()
    manifest["versions"][0]["plaintext_sha256"] = seal["plaintext_sha256"]
    root.chmod(0o700)
    original = root / "physical-metadata.json"
    original.write_bytes(p3_bytes)
    original.chmod(0o600)
    packet_file = root / "unapproved-source-packet.json"
    packet_file.write_bytes(raw)
    packet_file.chmod(0o600)
    manifest_file = root / "manifest.json"
    manifest_file.write_text(json.dumps(manifest))
    manifest_file.chmod(0o600)
    return {
        "version": seal["source_version_sha256"],
        "manifest": manifest_file,
        "packet": packet_file,
        "original": original,
        "target": root / "private-p3-metadata.json",
        "p3_bytes": p3_bytes,
    }


def call(obj):
    return preserve(
        manifest_path=obj["manifest"],
        version_sha256=obj["version"],
        packet_path=obj["packet"],
        original_p3_file=obj["original"],
        output_p3_file=obj["target"],
    )


def denied(action):
    try:
        action()
    except (ReviewBlocked, FinancialReviewBlocked, ValueError, OSError):
        return
    raise AssertionError("unsafe G5 P3 metadata custody approved")


def test_original_p3_is_byte_identical_and_private_for_two_distinct_schemas():
    if os.name != "posix":
        return
    for alternate in (False, True):
        with TemporaryDirectory() as name:
            info = source(root=Path(name), alternate=alternate)
            result = call(info)
            assert result == {
                "source_rows": 1, "physical_metadata_rows": 1, "sql_executed": 0,
            }
            assert info["target"].read_bytes() == info["p3_bytes"]
            assert stat.S_IMODE(info["target"].stat().st_mode) == 0o600
            denied(lambda: call(info))  # No replay/overwrite.


def test_digest_mismatch_and_untrusted_metadata_fail_closed():
    if os.name != "posix":
        return
    with TemporaryDirectory() as name:
        info = source(root=Path(name))
        info["original"].write_bytes(info["p3_bytes"] + b" ")
        denied(lambda: call(info))
        assert not info["target"].exists()

    with TemporaryDirectory() as name:
        info = source(root=Path(name))
        doc = json.loads(info["original"].read_bytes())
        doc["sql_executed"] = True
        raw = json.dumps(doc, sort_keys=True).encode()
        info["original"].write_bytes(raw)
        # Even with no bad digest, source flags still block. The test
        # intentionally changes synthetic G5 origin digest and seal.
        packet = json.loads(info["packet"].read_bytes())
        packet["origin"]["p3_snapshot_sha256"] = hashlib.sha256(raw).hexdigest()
        new_packet = json.dumps(packet, sort_keys=True).encode()
        info["packet"].write_bytes(new_packet)
        manifest = json.loads(info["manifest"].read_bytes())
        manifest["versions"][0]["plaintext_sha256"] = hashlib.sha256(new_packet).hexdigest()
        info["manifest"].write_text(json.dumps(manifest))
        denied(lambda: call(info))
        assert not info["target"].exists()


def test_permissions_and_input_symlink_fail_closed():
    if os.name != "posix":
        return
    with TemporaryDirectory() as name:
        info = source(root=Path(name))
        info["original"].chmod(0o644)
        denied(lambda: call(info))
        assert not info["target"].exists()
        info["original"].chmod(0o600)
        real = info["original"]
        alias = Path(name) / "original-symlink.json"
        alias.symlink_to(real)
        info["original"] = alias
        denied(lambda: call(info))
        assert not info["target"].exists()


def test_cli_output_does_not_include_business_values():
    if os.name != "posix":
        return
    from contextlib import redirect_stdout
    from io import StringIO
    with TemporaryDirectory() as name:
        info = source(root=Path(name))
        out = StringIO()
        with redirect_stdout(out):
            rc = main([
                "--manifest", str(info["manifest"]),
                "--source-version-sha256", info["version"],
                "--g5-packet-file", str(info["packet"]),
                "--original-p3-file", str(info["original"]),
                "--output-p3-file", str(info["target"]),
            ])
        assert rc == 0
        assert "G5_P3_CUSTODY=PASS" in out.getvalue()
        for token in ("tenant_a", "metric_amount", "synthetic_offline"):
            assert token not in out.getvalue()


def test_non_posix_is_explicitly_blocked():
    if os.name == "posix":
        return
    denied(lambda: preserve(
        manifest_path=Path("manifest.json"),
        version_sha256="f"*64,
        packet_path=Path("source.json"),
        original_p3_file=Path("source.json"),
        output_p3_file=Path("out.json"),
    ))


if __name__ == "__main__":
    tests = sorted((n,f) for n,f in globals().items()
                   if n.startswith("test_") and callable(f))
    for name, func in tests:
        func()
        print("PASS", name)
    print("TOTAL_TESTS", len(tests))

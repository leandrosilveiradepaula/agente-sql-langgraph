"""G5 encrypted-copy offline verifier: synthetic ciphertext only."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).parent / "operations" / "g5_verify_encrypted_copy_readonly.py"
SPEC = importlib.util.spec_from_file_location("g5_verify_encrypted_copy_readonly", SOURCE)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)

PROJECT = "a" * 20
TIMESTAMP = "20261028T145054Z"
NAME = f"source-{PROJECT}-{TIMESTAMP}-1557baa82308af9b.dump.gpg"
ENCRYPTED_FIXTURE = b"\x8c\xe4\x0d" + b"fake_gpg_ciphertext_not_a_real_backup" * 24


def make_copy(folder: Path) -> tuple[Path, str, Path]:
    archive = folder / NAME
    archive.write_bytes(ENCRYPTED_FIXTURE)
    archive.chmod(0o600)
    manifest = archive.with_name(NAME + ".manifest.json")
    fields = {
        "version": 1, "project_ref": PROJECT,
        "captured_at": TIMESTAMP, "archive_name": NAME,
        "encrypted_sha256": hashlib.sha256(ENCRYPTED_FIXTURE).hexdigest(),
        "encrypted_bytes": len(ENCRYPTED_FIXTURE),
        "format": "pg_dump_custom_openpgp_symmetric",
        "restore_verified": False,
    }
    manifest.write_text(
        json.dumps(fields, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    manifest.chmod(0o600)
    return manifest, hashlib.sha256(manifest.read_bytes()).hexdigest(), archive


class G5CopyVerificationTests(unittest.TestCase):
    def test_synthetic_encrypted_copy_hash_passes_not_offsite(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, trusted_sha, archive = make_copy(Path(td))
            before = archive.read_bytes()
            self.assertEqual(
                m.inspect_copy(manifest, PROJECT, trusted_sha),
                len(ENCRYPTED_FIXTURE),
            )
            self.assertEqual(before, archive.read_bytes())
            import sys
            argv = [
                "g5_verify_encrypted_copy_readonly.py",
                "--source-project-ref", PROJECT,
                "--manifest", str(manifest),
                "--trusted-manifest-sha256", trusted_sha,
            ]
            with patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(m.main(), 0)
            report = out.getvalue()
            self.assertIn("G5_COPY_MANIFEST_SHA256=PASS", report)
            self.assertIn("G5_COPY_CIPHERTEXT_SHA256=PASS", report)
            self.assertIn("G5_COPY_VERIFICATION=PASS", report)
            self.assertIn("G5_OFFSITE_CUSTODY=NOT_ATTESTED", report)
            self.assertIn("G5_RESTORE_TEST=NOT_PERFORMED", report)
            self.assertNotIn(archive.name, report)

    def test_trusted_manifest_checksum_is_independent_from_copy(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, trusted_sha, _ = make_copy(Path(td))
            with self.assertRaises(m.CopyBlocked) as blocked:
                m.inspect_copy(manifest, PROJECT, "f" * 64)
            self.assertEqual(str(blocked.exception), "MANIFEST_TRUST_HASH_MISMATCH")
            self.assertNotEqual(trusted_sha, "f" * 64)

    def test_ciphertext_change_always_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, trusted_sha, archive = make_copy(Path(td))
            archive.write_bytes(b"different_data_same_size".ljust(len(ENCRYPTED_FIXTURE), b"!"))
            archive.chmod(0o600)
            with self.assertRaises(m.CopyBlocked) as blocked:
                m.inspect_copy(manifest, PROJECT, trusted_sha)
            self.assertEqual(str(blocked.exception), "CIPHERTEXT_SHA256_MISMATCH")

    def test_missing_and_truncated_ciphertext_block(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, trusted_sha, archive = make_copy(Path(td))
            archive.unlink()
            with self.assertRaises(m.CopyBlocked) as blocked:
                m.inspect_copy(manifest, PROJECT, trusted_sha)
            self.assertEqual(str(blocked.exception), "COPY_FILE_MISSING")
        with tempfile.TemporaryDirectory() as td:
            manifest, trusted_sha, archive = make_copy(Path(td))
            archive.write_bytes(b"short")
            archive.chmod(0o600)
            with self.assertRaises(m.CopyBlocked) as blocked:
                m.inspect_copy(manifest, PROJECT, trusted_sha)
            self.assertEqual(str(blocked.exception), "CIPHERTEXT_SIZE_MISMATCH")

    def test_wrong_project_and_nonabsolute_manifest_block(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, trusted_sha, _ = make_copy(Path(td))
            with self.assertRaises(m.CopyBlocked) as blocked:
                m.inspect_copy(manifest, "b" * 20, trusted_sha)
            self.assertEqual(str(blocked.exception), "MANIFEST_METADATA_INVALID")
            with self.assertRaises(m.CopyBlocked) as blocked:
                m.inspect_copy(Path(NAME + ".manifest.json"), PROJECT, trusted_sha)
            self.assertEqual(str(blocked.exception), "COPY_PATH_NOT_ABSOLUTE")

    def test_invalid_trusted_checksum_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, _, _ = make_copy(Path(td))
            for bad in ("", "1" * 40, "g" * 64, "a" * 64 + "\n"):
                with self.subTest(bad=bad):
                    with self.assertRaises(m.CopyBlocked) as blocked:
                        m.inspect_copy(manifest, PROJECT, bad)
                    self.assertEqual(str(blocked.exception),
                                     "TRUSTED_MANIFEST_SHA256_INVALID")

    def test_mutated_manifest_hash_cannot_be_hidden_by_repairing_ciphertext(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, trusted_sha, archive = make_copy(Path(td))
            corrupted = archive.read_bytes() + b"NOT_SAME_BACKUP"
            archive.write_bytes(corrupted)
            archive.chmod(0o600)
            receipt = json.loads(manifest.read_text(encoding="utf-8"))
            receipt["encrypted_bytes"] = len(corrupted)
            receipt["encrypted_sha256"] = hashlib.sha256(corrupted).hexdigest()
            manifest.write_text(json.dumps(receipt), encoding="utf-8")
            manifest.chmod(0o600)
            with self.assertRaises(m.CopyBlocked) as blocked:
                m.inspect_copy(manifest, PROJECT, trusted_sha)
            self.assertEqual(str(blocked.exception), "MANIFEST_TRUST_HASH_MISMATCH")

    @unittest.skipUnless(os.name == "posix", "POSIX mode metadata")
    def test_group_readable_files_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, trusted_sha, archive = make_copy(Path(td))
            archive.chmod(0o644)
            with self.assertRaises(m.CopyBlocked) as blocked:
                m.inspect_copy(manifest, PROJECT, trusted_sha)
            self.assertEqual(str(blocked.exception), "COPY_FILE_PERMISSIONS_UNSAFE")
        with tempfile.TemporaryDirectory() as td:
            manifest, trusted_sha, archive = make_copy(Path(td))
            link = manifest.with_name("linked-backup")
            link.symlink_to(archive.name)
            with self.assertRaises(m.CopyBlocked) as blocked:
                m.private_regular_file(link)
            self.assertEqual(str(blocked.exception), "COPY_FILE_NOT_REGULAR")

    def test_malformed_manifest_is_never_echoed(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, _, _ = make_copy(Path(td))
            content = json.loads(manifest.read_text(encoding="utf-8"))
            content["dsn"] = "postgresql://supersecret"
            manifest.write_text(json.dumps(content), encoding="utf-8")
            manifest.chmod(0o600)
            sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
            with self.assertRaises(m.CopyBlocked) as blocked:
                m.inspect_copy(manifest, PROJECT, sha)
            self.assertEqual(str(blocked.exception), "MANIFEST_STRUCTURE_INVALID")
            self.assertNotIn("supersecret", str(blocked.exception))

    def test_receipt_format_does_not_claim_offsite_or_restore(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, trusted_sha, _ = make_copy(Path(td))
            import sys
            argv = [
                "copy-verify", "--manifest", str(manifest),
                "--source-project-ref", PROJECT,
                "--trusted-manifest-sha256", "f" * 64,
            ]
            with patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(m.main(), 2)
            s = out.getvalue()
            self.assertIn("G5_COPY_VERIFICATION=BLOCKED", s)
            self.assertIn("G5_OFFSITE_CUSTODY=NOT_ATTESTED", s)
            self.assertIn("G5_RESTORE_TEST=NOT_PERFORMED", s)
            self.assertNotIn(str(manifest), s)


if __name__ == "__main__":
    unittest.main()

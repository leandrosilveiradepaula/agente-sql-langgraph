#!/usr/bin/env python3
"""Seal recovered source semantics into *unapproved* version-isolated review packets.

Runs only against privately retained G5 archives/evidence. Nothing is loaded
into LangGraph, semantic_context or an LLM. SQL-pattern rows are deliberately
never decoded into the review packets. No database or network connection.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import getpass
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from scripts.operations import g5_semantic_lineage_candidate as g5

EXCLUDED = g5.EVALUATION_ONLY
REVIEWED = frozenset(g5.CATALOGS - {EXCLUDED})
MAX_REVIEW_BYTES = 128 * 1024 * 1024
CONTRACT = "g5-private-semantic-context-review-v1"


def require_private_directory(path: Path) -> None:
    g5.require_posix_io()
    if not path.is_absolute() or path.is_symlink() or not path.is_dir():
        g5.deny("REVIEW_DIRECTORY_INVALID")
    s = path.stat()
    if s.st_uid != os.geteuid() or s.st_mode & 0o077:
        g5.deny("REVIEW_DIRECTORY_NOT_PRIVATE")


class VersionedCollector:
    """Keep raw historical knowledge in memory, separated by source version."""

    def __init__(self) -> None:
        self.records = defaultdict(lambda: defaultdict(list))
        self.labels = {}
        self.approx_size = 0

    def accept(self, name: str, version_hash: str, row: dict, raw_line: bytes) -> None:
        if name not in REVIEWED:
            g5.deny("EVALUATION_ROW_REACHED_CONTEXT_COLLECTOR")
        raw_version = g5.decode_copy_field(row.get("agent_version", b"\\N"))
        if (not isinstance(raw_version, str) or not raw_version
                or g5.sha(raw_version.encode("utf-8")) != version_hash):
            g5.deny("CONTEXT_VERSION_INVALID")
        if version_hash in self.labels and self.labels[version_hash] != raw_version:
            g5.deny("CONTEXT_VERSION_HASH_COLLISION")
        self.labels[version_hash] = raw_version
        self.approx_size += len(raw_line)
        if self.approx_size > MAX_REVIEW_BYTES:
            g5.deny("CONTEXT_REVIEW_SIZE_LIMIT")
        values = {column: g5.decode_copy_field(value) for column, value in row.items()}
        self.records[version_hash][name].append({
            "source_row_sha256": g5.sha(raw_line),
            "source_fields_unreviewed": values,
        })

    def packages(self, *, receipt: dict, lineage: dict, hints: dict, p3_sha: str) -> list[dict]:
        candidates = hints.get("candidates")
        if not isinstance(candidates, list):
            g5.deny("CANDIDATES_INVALID")
        by_version = defaultdict(list)
        known_records = {
            (version, item["source_row_sha256"])
            for version, tables in self.records.items()
            for name, records in tables.items()
            for item in records
        }
        for candidate in candidates:
            if (not isinstance(candidate, dict) or candidate.get("collection") not in REVIEWED
                    or not isinstance(candidate.get("source_version_sha256"), str)
                    or not isinstance(candidate.get("source_record_sha256"), str)
                    or (candidate["source_version_sha256"], candidate["source_record_sha256"])
                    not in known_records
                    or candidate.get("accounting_equivalence") != "NOT_ATTESTED"):
                g5.deny("UNVERIFIED_CANDIDATE_REFERENCE")
            by_version[candidate["source_version_sha256"]].append(candidate)
        packages = []
        for version_hash in sorted(self.labels):
            collections = self.records[version_hash]
            counts = {name: len(collections.get(name, [])) for name in sorted(REVIEWED)}
            packages.append({
                "contract": CONTRACT,
                "origin": {
                    "source_archive_sha256": receipt["source_archive_sha256"],
                    "recovered_ciphertext_sha256": lineage["recovered_ciphertext_sha256"],
                    "p3_snapshot_sha256": p3_sha,
                    "source_version_sha256": version_hash,
                    "source_version": self.labels[version_hash],
                },
                "status": "QUARANTINED_SOURCE_EVIDENCE_UNAPPROVED",
                "tenant": None,
                "candidate_context_version": None,
                "can_import_into_semantic_catalog": False,
                "can_execute_financial_sql": False,
                "can_use_as_llm_or_planner_context": False,
                "financial_semantics_equivalence": "NOT_ATTESTED",
                "source_business_rules_are_unreviewed": True,
                "historical_sql_patterns_excluded": True,
                "row_counts": counts,
                "collections": {name: collections.get(name, []) for name in sorted(REVIEWED)},
                "physical_identifier_hints_unapproved": by_version.get(version_hash, []),
            })
        expected = {
            (scope["collection"], scope["version_sha256"]): scope["rows"]
            for scope in lineage.get("version_scope", []) if isinstance(scope, dict)
            and scope.get("collection") in REVIEWED
        }
        actual = {
            (name, version): len(records)
            for version, groups in self.records.items()
            for name, records in groups.items()
        }
        if actual != {k: v for k, v in expected.items() if v > 0}:
            g5.deny("CONTEXT_VERSION_ROWS_DO_NOT_MATCH_LINEAGE")
        return packages


def private_json(value: dict) -> bytes:
    data = (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n").encode("ascii")
    if len(data) > MAX_REVIEW_BYTES:
        g5.deny("CONTEXT_PACKET_SIZE_LIMIT")
    return data


def seal_gpg(path: Path, content: bytes, password: str) -> str:
    """Encrypt in memory to owner-only file. No plaintext file or CLI password."""
    g5.require_posix_io()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    pass_r, pass_w = os.pipe()
    proc = None
    try:
        proc = subprocess.Popen([
            "gpg", "--batch", "--no-tty", "--pinentry-mode", "loopback",
            "--no-symkey-cache", "--passphrase-fd", str(pass_r),
            "--symmetric", "--cipher-algo", "AES256", "--output", "-",
        ], stdin=subprocess.PIPE, stdout=fd, stderr=subprocess.DEVNULL,
            pass_fds=(pass_r,),
            env={k: os.environ[k] for k in ("HOME", "PATH", "LANG", "GNUPGHOME") if k in os.environ})
        os.close(pass_r)
        pass_r = -1
        with os.fdopen(pass_w, "wb") as secret:
            pass_w = -1
            secret.write(password.encode("ascii") + b"\n")
        proc.communicate(content, timeout=120)
        if proc.returncode != 0:
            g5.deny("CONTEXT_ENCRYPTION_FAILED")
    except (OSError, subprocess.TimeoutExpired, BrokenPipeError):
        g5.deny("CONTEXT_ENCRYPTION_FAILED")
    finally:
        if pass_r != -1:
            os.close(pass_r)
        if pass_w != -1:
            os.close(pass_w)
        os.close(fd)
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait()
    return g5.digest_private_file(path)


def verify_gpg(path: Path, password: str, expected: bytes) -> None:
    proc = g5.decrypt_gpg(path, password)
    try:
        assert proc.stdout is not None
        content = proc.stdout.read(len(expected) + 1)
        proc.stdout.close()
        status = proc.wait(timeout=120)
        if status != 0 or content != expected:
            g5.deny("CONTEXT_ENCRYPTED_ROUNDTRIP_FAILED")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def prepare_verified_context(receipt: dict, inventory: dict, lineage: dict,
                             hints: dict, p3: dict, p3_sha: str,
                             cipher: Path, password: str) -> tuple[list[dict], int]:
    cipher_sha = g5.digest_private_file(cipher)
    if (cipher_sha != receipt.get("output_sha256")
            or lineage.get("contract") != "g5-semantic-physical-lineage-v1"
            or lineage.get("recovered_ciphertext_sha256") != cipher_sha
            or lineage.get("p3_snapshot_sha256") != p3_sha
            or lineage.get("source_archive_sha256") != receipt.get("source_archive_sha256")
            or lineage.get("mapped_context_approved") is not False
            or lineage.get("financial_sql_executed") is not False
            or lineage.get("historical_sql_patterns_evaluation_only") is not True
            or hints.get("contract") != "g5-semantic-private-identifier-candidates-v1"
            or hints.get("p3_snapshot_sha256") != p3_sha
            or hints.get("source_archive_sha256") != receipt.get("source_archive_sha256")
            or hints.get("approved_for_context_activation") is not False):
        g5.deny("SOURCE_LINEAGE_PROVENANCE_INVALID")
    index, _ = g5.physical_shape(p3)
    collector = VersionedCollector()
    process = g5.decrypt_gpg(cipher, password)
    try:
        assert process.stdout is not None
        report, verified_hints = g5.scan(
            process.stdout, receipt, inventory, index, p3_sha=p3_sha,
            cipher_sha=cipher_sha, on_semantic_record=collector.accept,
        )
        process.stdout.close()
        if process.wait(timeout=120) != 0:
            g5.deny("SOURCE_GPG_DECRYPTION_INVALID")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
    if report != lineage or verified_hints != hints:
        g5.deny("INDEPENDENT_LINEAGE_RECONCILIATION_FAILED")
    packets = collector.packages(receipt=receipt, lineage=lineage, hints=hints, p3_sha=p3_sha)
    excluded_count = receipt["row_counts"].get(EXCLUDED, -1)
    if (len(packets) != len(collector.labels)
            or sum(sum(p["row_counts"].values()) for p in packets) + excluded_count
            != report["source_row_count"]):
        g5.deny("SOURCE_QUARANTINE_COVERAGE_INVALID")
    return packets, excluded_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--lineage-report", type=Path, required=True)
    parser.add_argument("--lineage-identifiers", type=Path, required=True)
    parser.add_argument("--p3-snapshot", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    print("G5_CONTEXT_MODE=OFFLINE_QUARANTINE_ONLY")
    try:
        receipt, _ = g5.read_json_private(args.receipt)
        inventory, _ = g5.read_json_private(args.inventory, 2_000_000)
        lineage, lineage_sha = g5.read_json_private(args.lineage_report, 2_000_000)
        hints, hints_sha = g5.read_json_private(args.lineage_identifiers, 3_000_000)
        p3, p3_sha = g5.read_json_private(args.p3_snapshot, 3_000_000)
        source_file = receipt.get("output_file")
        if (not isinstance(source_file, str) or Path(source_file).name != source_file
                or not source_file.endswith(".sql.gpg")
                or not g5.HEX_SHA.fullmatch(receipt.get("output_sha256", ""))):
            g5.deny("SOURCE_RECEIPT_INVALID")
        cipher = args.receipt.parent / source_file
        target = args.output_dir or args.receipt.parent / "g5-private-source-review-v1"
        g5_dir = target.parent
        require_private_directory(g5_dir)
        if not target.is_absolute() or target.exists() or target.is_symlink():
            g5.deny("REVIEW_OUTPUT_DIRECTORY_ALREADY_EXISTS")
        if not sys.stdin.isatty():
            g5.deny("INTERACTIVE_TERMINAL_REQUIRED")
        password = getpass.getpass("Senha EXISTENTE do backup G5 (sem eco): ")
        if not (g5.MIN_PASSWORD <= len(password) <= 256
                and all(33 <= ord(x) <= 126 for x in password)):
            g5.deny("SOURCE_PASSPHRASE_INVALID")
        packets, excluded_count = prepare_verified_context(
            receipt, inventory, lineage, hints, p3, p3_sha, cipher, password)
        os.mkdir(target, 0o700)
        try:
            receipts = []
            for packet in packets:
                data = private_json(packet)
                version_hash = packet["origin"]["source_version_sha256"]
                file = target / ("source-version-" + version_hash + ".json.gpg")
                ciphertext_sha = seal_gpg(file, data, password)
                verify_gpg(file, password, data)
                receipts.append({
                    "source_version_sha256": version_hash,
                    "file": file.name,
                    "ciphertext_sha256": ciphertext_sha,
                    "plaintext_sha256": hashlib.sha256(data).hexdigest(),
                    "row_counts": packet["row_counts"],
                    "identifier_hints_count": len(packet["physical_identifier_hints_unapproved"]),
                    "sealed_and_roundtrip_verified": True,
                })
            manifest = {
                "contract": "g5-private-source-review-manifest-v1",
                "status": "ENCRYPTED_NOT_APPROVED",
                "source_archive_sha256": receipt["source_archive_sha256"],
                "p3_snapshot_sha256": p3_sha,
                "lineage_report_sha256": lineage_sha,
                "lineage_identifier_sha256": hints_sha,
                "versions": receipts,
                "sql_pattern_rows_excluded": excluded_count,
                "financial_sql_executed": False,
                "context_activated": False,
                "approved_for_generation": False,
                "approved_for_import": False,
            }
            g5.private_write(target / "manifest.json", manifest)
        except BaseException:
            for file in target.iterdir():
                if file.is_file() and not file.is_symlink():
                    file.unlink()
            target.rmdir()
            raise
        print("G5_CONTEXT_RESULT=PASS")
        print("G5_CONTEXT_SEALED_VERSIONS=" + str(len(packets)))
        print("G5_CONTEXT_SEALED_ROWS=" + str(sum(sum(p["row_counts"].values()) for p in packets)))
        print("G5_CONTEXT_EVALUATION_ROWS_EXCLUDED=" + str(excluded_count))
        print("G5_CONTEXT_APPROVED=false")
        print("G5_CONTEXT_SQL_EXECUTED=false")
        print("G5_CONTEXT_OUTPUT=" + str(target / "manifest.json"))
        return 0
    except g5.Blocked as error:
        print("G5_CONTEXT_RESULT=BLOCKED")
        print("G5_CONTEXT_REASON=" + str(error))
        return 2
    except Exception:
        print("G5_CONTEXT_RESULT=BLOCKED")
        print("G5_CONTEXT_REASON=UNEXPECTED_ERROR")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

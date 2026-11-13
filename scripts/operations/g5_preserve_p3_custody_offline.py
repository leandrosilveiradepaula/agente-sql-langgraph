"""Custody transfer of an EXISTING G5-pinned P3 metadata snapshot (offline).

Copies exact original bytes after verifying the SHA from a sealed, previously
decrypted G5 packet. Does not capture fresh metadata, query any database,
modify n8n, select a financial mapping, import context, or execute SQL.
Both source and destination must be restricted local files/directories.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path

from scripts.operations.g5_financial_crosswalk_review import FinancialReviewBlocked
from scripts.operations.g5_financial_crosswalk_review_cli import (
    private_bytes, private_json,
)
from scripts.operations.g5_targeted_financial_review_offline import (
    ReviewBlocked, select_verified_seal, verify_decrypted_packet,
    write_private_once,
)

_P3_FIELDS = frozenset({
    "contract", "database", "role_name", "context_version", "context",
    "physical", "grants", "identity", "sql_executed", "llm_calls",
})


def refuse(code: str) -> None:
    raise FinancialReviewBlocked(code)


def preserve(
    *, manifest_path: Path, version_sha256: str, packet_path: Path,
    original_p3_file: Path, output_p3_file: Path,
) -> dict[str, int]:
    if os.name != "posix":
        refuse("G5_P3_POSIX_RESTRICTED_CUSTODY_REQUIRED")
    seal = select_verified_seal(private_json(manifest_path), version_sha256)
    packet, verified = verify_decrypted_packet(
        private_bytes(packet_path), seal,
    )
    original_sha = packet.get("origin", {}).get("p3_snapshot_sha256")
    if not isinstance(original_sha, str) or len(original_sha) != 64:
        refuse("G5_P3_SEALED_SOURCE_DIGEST_MISSING")

    if (
        not original_p3_file.is_absolute()
        or not output_p3_file.is_absolute()
        or original_p3_file == output_p3_file
        or output_p3_file.exists() or output_p3_file.is_symlink()
        or output_p3_file.parent != packet_path.parent
        or stat.S_IMODE(output_p3_file.parent.stat().st_mode) != 0o700
        or output_p3_file.parent.stat().st_uid != os.geteuid()
    ):
        refuse("G5_P3_CUSTODY_LOCATION_UNSAFE")

    p3_bytes = private_bytes(original_p3_file, 3_000_000)
    if hashlib.sha256(p3_bytes).hexdigest() != original_sha:
        refuse("G5_P3_ORIGINAL_DIGEST_MISMATCH")
    try:
        snapshot = json.loads(p3_bytes)
    except (ValueError, UnicodeError):
        refuse("G5_P3_METADATA_UNREADABLE")
    if (
        not isinstance(snapshot, dict)
        or set(snapshot) != _P3_FIELDS
        or snapshot.get("contract") != "p3-metadata-snapshot-v1"
        or snapshot.get("sql_executed") is not False
        or snapshot.get("llm_calls") != 0
        or not isinstance(snapshot.get("physical"), list)
        or not snapshot["physical"] or len(snapshot["physical"]) > 100000
        or not all(
            isinstance(row, list) and len(row) == 4
            and all(isinstance(value, str) and value for value in row)
            for row in snapshot["physical"]
        )
        or not isinstance(snapshot.get("context"), list)
        or not isinstance(snapshot.get("grants"), list)
        or not isinstance(snapshot.get("identity"), list)
        or len(snapshot["identity"]) != 14
    ):
        refuse("G5_P3_METADATA_SHAPE_UNVERIFIED")

    write_private_once(output_p3_file, p3_bytes)
    if (
        output_p3_file.read_bytes() != p3_bytes
        or stat.S_IMODE(output_p3_file.stat().st_mode) != 0o600
    ):
        refuse("G5_P3_COPY_NOT_ATTESTED")
    return {
        "source_rows": verified["source_row_count"],
        "physical_metadata_rows": len(snapshot["physical"]),
        "sql_executed": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-version-sha256", required=True)
    parser.add_argument("--g5-packet-file", required=True, type=Path)
    parser.add_argument("--original-p3-file", required=True, type=Path)
    parser.add_argument("--output-p3-file", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = preserve(
            manifest_path=args.manifest,
            version_sha256=args.source_version_sha256,
            packet_path=args.g5_packet_file,
            original_p3_file=args.original_p3_file,
            output_p3_file=args.output_p3_file,
        )
    except (ReviewBlocked, FinancialReviewBlocked, ValueError, OSError, TypeError):
        print("G5_P3_CUSTODY=BLOCKED")
        print("SQL_EXECUTED=false")
        print("LANGGRAPH_CONTEXT_ACTIVATED=false")
        return 2
    print("G5_P3_CUSTODY=PASS")
    print("G5_P3_PHYSICAL_METADATA_ROWS=" + str(result["physical_metadata_rows"]))
    print("G5_SOURCE_ROW_COUNT=" + str(result["source_rows"]))
    print("G5_P3_FINANCIAL_APPROVAL=false")
    print("SQL_EXECUTED=false")
    print("LANGGRAPH_CONTEXT_ACTIVATED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

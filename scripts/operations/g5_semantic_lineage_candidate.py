#!/usr/bin/env python3
"""G5: offline physical-lineage review for recovered versioned semantic catalogs.

No DB connection, SQL execution, provider invocation, schema activation, or
benchmark-as-generator. No financial rules or SQL-pattern contents are emitted.
Private review artifacts are technical hints, never approved financial mappings.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import getpass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

CATALOGS = frozenset((
    "ai_ducklake_agent_rules", "ai_ducklake_dre_mapping",
    "ai_ducklake_entity_aliases", "ai_ducklake_sql_patterns",
    "ai_ducklake_table_catalog",
))
EVALUATION_ONLY = "ai_ducklake_sql_patterns"
HEADER = re.compile(
    rb"^COPY public\.([A-Za-z_][A-Za-z0-9_]*) \(([A-Za-z_][A-Za-z0-9_]*"
    rb"(?:, [A-Za-z_][A-Za-z0-9_]*)*)\) FROM stdin;\r?\n$"
)
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
HEX_SHA = re.compile(r"^[a-f0-9]{64}$")
MAX_LINE = 16 * 1024 * 1024
MAX_PLAINTEXT = 1024 * 1024 * 1024
MIN_PASSWORD = 32


class Blocked(Exception):
    pass


def deny(reason: str) -> None:
    raise Blocked(reason)


def require_posix_io() -> None:
    """Owner-only, no-follow private I/O is deliberately Linux/POSIX only."""
    if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
            or not hasattr(os, "geteuid")):
        deny("PRIVATE_POSIX_REQUIRED")


def sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def read_private(path: Path, limit: int) -> bytes:
    if not path.is_absolute() or os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        deny("PRIVATE_POSIX_PATH_REQUIRED")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            s = os.fstat(fd)
            if (not stat.S_ISREG(s.st_mode) or s.st_uid != os.geteuid()
                    or (s.st_mode & 0o077) or s.st_size > limit):
                deny("PRIVATE_FILE_UNSAFE")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                result = stream.read(limit + 1)
            if len(result) > limit:
                deny("PRIVATE_FILE_LIMIT")
            return result
        finally:
            os.close(fd)
    except Blocked:
        raise
    except OSError:
        deny("PRIVATE_FILE_NOT_AVAILABLE")


def read_json_private(path: Path, limit: int = 256_000) -> tuple[dict, str]:
    raw = read_private(path, limit)
    try:
        parsed = json.loads(raw)
    except (ValueError, UnicodeError):
        deny("PRIVATE_JSON_INVALID")
    if not isinstance(parsed, dict):
        deny("PRIVATE_JSON_INVALID")
    return parsed, sha(raw)


def digest_private_file(path: Path) -> str:
    if not path.is_absolute() or os.name != "posix":
        deny("CIPHER_PATH_INVALID")
    h = hashlib.sha256()
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "rb") as f:
            s = os.fstat(f.fileno())
            if not stat.S_ISREG(s.st_mode) or s.st_uid != os.geteuid() or s.st_mode & 0o077:
                deny("CIPHER_FILE_UNSAFE")
            while part := f.read(1024 * 1024):
                h.update(part)
    except Blocked:
        raise
    except OSError:
        deny("CIPHER_FILE_NOT_AVAILABLE")
    return h.hexdigest()


def physical_shape(p3: dict) -> tuple[dict[str, dict[str, set[str]]], list]:
    if (p3.get("contract") != "p3-metadata-snapshot-v1"
            or p3.get("sql_executed") is not False
            or p3.get("llm_calls") != 0
            or not isinstance(p3.get("physical"), list)
            or not p3["physical"] or len(p3["physical"]) > 100_000):
        deny("P3_SNAPSHOT_SCOPE_INVALID")
    index: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for entry in p3["physical"]:
        if (not isinstance(entry, list) or len(entry) != 4
                or any(not isinstance(v, str) or not v for v in entry)
                or not all(IDENT.fullmatch(v) for v in entry[:3])):
            deny("P3_SNAPSHOT_PHYSICAL_INVALID")
        schema, table, column, _type = entry
        index[table][schema].add(column)
    return index, sorted({(row[0], row[1]) for row in p3["physical"]})


def decode_copy_field(raw: bytes) -> str | None:
    """COPY text escapes. Never evaluate the SQL contained in other columns."""
    if raw == b"\\N":
        return None
    output = bytearray()
    escapes = {ord("b"): 8, ord("f"): 12, ord("n"): 10,
               ord("r"): 13, ord("t"): 9, ord("v"): 11}
    i = 0
    while i < len(raw):
        ch = raw[i]
        if ch != 92:
            output.append(ch)
            i += 1
            continue
        i += 1
        if i >= len(raw):
            deny("COPY_ESCAPE_INVALID")
        nxt = raw[i]
        if nxt in escapes:
            output.append(escapes[nxt])
            i += 1
        elif nxt == ord("x"):
            i += 1
            start = i
            while i < len(raw) and i < start + 2 and chr(raw[i]) in "0123456789abcdefABCDEF":
                i += 1
            if i == start:
                deny("COPY_ESCAPE_INVALID")
            output.append(int(raw[start:i], 16))
        elif 48 <= nxt <= 55:
            start = i
            while i < len(raw) and i < start + 3 and 48 <= raw[i] <= 55:
                i += 1
            output.append(int(raw[start:i], 8))
        else:
            output.append(nxt)
            i += 1
    try:
        return output.decode("utf-8", "strict")
    except UnicodeDecodeError:
        deny("COPY_UTF8_INVALID")


def select_reference(index: dict, source_schema: str | None,
                     source_table: str | None) -> tuple[str, str | None, set[str]]:
    """Surface an *identifier* candidate; no accounting equivalence claim."""
    if (not source_table or not IDENT.fullmatch(source_table)
            or (source_schema and not IDENT.fullmatch(source_schema))):
        return "REFERENCE_INVALID", None, set()
    schemas = index.get(source_table) or {}
    if source_schema in schemas:
        return "EXACT_IDENTIFIER_ONLY", source_schema, schemas[source_schema]
    if len(schemas) == 1:
        only = next(iter(schemas))
        return "TABLE_NAME_ONLY", only, schemas[only]
    if len(schemas) > 1:
        return "AMBIGUOUS_TABLE_NAME", None, set()
    return "NO_PHYSICAL_NAME_MATCH", None, set()


def split_reference(value: str | None) -> tuple[str | None, str | None]:
    """Accept unqualified name, or schema-qualified table name. No SQL parse."""
    if value is None or not value.strip():
        return None, None
    parts = value.split(".")
    if len(parts) == 1 and IDENT.fullmatch(parts[0]):
        return None, parts[0]
    if len(parts) == 2 and all(IDENT.fullmatch(p) for p in parts):
        return parts[0], parts[1]
    return "<invalid>", "<invalid>"


def check_primary_key(columns: set[str], raw: str | None) -> str:
    if not raw:
        return "PRIMARY_KEY_NOT_DECLARED"
    # Can contain a composite list. Do not infer a key from SQL expressions.
    parts = [v.strip() for v in raw.split(",")]
    if not parts or not all(IDENT.fullmatch(v) for v in parts):
        return "PRIMARY_KEY_UNPARSEABLE"
    if all(p in columns for p in parts):
        return "PRIMARY_KEY_COLUMNS_EXIST"
    return "PRIMARY_KEY_COLUMNS_MISSING"


def scan(stream, receipt: dict, prior: dict, index: dict,
         *, p3_sha: str, cipher_sha: str, on_semantic_record=None) -> tuple[dict, dict]:
    if (receipt.get("version") != 1
            or set(receipt.get("selected_collections", [])) != CATALOGS
            or receipt.get("sql_executed") is not False
            or receipt.get("context_activated") is not False
            or not isinstance(receipt.get("row_counts"), dict)
            or not isinstance(receipt.get("decrypted_bytes"), int)
            or not isinstance(receipt.get("decrypted_sha256"), str)):
        deny("RECOVERY_RECEIPT_INVALID")
    if (prior.get("contract") != "g5-semantic-source-inventory-offline-v1"
            or prior.get("source_archive_sha256") != receipt.get("source_archive_sha256")
            or prior.get("recovered_ciphertext_sha256") != cipher_sha
            or prior.get("p3_snapshot_sha256") != p3_sha
            or prior.get("financial_sql_executed") is not False):
        deny("PRIOR_INVENTORY_MISMATCH")
    counters = Counter()
    source_row_hashes = {name: hashlib.sha256() for name in CATALOGS}
    versions = defaultdict(lambda: defaultdict(Counter))
    classifiers = Counter()
    suggestions = []
    current, columns = None, []
    found = set()
    stream_sha = hashlib.sha256()
    stream_size = 0
    while True:
        line = stream.readline(MAX_LINE + 1)
        if not line:
            break
        stream_size += len(line)
        stream_sha.update(line)
        if len(line) > MAX_LINE or stream_size > MAX_PLAINTEXT:
            deny("SOURCE_RESOURCE_LIMIT")
        if current is None:
            if not line.startswith(b"COPY "):
                continue  # Structural pg_restore prologue. Never execute it.
            m = HEADER.fullmatch(line)
            if not m:
                deny("COPY_HEADER_INVALID")
            current = m.group(1).decode("ascii")
            if current not in CATALOGS or current in found:
                deny("COPY_UNEXPECTED_COLLECTION")
            found.add(current)
            columns = m.group(2).decode("ascii").split(", ")
            if len(set(columns)) != len(columns) or "agent_version" not in columns:
                deny("COPY_COLUMNS_INVALID")
            continue
        if line in (b"\\.\n", b"\\.\r\n"):
            current, columns = None, []
            continue
        if not line.endswith(b"\n"):
            deny("COPY_ROW_UNTERMINATED")
        fields = line[:-1].removesuffix(b"\r").split(b"\t")
        if len(fields) != len(columns):
            deny("COPY_FIELD_COUNT_MISMATCH")
        record = dict(zip(columns, fields))
        version_value = decode_copy_field(record["agent_version"])
        version_hash = sha((version_value if version_value is not None else "<NULL>").encode("utf-8"))
        counters[current] += 1
        source_row_hashes[current].update(line)
        versions[current][version_hash]["rows"] += 1
        if current == EVALUATION_ONLY:
            # Do not read sql_pattern, required_rules, benchmark examples or names.
            versions[current][version_hash]["evaluation_only"] += 1
            continue
        if on_semantic_record is not None:
            on_semantic_record(current, version_hash, record, line)
        if current == "ai_ducklake_table_catalog":
            source_schema = decode_copy_field(record.get("schema_name", b"\\N"))
            source_table = decode_copy_field(record.get("table_name", b"\\N"))
            status, target_schema, target_columns = select_reference(index, source_schema, source_table)
            key_status = (check_primary_key(target_columns, decode_copy_field(record.get("primary_key", b"\\N")))
                          if target_schema else "PRIMARY_KEY_UNRESOLVED")
            classifiers["catalog_" + status] += 1
            classifiers["catalog_" + key_status] += 1
            versions[current][version_hash][status] += 1
            suggestions.append({
                "collection": current, "source_version_sha256": version_hash,
                "source_record_sha256": sha(line), "source_schema": source_schema,
                "source_table": source_table, "physical_schema_candidate": target_schema,
                "candidate_status": status, "key_status": key_status,
                "accounting_equivalence": "NOT_ATTESTED",
            })
        elif current == "ai_ducklake_entity_aliases":
            target_ref = decode_copy_field(record.get("target_table", b"\\N"))
            target_column = decode_copy_field(record.get("target_column", b"\\N"))
            if not target_ref:
                kind = "SEMANTIC_ONLY_NO_PHYSICAL_TARGET"
                classifiers["alias_" + kind] += 1
                versions[current][version_hash][kind] += 1
                continue
            schema, name = split_reference(target_ref)
            status, mapped_schema, column_set = select_reference(index, schema, name)
            if mapped_schema and target_column:
                col_status = ("COLUMN_NAME_EXISTS" if target_column in column_set
                              else "COLUMN_NAME_MISSING")
            elif mapped_schema:
                col_status = "COLUMN_NOT_SPECIFIED"
            else:
                col_status = "COLUMN_UNRESOLVED"
            classifiers["alias_" + status] += 1
            classifiers["alias_" + col_status] += 1
            versions[current][version_hash][status] += 1
            suggestions.append({
                "collection": current, "source_version_sha256": version_hash,
                "source_record_sha256": sha(line), "source_table_ref": target_ref,
                "source_column_ref": target_column,
                "physical_schema_candidate": mapped_schema,
                "candidate_status": status, "column_status": col_status,
                "accounting_equivalence": "NOT_ATTESTED",
            })
        elif current == "ai_ducklake_dre_mapping":
            # Only evidence of explicit sign conventions, not accounting truth.
            sign_value = decode_copy_field(record.get("sign_convention", b"\\N"))
            versions[current][version_hash]["sign_declared" if sign_value else "sign_absent"] += 1
            classifiers["dre_sign_declared" if sign_value else "dre_sign_absent"] += 1
        elif current == "ai_ducklake_agent_rules":
            # Rule text is intentionally NOT decoded, printed, or used as generator input.
            status = decode_copy_field(record.get("is_active", b"\\N"))
            if status in ("t", "true", "1"):
                label = "rule_active_at_backup"
            elif status in ("f", "false", "0"):
                label = "rule_inactive_at_backup"
            else:
                label = "rule_activation_unknown"
            classifiers[label] += 1
            versions[current][version_hash][label] += 1
    if current is not None or found != CATALOGS:
        deny("SOURCE_COLLECTION_INCOMPLETE")
    if stream_size != receipt["decrypted_bytes"] or stream_sha.hexdigest() != receipt["decrypted_sha256"]:
        deny("SOURCE_CONTENT_DIGEST_MISMATCH")
    if dict(counters) != receipt["row_counts"]:
        deny("SOURCE_COLLECTION_COUNT_MISMATCH")
    past = prior.get("source_collections")
    if not isinstance(past, list) or set(x.get("name") for x in past if isinstance(x, dict)) != CATALOGS:
        deny("PRIOR_COLLECTION_INVALID")
    for previous in past:
        name = previous["name"]
        if (previous["rows"] != counters[name]
                or previous["rows_sha256"] != source_row_hashes[name].hexdigest()):
            deny("PRIOR_SOURCE_ROWS_MISMATCH")
        prior_versions = {v["version_sha256"]: v["rows"] for v in previous["versions"]}
        current_versions = {v: c["rows"] for v, c in versions[name].items()}
        if current_versions != prior_versions:
            deny("PRIOR_SOURCE_VERSION_MISMATCH")
    report = {
        "contract": "g5-semantic-physical-lineage-v1",
        "source_archive_sha256": receipt["source_archive_sha256"],
        "recovered_ciphertext_sha256": cipher_sha,
        "p3_snapshot_sha256": p3_sha,
        "source_collection_count": len(CATALOGS),
        "source_row_count": sum(counters.values()),
        "source_version_count_per_collection": {
            name: len(versions[name]) for name in sorted(CATALOGS)
        },
        "version_scope": [
            {"collection": name, "version_sha256": version_hash, "rows": values["rows"],
             "classification_counts": dict(sorted((k, v) for k, v in values.items() if k != "rows"))}
            for name in sorted(CATALOGS)
            for version_hash, values in sorted(versions[name].items())
        ],
        "physical_evidence_counts": dict(sorted(classifiers.items())),
        "source_rules_not_rewritten": True,
        "historical_sql_patterns_evaluation_only": True,
        "mapped_context_approved": False,
        "source_reactivated": False,
        "financial_sql_executed": False,
        "semantic_agent_version_activated": False,
        "candidate_status": "PHYSICAL_NAME_CANDIDATES_NEED_BUSINESS_REVIEW",
    }
    # Contains only identifiers, never rule text, aliases' canonical values,
    # historical SQL, benchmark questions, or LLM/generator inputs.
    private_review = {
        "contract": "g5-semantic-private-identifier-candidates-v1",
        "source_archive_sha256": receipt["source_archive_sha256"],
        "p3_snapshot_sha256": p3_sha,
        "candidate_status": "UNAPPROVED_TECHNICAL_NAMES_ONLY",
        "source_context_versions_not_merged": True,
        "source_business_rules_excluded": True,
        "source_sql_patterns_excluded": True,
        "approved_for_context_activation": False,
        "approved_for_financial_sql": False,
        "candidates": suggestions,
    }
    return report, private_review


def decrypt_gpg(path: Path, passphrase: str) -> subprocess.Popen:
    require_posix_io()
    read_fd, write_fd = os.pipe()
    proc = None
    try:
        proc = subprocess.Popen(
            ["gpg", "--batch", "--no-tty", "--pinentry-mode", "loopback",
             "--no-symkey-cache", "--passphrase-fd", str(read_fd),
             "--decrypt", str(path)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, pass_fds=(read_fd,),
            env={k: os.environ[k] for k in ("HOME", "PATH", "LANG", "GNUPGHOME") if k in os.environ},
        )
    finally:
        os.close(read_fd)
    try:
        with os.fdopen(write_fd, "wb") as secret:
            secret.write(passphrase.encode("ascii") + b"\n")
    except (BrokenPipeError, OSError):
        if proc is not None:
            proc.kill()
            proc.wait()
        deny("GPG_AUTH_PIPE_FAILED")
    return proc


def private_write(path: Path, value: dict) -> None:
    require_posix_io()
    if not path.is_absolute() or path.parent.is_symlink():
        deny("OUTPUT_PATH_UNSAFE")
    if (not path.parent.is_dir() or path.parent.stat().st_uid != os.geteuid()
            or path.parent.stat().st_mode & 0o077):
        deny("OUTPUT_DIR_NOT_PRIVATE")
    data = (json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("ascii")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--p3-snapshot", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path)
    args = parser.parse_args(argv)
    print("G5_LINEAGE_MODE=OFFLINE_ONLY")
    try:
        receipt, _ = read_json_private(args.receipt)
        source_file = receipt.get("output_file")
        if (not isinstance(source_file, str) or source_file != Path(source_file).name
                or not source_file.endswith(".sql.gpg")
                or not HEX_SHA.fullmatch(receipt.get("output_sha256", ""))):
            deny("RECOVERY_RECEIPT_PATH_INVALID")
        cipher = args.receipt.parent / source_file
        ciphertext_sha = digest_private_file(cipher)
        if ciphertext_sha != receipt["output_sha256"]:
            deny("RECOVERY_CIPHERTEXT_DRIFT")
        prior, _ = read_json_private(args.inventory, 2_000_000)
        p3, p3_sha = read_json_private(args.p3_snapshot, 3_000_000)
        index, _ = physical_shape(p3)
        if not sys.stdin.isatty():
            deny("INTERACTIVE_TERMINAL_REQUIRED")
        passphrase = getpass.getpass("Senha EXISTENTE do backup G5 (sem eco): ")
        if (not MIN_PASSWORD <= len(passphrase) <= 256
                or any(not 33 <= ord(x) <= 126 for x in passphrase)):
            deny("PASSPHRASE_INVALID")
        proc = decrypt_gpg(cipher, passphrase)
        try:
            assert proc.stdout is not None
            report, private_review = scan(proc.stdout, receipt, prior, index,
                                          p3_sha=p3_sha, cipher_sha=ciphertext_sha)
            proc.stdout.close()
            if proc.wait(timeout=120) != 0:
                deny("GPG_DECRYPTION_FAILED")
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        out_dir = args.out_dir if args.out_dir else args.receipt.parent
        if (not out_dir.is_absolute() or out_dir.is_symlink() or not out_dir.is_dir()
                or out_dir.stat().st_uid != os.geteuid() or out_dir.stat().st_mode & 0o077):
            deny("OUTPUT_DIR_NOT_PRIVATE")
        report_path = out_dir / "source-semantic-lineage-v1.json"
        candidate_path = out_dir / "source-semantic-identifiers-unapproved-v1.json"
        if report_path.exists() or candidate_path.exists():
            deny("LINEAGE_REPORT_ALREADY_EXISTS")
        created = []
        try:
            private_write(report_path, report)
            created.append(report_path)
            private_write(candidate_path, private_review)
            created.append(candidate_path)
        except Exception:
            for path in created:
                path.unlink(missing_ok=True)
            raise
        print("G5_LINEAGE_RESULT=PASS")
        print("G5_LINEAGE_RECORDS=" + str(report["source_row_count"]))
        print("G5_LINEAGE_SOURCE_VERSIONS=" + ",".join(
            str(report["source_version_count_per_collection"][name])
            for name in sorted(CATALOGS)))
        for name, count in report["physical_evidence_counts"].items():
            print("G5_LINEAGE_" + name.upper() + "=" + str(count))
        print("G5_LINEAGE_CANDIDATES=" + str(len(private_review["candidates"])))
        print("G5_LINEAGE_APPROVED=false")
        print("G5_LINEAGE_SQL_EXECUTED=false")
        print("G5_LINEAGE_REPORT=" + str(report_path))
        return 0
    except Blocked as exc:
        print("G5_LINEAGE_RESULT=BLOCKED")
        print("G5_LINEAGE_REASON=" + str(exc))
        return 2
    except Exception:
        print("G5_LINEAGE_RESULT=BLOCKED")
        print("G5_LINEAGE_REASON=UNEXPECTED_ERROR")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

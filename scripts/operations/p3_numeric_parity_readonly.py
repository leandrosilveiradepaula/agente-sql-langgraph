"""P3 independent same-snapshot SQL result comparator.

This is NOT LangGraph Execute Approved, a n8n workflow, a benchmark runner,
or a generator. It cannot enable real SQL execution in the Shadow service.
Actual queries require a separately approved, pinned pair and operator gate.
Never include SQL, DSNs, raw values, or provider output in stdout.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, time, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any
from uuid import UUID

from app.domain.sql_analysis import SqlAnalysisError, analyze_sql
from app.domain.sql_security import run_sql_security_gate

SHA = re.compile(r"^[0-9a-f]{64}$")
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
MAX_FILE_BYTES = 650000
MAX_SQL_BYTES = 262144
EXEC_CONFIRM = "EXECUTE-P3-READONLY-COMPARISON"


class P3Blocked(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _fail(code: str) -> None:
    raise P3Blocked(code)


def _hash(content: bytes | str) -> str:
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _uuid(value: object) -> bool:
    try:
        return isinstance(value, str) and str(UUID(value)) == value.lower()
    except (ValueError, TypeError, AttributeError):
        return False


def _sha(value: object) -> bool:
    return isinstance(value, str) and SHA.fullmatch(value) is not None


def _label(value: object) -> bool:
    return isinstance(value, str) and LABEL.fullmatch(value) is not None


def _record(value: object, keys: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == keys


def _integer(value: object, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _private_json(path: Path) -> tuple[dict[str, Any], str]:
    # Protect local SQL manifests and policy from symlinks, group/world access.
    # File ownership and 0600 protections are POSIX-only. Never read or
    # execute a private SQL manifest on an unverified permission model.
    if os.name != "posix" or not hasattr(os, "geteuid") or not hasattr(os, "O_NOFOLLOW"):
        _fail("PRIVATE_FILES_POSIX_REQUIRED")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_mode & 0o077 or info.st_size > MAX_FILE_BYTES):
                _fail("PRIVATE_FILE_UNSAFE")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                blob = stream.read(MAX_FILE_BYTES + 1)
        finally:
            os.close(fd)
    except P3Blocked:
        raise
    except (OSError, ValueError):
        _fail("PRIVATE_FILE_UNAVAILABLE")
    if len(blob) > MAX_FILE_BYTES:
        _fail("PRIVATE_FILE_TOO_LARGE")
    try:
        parsed = json.loads(blob.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        _fail("PRIVATE_JSON_INVALID")
    if not isinstance(parsed, dict):
        _fail("PRIVATE_JSON_INVALID")
    return parsed, _hash(blob)


def _parse_policy(value: object) -> dict[str, Any]:
    required = {
        "contract_version", "organization_id", "expected_database",
        "expected_role", "authorized_relations", "authorized_functions",
        "max_rows", "max_result_bytes", "statement_timeout_ms",
        "lock_timeout_ms",
    }
    if not _record(value, required):
        _fail("POLICY_INVALID")
    policy = dict(value)
    if (policy["contract_version"] != "1"
            or not _uuid(policy["organization_id"])
            or not _label(policy["expected_database"])
            or not IDENT.fullmatch(str(policy["expected_role"]))):
        _fail("POLICY_INVALID")
    relations = policy["authorized_relations"]
    if (not isinstance(relations, list) or not 1 <= len(relations) <= 100
            or any(not isinstance(r, str) or len(r.split(".")) != 2
                   or not all(IDENT.fullmatch(part) for part in r.split("."))
                   for r in relations)
            or len(set(relations)) != len(relations)):
        _fail("POLICY_RELATIONS_INVALID")
    funcs = policy["authorized_functions"]
    if (not isinstance(funcs, list) or len(funcs) > 120
            or any(not isinstance(f, str) or not IDENT.fullmatch(f) or f != f.lower()
                   for f in funcs)
            or len(set(funcs)) != len(funcs)):
        _fail("POLICY_FUNCTIONS_INVALID")
    if (not _integer(policy["max_rows"], 1, 10000)
            or not _integer(policy["max_result_bytes"], 1024, 10000000)
            or not _integer(policy["statement_timeout_ms"], 1000, 30000)
            or not _integer(policy["lock_timeout_ms"], 100, 5000)):
        _fail("POLICY_LIMITS_INVALID")
    return policy


def _parse_pair(value: object, policy: dict[str, Any]) -> dict[str, Any]:
    required = {
        "contract_version", "agent_run_id", "organization_id",
        "question_sha256", "context_version", "official", "shadow",
    }
    if not _record(value, required):
        _fail("PAIR_INVALID")
    pair = dict(value)
    if (pair["contract_version"] != "1" or not _uuid(pair["agent_run_id"])
            or pair["organization_id"] != policy["organization_id"]
            or not _sha(pair["question_sha256"]) or not _label(pair["context_version"])):
        _fail("PAIR_IDENTITY_INVALID")
    shared = {
        "sql", "sql_sha256", "run_id", "provider_key", "model_key",
        "config_version", "question_sha256",
    }
    for side in ("official", "shadow"):
        x = pair[side]
        expected = shared | ({"shadow_record_id", "gates", "preflight_executed",
                              "requires_reapproval", "real_sql_executed"} if side == "shadow"
                             else set())
        if not _record(x, expected):
            _fail("PAIR_EVIDENCE_INVALID")
        if (not isinstance(x["sql"], str)
                or not 1 <= len(x["sql"].encode("utf-8")) <= MAX_SQL_BYTES
                or not _sha(x["sql_sha256"]) or _hash(x["sql"]) != x["sql_sha256"]
                or x["question_sha256"] != pair["question_sha256"]
                or any(not _label(x[key]) for key in
                       ("run_id", "provider_key", "model_key", "config_version"))):
            _fail("PAIR_EVIDENCE_INVALID")
    a, b = pair["official"], pair["shadow"]
    if any(a[key] != b[key] for key in ("provider_key", "model_key", "config_version")):
        _fail("PAIR_PROVIDER_PARITY_UNATTESTED")
    if (not _label(b["shadow_record_id"])
            or not _record(b["gates"], {"security", "contract", "preflight"})
            or any(status != "approved" for status in b["gates"].values())
            or b["preflight_executed"] is not False
            or b["requires_reapproval"] is not False
            or b["real_sql_executed"] is not False):
        _fail("PAIR_SHADOW_GATES_INVALID")
    return pair


def _guard_sql(sql: str, policy: dict[str, Any]) -> None:
    # Use the SAME security gate as LangGraph; the policy is external,
    # independently reviewed and versioned, never inferred from SQL.
    tables = policy["authorized_relations"]
    plan = {"planning_context": {
        "required_tables": [{"qualified_name": name} for name in tables],
        "allowed_schemas": sorted({name.split(".")[0] for name in tables}),
    }}
    try:
        result, analysis = run_sql_security_gate(current_sql=sql, query_plan=plan)
    except (SqlAnalysisError, ValueError, TypeError):
        _fail("SQL_SECURITY_UNAVAILABLE")
    if result["status"] != "approved" or not isinstance(analysis, dict):
        _fail("SQL_SECURITY_REJECTED")
    physical = [r for r in analysis.get("object_references", [])
                if not r.get("is_cte")]
    if not physical or any(not r.get("schema") for r in physical):
        _fail("SQL_EXPLICIT_SCHEMA_REQUIRED")
    if analysis.get("has_select_star") or analysis.get("has_table_star"):
        _fail("SQL_WILDCARD_NOT_ALLOWED")
    if any(f not in set(policy["authorized_functions"])
           for f in analysis.get("functions", [])):
        _fail("SQL_FUNCTION_NOT_ALLOWED")


def prepare(policy_doc: object, pair_doc: object) -> tuple[dict[str, Any], dict[str, Any]]:
    policy = _parse_policy(policy_doc)
    pair = _parse_pair(pair_doc, policy)
    for side in ("official", "shadow"):
        _guard_sql(pair[side]["sql"], policy)
    return policy, pair


def _typed(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return [type(value).__name__, value]
    if isinstance(value, Decimal):
        if not value.is_finite():
            _fail("RESULT_UNSUPPORTED_TYPE")
        # Decimal.normalize() uses the active decimal context and can ROUND
        # high-precision financial values (default precision is only 28).
        # Canonicalize the coefficient/exponent exactly, without arithmetic.
        parts = value.as_tuple()
        digits = "".join(str(digit) for digit in parts.digits).lstrip("0")
        if not digits:
            return ["numeric", [0, "0", 0]]
        exponent = parts.exponent
        if not isinstance(exponent, int):
            _fail("RESULT_UNSUPPORTED_TYPE")
        trailing = len(digits) - len(digits.rstrip("0"))
        if trailing:
            digits = digits[:-trailing]
            exponent += trailing
        return ["numeric", [int(parts.sign), digits, exponent]]
    if isinstance(value, float):
        if not math.isfinite(value):
            _fail("RESULT_UNSUPPORTED_TYPE")
        return ["float", repr(value)]
    if isinstance(value, datetime):
        return ["datetime", (value.astimezone(timezone.utc) if value.tzinfo
                             else value).isoformat()]
    if isinstance(value, (date, time)):
        return [type(value).__name__, value.isoformat()]
    if isinstance(value, UUID):
        return ["uuid", str(value)]
    if isinstance(value, (bytes, bytearray, memoryview)):
        return ["bytes-sha256", _hash(bytes(value))]
    if isinstance(value, (list, tuple)):
        return ["list", [_typed(x) for x in value]]
    if isinstance(value, dict) and all(isinstance(k, str) for k in value):
        return ["object", [[k, _typed(value[k])] for k in sorted(value)]]
    _fail("RESULT_UNSUPPORTED_TYPE")


def _collect(cursor: Any, sql: str, policy: dict[str, Any]) -> dict[str, Any]:
    # Extended protocol rejects stacked SQL statements at server boundary.
    cursor.execute(sql, prepare=True)
    columns = cursor.description
    if not columns or len(columns) > 100:
        _fail("RESULT_COLUMNS_INVALID")
    oids = tuple(int(c.type_code) for c in columns)
    rows: Counter[str] = Counter()
    count = size = 0
    while True:
        batch = cursor.fetchmany(128)
        if not batch:
            break
        for row in batch:
            count += 1
            if count > policy["max_rows"]:
                _fail("RESULT_ROWS_LIMIT")
            encoded = json.dumps([_typed(v) for v in row], sort_keys=True,
                                 ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            size += len(encoded)
            if size > policy["max_result_bytes"]:
                _fail("RESULT_BYTES_LIMIT")
            rows[_hash(encoded)] += 1
    return {"column_oids": oids, "row_count": count, "row_hashes": rows}


def _check_role(cursor: Any, policy: dict[str, Any]) -> None:
    cursor.execute(
        "SELECT current_user, current_database(), "
        "current_setting('transaction_read_only'), "
        "current_setting('transaction_isolation'), "
        "rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
        "FROM pg_catalog.pg_roles WHERE rolname=current_user"
    )
    row = cursor.fetchone()
    if (row is None or len(row) != 9 or row[0] != policy["expected_role"]
            or row[1] != policy["expected_database"] or row[2] != "on"
            or row[3] != "repeatable read" or any(row[4:])):
        _fail("READONLY_ROLE_UNVERIFIED")
    for relation in policy["authorized_relations"]:
        cursor.execute(
            "SELECT pg_catalog.has_table_privilege(current_user,%s,'SELECT'),"
            "pg_catalog.has_table_privilege(current_user,%s,"
            "'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')",
            (relation, relation),
        )
        privileges = cursor.fetchone()
        if privileges != (True, False):
            _fail("READONLY_RELATION_PRIVILEGES_UNVERIFIED")


def compare_readonly(policy: dict[str, Any], pair: dict[str, Any],
                     connect: Any) -> dict[str, Any]:
    # This function must only be invoked after separate human authorization.
    # A dedicated SELECT-only LOGIN, NOT an admin session with SET ROLE.
    with connect() as db:
        with db.cursor() as cursor:
            cursor.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            try:
                cursor.execute("SELECT pg_catalog.set_config('statement_timeout',%s,true)",
                               (str(policy["statement_timeout_ms"]) + "ms",))
                cursor.execute("SELECT pg_catalog.set_config('lock_timeout',%s,true)",
                               (str(policy["lock_timeout_ms"]) + "ms",))
                cursor.execute("SELECT pg_catalog.set_config('search_path','pg_catalog',true)")
                _check_role(cursor, policy)
                cursor.execute("SELECT pg_catalog.txid_current_snapshot()::text")
                snapshot = str(cursor.fetchone()[0])
                official = _collect(cursor, pair["official"]["sql"], policy)
                shadow = _collect(cursor, pair["shadow"]["sql"], policy)
            finally:
                cursor.execute("ROLLBACK")
    same_types = official["column_oids"] == shadow["column_oids"]
    same_rows = official["row_hashes"] == shadow["row_hashes"]
    non_empty = official["row_count"] > 0 and shadow["row_count"] > 0
    exact = bool(same_types and same_rows and non_empty)
    return {
        "status": ("exact_numeric_case_match" if exact else
                   "inconclusive_empty" if same_types and same_rows else
                   "numeric_case_difference"),
        "same_snapshot": True,
        "snapshot_fingerprint": _hash(snapshot),
        "row_counts": {"official": official["row_count"],
                       "shadow": shadow["row_count"]},
        "column_type_match": same_types,
        "exact_row_multiset_match": same_rows,
        "numeric_case_equivalence_proven": exact,
        # One matched case is NOT global financial parity.
        "financial_parity_proven": False,
        "shadow_real_sql_execution_enabled": False,
        "isolated_readonly_evaluation_executed": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", type=Path, required=True)
    parser.add_argument("--pair", type=Path, required=True)
    parser.add_argument("--execute-readonly", action="store_true")
    parser.add_argument("--approved-policy-sha256")
    parser.add_argument("--approved-pair-sha256")
    parser.add_argument("--approval-reference")
    args = parser.parse_args(argv)
    try:
        policy_raw, policy_hash = _private_json(args.policy)
        pair_raw, pair_hash = _private_json(args.pair)
        policy, pair = prepare(policy_raw, pair_raw)
        report: dict[str, Any] = {
            "P3_PREFLIGHT": "PASS",
            "policy_sha256": policy_hash,
            "pair_sha256": pair_hash,
            "agent_run_id": pair["agent_run_id"],
            "organization_id": pair["organization_id"],
            "official_sql_sha256": pair["official"]["sql_sha256"],
            "shadow_sql_sha256": pair["shadow"]["sql_sha256"],
            "isolated_readonly_evaluation_executed": False,
            "financial_parity_proven": False,
        }
        if args.execute_readonly:
            if (os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") != "false"
                    or not _sha(args.approved_policy_sha256)
                    or not _sha(args.approved_pair_sha256)
                    or args.approved_policy_sha256 != policy_hash
                    or args.approved_pair_sha256 != pair_hash
                    or not _label(args.approval_reference)
                    or not sys.stdin.isatty()):
                _fail("EXECUTION_APPROVAL_UNVERIFIED")
            if input("Confirm isolated financial SELECT with " + EXEC_CONFIRM + ": ").strip() != EXEC_CONFIRM:
                _fail("EXECUTION_NOT_CONFIRMED")
            if not os.environ.get("P3_READONLY_DSN"):
                _fail("READONLY_DSN_MISSING")
            import psycopg

            # No change to LangGraph config, n8n or dataset. No admin login.
            report.update(compare_readonly(
                policy, pair,
                lambda: psycopg.connect(
                    os.environ["P3_READONLY_DSN"], autocommit=True, connect_timeout=8
                ),
            ))
            report["approval_reference"] = args.approval_reference
        print(json.dumps(report, sort_keys=True))
        return 0 if report.get("status") != "numeric_case_difference" else 2
    except P3Blocked as exc:
        print(json.dumps({"P3_PREFLIGHT": "BLOCKED", "reason": exc.code,
                          "financial_parity_proven": False}, sort_keys=True))
        return 3
    except Exception:
        # psycopg errors often include SQL/DSN details; NEVER echo them.
        print(json.dumps({"P3_PREFLIGHT": "BLOCKED", "reason": "UNAVAILABLE",
                          "financial_parity_proven": False}, sort_keys=True))
        return 4


if __name__ == "__main__":
    raise SystemExit(main())

"""P3: verify *physical* scope before a same-dataset financial canary.

Metadata-only: SELECT on versioned semantic catalog + pg_catalog. No LLM,
financial-table SELECT, n8n write, GRANT, migration or cutover. The schema,
table and role are supplied by a reviewed external policy. A physical match
is NOT accounting-semantic validation or authority to execute financial SQL.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Mapping

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class AlignmentBlocked(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def deny(reason: str) -> None:
    raise AlignmentBlocked(reason)


def ident(value: Any) -> bool:
    return isinstance(value, str) and IDENT.fullmatch(value) is not None


def fingerprint(value: Any) -> str:
    return sha256(json.dumps(value, separators=(",", ":"), sort_keys=True,
                             ensure_ascii=True).encode("utf-8")).hexdigest()


def validate_policy(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(
        key in value for key in ("database", "role_name", "schema", "relations", "n8n")
    ):
        deny("POLICY_INVALID")
    if not all(ident(value[k]) for k in ("database", "role_name", "schema")):
        deny("POLICY_INVALID")
    names = value["relations"]
    if (not isinstance(names, list) or not 1 <= len(names) <= 100
            or len(set(str(v) for v in names)) != len(names)
            or any(not ident(v) for v in names)):
        deny("POLICY_RELATIONS_INVALID")
    n8n = value["n8n"]
    if (not isinstance(n8n, dict) or not isinstance(n8n.get("workflow_id"), str)
            or VERSION.fullmatch(n8n["workflow_id"]) is None
            or type(n8n.get("expected_node_count")) is not int
            or n8n["expected_node_count"] < 1
            or not isinstance(n8n.get("binding_node_ids"), list)
            or not n8n["binding_node_ids"]):
        deny("POLICY_WORKFLOW_INVALID")
    return value


def read_private_proof(path: Path) -> dict[str, str]:
    """Read sanitized CLI output only. Never print raw file or tool exceptions."""
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        deny("PROOF_POSIX_REQUIRED")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            mode = os.fstat(fd)
            if (not stat.S_ISREG(mode.st_mode) or mode.st_uid != os.geteuid()
                    or (mode.st_mode & 0o077) or mode.st_size > 50000):
                deny("PROOF_FILE_UNSAFE")
            data = os.read(fd, 50001).decode("ascii")
        finally:
            os.close(fd)
    except AlignmentBlocked:
        raise
    except (OSError, UnicodeError):
        deny("PROOF_FILE_UNAVAILABLE")
    if len(data) > 50000:
        deny("PROOF_FILE_UNSAFE")
    output: dict[str, str] = {}
    for line in data.splitlines():
        if not line:
            continue
        if "=" not in line:
            deny("PROOF_FORMAT_INVALID")
        key, value = line.split("=", 1)
        if (not re.fullmatch(r"[A-Z][A-Z0-9_]{2,95}", key)
                or not re.fullmatch(r"[A-Za-z0-9_./:-]{1,128}", value)
                or key in output):
            deny("PROOF_FORMAT_INVALID")
        output[key] = value
    return output


def verify_published(g1: Mapping[str, str] | None,
                     deps: Mapping[str, str] | None,
                     policy: Mapping[str, Any]) -> list[str]:
    blockers: list[str] = []
    if (not g1 or g1.get("G1_AUDIT_MODE") != "LOCAL_CLI_READ_ONLY"
            or g1.get("G1_AUDIT_RESULT") not in
            {"STRICT_PASS", "N8N_248_NORMALIZED_PASS"}
            or g1.get("G1_PUBLISHED_VERSION") != "ACTIVE_MATCH"
            or g1.get("G1_WORKFLOW_CONTRACT") != "PASS"
            or g1.get("G1_CREDENTIAL") != "ENCRYPTED_RECORD_MATCH"
            or g1.get("G1_NEW_BINDINGS") !=
            str(len(policy["n8n"]["binding_node_ids"]))
            or g1.get("G1_OLD_BINDINGS") != "0"
            or g1.get("G1_OTHER_BINDINGS") != "0"
            or g1.get("G1_UNAUTHORIZED_NODE_DRIFT") != "0"):
        blockers.append("N8N_PUBLISHED_NOT_ATTESTED")
    if (not deps or deps.get("SUPABASE_DEPENDENCY_AUDIT") != "READ_ONLY"
            or deps.get("SUPABASE_N8N_EXECUTION_CREDENTIAL_TARGET") != "DEMO"
            or deps.get("SUPABASE_N8N_EXECUTION_ROLE_ATTESTED") != "PASS"
            or deps.get("SUPABASE_SHADOW_CONTEXT_TARGET") != "DEMO"
            or deps.get("SUPABASE_SHADOW_EVIDENCE_TARGET") != "DEMO"
            or deps.get("SUPABASE_SHADOW_REAL_SQL_EXECUTION_DISABLED") != "PASS"
            or deps.get("SUPABASE_N8N_OFFICIAL_NODE_COUNT") !=
            str(policy["n8n"]["expected_node_count"])):
        blockers.append("N8N_DATASOURCE_NOT_ATTESTED")
    if deps:
        # The financial executor and other reachable PostgreSQL dependencies
        # are separate attestations. No valid canary with reachable SOURCE.
        if (deps.get("SUPABASE_N8N_REACHABLE_SOURCE_POSTGRES_NODES") is None
                or deps.get("SUPABASE_N8N_REACHABLE_UNKNOWN_POSTGRES_NODES") is None
                or deps.get("SUPABASE_N8N_REACHABLE_OTHER_SUPABASE_UNVERIFIED_POSTGRES_NODES") is None):
            blockers.append("N8N_REACHABLE_DEPENDENCIES_UNVERIFIED")
        elif any(deps.get(key) != "0" for key in (
            "SUPABASE_N8N_REACHABLE_SOURCE_POSTGRES_NODES",
            "SUPABASE_N8N_REACHABLE_UNKNOWN_POSTGRES_NODES",
            "SUPABASE_N8N_REACHABLE_OTHER_SUPABASE_UNVERIFIED_POSTGRES_NODES",
        )):
            blockers.append("N8N_REACHABLE_EXTERNAL_DEPENDENCIES")
    return blockers


def evaluate(policy: Mapping[str, Any], version: str,
             context: list[tuple[str, str]],
             physical: list[tuple[str, str, str, str]],
             role_rows: list[tuple[str, str, bool, bool]],
             role_identity: tuple[Any, ...],
             g1: Mapping[str, str] | None = None,
             deps: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Pure evaluation; independent of DB and client. No business mapping."""
    validate_policy(dict(policy))
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        deny("CONTEXT_VERSION_INVALID")
    official = {policy["schema"] + "." + n for n in policy["relations"]}
    selected = [f"{s}.{n}" for s, n in context if ident(s) and ident(n)]
    if len(selected) != len(context) or not selected or len(set(selected)) != len(selected):
        deny("CONTEXT_CATALOG_INVALID")
    catalog = set(selected)
    columns: dict[str, list[tuple[str, str]]] = {}
    for schema, table, column, kind in physical:
        if not all(ident(v) for v in (schema, table, column, kind)):
            deny("PHYSICAL_CATALOG_INVALID")
        columns.setdefault(f"{schema}.{table}", []).append((column, kind))
    readable, writable = set(), set()
    for schema, table, read, write in role_rows:
        if not ident(schema) or not ident(table) or type(read) is not bool or type(write) is not bool:
            deny("ROLE_SCOPE_INVALID")
        name = f"{schema}.{table}"
        if read:
            readable.add(name)
        if write:
            writable.add(name)
    # role: name, login, superuser, createdb, createrole, replication,
    # bypassrls, inherit, membership, database_create, temp,
    # creatable_schema_count, usable_sequence_count, definer_function_count.
    if (not isinstance(role_identity, tuple) or len(role_identity) != 14
            or role_identity[0] != policy["role_name"]
            or role_identity[1] is not True
            or any(v is not False for v in role_identity[2:11])
            or any(type(v) is not int or v != 0 for v in role_identity[11:])):
        deny("ROLE_NOT_LEAST_PRIVILEGED")
    blockers = verify_published(g1, deps, policy)
    if official != catalog:
        blockers.append("CONTEXT_SOURCE_MISMATCH")
    if official != readable:
        blockers.append("ROLE_SCOPE_MISMATCH")
    if writable:
        blockers.append("ROLE_WRITE_PRIVILEGE")
    if any(not columns.get(name) for name in official | catalog):
        blockers.append("PHYSICAL_COLUMNS_MISSING")
    shape = lambda names: [
        (name, sorted(columns.get(name, []))) for name in sorted(names)
    ]
    return {
        "status": "ready_for_semantic_review" if not blockers else "blocked",
        "blockers": sorted(set(blockers)),
        "version": version,
        "official_relation_count": len(official),
        "catalog_relation_count": len(catalog),
        "matched_relations": len(official & catalog),
        "effective_read_relations": len(readable),
        "official_fingerprint": fingerprint(shape(official)),
        "catalog_fingerprint": fingerprint(shape(catalog)),
        "semantic_mapping_approved": False,
        "numeric_parity_proven": False,
        "financial_sql_executed": False,
        "llm_calls": 0,
    }


def collect_metadata(cursor: Any, policy: Mapping[str, Any],
                     version: str, semantic_schema: str,
                     catalog_table: str = "ai_ducklake_table_catalog") -> tuple[list, list, list, tuple]:
    """Read only approved semantic table catalog and PostgreSQL system metadata."""
    from psycopg import sql
    if not ident(semantic_schema) or not ident(catalog_table):
        deny("SEMANTIC_SCHEMA_INVALID")
    cursor.execute(
        sql.SQL("SELECT schema_name,table_name FROM {}.{} "
                "WHERE agent_version=%s AND is_allowed IS TRUE").format(
                    sql.Identifier(semantic_schema),
                    sql.Identifier(catalog_table)),
        (version,),
    )
    context = cursor.fetchall()
    schemas = sorted({policy["schema"]} | {s for s, _ in context if ident(s)})
    cursor.execute(
        """SELECT n.nspname,c.relname,a.attname,t.typname
           FROM pg_catalog.pg_class c
           JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
           JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid
             AND a.attnum>0 AND NOT a.attisdropped
           JOIN pg_catalog.pg_type t ON t.oid=a.atttypid
           WHERE c.relkind IN ('r','v','m','p','f')
             AND n.nspname=ANY(%s::text[])""",
        (schemas,),
    )
    physical = cursor.fetchall()
    role = policy["role_name"]
    cursor.execute(
        """SELECT n.nspname,c.relname,
           pg_catalog.has_schema_privilege(%s,n.oid,'USAGE')
             AND pg_catalog.has_table_privilege(%s,c.oid,'SELECT'),
           pg_catalog.has_table_privilege(%s,c.oid,
             'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
           FROM pg_catalog.pg_class c
           JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
           WHERE c.relkind IN ('r','v','m','p','f')
             AND n.nspname NOT IN ('pg_catalog','information_schema')
             AND n.nspname NOT LIKE 'pg_toast%%'
             AND n.nspname NOT LIKE 'pg_temp%%'""",
        (role, role, role),
    )
    grants = cursor.fetchall()
    cursor.execute(
        """SELECT r.rolname,r.rolcanlogin,r.rolsuper,r.rolcreatedb,
           r.rolcreaterole,r.rolreplication,r.rolbypassrls,r.rolinherit,
           EXISTS(SELECT 1 FROM pg_catalog.pg_auth_members m WHERE m.member=r.oid),
           pg_catalog.has_database_privilege(r.oid,current_database(),'CREATE'),
           pg_catalog.has_database_privilege(r.oid,current_database(),'TEMPORARY'),
           (SELECT COUNT(*)::int FROM pg_catalog.pg_namespace n
             WHERE n.nspname NOT LIKE 'pg_toast%%'
             AND n.nspname NOT LIKE 'pg_temp%%'
             AND pg_catalog.has_schema_privilege(r.oid,n.oid,'CREATE')),
           (SELECT COUNT(*)::int FROM pg_catalog.pg_class c
             WHERE c.relkind='S'
             AND (pg_catalog.has_sequence_privilege(r.oid,c.oid,'SELECT')
               OR pg_catalog.has_sequence_privilege(r.oid,c.oid,'USAGE')
               OR pg_catalog.has_sequence_privilege(r.oid,c.oid,'UPDATE'))),
           (SELECT COUNT(*)::int FROM pg_catalog.pg_proc p
             JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
             WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog','information_schema')
             AND pg_catalog.has_schema_privilege(r.oid,n.oid,'USAGE')
             AND pg_catalog.has_function_privilege(r.oid,p.oid,'EXECUTE'))
           FROM pg_catalog.pg_roles r WHERE r.rolname=%s""",
        (role,),
    )
    identity = cursor.fetchone()
    if identity is None:
        deny("ROLE_NOT_FOUND")
    return context, physical, grants, tuple(identity)



def read_private_snapshot(path: Path, *, limit: int = 3000000) -> dict[str, Any]:
    """Read owner-only metadata; fail closed on symlink or non-POSIX."""
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        deny("SNAPSHOT_POSIX_REQUIRED")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or (info.st_mode & 0o077) or info.st_size > limit):
                deny("SNAPSHOT_FILE_UNSAFE")
            data = os.read(fd, limit + 1)
        finally:
            os.close(fd)
        if len(data) > limit:
            deny("SNAPSHOT_FILE_UNSAFE")
        result = json.loads(data)
    except AlignmentBlocked:
        raise
    except (OSError, ValueError, UnicodeError):
        deny("SNAPSHOT_INVALID")
    if not isinstance(result, dict):
        deny("SNAPSHOT_INVALID")
    return result


def verify_probe_snapshot(raw: Mapping[str, Any], policy: Mapping[str, Any],
                          version: str) -> tuple[list, list, list, tuple]:
    required = {
        "contract", "database", "role_name", "context_version",
        "context", "physical", "grants", "identity", "sql_executed",
        "llm_calls",
    }
    if (set(raw) != required
            or raw.get("contract") != "p3-metadata-snapshot-v1"
            or raw.get("database") != policy["database"]
            or raw.get("role_name") != policy["role_name"]
            or raw.get("context_version") != version
            or raw.get("sql_executed") is not False
            or raw.get("llm_calls") != 0):
        deny("SNAPSHOT_IDENTITY_MISMATCH")
    specs = (("context", 2), ("physical", 4), ("grants", 4))
    for field, columns in specs:
        group = raw.get(field)
        if (not isinstance(group, list) or len(group) > 100000
                or any(not isinstance(row, list) or len(row) != columns
                       for row in group)):
            deny("SNAPSHOT_SHAPE_INVALID")
    identity = raw.get("identity")
    if not isinstance(identity, list) or len(identity) != 14:
        deny("SNAPSHOT_SHAPE_INVALID")
    return (
        [tuple(v) for v in raw["context"]],
        [tuple(v) for v in raw["physical"]],
        [tuple(v) for v in raw["grants"]],
        tuple(identity),
    )


def probe_existing_shadow(version: str, semantic_schema: str,
                          catalog_table: str) -> int:
    """Run inside Shadow container using its private CONTEXT_POSTGRES_DSN."""
    if os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") != "false":
        deny("SHADOW_EXECUTION_FLAG_UNVERIFIED")
    if os.environ.get("SEMANTIC_AGENT_VERSION") != version:
        deny("SHADOW_CONTEXT_VERSION_MISMATCH")
    dsn = os.environ.get("CONTEXT_POSTGRES_DSN")
    if not dsn:
        deny("SHADOW_CONTEXT_DSN_MISSING")
    context_schema = os.environ.get("POSTGRES_CONTEXT_SCHEMA") or semantic_schema
    table = catalog_table
    config = os.environ.get("CONTEXT_CATALOG_TABLES_JSON")
    if config is not None:
        try:
            catalog_config = json.loads(config)
        except ValueError:
            deny("CONTEXT_TABLE_MAPPING_INVALID")
        if not isinstance(catalog_config, dict) or not ident(catalog_config.get("catalog")):
            deny("CONTEXT_TABLE_MAPPING_INVALID")
        table = catalog_config["catalog"]
    # Local operator only, no public HTTP and no DSN sent to host logs.
    raw = os.environ.get("P3_PHYSICAL_POLICY_JSON")
    if not raw or len(raw) > 65000:
        deny("PROBE_POLICY_MISSING")
    try:
        policy = validate_policy(json.loads(raw))
    except (ValueError, TypeError):
        deny("PROBE_POLICY_INVALID")
    import psycopg
    with psycopg.connect(dsn, autocommit=True, connect_timeout=8) as conn:
        with conn.cursor() as cursor:
            cursor.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute(
                "SELECT pg_catalog.set_config('statement_timeout','10000',true)"
            )
            cursor.execute("SELECT current_database()")
            database = cursor.fetchone()[0]
            if database != policy["database"]:
                deny("DATABASE_MISMATCH")
            result = collect_metadata(cursor, policy, version, context_schema, table)
            cursor.execute("ROLLBACK")
    context, physical, grants, identity = result
    print(json.dumps({
        "contract": "p3-metadata-snapshot-v1",
        "database": database, "role_name": policy["role_name"],
        "context_version": version, "context": context, "physical": physical,
        "grants": grants, "identity": identity,
        "sql_executed": False, "llm_calls": 0,
    }, sort_keys=True))
    return 0


def schema_draft(policy: Mapping[str, Any],
                 physical: list[tuple[str, str, str, str]]) -> dict[str, Any]:
    """Generate a non-executable physical inventory with NO business assumptions."""
    entries: list[dict[str, Any]] = []
    for table in sorted(policy["relations"]):
        cols = sorted((column, kind)
                      for schema, name, column, kind in physical
                      if schema == policy["schema"] and name == table)
        entries.append({
            "schema": policy["schema"], "table": table,
            "columns": [{"name": column, "postgres_type": kind} for column, kind in cols],
            "approved_grain": None, "approved_joins": None,
            "approved_metrics": None, "approved_dimensions": None,
            "approved_date_semantics": None, "approved_sign_conventions": None,
            "approved_dre": None, "review": "UNMAPPED",
        })
    return {
        "kind": "p3-physical-schema-review-draft-v1",
        "status": "UNAPPROVED_NOT_AN_AGENT_CONTEXT",
        "tables": entries,
        "can_import_into_semantic_catalog": False,
        "can_execute_financial_sql": False,
    }


def create_private_draft(path: Path, document: Mapping[str, Any]) -> None:
    if os.name != "posix" or not hasattr(os, "O_NOFOLLOW"):
        deny("PRIVATE_POSIX_REQUIRED")
    try:
        folder = path.parent.stat()
        if (not stat.S_ISDIR(folder.st_mode) or folder.st_uid != os.geteuid()
                or folder.st_mode & 0o077):
            deny("PRIVATE_DIRECTORY_REQUIRED")
        content = (json.dumps(document, sort_keys=True) + "\n").encode("utf-8")
        if len(content) > 2000000:
            deny("PRIVATE_DRAFT_TOO_LARGE")
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(fd, "wb", closefd=False) as stream:
                stream.write(content)
        finally:
            os.close(fd)
    except AlignmentBlocked:
        raise
    except OSError:
        deny("PRIVATE_DRAFT_WRITE_BLOCKED")

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--policy", type=Path)
    p.add_argument("--context-version", required=True)
    p.add_argument("--semantic-schema", default="semantic_context")
    p.add_argument("--catalog-table", default="ai_ducklake_table_catalog")
    p.add_argument("--g1-proof", type=Path)
    p.add_argument("--dependency-proof", type=Path)
    p.add_argument("--snapshot", type=Path)
    p.add_argument("--private-schema-draft", type=Path)
    p.add_argument("--probe-shadow", action="store_true")
    args = p.parse_args(argv)
    try:
        if not isinstance(args.context_version, str) or not VERSION.fullmatch(args.context_version):
            deny("CONTEXT_VERSION_INVALID")
        if args.probe_shadow:
            return probe_existing_shadow(args.context_version, args.semantic_schema,
                                         args.catalog_table)
        if args.policy is None:
            deny("SOURCE_POLICY_REQUIRED")
        policy = validate_policy(json.loads(args.policy.read_text(encoding="utf-8")))
        g1 = read_private_proof(args.g1_proof) if args.g1_proof else None
        deps = read_private_proof(args.dependency_proof) if args.dependency_proof else None
        if args.snapshot:
            result = verify_probe_snapshot(read_private_snapshot(args.snapshot),
                                           policy, args.context_version)
        else:
            dsn = os.environ.get("P3_METADATA_DSN")
            if not dsn:
                deny("P3_METADATA_DSN_MISSING")
            import psycopg
            with psycopg.connect(dsn, autocommit=True, connect_timeout=8) as conn:
                with conn.cursor() as cursor:
                    cursor.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
                    cursor.execute(
                        "SELECT pg_catalog.set_config('statement_timeout','10000',true)"
                    )
                    cursor.execute("SELECT current_database()")
                    if cursor.fetchone()[0] != policy["database"]:
                        deny("DATABASE_MISMATCH")
                    result = collect_metadata(cursor, policy, args.context_version,
                                              args.semantic_schema,args.catalog_table)
                    cursor.execute("ROLLBACK")
        report = evaluate(policy, args.context_version, *result, g1=g1, deps=deps)
        if args.private_schema_draft:
            create_private_draft(args.private_schema_draft,
                                 schema_draft(policy, result[1]))
            report["private_draft_written"] = True
        print(json.dumps(report, sort_keys=True))
        return 0 if report["status"] == "ready_for_semantic_review" else 2
    except AlignmentBlocked as exc:
        print(json.dumps({"status": "blocked", "reason": exc.reason,
                          "financial_sql_executed": False, "llm_calls": 0}))
        return 2
    except Exception:
        # psycopg exceptions can contain SQL/connection metadata.
        print(json.dumps({"status": "blocked", "reason": "METADATA_UNAVAILABLE",
                          "financial_sql_executed": False, "llm_calls": 0}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""J2/G4: read two *physical* semantic catalogs via independent SELECT-only roles.

This runs only inside the disposable PostgreSQL 16 GitHub Actions container,
without warehouse access, n8n activation, paid LLMs, benchmark material,
deployment changes or financial SQL execution.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb

from app.adapters.postgres.context_repository import PostgresContextRepository
from app.adapters.testing.fake_shadow_evidence_repository import (
    FakeShadowEvidenceRepository,
)
from app.domain.context_validator import validate_context_snapshot
from app.ports.context_repository import ContextRepositoryError
from app.test_runtime.composition import create_shadow_test_runtime
from app.test_runtime.offline_adapters import (
    ShadowTestSqlGenerator, ShadowTestSqlRepairer,
)
from scripts.validation.test_shadow_evidence_integrity_postgres import (
    _require_disposable_environment,
)
from testar_shadow_context_portability_e2e import (
    _raw_alternative, _raw_base, _request,
)
from testar_shadow_test_runtime import _env, _run_asgi

# These identifiers and credentials belong ONLY to the temporary CI fixture;
# they are never used in the application or persisted customer configuration.
CASES = (
    {
        "schema": "ci_semantic_alpha",
        "role": "ci_reader_alpha",
        "password": "fixture_alpha_only",
        "tenant": "tenant-A",
        "raw": _raw_base,
        "names": {
            "rules": "ai_ducklake_agent_rules",
            "entities": "ai_ducklake_entity_aliases",
            "dre": "ai_ducklake_dre_mapping",
            "patterns": "ai_ducklake_sql_patterns",
            "catalog": "ai_ducklake_table_catalog",
        },
        "question": "Execute uma generic analysis de teste.",
        "sql": "SELECT id FROM schema_test.table_test",
        "expected_schema": "schema_test",
    },
    {
        "schema": "ci_semantic_beta",
        "role": "ci_reader_beta",
        "password": "fixture_beta_only",
        "tenant": "tenant-B",
        "raw": _raw_alternative,
        "names": {
            "rules": "semantic_rules",
            "entities": "semantic_aliases",
            "dre": None,
            "patterns": "semantic_patterns",
            "catalog": "semantic_tables",
        },
        "question": "Execute uma invoice ledger analysis de teste.",
        "sql": "SELECT record_key FROM billing_archive.billing_entries",
        "expected_schema": "billing_archive",
    },
)

FIELDS = {
    "rules": (
        "rule_group", "rule_name", "rule_content", "applies_to_intents",
        "validation_hint", "severity", "priority",
    ),
    "entities": (
        "entity_type", "user_term", "canonical_value", "target_table",
        "target_column", "sql_filter_hint", "business_rule", "priority",
    ),
    "patterns": (
        "intent_name", "pattern_name", "business_question_examples",
        "required_tables", "required_rules", "sql_pattern", "notes", "priority",
    ),
    "catalog": (
        "table_name", "schema_name", "table_type", "description", "grain",
        "primary_key", "key_columns", "metric_columns", "date_columns",
        "join_rules", "ai_hint", "priority",
    ),
}
JSON_FIELDS = {
    "rules": frozenset(("applies_to_intents", "validation_hint")),
    "entities": frozenset(("sql_filter_hint", "business_rule")),
    "patterns": frozenset(("business_question_examples", "required_tables", "required_rules")),
    "catalog": frozenset((
        "grain", "primary_key", "key_columns", "metric_columns", "date_columns",
        "join_rules", "ai_hint",
    )),
}
COLLECTIONS = {
    "rules": "regras",
    "entities": "entidades",
    "patterns": "padroes",
    "catalog": "catalogo",
}
ORIGINAL_TABLES = {
    "rules": "ai_ducklake_agent_rules",
    "entities": "ai_ducklake_entity_aliases",
    "dre": "ai_ducklake_dre_mapping",
    "patterns": "ai_ducklake_sql_patterns",
    "catalog": "ai_ducklake_table_catalog",
}


def _template_ddl() -> dict[str, str]:
    fixture = (
        ROOT / "scripts/validation/v11_synthetic_postgres_fixture.sql"
    ).read_text(encoding="utf-8")
    start = fixture.index("CREATE TABLE ai_ducklake_agent_rules (")
    stop = fixture.index("INSERT INTO ai_ducklake_agent_rules (")
    ddl = [
        statement.strip() for statement in fixture[start:stop].split(";")
        if statement.strip()
    ]
    if len(ddl) != 5:
        raise AssertionError("synthetic fixture schema contract drift")
    found = {}
    for key, original in ORIGINAL_TABLES.items():
        matches = [
            statement for statement in ddl
            if statement.startswith("CREATE TABLE " + original + " (")
        ]
        if len(matches) != 1:
            raise AssertionError("unexpected fixture table definition")
        found[key] = matches[0]
    return found


def _insert_rows(cursor, case: dict, raw: dict) -> None:
    for kind, collection in COLLECTIONS.items():
        table = case["names"][kind]
        assert isinstance(table, str)
        columns = ("agent_version",) + FIELDS[kind] + (
            ("is_allowed",) if kind == "catalog" else ("is_active",)
        )
        query = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
            sql.Identifier(case["schema"]),
            sql.Identifier(table),
            sql.SQL(", ").join(map(sql.Identifier, columns)),
            sql.SQL(", ").join(sql.Placeholder() for _ in columns),
        )
        for record in raw[collection]:
            values = [raw["semantic_agent_version"]]
            for field in FIELDS[kind]:
                value = record.get(field)
                if field == "rule_content" and kind == "rules":
                    value = json.dumps(value, ensure_ascii=False)
                elif field in JSON_FIELDS[kind] and value is not None:
                    value = Jsonb(value)
                values.append(value)
            values.append(True)
            cursor.execute(query, tuple(values))


def _setup_fixture(dsn: str) -> None:
    definitions = _template_ddl()
    with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
        for case in CASES:
            schema = case["schema"]
            role = case["role"]
            cursor.execute(
                sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))
            )
            for kind, table in case["names"].items():
                if table is None:
                    continue  # Optional DRE: do not create a dummy tenant table.
                statement = definitions[kind].replace(
                    "CREATE TABLE " + ORIGINAL_TABLES[kind] + " (",
                    "CREATE TABLE " + table + " (",
                    1,
                )
                cursor.execute(
                    sql.SQL("SET LOCAL search_path TO {}").format(
                        sql.Identifier(schema)
                    )
                )
                cursor.execute(statement)
            raw = case["raw"]()
            _insert_rows(cursor, case, raw)
            cursor.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(case["password"])
                )
            )
            cursor.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(schema), sql.Identifier(role)
                )
            )
            cursor.execute(
                sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(
                    sql.Identifier(schema), sql.Identifier(role)
                )
            )
            cursor.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier("synthetic_ci"), sql.Identifier(role)
                )
            )


def _reader(case: dict, dsn: str, *, pin: str | None = None,
            schema_override: str | None = None) -> PostgresContextRepository:
    credentials = make_conninfo(
        dsn, user=case["role"], password=case["password"],
    )
    return PostgresContextRepository(
        dsn=credentials,
        semantic_agent_version=case["raw"]()["semantic_agent_version"],
        context_schema=schema_override or case["schema"],
        catalog_tables=case["names"],
        expected_context_fingerprint=pin,
    )


def _assert_acl(dsn: str) -> None:
    with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
        for index, case in enumerate(CASES):
            foreign = CASES[1 - index]
            for owner, allowed in ((case, True), (foreign, False)):
                relation = (
                    owner["schema"] + "." + owner["names"]["rules"]
                )
                cursor.execute(
                    "SELECT has_schema_privilege(%s, %s, 'USAGE'), "
                    "has_table_privilege(%s, %s, 'SELECT'), "
                    "has_table_privilege(%s, %s, 'INSERT')",
                    (
                        case["role"], owner["schema"],
                        case["role"], relation,
                        case["role"], relation,
                    ),
                )
                usage, read, write = cursor.fetchone()
                assert usage is allowed
                assert read is allowed
                assert write is False
            cursor.execute(
                "SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles "
                "WHERE rolname = %s",
                (case["role"],),
            )
            assert cursor.fetchone() == (False, False, False)
    print("J2_POSTGRES_SELECT_ONLY_ACL=PASS")


def _run_case(case: dict, dsn: str) -> tuple[str, PostgresContextRepository]:
    initial = _reader(case, dsn)
    snapshot = initial.load_active_context(user_profile="synthetic_ci")
    assert snapshot["version"] == case["raw"]()["semantic_agent_version"]
    assert snapshot["allowed_schemas"] == [case["expected_schema"]]
    assert snapshot["dre_mappings"] == []
    assert validate_context_snapshot(snapshot)["status"] == "valid"
    fingerprint = snapshot["fingerprint"]
    assert isinstance(fingerprint, str) and len(fingerprint) == 64

    pinned = _reader(case, dsn, pin=fingerprint)
    assert pinned.load_active_context(user_profile="synthetic_ci")["fingerprint"] == fingerprint

    provider = ShadowTestSqlGenerator(case["sql"])
    evidence = FakeShadowEvidenceRepository()
    env = _env(
        SEMANTIC_AGENT_VERSION=case["raw"]()["semantic_agent_version"],
        LANGGRAPH_EXPECTED_ORGANIZATION_ID=case["tenant"],
        SEMANTIC_CONTEXT_EXPECTED_FINGERPRINT=fingerprint,
        LANGGRAPH_ALLOW_REAL_SQL_EXECUTION="false",
    )
    runtime = create_shadow_test_runtime(
        env,
        context_repository_override=pinned,
        shadow_repository_override=evidence,
        sql_generator_override=provider,
        sql_repairer_override=ShadowTestSqlRepairer(case["sql"]),
    )
    assert runtime.config.allow_real_sql_execution is False
    code, response = _run_asgi(
        runtime.app, "POST", "/v1/internal/sql-agent/generate",
        _request(
            case["question"], "synthetic-pg-" + case["tenant"], case["tenant"],
        ),
    )
    assert code == 200 and response["status"] == "success"
    assert response["sql"] == case["sql"]
    assert provider.calls == 1
    assert evidence.create_calls >= 1

    other = CASES[0] if case is CASES[1] else CASES[1]
    denied, denied_body = _run_asgi(
        runtime.app, "POST", "/v1/internal/sql-agent/generate",
        _request(
            case["question"], "synthetic-foreign-" + case["tenant"],
            other["tenant"],
        ),
    )
    assert denied != 200 or denied_body.get("status") != "success"
    assert provider.calls == 1
    assert case["sql"] not in json.dumps(denied_body, ensure_ascii=False)
    print("J2_REAL_CONTEXT_" + case["tenant"] + "=PASS")
    return fingerprint, pinned


def _assert_database_cross_boundary(dsn: str) -> None:
    for index, case in enumerate(CASES):
        other = CASES[1 - index]
        # Use the other tenant's REAL physical table mapping. An unknown
        # table would also fail, but would not prove an ACL boundary.
        foreign_reader = PostgresContextRepository(
            dsn=make_conninfo(
                dsn, user=case["role"], password=case["password"],
            ),
            semantic_agent_version=other["raw"]()["semantic_agent_version"],
            context_schema=other["schema"],
            catalog_tables=other["names"],
        )
        try:
            foreign_reader.load_active_context(user_profile="synthetic_ci")
        except ContextRepositoryError as error:
            assert isinstance(
                error.__cause__, psycopg.errors.InsufficientPrivilege,
            ), "foreign context must fail specifically on PostgreSQL ACL"
        else:
            raise AssertionError("reader escaped its private metadata schema")
    print("J2_CROSS_TENANT_CONTEXT_READ=DENIED")


def _assert_mutated_catalog_rejected(dsn: str, approved_pin: str) -> None:
    beta = CASES[1]
    with psycopg.connect(dsn) as connection, connection.cursor() as cursor:
        cursor.execute(
            sql.SQL(
                "UPDATE {}.{} SET metric_columns = %s "
                "WHERE agent_version = %s"
            ).format(
                sql.Identifier(beta["schema"]),
                sql.Identifier(beta["names"]["catalog"]),
            ),
            (
                Jsonb(["unapproved_fixture_metric"]),
                beta["raw"]()["semantic_agent_version"],
            ),
        )
        assert cursor.rowcount == 1
    reader = _reader(beta, dsn, pin=approved_pin)
    try:
        reader.load_active_context(user_profile="synthetic_ci")
    except ContextRepositoryError as error:
        assert error.__cause__ is None, (
            "drift must fail on approved fingerprint, not connection or SQL",
        )
    else:
        raise AssertionError("changed catalog bypassed approved fingerprint")
    # Verify the same failure is enforced BEFORE a generator can run.
    provider = ShadowTestSqlGenerator(beta["sql"])
    env = _env(
        SEMANTIC_AGENT_VERSION=beta["raw"]()["semantic_agent_version"],
        LANGGRAPH_EXPECTED_ORGANIZATION_ID=beta["tenant"],
        SEMANTIC_CONTEXT_EXPECTED_FINGERPRINT=approved_pin,
        LANGGRAPH_ALLOW_REAL_SQL_EXECUTION="false",
    )
    runtime = create_shadow_test_runtime(
        env,
        context_repository_override=reader,
        shadow_repository_override=FakeShadowEvidenceRepository(),
        sql_generator_override=provider,
        sql_repairer_override=ShadowTestSqlRepairer(beta["sql"]),
    )
    code, result = _run_asgi(
        runtime.app, "POST", "/v1/internal/sql-agent/generate",
        _request(beta["question"], "j2-physical-drift", beta["tenant"]),
    )
    assert code != 200 or result.get("status") != "success"
    assert provider.calls == 0
    assert "unapproved_fixture_metric" not in json.dumps(result)
    assert beta["sql"] not in json.dumps(result)
    print("J2_CONTEXT_FINGERPRINT_DRIFT=DENIED")


def main() -> None:
    # Reject any real/non-CI connection before creating roles or schemas.
    dsn = _require_disposable_environment()
    _setup_fixture(dsn)
    _assert_acl(dsn)
    fingerprints = [_run_case(case, dsn)[0] for case in CASES]
    assert fingerprints[0] != fingerprints[1]
    _assert_database_cross_boundary(dsn)
    _assert_mutated_catalog_rejected(dsn, fingerprints[1])
    print("J2_REAL_POSTGRES_PORTABILITY=PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Never print DSNs/SQL, even if the fixture's code is later reused.
        print("J2_REAL_POSTGRES_PORTABILITY=FAIL", type(exc).__name__)
        raise SystemExit(1)

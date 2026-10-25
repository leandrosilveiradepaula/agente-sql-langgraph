from __future__ import annotations

import contextlib
import io
import os
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts" / "operations"))
import g1_public_acl_impact_audit as audit


class Cursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class CatalogDB:
    def __init__(self, *, public_temp=True, role_exists=False):
        self.public_temp = public_temp
        self.role_exists = role_exists
        self.readonly = False
        self.queries = []

    def execute(self, query, params=()):
        self.queries.append((query, params))
        if query == "SET TRANSACTION READ ONLY":
            self.readonly = True
            return Cursor(None)
        if not self.readonly:
            raise AssertionError("read-only transaction not established")
        if query == "SELECT current_database()":
            return Cursor(("database",))
        if query == audit.DATABASE_ACL_SQL:
            return Cursor((True, self.public_temp, False, 4))
        if query == audit.ROLE_ACTIVITY_SQL:
            return Cursor((10, 5, 2))
        if query == audit.SCHEMA_PUBLIC_USAGE_SQL:
            return Cursor((3,))
        if query == audit.PUBLIC_RELATIONS_SQL:
            return Cursor((2, 1, 0))
        if query == audit.PUBLIC_DEFINER_SQL:
            return Cursor((1,))
        if query == audit.ROLE_PRESENT_SQL:
            if params != ("readonly_role",):
                raise AssertionError("wrong target role")
            return Cursor((self.role_exists,))
        raise AssertionError("unexpected query")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class PublicAclAuditTests(unittest.TestCase):
    def setUp(self):
        self.config = {
            "database": "database", "role_name": "readonly_role",
        }
        self.dsn = (
            "postgresql://postgres.testprojref12:synthetic-secret"
            "@aws-0-us-west-2.pooler.supabase.com:5432/database"
            "?sslmode=verify-full"
        )

    def test_catalogue_audit_is_redacted_and_read_only(self):
        db = CatalogDB(public_temp=True)
        db.readonly = True
        output = audit.inventory(db, self.config)
        self.assertEqual(output["G1_PUBLIC_TEMPORARY"], "TRUE")
        self.assertEqual(output["G1_PUBLIC_CREATE"], "FALSE")
        self.assertEqual(output["G1_EXPLICIT_TEMP_GRANTEE_COUNT"], "4")
        self.assertEqual(output["G1_LOGIN_ROLES_WITH_CONNECT"], "10")
        self.assertEqual(output["G1_DB_ACTIVE_SESSIONS"], "2")
        self.assertEqual(output["G1_PUBLIC_READABLE_RELATION_COUNT"], "2")
        self.assertEqual(output["G1_PUBLIC_WRITABLE_RELATION_COUNT"], "1")
        self.assertEqual(output["G1_PUBLIC_EXECUTABLE_DEFINER_COUNT"], "1")
        self.assertEqual(output["G1_AUDIT_RESULT"], "REVIEW_REQUIRED")
        self.assertEqual(output["G1_TARGET_ROLE_EXISTS"], "FALSE")
        self.assertNotIn("postgres", str(output).lower())
        self.assertNotIn("secret", str(output).lower())
        self.assertNotIn("readonly_role", str(output).lower())
        self.assertTrue(all(q.lstrip().upper().startswith("SELECT")
                            for q, _ in db.queries))

    def test_role_present_is_reported_without_creation(self):
        db = CatalogDB(role_exists=True, public_temp=False)
        db.readonly = True
        output = audit.inventory(db, self.config)
        self.assertEqual(output["G1_PUBLIC_TEMPORARY"], "FALSE")
        self.assertEqual(output["G1_TARGET_ROLE_EXISTS"], "TRUE")
        self.assertFalse(any("CREATE ROLE" in q for q, _ in db.queries))

    def test_audit_rejects_wrong_database_without_other_queries(self):
        db = CatalogDB()
        db.readonly = True
        with self.assertRaises(audit.RolloutError):
            audit.inventory(db, {"database": "another", "role_name": "readonly_role"})
        self.assertEqual(len(db.queries), 1)

    def test_main_marks_transaction_readonly_before_catalogue_and_hides_dsn(self):
        db = CatalogDB()
        psycopg = types.SimpleNamespace(connect=lambda *a, **kw: db)
        cfg = types.SimpleNamespace(raw=self.config)
        capture = io.StringIO()
        with mock.patch.object(audit, "load_config", return_value=cfg), \
             mock.patch.object(audit, "require_verified_tls_dsn"), \
             mock.patch.object(audit, "pooler_template_from_admin_dsn"), \
             mock.patch.object(audit.getpass, "getpass", return_value=self.dsn), \
             mock.patch.dict(sys.modules, {"psycopg": psycopg}), \
             contextlib.redirect_stdout(capture):
            rc = audit.main(["--project-ref", "testprojref12"])
        self.assertEqual(rc, 0)
        self.assertTrue(db.readonly)
        self.assertEqual(db.queries[0][0], "SET TRANSACTION READ ONLY")
        self.assertEqual(db.queries[1][0], "SELECT current_database()")
        out = capture.getvalue()
        self.assertIn("G1_PUBLIC_TEMPORARY=TRUE", out)
        self.assertIn("G1_AUDIT_RESULT=REVIEW_REQUIRED", out)
        self.assertNotIn("synthetic-secret", out)
        self.assertNotIn("pooler.supabase.com", out)

    def test_main_redacts_driver_failure_and_never_runs_catalogue(self):
        db = CatalogDB()
        secret_message = "invalid password synthetic-secret at pooler.example"
        def fail(*args, **kwargs):
            raise RuntimeError(secret_message)
        psycopg = types.SimpleNamespace(connect=fail)
        cfg = types.SimpleNamespace(raw=self.config)
        capture = io.StringIO()
        with mock.patch.object(audit, "load_config", return_value=cfg), \
             mock.patch.object(audit, "require_verified_tls_dsn"), \
             mock.patch.object(audit, "pooler_template_from_admin_dsn"), \
             mock.patch.object(audit.getpass, "getpass", return_value=self.dsn), \
             mock.patch.dict(sys.modules, {"psycopg": psycopg}), \
             contextlib.redirect_stdout(capture):
            rc = audit.main(["--project-ref", "testprojref12"])
        self.assertEqual(rc, 2)
        out = capture.getvalue()
        self.assertIn("G1_FAIL_STAGE=CONNECT", out)
        self.assertNotIn(secret_message, out)
        self.assertNotIn(self.dsn, out)
        self.assertEqual(db.queries, [])

    def test_sql_queries_are_catalogue_only_and_no_business_identifiers(self):
        sql = "\n".join([
            audit.DATABASE_ACL_SQL, audit.ROLE_ACTIVITY_SQL,
            audit.SCHEMA_PUBLIC_USAGE_SQL, audit.PUBLIC_RELATIONS_SQL,
            audit.PUBLIC_DEFINER_SQL, audit.ROLE_PRESENT_SQL,
        ]).upper()
        for term in ("FROM PG_DATABASE", "FROM PG_NAMESPACE",
                     "FROM PG_PROC", "FROM PG_ROLES"):
            self.assertIn(term, sql)
        for statement in ("CREATE ROLE", "GRANT SELECT", "REVOKE ", "DROP TABLE"):
            self.assertNotIn(statement, sql)
        self.assertNotIn("RIVATTI", sql)
        self.assertNotIn("DRE", sql)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
import types
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts" / "operations"))
import g1_public_temp_preserve_roles as acl
from g1_readonly_rollout import RolloutError, private_snapshot


class Result:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeDatabase:
    def __init__(self):
        self.database = "finance_db"
        # Include a NOLOGIN role, a LOGIN role, a role with direct grant
        # and a built-in-like superuser, all with baseline TEMP privilege.
        self.roles = [
            (10, "admin", True),
            (11, "service_user", False),
            (12, "group_reader", False),
            (13, "direct_grantee", False),
        ]
        self.public_temp = True
        self.direct_temp = {10, 13}
        self.direct_connect = set()
        self.create_grants = {10}
        self.executed = []
        self.inject_role_drift = False

    def state(self):
        return deepcopy((self.roles, self.public_temp, self.direct_temp,
                         self.direct_connect, self.create_grants))

    def restore(self, state):
        (self.roles, self.public_temp, self.direct_temp,
         self.direct_connect, self.create_grants) = deepcopy(state)

    def transaction(self):
        db = self
        class Tx:
            def __enter__(self):
                self.initial = db.state()
                return self
            def __exit__(self, kind, value, traceback):
                if kind is not None:
                    db.restore(self.initial)
                return False
        return Tx()

    def execute(self, statement, params=()):
        self.executed.append(statement)
        if statement == acl.DB_ID_SQL:
            return Result([(self.database,)])
        if statement == acl.ROLE_SQL:
            assert params == (self.database,) * 3
            return Result([
                (oid, name, (self.public_temp or oid in self.direct_temp),
                 True, oid in self.create_grants)
                for oid, name, _super in self.roles
            ])
        if statement == acl.DB_ACL_SQL:
            assert params == (self.database,)
            grants = [(0, "CONNECT"), (10, "CREATE")]
            if self.public_temp:
                grants.append((0, "TEMPORARY"))
            grants.extend((oid, "TEMPORARY") for oid in self.direct_temp)
            grants.extend((oid, "CONNECT") for oid in self.direct_connect)
            return Result(sorted(grants))
        if statement.startswith("SET LOCAL "):
            return Result([])
        if statement == 'REVOKE TEMPORARY ON DATABASE "finance_db" FROM PUBLIC':
            self.public_temp = False
            if self.inject_role_drift:
                self.roles.append((14, "unapproved_new_role", False))
            return Result([])
        if statement == 'GRANT TEMPORARY ON DATABASE "finance_db" TO PUBLIC':
            self.public_temp = True
            return Result([])
        prefix = 'GRANT TEMPORARY ON DATABASE "finance_db" TO "'
        if statement.startswith(prefix):
            name = statement[len(prefix):-1].replace('""', '"')
            oid = next(x[0] for x in self.roles if x[1] == name)
            self.direct_temp.add(oid)
            return Result([])
        prefix = 'REVOKE TEMPORARY ON DATABASE "finance_db" FROM "'
        if statement.startswith(prefix):
            name = statement[len(prefix):-1].replace('""', '"')
            oid = next(x[0] for x in self.roles if x[1] == name)
            self.direct_temp.remove(oid)
            return Result([])
        raise AssertionError("unexpected statement")


class PreserveTempTests(unittest.TestCase):
    def test_catalogue_only_plan_does_not_mutate(self):
        db = FakeDatabase()
        old = db.state()
        before = acl.inventory(db, db.database)
        acl.preflight(before, "finance_reader")
        self.assertEqual(db.state(), old)
        self.assertEqual(len(before["roles"]), 4)
        self.assertTrue(all(
            s.lstrip().startswith(("SELECT", "SET")) for s in db.executed
        ))

    def test_preserves_existing_login_and_nologin_without_global_temp(self):
        db = FakeDatabase()
        before = acl.inventory(db, db.database)
        with db.transaction():
            compensated = acl.preserve_existing_roles(db, before, db.database, "finance_reader")
        self.assertEqual(compensated, [11, 12])
        self.assertFalse(db.public_temp)
        self.assertEqual(db.direct_temp, {10, 11, 12, 13})
        acl.validate_after(before, acl.inventory(db, db.database), compensated)
        self.assertFalse(any(s.startswith("CREATE ROLE") for s in db.executed))

    def test_rolls_back_atomically_when_privileges_drift(self):
        db = FakeDatabase()
        before = acl.inventory(db, db.database)
        db.inject_role_drift = True
        old = db.state()
        with self.assertRaisesRegex(RolloutError, "concorrencia"):
            with db.transaction():
                acl.preserve_existing_roles(db, before, db.database, "finance_reader")
        self.assertEqual(db.state(), old)

    def test_refuses_unexpected_extra_privileges(self):
        db = FakeDatabase()
        before = acl.inventory(db, db.database)
        with db.transaction():
            compensation = acl.preserve_existing_roles(db, before, db.database, "finance_reader")
        db.create_grants.add(11)
        with self.assertRaisesRegex(RolloutError, "privilegios existentes mudaram"):
            acl.validate_after(before, acl.inventory(db, db.database), compensation)
        db.create_grants.remove(11)
        db.direct_temp.add(99)
        with self.assertRaisesRegex(RolloutError, "ACL alem"):
            acl.validate_after(before, acl.inventory(db, db.database), compensation)

    def test_snapshot_verify_and_reversible_rollback_before_role_creation(self):
        db = FakeDatabase()
        original = acl.inventory(db, db.database)
        with db.transaction():
            compensated = acl.preserve_existing_roles(db, original, db.database, "finance_reader")
        snapshot = {
            "version": acl.VERSION, "database": db.database, "role_name": "finance_reader",
            "before": original, "compensated": compensated,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            private_snapshot(path, snapshot)
            read = acl._load_private(path)
            acl.verify(db, db.database, "finance_reader", read, allow_target=True)
            with db.transaction():
                acl.rollback(db, db.database, "finance_reader", read)
            self.assertEqual(acl.inventory(db, db.database), original)
            self.assertTrue(db.public_temp)
            if os.name != "nt":
                path.chmod(0o644)
                with self.assertRaisesRegex(RolloutError, "terceiros"):
                    acl._load_private(path)

    def test_rollback_refuses_after_a_new_role_is_created(self):
        db = FakeDatabase()
        before = acl.inventory(db, db.database)
        with db.transaction():
            compensated = acl.preserve_existing_roles(db, before, db.database, "finance_reader")
        db.roles.append((30, "finance_reader", False))
        db.direct_connect.add(30)
        record = {"version": acl.VERSION, "database": db.database,
                  "role_name": "finance_reader", "before": before,
                  "compensated": compensated}
        acl.verify(db, db.database, "finance_reader", record, allow_target=True)
        with self.assertRaisesRegex(RolloutError, "novas roles inesperadas"):
            with db.transaction():
                acl.rollback(db, db.database, "finance_reader", record)
        self.assertFalse(db.public_temp)

    def test_snapshot_cannot_be_used_for_another_database_or_role(self):
        db = FakeDatabase()
        before = acl.inventory(db, db.database)
        with db.transaction():
            compensated = acl.preserve_existing_roles(db, before, db.database, "finance_reader")
        record = {"version": acl.VERSION, "database": db.database,
                  "role_name": "finance_reader", "before": before, "compensated": compensated}
        with self.assertRaisesRegex(RolloutError, "outro banco"):
            acl.verify(db, "other", "finance_reader", record, allow_target=True)
        with self.assertRaisesRegex(RolloutError, "outro banco"):
            acl.verify(db, db.database, "other_role", record, allow_target=True)

    def test_missing_public_temp_or_existing_role_blocks_changes(self):
        db = FakeDatabase()
        before = acl.inventory(db, db.database)
        with self.assertRaisesRegex(RolloutError, "G1 ja existe"):
            acl.preflight(before, "service_user")
        db.public_temp = False
        with self.assertRaisesRegex(RolloutError, "PUBLIC TEMPORARY"):
            acl.preflight(acl.inventory(db, db.database), "finance_reader")
        self.assertFalse(any("REVOKE TEMPORARY" in x for x in db.executed))

    def test_main_defaults_to_read_only_and_redacts_dsn(self):
        db = FakeDatabase()
        dsn = "postgresql://postgres.example:s3cr3t@db.example.supabase.co/finance_db?sslmode=verify-full"
        conf = types.SimpleNamespace(raw={"database": "finance_db", "role_name": "finance_reader"})
        printed = io.StringIO()
        psycopg = types.SimpleNamespace(connect=lambda *args, **kwargs: contextlib.nullcontext(db))
        with mock.patch.object(acl, "load_config", return_value=conf), \
             mock.patch.object(acl, "require_verified_tls_dsn"), \
             mock.patch.object(acl.getpass, "getpass", return_value=dsn), \
             mock.patch.dict(sys.modules, {"psycopg": psycopg}), \
             contextlib.redirect_stdout(printed):
            rc = acl.main(["--project-ref", "syntheticproj12"])
        self.assertEqual(rc, 0)
        self.assertIn("P3_ACL_MUTATION=FALSE", printed.getvalue())
        self.assertNotIn("s3cr3t", printed.getvalue())
        self.assertNotIn("service_user", printed.getvalue())
        self.assertTrue(all(s.lstrip().startswith("SELECT") for s in db.executed))


if __name__ == "__main__":
    unittest.main()

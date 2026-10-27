from __future__ import annotations

import copy
import importlib.util
import json
import sys
import tempfile
import types
import unittest
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
OPS = ROOT / "scripts" / "operations"
sys.path.insert(0, str(OPS))
import g1_readonly_rollout as g1
import g1_resume_existing_role as resume


class Cursor:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class FakeDb:
    def __init__(self, events, readonly=False):
        self.events = events
        self.readonly = readonly

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    @contextmanager
    def transaction(self):
        self.events.append("BEGIN")
        yield self
        self.events.append("COMMIT")

    def execute(self, sql, *args):
        if sql.startswith("ALTER ROLE"):
            self.events.append("ALTER_ROLE")
            assert "PASSWORD 'SCRAM-SHA-256$" in sql
        if "rolconfig,rolconnlimit" in sql:
            return Cursor((
                ["default_transaction_read_only=on",
                 "statement_timeout=15s",
                 "idle_in_transaction_session_timeout=15s"], 5,
            ))
        return Cursor()


class FakeApi:
    def __init__(self, workflow, events, reject_post=False):
        self.workflow = copy.deepcopy(workflow)
        self.events = events
        self.credential = None
        self.reject_post = reject_post
        self.persist_then_fail = False

    def request(self, method, path, body=None):
        if method == "GET" and path.startswith("/api/v1/workflows/"):
            self.events.append("GET_WORKFLOW")
            return copy.deepcopy(self.workflow)
        if method == "GET" and path == "/api/v1/credentials/schema/postgres":
            return {"properties": {
                "host": {}, "port": {}, "database": {},
                "ssl": {"enum": ["require"]}, "user": {},
                "password": {}, "allowUnauthorizedCerts": {"type": "boolean"},
                "sshTunnel": {"type": "boolean"},
            }}
        if method == "POST" and path == "/api/v1/credentials":
            self.events.append("POST_CREDENTIAL")
            if self.reject_post:
                raise g1.RolloutError("n8n API HTTP_STATUS_403")
            self.credential = copy.deepcopy(body)
            if self.persist_then_fail:
                raise g1.RolloutError("n8n API HTTP_STATUS_502")
            return {"id": "credential-new", "name": body["name"], "type": "postgres"}
        if method == "PUT" and path.startswith("/api/v1/workflows/"):
            self.events.append("PUT_WORKFLOW")
            for key in ("name", "nodes", "settings", "connections", "staticData"):
                if key in body:
                    self.workflow[key] = copy.deepcopy(body[key])
            self.workflow["versionId"] = "published-v2"
            self.workflow["activeVersionId"] = "published-v2"
            return {"id": self.workflow["id"]}
        raise AssertionError("unapproved API call")


class ResumeG1Tests(unittest.TestCase):
    def setUp(self):
        self.ref = "fakeprojectid1234"
        self.dsn = (
            "postgresql://postgres." + self.ref + ":secret@"
            "aws-0-us-west-2.pooler.supabase.com:5432/database?sslmode=verify-full"
        )
        self.cfg = g1.RolloutConfig({
            "rollout_id": "test", "database": "database",
            "role_name": "readonly_role", "schema": "data",
            "relations": [f"table_{i}" for i in range(8)],
            "relation_types": ["BASE TABLE"],
            "n8n": {
                "workflow_id": "official", "workflow_name": "official test workflow",
                "expected_node_count": 68, "expected_n8n_version": "2.4.8",
                "webhook_path": "webhook", "credential_type": "postgres",
                "old_credential_id": "old",
                "old_credential_name": "Old Postgres account",
                "binding_node_ids": ["node-one", "node-two"],
                "connection_fields": {
                    "host": "host", "port": "port", "database": "database",
                    "ssl": "ssl", "user": "user", "password": "password",
                    "allow_unauthorized_certs": "allowUnauthorizedCerts",
                    "ssh_tunnel": "sshTunnel",
                },
            },
        })
        nodes = [
            {"id": node_id, "credentials": {"postgres": {"id": "old", "name": "Old Postgres account"}}}
            for node_id in ("node-one", "node-two")
        ]
        nodes += [
            {"id": f"node-{i}",
             "type": "n8n-nodes-base.webhook" if i == 0 else "n8n-nodes-base.noOp",
             "parameters": {"path": "webhook"} if i == 0 else {"name": f"node-{i}"}}
            for i in range(66)
        ]
        self.workflow = {
            "id": "official", "name": "official test workflow",
            "active": True, "versionId": "published-v1",
            "activeVersionId": "published-v1", "nodes": nodes,
            "settings": {}, "connections": {}, "pinData": {}, "meta": {},
        }
        self.events = []
        self.api = FakeApi(self.workflow, self.events)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.snapshot = Path(self.temp.name) / "g1-snapshot.json"
        self.fingerprint = g1.workflow_fingerprint(self.workflow)[:12]
        resume.STATE.update({
            "role": "NOT_CHECKED", "credential": "NOT_CREATED",
            "bindings": "NOT_CHECKED", "snapshot": "NOT_CREATED",
        })

    def run_case(self, recover=False, drift=False, confirm_action=None):
        calls = ["--n8n-url", "https://n8n.example",
                 "--project-ref", self.ref,
                 "--snapshot", str(self.snapshot),
                 "--expected-fingerprint", "000000000000" if drift else self.fingerprint]
        if recover:
            calls.append("--recover")
        with ExitStack() as stack:
            def patch(obj, name, value):
                stack.enter_context(mock.patch.object(obj, name, value))
            patch(resume, "load_config", lambda p: self.cfg)
            patch(resume, "find_n8n_container", lambda name: "n8n")
            patch(resume, "read_n8n_runtime_version", lambda *args: None)
            patch(resume, "inventory_credentials",
                  lambda *args: 1 if self.api.credential else 0)
            patch(resume, "N8nApi", lambda *args: self.api)
            patch(resume.getpass, "getpass",
                  lambda prompt: "test-api-key-01234567890" if "API key" in prompt else self.dsn)
            patch(resume, "validate_database", lambda *args: None)
            patch(resume, "_role_exists", lambda *args: True)
            patch(resume, "assert_role_effective_permissions", lambda *args: None)
            patch(resume, "confirm", confirm_action or (lambda *args: None))
            patch(resume, "verify_role",
                  lambda *args: self.events.append("VERIFY_LOGIN"))
            patch(resume.sys, "stderr", __import__("io").StringIO())
            stack.enter_context(mock.patch.dict(sys.modules, {
                "psycopg": types.SimpleNamespace(
                    connect=lambda dsn, autocommit=True: FakeDb(
                        self.events, readonly=dsn != self.dsn
                    )
                )
            }))
            return resume.main(calls)

    def test_dry_run_never_post_or_rotate_or_write_snapshot(self):
        self.assertEqual(self.run_case(), 0)
        self.assertNotIn("POST_CREDENTIAL", self.events)
        self.assertNotIn("ALTER_ROLE", self.events)
        self.assertNotIn("PUT_WORKFLOW", self.events)
        self.assertFalse(self.snapshot.exists())
        self.assertEqual(resume.STATE["role"], "EXISTING_SELECT_ONLY_VERIFIED")
        self.assertEqual(resume.STATE["bindings"], "OLD_BINDINGS_CONFIRMED")

    def test_403_before_rotation_leaves_role_and_workflow_unchanged(self):
        self.api.reject_post = True
        with self.assertRaisesRegex(g1.RolloutError, "HTTP_STATUS_403"):
            self.run_case(recover=True)
        self.assertIn("POST_CREDENTIAL", self.events)
        self.assertNotIn("ALTER_ROLE", self.events)
        self.assertNotIn("PUT_WORKFLOW", self.events)
        self.assertFalse(self.snapshot.exists())
        self.assertEqual(resume.STATE["credential"], "POST_OUTCOME_UNKNOWN")

    def test_successful_recovery_only_rotates_role_after_credential_created(self):
        self.assertEqual(self.run_case(recover=True), 0)
        self.assertEqual(self.events.count("POST_CREDENTIAL"), 1)
        self.assertIs(self.api.credential["data"]["sshTunnel"], False)
        self.assertIs(self.api.credential["data"]["allowUnauthorizedCerts"], False)
        self.assertEqual(self.events.count("ALTER_ROLE"), 1)
        self.assertEqual(self.events.count("PUT_WORKFLOW"), 1)
        self.assertLess(self.events.index("POST_CREDENTIAL"), self.events.index("ALTER_ROLE"))
        self.assertLess(self.events.index("ALTER_ROLE"), self.events.index("VERIFY_LOGIN"))
        self.assertLess(self.events.index("VERIFY_LOGIN"), self.events.index("PUT_WORKFLOW"))
        self.assertTrue(self.snapshot.exists())
        snapshot = json.loads(self.snapshot.read_text())
        self.assertEqual(snapshot["old_credential_id"], "old")
        self.assertEqual(snapshot["credential_id"], "credential-new")
        self.assertEqual(resume.STATE["bindings"], "PASS")
        self.assertEqual(resume.STATE["role"], "SELECT_ONLY_LOGIN_VERIFIED")
        g1.assert_binding_id(self.api.workflow, self.cfg, "credential-new")

    def test_drift_and_existing_snapshot_prevent_any_writes(self):
        with self.assertRaisesRegex(g1.RolloutError, "fingerprint mudou"):
            self.run_case(recover=True, drift=True)
        self.assertNotIn("POST_CREDENTIAL", self.events)
        self.snapshot.write_text("something")
        with self.assertRaisesRegex(g1.RolloutError, "snapshot G1 existente"):
            self.run_case(recover=True)
        self.assertNotIn("POST_CREDENTIAL", self.events)



    def test_ambiguous_post_result_may_persist_but_must_never_be_replayed(self):
        self.api.persist_then_fail = True
        with self.assertRaisesRegex(g1.RolloutError, "HTTP_STATUS_502"):
            self.run_case(recover=True)
        self.assertIsNotNone(self.api.credential)
        self.assertEqual(self.events.count("POST_CREDENTIAL"), 1)
        self.assertNotIn("ALTER_ROLE", self.events)
        self.assertNotIn("PUT_WORKFLOW", self.events)
        with self.assertRaisesRegex(g1.RolloutError, "credencial G1 encontrada"):
            self.run_case(recover=True)
        self.assertEqual(self.events.count("POST_CREDENTIAL"), 1)
        self.assertFalse(self.snapshot.exists())

    def test_concurrent_credential_during_confirmation_blocks_before_post(self):
        def concurrent_create(*args):
            self.api.credential = {
                "name": "readonly_role-20261027000000", "type": "postgres"
            }
        with self.assertRaisesRegex(g1.RolloutError, "durante confirmacao"):
            self.run_case(recover=True, confirm_action=concurrent_create)
        self.assertNotIn("POST_CREDENTIAL", self.events)
        self.assertNotIn("ALTER_ROLE", self.events)
        self.assertFalse(self.snapshot.exists())

    def test_concurrent_workflow_edit_during_confirmation_blocks_before_post(self):
        def concurrent_edit(*args):
            self.api.workflow["nodes"][2]["parameters"]["unrelated"] = "drift"
        with self.assertRaisesRegex(g1.RolloutError, "durante confirmacao"):
            self.run_case(recover=True, confirm_action=concurrent_edit)
        self.assertNotIn("POST_CREDENTIAL", self.events)
        self.assertNotIn("ALTER_ROLE", self.events)
        self.assertFalse(self.snapshot.exists())

    def test_role_settings_require_both_timeouts_and_connection_limit(self):
        resume._role_settings_complete(FakeDb([]), self.cfg.raw["role_name"])
        class BadDb:
            def execute(self, *args):
                return Cursor((["default_transaction_read_only=on"], 5))
        with self.assertRaises(g1.RolloutError):
            resume._role_settings_complete(BadDb(), self.cfg.raw["role_name"])


if __name__ == "__main__":
    unittest.main()

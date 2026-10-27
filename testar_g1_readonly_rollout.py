from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
import types
from unittest import mock
from contextlib import contextmanager
from urllib.parse import urlparse
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("g1_rollout", ROOT / "scripts" / "operations" / "g1_readonly_rollout.py")
assert SPEC and SPEC.loader
rollout = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = rollout
SPEC.loader.exec_module(rollout)


class G1ReadonlyRolloutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = rollout.RolloutConfig({
            "rollout_id": "test", "database": "database", "role_name": "readonly_role", "schema": "data",
            "relations": [f"relation_{index}" for index in range(8)], "relation_types": ["BASE TABLE"],
            "n8n": {
                "workflow_id": "workflow", "workflow_name": "workflow name", "expected_node_count": 68,
                "expected_n8n_version": "2.4.8", "webhook_path": "webhook", "credential_type": "postgres",
                "old_credential_id": "old", "binding_node_ids": ["one", "two"],
                "connection_fields": {"host": "host", "port": "port", "database": "database",
                    "ssl": "ssl", "user": "user", "password": "password",
                    "allow_unauthorized_certs": "allowUnauthorizedCerts"}
            }
        })
        self.workflow = {
            "id": self.config.n8n["workflow_id"], "name": self.config.n8n["workflow_name"],
            "active": True, "versionId": "version", "activeVersionId": "version", "n8nVersion": "2.4.8",
            "nodes": [
                {"id": node_id, "credentials": {"postgres": {"id": self.config.n8n["old_credential_id"], "name": "old"}}}
                for node_id in self.config.n8n["binding_node_ids"]
            ] + [{"id": f"node-{index}", "type": "n8n-nodes-base.webhook" if index == 0 else "n8n-nodes-base.noOp", "parameters": {"path": self.config.n8n["webhook_path"]} if index == 0 else {"test_value": index}}
                 for index in range(66)],
            "connections": {"node-0": {"main": [[]]}}, "settings": {}, "pinData": {}, "meta": {"safe": True}
        }

    def test_scram_is_deterministic_with_test_salt_and_never_contains_password(self) -> None:
        verifier = rollout.scram_verifier("not-a-real-password", salt=b"0123456789abcdef")
        self.assertTrue(verifier.startswith("SCRAM-SHA-256$4096:"))
        self.assertNotIn("not-a-real-password", verifier)

    def test_bad_tls_or_project_identity_fails_closed(self) -> None:
        with self.assertRaises(rollout.RolloutError):
            rollout.require_verified_tls_dsn("postgresql://postgres.bad@pooler.example/postgres?sslmode=require", "postgres", "expected")
        with self.assertRaises(rollout.RolloutError):
            rollout.require_verified_tls_dsn("postgresql://postgres.bad@pooler.example/other?sslmode=verify-full", "postgres", "bad")

    def test_preflight_rejects_draft_and_extra_old_credential_use(self) -> None:
        broken = json.loads(json.dumps(self.workflow))
        broken["activeVersionId"] = "draft"
        with self.assertRaises(rollout.RolloutError):
            rollout.validate_workflow(broken, self.config)
        broken = json.loads(json.dumps(self.workflow))
        broken["nodes"][2]["credentials"] = {"postgres": {"id": self.config.n8n["old_credential_id"]}}
        with self.assertRaises(rollout.RolloutError):
            rollout.validate_workflow(broken, self.config)

    def test_rebinding_changes_exactly_two_nodes_and_preserves_public_state(self) -> None:
        updated = rollout.rebind_only(self.workflow, self.config, "new-credential", "new")
        rollout.assert_only_two_rebindings(self.workflow, updated, self.config)
        self.assertEqual(updated["connections"], self.workflow["connections"])
        self.assertEqual(updated["nodes"][2], self.workflow["nodes"][2])
        updated["nodes"][2]["parameters"]["other"] = "drift"
        with self.assertRaises(rollout.RolloutError):
            rollout.assert_only_two_rebindings(self.workflow, updated, self.config)

    def test_snapshot_requires_private_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            rollout.private_snapshot(path, {"workflow": rollout.workflow_projection(self.workflow), "credential_id": "new"})
            self.assertEqual(rollout.read_private_snapshot(path)["credential_id"], "new")
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                path.chmod(0o644)
                with self.assertRaises(rollout.RolloutError):
                    rollout.read_private_snapshot(path)

    def test_database_preflight_rejects_missing_relation_public_dml_and_definer(self) -> None:
        class FakeDb:
            def __init__(self, relations, dml=(), definer=(),
                         public_temp=False, public_create=False, public_acl_missing=False):
                self.relations, self.dml, self.definer = relations, dml, definer
                self.public_temp, self.public_create = public_temp, public_create
                self.public_acl_missing = public_acl_missing
            def execute(self, query, params=()):
                class Cursor:
                    def __init__(self, rows): self.rows = rows
                    def fetchone(self): return self.rows[0] if self.rows else None
                    def fetchall(self): return self.rows
                if "current_database" in query: return Cursor([("database",)])
                if "FROM pg_database d" in query:
                    assert params == ("database",)
                    return Cursor([] if self.public_acl_missing else
                                  [(self.public_temp, self.public_create)])
                if "information_schema.tables" in query: return Cursor(self.relations)
                if "aclexplode" in query and "pg_class" in query: return Cursor([(item,) for item in self.dml])
                if "prosecdef" in query: return Cursor([(item,) for item in self.definer])
                raise AssertionError(query)
        relations = [(name, "BASE TABLE") for name in self.config.raw["relations"]]
        rollout.validate_database(FakeDb(relations), self.config)
        with self.assertRaises(rollout.RolloutError):
            rollout.validate_database(FakeDb(relations[:-1]), self.config)
        with self.assertRaises(rollout.RolloutError):
            rollout.validate_database(FakeDb(relations, dml=("relation_0",)), self.config)
        with self.assertRaises(rollout.RolloutError):
            rollout.validate_database(FakeDb(relations, definer=("123",)), self.config)
        with self.assertRaisesRegex(rollout.RolloutError, "PUBLIC tem TEMPORARY"):
            rollout.validate_database(FakeDb(relations, public_temp=True), self.config)
        with self.assertRaisesRegex(rollout.RolloutError, "PUBLIC tem CREATE"):
            rollout.validate_database(FakeDb(relations, public_create=True), self.config)
        with self.assertRaisesRegex(rollout.RolloutError, "PUBLIC tem TEMPORARY"):
            rollout.validate_database(FakeDb(relations, public_temp=True, public_create=True), self.config)
        with self.assertRaisesRegex(rollout.RolloutError, "nao verificavel"):
            rollout.validate_database(FakeDb(relations, public_acl_missing=True), self.config)

    def test_pooler_connection_never_reuses_old_user_and_requires_tls_template(self) -> None:
        template = {"host": "aws-0-us-west-2.pooler.supabase.com", "port": 6543, "database": "database", "ssl": "require"}
        dsn = rollout.build_pooler_dsn(template, self.config, "project", "private")
        self.assertIn("readonly_role.project", dsn)
        self.assertIn("sslmode=verify-full", dsn)
        template["ssl"] = False
        with self.assertRaises(rollout.RolloutError):
            rollout.build_pooler_dsn(template, self.config, "project", "private")


    def test_n8n_public_put_excludes_read_only_fields_and_retained_settings(self) -> None:
        live = json.loads(json.dumps(self.workflow))
        live["settings"] = {"executionOrder": "v1", "timeSavedMode": "fixed"}
        live["nodes"][2]["createdAt"] = "server timestamp"
        payload = rollout.workflow_projection(live)
        self.assertNotIn("timeSavedMode", payload["settings"])
        self.assertNotIn("createdAt", payload["nodes"][2])
        for key in ("pinData", "meta", "tags"):
            self.assertNotIn(key, payload)
        self.assertEqual(live["settings"]["timeSavedMode"], "fixed")
        live["settings"]["notARealSetting"] = True
        with self.assertRaises(rollout.RolloutError):
            rollout.workflow_projection(live)

    def test_redirect_handler_refuses_redirect_before_credential_transfer(self) -> None:
        handler = rollout._NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "Found", {}, "https://untrusted.example"))
        class RedirectingOpener:
            def open(self, request, timeout=20):
                raise OSError("HTTP redirect refused")
        api = rollout.N8nApi("https://n8n.example", "test-api-key-0123456789", opener=RedirectingOpener())
        with self.assertRaises(rollout.RolloutError):
            api.request("GET", "/api/v1/workflows/workflow")

    def test_snapshot_exclusivity_and_sql_public_acl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "snapshot.json"
            rollout.private_snapshot(path, {"workflow": self.workflow, "credential_id": "new"})
            with self.assertRaises(rollout.RolloutError):
                rollout.private_snapshot(path, {"workflow": self.workflow, "credential_id": "malicious"})

    def test_full_apply_verify_rollback_with_cursor_and_published_n8n_api(self) -> None:
        project_ref = "fakeprojectid1234"
        admin_dsn = ("postgresql://postgres." + project_ref + ":secret"
                     "@aws-0-us-west-2.pooler.supabase.com:5432/database?sslmode=verify-full")
        cfg, state = self.config, {
            "role": False, "writes": [], "api_payload": None,
            "public_temp": False, "public_create": False,
        }
        class Cursor:
            def __init__(self, rows=()): self.rows = list(rows)
            def fetchone(self): return self.rows[0] if self.rows else None
            def fetchall(self): return self.rows
        class DbConn:
            def __init__(self, readonly=False): self.readonly = readonly
            def execute(self, query, params=()):
                if query.startswith("SELECT current_database"): return Cursor([("database",)])
                if "information_schema.tables" in query:
                    return Cursor((name, "BASE TABLE") for name in cfg.raw["relations"])
                if "FROM pg_database d" in query:
                    return Cursor([(state["public_temp"], state["public_create"])])
                if "aclexplode" in query: return Cursor()
                if "FROM pg_roles WHERE rolname" in query and "SELECT 1" in query:
                    return Cursor([(1,)] if state["role"] else [])
                if "SELECT rolconfig FROM pg_roles" in query:
                    return Cursor([(["default_transaction_read_only=on", "statement_timeout=15s"],)])
                if "SELECT rolsuper" in query: return Cursor([(False,False,False,False,False,True,False)])
                if "FROM pg_auth_members" in query: return Cursor()
                if "has_database_privilege" in query: return Cursor([(False,)])
                if "FROM pg_class c" in query or "FROM pg_proc p" in query: return Cursor()
                if "SELECT current_user" in query:
                    return Cursor([("readonly_role", "database", "on")])
                if query.startswith('SELECT 1 FROM "data"'): return Cursor([(1,)])
                if query.startswith("CREATE ROLE"):
                    state["role"] = True
                    state["writes"].append("CREATE ROLE")
                    return Cursor()
                if query.startswith("GRANT ") or query.startswith("ALTER ROLE "):
                    state["writes"].append(query.split()[0])
                    return Cursor()
                raise AssertionError("unrecognized postgres query")
            @contextmanager
            def transaction(self):
                before = state["role"]
                try:
                    yield self
                except Exception:
                    state["role"] = before
                    raise
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def close(self): return None
        class FakeApi:
            def __init__(self, workflow):
                self.workflow = json.loads(json.dumps(workflow))
                self.new_credential = None
            def request(self, method, path, body=None):
                if method == "GET" and path == "/api/v1/workflows/workflow":
                    return json.loads(json.dumps(self.workflow))
                if method == "GET" and path == "/api/v1/credentials/schema/postgres":
                    return {"properties": {
                        "host": {}, "port": {}, "database": {}, "user": {},
                        "password": {}, "ssl": {"enum": ["disable", "allow", "require"]},
                        "allowUnauthorizedCerts": {"type": "boolean"},
                    }}
                # Exact n8n@2.4.8 public credential API: POST and schema GET
                # only. Credential list and ID GET endpoints do not exist.
                if method == "POST" and path == "/api/v1/credentials":
                    self_test_state = rollout.OPERATION_STATUS["bindings"]
                    assert self_test_state == "CREDENTIAL_POST_OUTCOME_UNKNOWN"
                    state["api_payload"] = json.loads(json.dumps(body))
                    return {"id": "new", "name": body["name"], "type": "postgres"}
                if method == "PUT" and path == "/api/v1/workflows/workflow":
                    assert "pinData" not in body and "meta" not in body
                    updated = json.loads(json.dumps(self.workflow))
                    for key in ("name", "nodes", "connections", "settings"):
                        updated[key] = body[key]
                    updated["versionId"] = "new-version"
                    updated["activeVersionId"] = "new-version"
                    self.workflow = updated
                    return {"id": "workflow"}
                raise AssertionError("unrecognized n8n request " + method + " " + path)
        api = FakeApi(self.workflow)
        conn_factory = lambda dsn, autocommit=True: DbConn(
            readonly=(urlparse(dsn).username or "").startswith("readonly_role.")
        )
        psycopg_stub = types.SimpleNamespace(connect=conn_factory)
        def secret_input(label):
            return "test-api-key-0123456789" if "API key" in label else admin_dsn
        def run(mode, snapshot):
            return rollout.main([
                mode, "--n8n-url", "https://n8n.example", "--project-ref", project_ref,
                "--snapshot", str(snapshot),
            ])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "g1-private.json"
            with mock.patch.object(rollout, "load_config", return_value=cfg), \
                 mock.patch.object(rollout, "read_n8n_runtime_version"), \
                 mock.patch.object(rollout, "N8nApi", return_value=api), \
                 mock.patch.object(rollout.getpass, "getpass", side_effect=secret_input), \
                 mock.patch.object(rollout, "confirm"), \
                 mock.patch.dict(sys.modules, {"psycopg": psycopg_stub}):
                # A real Supabase PUBLIC TEMP grant must stop even dry-run,
                # and --apply must never reach CREATE ROLE or n8n POST.
                state["public_temp"] = True
                with self.assertRaisesRegex(rollout.RolloutError, "PUBLIC tem TEMPORARY"):
                    run("--dry-run", path)
                with self.assertRaisesRegex(rollout.RolloutError, "PUBLIC tem TEMPORARY"):
                    run("--apply", path)
                self.assertFalse(state["role"])
                self.assertEqual(state["writes"], [])
                self.assertIsNone(state["api_payload"])
                state["public_temp"] = False

                self.assertEqual(run("--dry-run", path), 0)
                self.assertFalse(state["role"])
                self.assertEqual(run("--apply", path), 0)
                self.assertTrue(state["role"])
                self.assertEqual(state["api_payload"]["data"]["user"],
                                 "readonly_role." + project_ref)
                self.assertEqual(state["api_payload"]["data"]["ssl"], "require")
                self.assertIs(state["api_payload"]["data"]["allowUnauthorizedCerts"], False)
                self.assertNotIn("ignoreSSLIssues", state["api_payload"]["data"])
                self.assertTrue(path.exists())
                rollout.assert_binding_id(api.workflow, cfg, "new")
                self.assertEqual(run("--verify", path), 0)
                # A concurrent edit to another node must block rollback.
                api.workflow["nodes"][2]["parameters"]["unexpected"] = True
                with self.assertRaises(rollout.RolloutError):
                    run("--rollback", path)
                del api.workflow["nodes"][2]["parameters"]["unexpected"]
                self.assertEqual(run("--rollback", path), 0)
                rollout.assert_binding_id(api.workflow, cfg, "old")
                with self.assertRaises(rollout.RolloutError):
                    run("--verify", path)

    def test_credential_schema_is_exactly_n8n_248_postgres(self) -> None:
        schema = {"properties": {
            "host": {"type": "string"}, "port": {"type": "number"},
            "database": {"type": "string"}, "user": {"type": "string"},
            "password": {"type": "string"},
            "ssl": {"type": "string", "enum": ["allow", "disable", "require"]},
            "allowUnauthorizedCerts": {"type": "boolean"},
        }}
        rollout.validate_credential_schema(schema, self.config)
        legacy = json.loads(json.dumps(schema))
        legacy["properties"]["ignoreSSLIssues"] = legacy["properties"].pop("allowUnauthorizedCerts")
        with self.assertRaises(rollout.RolloutError):
            rollout.validate_credential_schema(legacy, self.config)
        not_boolean = json.loads(json.dumps(schema))
        not_boolean["properties"]["allowUnauthorizedCerts"]["type"] = "string"
        with self.assertRaises(rollout.RolloutError):
            rollout.validate_credential_schema(not_boolean, self.config)

    def test_post_create_credential_metadata_required_without_get(self) -> None:
        valid = {"id": "created-credential", "name": "safe-name", "type": "postgres"}
        self.assertEqual(
            rollout.validate_created_credential_response(valid, self.config, "safe-name"),
            "created-credential",
        )
        for bad in (
            {"id": "created-credential", "name": "wrong-name", "type": "postgres"},
            {"id": "created-credential", "name": "safe-name", "type": "other"},
            {"id": "old", "name": "safe-name", "type": "postgres"},
            {"name": "safe-name", "type": "postgres"},
            {"id": "../creds", "name": "safe-name", "type": "postgres"},
        ):
            with self.assertRaises(rollout.RolloutError):
                rollout.validate_created_credential_response(bad, self.config, "safe-name")

    def test_published_workflow_version_and_webhook_are_required(self) -> None:
        invalid = json.loads(json.dumps(self.workflow))
        invalid["activeVersionId"] = "not-published"
        with self.assertRaises(rollout.RolloutError):
            rollout.validate_workflow(invalid, self.config)
        invalid = json.loads(json.dumps(self.workflow))
        invalid["nodes"][2]["parameters"]["path"] = "wrong"
        with self.assertRaises(rollout.RolloutError):
            rollout.validate_workflow(invalid, self.config)


    def test_n8n_http_error_reports_only_numeric_status(self) -> None:
        from urllib.error import HTTPError

        class ForbiddenOpener:
            def open(self, request, timeout=20):
                raise HTTPError(
                    "https://secret.invalid/path?token=SECRET", 403,
                    "body=SECRET", None, None,
                )

        api = rollout.N8nApi(
            "https://n8n.example", "test-api-key-0123456789",
            opener=ForbiddenOpener(),
        )
        with self.assertRaisesRegex(rollout.RolloutError, "HTTP_STATUS_403") as observed:
            api.request("POST", "/api/v1/credentials", {"secret": "NEVER_PRINT"})
        self.assertNotIn("SECRET", str(observed.exception))
        self.assertNotIn("NEVER_PRINT", str(observed.exception))



if __name__ == "__main__":
    unittest.main()

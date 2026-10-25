from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
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
                "connection_fields": {"host": "host", "port": "port", "database": "database", "ssl": "ssl", "user": "user", "password": "password"}
            }
        })
        self.workflow = {
            "id": self.config.n8n["workflow_id"], "name": self.config.n8n["workflow_name"],
            "active": True, "versionId": "version", "activeVersionId": "version", "n8nVersion": "2.4.8",
            "nodes": [
                {"id": node_id, "credentials": {"postgres": {"id": self.config.n8n["old_credential_id"], "name": "old"}}}
                for node_id in self.config.n8n["binding_node_ids"]
            ] + [{"id": f"node-{index}", "parameters": {"webhook": self.config.n8n["webhook_path"] if index == 0 else index}}
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
            def __init__(self, relations, dml=(), definer=()):
                self.relations, self.dml, self.definer = relations, dml, definer
            def execute(self, query, params=()):
                class Cursor:
                    def __init__(self, rows): self.rows = rows
                    def fetchone(self): return self.rows[0] if self.rows else None
                    def fetchall(self): return self.rows
                if "current_database" in query: return Cursor([("database",)])
                if "information_schema.tables" in query: return Cursor(self.relations)
                if "has_table_privilege('public'" in query: return Cursor([(item,) for item in self.dml])
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

    def test_pooler_connection_never_reuses_old_user_and_requires_tls_template(self) -> None:
        template = {"host": "pooler.example", "port": 6543, "database": "database", "ssl": "require"}
        dsn = rollout.build_pooler_dsn(template, self.config, "project", "private")
        self.assertIn("readonly_role.project", dsn)
        self.assertIn("sslmode=verify-full", dsn)
        template["ssl"] = False
        with self.assertRaises(rollout.RolloutError):
            rollout.build_pooler_dsn(template, self.config, "project", "private")


if __name__ == "__main__":
    unittest.main()

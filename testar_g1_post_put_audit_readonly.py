from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from scripts.operations import g1_post_put_audit_readonly as audit
from scripts.operations import g1_readonly_rollout as rollout


class G1PostPutKeylessAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.snapshot_path = Path(self.temp.name) / "private" / "g1.json"
        self.config_path = Path(self.temp.name) / "g1-config.json"
        self.raw_config = {
            "rollout_id": "test-g1-audit", "database": "postgres",
            "role_name": "g1_test_readonly", "schema": "demo",
            "relations": ["first"], "relation_types": ["BASE TABLE"],
            "n8n": {
                "workflow_id": "workflow-test", "workflow_name": "Workflow TEST",
                "expected_node_count": 4, "expected_n8n_version": "2.4.8",
                "webhook_path": "internal-route", "credential_type": "postgres",
                "old_credential_id": "cred-old", "old_credential_name": "Old",
                "binding_node_ids": ["postgres-a", "postgres-b"],
                "connection_fields": {
                    "host": "host", "port": "port", "database": "database",
                    "ssl": "ssl", "user": "user", "password": "password",
                    "allow_unauthorized_certs": "allowUnauthorizedCerts",
                    "ssh_tunnel": "sshTunnel",
                },
            },
        }
        self.config_path.write_text(json.dumps(self.raw_config), encoding="utf-8")
        self.config = rollout.load_config(self.config_path)
        nodes = [
            {
                "id": node_id, "name": node_id,
                "type": "n8n-nodes-base.postgres", "typeVersion": 2,
                "position": [0, 0], "parameters": {},
                "credentials": {"postgres": {"id": "cred-old", "name": "Old"}},
            }
            for node_id in ("postgres-a", "postgres-b")
        ]
        nodes += [{
            "id": "webhook", "name": "webhook",
            "type": "n8n-nodes-base.webhook", "typeVersion": 2,
            "position": [0, 0], "parameters": {"path": "internal-route"},
        }, {
            "id": "noop", "name": "noop", "type": "n8n-nodes-base.noOp",
            "typeVersion": 1, "position": [0, 0], "parameters": {},
        }]
        self.original = {
            "id": "workflow-test", "name": "Workflow TEST", "active": True,
            "versionId": "old-v1", "activeVersionId": "old-v1",
            "nodes": nodes, "settings": {"executionOrder": "v1"},
            "connections": {}, "staticData": None,
            "pinData": {"webhook": [{"sensitive": "DO_NOT_PRINT"}]},
            "meta": {"templateCredsSetupCompleted": True}, "tags": [],
        }
        self.current = copy.deepcopy(self.original)
        self.current["versionId"] = "new-v2"
        self.current["activeVersionId"] = "new-v2"
        for node in self.current["nodes"][:2]:
            node["credentials"]["postgres"] = {
                "id": "cred-new", "name": "g1_test_readonly-20261027150000",
            }
        self.credential = {
            "id": "cred-new", "name": "g1_test_readonly-20261027150000",
            "type": "postgres", "data": "ENCRYPTED_PASSWORD_NEVER_PRINT",
        }
        self.snapshot = {
            "workflow": self.original,
            "fingerprint": rollout.workflow_fingerprint(self.original),
            "old_credential_id": "cred-old", "old_credential_name": "Old",
            "credential_id": "cred-new",
            "credential_name": self.credential["name"],
        }
        rollout.private_snapshot(self.snapshot_path, self.snapshot)

    def assess(self):
        return audit.evaluate(
            self.snapshot, self.current, self.credential, self.config
        )

    def test_strict_success_accepts_new_active_version_and_two_new_bindings(self):
        result = self.assess()
        self.assertEqual(result["G1_AUDIT_RESULT"], "STRICT_PASS")
        self.assertEqual(result["G1_PUBLISHED_VERSION"], "ACTIVE_MATCH")
        self.assertEqual(result["G1_NEW_BINDINGS"], "2")
        self.assertEqual(result["G1_UNAUTHORIZED_NODE_DRIFT"], "0")
        self.assertEqual(result["G1_FIELD_META"], "UNCHANGED")

    def test_server_metadata_change_requires_review_not_auto_whitelist(self):
        self.current["meta"]["templateCredsSetupCompleted"] = False
        result = self.assess()
        self.assertEqual(result["G1_FIELD_META"], "CHANGED")
        self.assertEqual(result["G1_AUDIT_RESULT"], "NONBINDING_FIELD_DRIFT_REVIEW")

    def test_business_settings_or_pindata_change_requires_review(self):
        self.current["settings"]["executionOrder"] = "v0"
        self.current["pinData"]["webhook"][0]["sensitive"] = "CHANGED_SECRET"
        result = self.assess()
        self.assertEqual(result["G1_FIELD_SETTINGS"], "CHANGED")
        self.assertEqual(result["G1_FIELD_PINDATA"], "CHANGED")
        self.assertEqual(result["G1_AUDIT_RESULT"], "NONBINDING_FIELD_DRIFT_REVIEW")

    def test_one_unbound_node_rejects_as_partial_rollout(self):
        self.current["nodes"][1]["credentials"]["postgres"] = {
            "id": "cred-old", "name": "Old",
        }
        result = self.assess()
        self.assertEqual(result["G1_NEW_BINDINGS"], "1")
        self.assertEqual(result["G1_OLD_BINDINGS"], "1")
        self.assertEqual(result["G1_AUDIT_RESULT"], "BINDINGS_REVIEW_REQUIRED")

    def test_unauthorized_node_drift_blocks_even_with_two_new_bindings(self):
        self.current["nodes"][3]["parameters"]["evil"] = "SECRET"
        result = self.assess()
        self.assertEqual(result["G1_UNAUTHORIZED_NODE_DRIFT"], "1")
        self.assertEqual(result["G1_AUDIT_RESULT"], "STRUCTURAL_REVIEW_REQUIRED")

    def test_workflow_active_version_drift_blocks(self):
        self.current["activeVersionId"] = "old-v1"
        result = self.assess()
        self.assertEqual(result["G1_PUBLISHED_VERSION"], "REVIEW_REQUIRED")
        self.assertEqual(result["G1_AUDIT_RESULT"], "STRUCTURAL_REVIEW_REQUIRED")

    def test_credential_id_mismatch_is_not_silently_accepted(self):
        self.credential["id"] = "not-expected"
        with self.assertRaises(rollout.RolloutError):
            self.assess()

    def test_parser_handles_cli_logger_without_exposing_ciphertext(self):
        raw = "INFO n8n initialized\n" + json.dumps([self.credential]) + "\n"
        record = audit.parse_single_cli_export(
            raw, expected_id="cred-new", kind="credential",
        )
        self.assertEqual(record["id"], "cred-new")
        self.assertEqual(record["data"], "ENCRYPTED_PASSWORD_NEVER_PRINT")
        with self.assertRaises(rollout.RolloutError) as e:
            audit.parse_single_cli_export(
                raw, expected_id="wrong-id", kind="credential",
            )
        self.assertNotIn("ENCRYPTED_PASSWORD", str(e.exception))
        self.assertNotIn("DO_NOT_PRINT", str(e.exception))

    def test_export_uses_only_read_only_cli_no_decryption_or_file(self):
        for kind, record in [("workflow", self.current), ("credential", self.credential)]:
            with self.subTest(kind=kind), mock.patch.object(
                audit.subprocess, "run",
                return_value=type("Result", (), {"stdout": json.dumps([record])})(),
            ) as run:
                obj = audit.export_one("n8n-test", kind, record["id"])
                self.assertEqual(obj["id"], record["id"])
                args = run.call_args.args[0]
                self.assertEqual(args[:6], [
                    "docker", "exec", "-u", "node", "n8n-test", "n8n",
                ])
                self.assertEqual(args[6], "export:" + kind)
                self.assertEqual(args[7], "--id=" + record["id"])
                self.assertNotIn("--decrypted", args)
                self.assertNotIn("--output", args)
                self.assertTrue(run.call_args.kwargs["capture_output"])

    def test_cli_error_is_redacted_and_fails_closed(self):
        with self.assertRaises(rollout.RolloutError):
            audit.export_one("n8n", "workflow", "--id=other")
        with mock.patch.object(
            audit.subprocess, "run",
            side_effect=RuntimeError("SECRET_IN_EXCEPTION"),
        ):
            # Unexpected exceptions are caught at top-level as a constant,
            # not printed with potentially sensitive underlying content.
            with self.assertRaises(RuntimeError):
                audit.export_one("n8n", "credential", "cred-new")

    def test_main_no_api_key_or_dsn_and_only_sanitized_output(self):
        def export(container, kind, identifier):
            return copy.deepcopy(
                self.credential if kind == "credential" else self.current
            )
        with mock.patch.object(audit, "find_n8n_container", return_value="n8n-test"), \
             mock.patch.object(audit, "read_n8n_runtime_version"), \
             mock.patch.object(audit, "export_one", side_effect=export), \
             redirect_stdout(io.StringIO()) as stream:
            code = audit.main([
                "--config", str(self.config_path),
                "--snapshot", str(self.snapshot_path),
                "--n8n-container", "n8n-test",
            ])
        output = stream.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("G1_AUDIT_RESULT=STRICT_PASS", output)
        self.assertNotIn("ENCRYPTED_PASSWORD", output)
        self.assertNotIn("DO_NOT_PRINT", output)
        self.assertNotIn("CHANGED_SECRET", output)


if __name__ == "__main__":
    unittest.main()

"""Offline, synthetic tests for the inactive 5-node n8n evidence relay audit."""
from __future__ import annotations

import copy
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from scripts.n8n.render_shadow_evidence_read_workflow import render
from scripts.n8n.verify_shadow_evidence_read_bindings_export import (
    EvidenceBindingAuditError,
    validate_export,
)

WORKFLOW_ID = "synthetic-evidence-workflow"


def fixture() -> dict:
    data = render("http://shadow-internal:8000")
    data["id"] = WORKFLOW_ID
    by_name = {n["name"]: n for n in data["nodes"]}
    by_name["Webhook - Evidence Read"]["credentials"] = {
        "httpHeaderAuth": {"id": "evidence-webhook-secret", "name": "do-not-echo"}
    }
    by_name["Read LangGraph Evidence"]["credentials"] = {
        "httpHeaderAuth": {"id": "private-s2s-secret", "name": "do-not-echo"}
    }
    return data


class EvidenceBindingAuditTests(unittest.TestCase):
    def test_accepts_imported_inactive_bound_workflow_without_exposing_secrets(self):
        report = validate_export([fixture()], WORKFLOW_ID)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["node_count"], 5)
        self.assertEqual(report["langgraph_method"], "GET")
        self.assertTrue(report["webhook_credential_separate"])
        self.assertFalse(report["workflow_active"])
        for flag in ("credentials_values_verified", "authenticated_http_verified",
                     "shadow_evidence_read_verified", "tenant_isolation_verified",
                     "financial_parity_verified"):
            self.assertFalse(report[flag])
        self.assertNotIn("do-not-echo", json.dumps(report))
        self.assertNotIn("shadow-internal", json.dumps(report))

    def test_accepts_new_n8n_node_ids_and_missing_default_get(self):
        data = fixture()
        for index, node in enumerate(data["nodes"]):
            node["id"] = f"imported-node-{index + 1}"
        read = next(n for n in data["nodes"] if n["name"] == "Read LangGraph Evidence")
        del read["parameters"]["method"]
        self.assertEqual(validate_export(data, WORKFLOW_ID)["status"], "pass")

    def test_rejects_invalid_drift_and_separated_auth_failures(self):
        cases = (
            "wrong_id", "empty_array", "active", "archived", "no_webhook_cred",
            "no_reader_cred", "same_credential", "embedded_secret", "bad_cred_type",
            "duplicate_node_id", "bad_node_id", "wrong_node_count", "node_type_drift",
            "code_drift", "webhook_path", "public_endpoint", "env_expression",
            "wrong_expression", "read_post", "read_delete", "read_head",
            "read_null", "extra_read_param", "topology_drift", "pinned_data",
            "save_execution", "save_error_execution", "manual_execution_storage",
            "disabled", "continue_on_fail", "retry", "unexpected_credentials",
        )
        for case in cases:
            data = fixture()
            by_name = {n["name"]: n for n in data["nodes"]}
            webhook = by_name["Webhook - Evidence Read"]
            read = by_name["Read LangGraph Evidence"]
            if case == "wrong_id": data["id"] = "other-workflow"
            elif case == "empty_array": data = []
            elif case == "active": data["active"] = True
            elif case == "archived": data["isArchived"] = True
            elif case == "no_webhook_cred": del webhook["credentials"]
            elif case == "no_reader_cred": del read["credentials"]
            elif case == "same_credential": read["credentials"]["httpHeaderAuth"]["id"] = "evidence-webhook-secret"
            elif case == "embedded_secret": read["credentials"]["httpHeaderAuth"]["value"] = "DO_NOT_ECHO"
            elif case == "bad_cred_type": webhook["credentials"] = {"httpBasicAuth": {"id": "wrong"}}
            elif case == "duplicate_node_id": read["id"] = webhook["id"]
            elif case == "bad_node_id": read["id"] = "invalid id"
            elif case == "wrong_node_count": data["nodes"].append(copy.deepcopy(read))
            elif case == "node_type_drift": read["type"] = "n8n-nodes-base.code"
            elif case == "code_drift": by_name["Sanitize Evidence Response"]["parameters"]["jsCode"] += "// drift"
            elif case == "webhook_path": webhook["parameters"]["path"] = "wrong-path"
            elif case == "public_endpoint": read["parameters"]["url"] = '={{ "https://public.example" + $json.target_path }}'
            elif case == "env_expression": read["parameters"]["url"] = "={{ $env.SECRET + $json.target_path }}"
            elif case == "wrong_expression": read["parameters"]["url"] = '={{ "http://shadow-internal:8000" + $json.evil }}'
            elif case == "read_post": read["parameters"]["method"] = "POST"
            elif case == "read_delete": read["parameters"]["method"] = "DELETE"
            elif case == "read_head": read["parameters"]["method"] = "HEAD"
            elif case == "read_null": read["parameters"]["method"] = None
            elif case == "extra_read_param": read["parameters"]["sendBody"] = True
            elif case == "topology_drift": data["connections"] = {}
            elif case == "pinned_data": data["pinData"] = {"sensitive": [{"json": {"password": "DO_NOT_ECHO"}}]}
            elif case == "save_execution": data["settings"]["saveDataSuccessExecution"] = "all"
            elif case == "save_error_execution": data["settings"]["saveDataErrorExecution"] = "all"
            elif case == "manual_execution_storage": data["settings"]["saveManualExecutions"] = True
            elif case == "disabled": read["disabled"] = True
            elif case == "continue_on_fail": read["continueOnFail"] = True
            elif case == "retry": read["retryOnFail"] = True
            elif case == "unexpected_credentials": by_name["Sanitize Evidence Response"]["credentials"] = copy.deepcopy(webhook["credentials"])
            with self.subTest(case=case):
                with self.assertRaises(EvidenceBindingAuditError):
                    validate_export(data, WORKFLOW_ID)

    def test_cli_emits_only_bounded_labels(self):
        script = pathlib.Path(__file__).parent / "scripts/n8n/verify_shadow_evidence_read_bindings_export.py"
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "workflow-private.json"
            path.write_text(json.dumps(fixture()), encoding="utf-8")
            good = subprocess.run(
                [sys.executable, str(script), "--workflow", str(path), "--workflow-id", WORKFLOW_ID],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertEqual(json.loads(good.stdout)["status"], "pass")
            for secret in ("do-not-echo", "shadow-internal", "private-s2s-secret"):
                self.assertNotIn(secret, good.stdout + good.stderr)
            bad = fixture()
            bad["nodes"][0]["credentials"]["httpHeaderAuth"]["secret"] = "secret-never-echo"
            path.write_text(json.dumps(bad), encoding="utf-8")
            invalid = subprocess.run(
                [sys.executable, str(script), "--workflow", str(path), "--workflow-id", WORKFLOW_ID],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(invalid.returncode, 2)
            self.assertEqual(json.loads(invalid.stdout)["status"], "rejected")
            self.assertNotIn("secret-never-echo", invalid.stdout + invalid.stderr)

    def test_live_shell_wrapper_is_read_only(self):
        script = pathlib.Path(__file__).parent / "scripts/n8n/audit_shadow_evidence_read_bindings_readonly.sh"
        source = script.read_text(encoding="utf-8")
        self.assertIn("n8n export:workflow", source)
        self.assertIn("verify_shadow_evidence_read_bindings_export.py", source)
        self.assertIn("EVIDENCE_READ_BINDINGS=PASS", source)
        for unsafe in ("n8n import:workflow", "n8n publish", "n8n activate", "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=true"):
            self.assertNotIn(unsafe, source)


if __name__ == "__main__":
    unittest.main()

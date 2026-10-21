"""Synthetic, offline fail-closed tests for imported n8n Shadow binding audit."""
from __future__ import annotations

import copy
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from scripts.n8n.render_parallel_shadow_workflow import render_private_candidate
from scripts.n8n.verify_parallel_shadow_bindings_export import (
    BindingAuditError,
    validate_export,
)

WORKFLOW_ID = "synthetic-workflow-id"


def fixture():
    data = render_private_candidate("http://shadow-internal:8000")
    data["id"] = WORKFLOW_ID
    data["nodes"][0]["credentials"] = {"httpHeaderAuth": {"id": "webhook-secret-id", "name": "do-not-echo"}}
    for node in data["nodes"]:
        if node["name"] in ("Call LangGraph Shadow", "Read Correlated Evidence"):
            node["credentials"] = {"httpHeaderAuth": {"id": "s2s-secret-id", "name": "do-not-echo"}}
    return data


class ParallelShadowBindingAuditTests(unittest.TestCase):
    def test_accepts_one_inactive_workflow_with_three_credential_bindings(self):
        result = validate_export([fixture()], WORKFLOW_ID)
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["workflow_active"])
        self.assertTrue(result["langgraph_http_nodes_share_credential"])
        self.assertFalse(result["credentials_values_verified"])
        self.assertFalse(result["shadow_execution_verified"])
        self.assertNotIn("do-not-echo", json.dumps(result))

    def test_rejects_drift_and_unbound_or_misbound_credentials(self):
        for mutation in (
            "wrong_id", "active", "archived", "no_webhook_cred", "no_http_cred",
            "mismatched_http_creds", "shared_webhook_s2s", "inline_secret",
            "extra_node", "disabled", "code_drift", "http_url_drift",
            "env_expression", "public_endpoint", "topology", "save_execution",
            "pinned_data", "unwanted_credential", "bad_credential_shape",
        ):
            d = fixture()
            webhook = next(n for n in d["nodes"] if n["name"] == "Webhook - Parallel Shadow")
            call = next(n for n in d["nodes"] if n["name"] == "Call LangGraph Shadow")
            read = next(n for n in d["nodes"] if n["name"] == "Read Correlated Evidence")
            if mutation == "wrong_id": d["id"] = "another-id"
            elif mutation == "active": d["active"] = True
            elif mutation == "archived": d["isArchived"] = True
            elif mutation == "no_webhook_cred": del webhook["credentials"]
            elif mutation == "no_http_cred": del read["credentials"]
            elif mutation == "mismatched_http_creds": read["credentials"]["httpHeaderAuth"]["id"] = "another-s2s"
            elif mutation == "shared_webhook_s2s": webhook["credentials"]["httpHeaderAuth"]["id"] = "s2s-secret-id"
            elif mutation == "inline_secret": call["credentials"]["httpHeaderAuth"]["value"] = "private"
            elif mutation == "extra_node": d["nodes"].append(copy.deepcopy(call))
            elif mutation == "disabled": call["disabled"] = True
            elif mutation == "code_drift": d["nodes"][1]["parameters"]["jsCode"] += "// drift"
            elif mutation == "http_url_drift": read["parameters"]["url"] = "http://public.example"
            elif mutation == "env_expression": call["parameters"]["url"] = "={{ $env.SECRET + $json.target_path }}"
            elif mutation == "public_endpoint": call["parameters"]["url"] = '={{ "https://example.com" + $json.target_path }}'
            elif mutation == "topology": d["connections"] = {}
            elif mutation == "save_execution": d["settings"]["saveDataSuccessExecution"] = "all"
            elif mutation == "pinned_data": d["pinData"] = {"a": [{"json": {"secret": "private"}}]}
            elif mutation == "unwanted_credential": d["nodes"][1]["credentials"] = webhook["credentials"]
            elif mutation == "bad_credential_shape": webhook["credentials"] = {"httpBasicAuth": {"id": "secret"}}
            with self.subTest(mutation=mutation):
                with self.assertRaises(BindingAuditError):
                    validate_export(d, WORKFLOW_ID)

    def test_cli_does_not_echo_credential_names_or_secrets(self):
        script = pathlib.Path(__file__).parent / "scripts/n8n/verify_parallel_shadow_bindings_export.py"
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "private.json"
            path.write_text(json.dumps([fixture()]), encoding="utf-8")
            run = subprocess.run([sys.executable, str(script), "--workflow", str(path), "--workflow-id", WORKFLOW_ID],
                                 capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertNotIn("do-not-echo", run.stdout)
            self.assertNotIn("shadow-internal", run.stdout)
            bad = fixture()
            bad["nodes"][0]["credentials"]["httpHeaderAuth"]["value"] = "secret-never-echo"
            path.write_text(json.dumps(bad), encoding="utf-8")
            run = subprocess.run([sys.executable, str(script), "--workflow", str(path), "--workflow-id", WORKFLOW_ID],
                                 capture_output=True, text=True, timeout=15)
            self.assertEqual(run.returncode, 2)
            self.assertNotIn("secret-never-echo", run.stdout + run.stderr)
            self.assertEqual(json.loads(run.stdout)["status"], "rejected")


if __name__ == "__main__":
    unittest.main()

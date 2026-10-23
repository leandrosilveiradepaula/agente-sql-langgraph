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

    def test_only_explicit_published_mode_accepts_a_real_active_workflow(self):
        data = fixture()
        data["active"] = True
        with self.assertRaisesRegex(
            BindingAuditError, "SHADOW_WORKFLOW_NOT_INACTIVE"
        ):
            validate_export(data, WORKFLOW_ID)
        report = validate_export(data, WORKFLOW_ID, expect_active=True)
        self.assertTrue(report["workflow_active"])
        self.assertEqual(report["workflow_state_expectation"], "active")
        self.assertEqual(report["node_count"], 7)
        self.assertTrue(report["webhook_credential_separate"])
        self.assertFalse(report["credentials_values_verified"])
        self.assertFalse(report["authenticated_http_verified"])
        self.assertFalse(report["shadow_execution_verified"])
        self.assertNotIn("do-not-echo", json.dumps(report))
        with self.assertRaisesRegex(
            BindingAuditError, "SHADOW_WORKFLOW_NOT_ACTIVE"
        ):
            validate_export(fixture(), WORKFLOW_ID, expect_active=True)

    def test_active_mode_does_not_relax_credential_topology_or_safety_checks(self):
        for mutation in (
            "archived", "credential_missing", "credential_shared", "code_drift",
            "public_url", "pinned_data", "execution_saved", "extra_node",
            "unsafe_flag", "read_post",
        ):
            data = fixture()
            data["active"] = True
            by_name = {node["name"]: node for node in data["nodes"]}
            webhook = by_name["Webhook - Parallel Shadow"]
            call = by_name["Call LangGraph Shadow"]
            read = by_name["Read Correlated Evidence"]
            if mutation == "archived":
                data["isArchived"] = True
            elif mutation == "credential_missing":
                del webhook["credentials"]
            elif mutation == "credential_shared":
                webhook["credentials"] = copy.deepcopy(call["credentials"])
            elif mutation == "code_drift":
                by_name["Validate Shadow Envelope"]["parameters"]["jsCode"] += "// changed"
            elif mutation == "public_url":
                call["parameters"]["url"] = '={{ "https://example.org" + $json.target_path }}'
            elif mutation == "pinned_data":
                data["pinData"] = {"some": [{"json": {"unexpected": True}}]}
            elif mutation == "execution_saved":
                data["settings"]["saveDataErrorExecution"] = "all"
            elif mutation == "extra_node":
                data["nodes"].append(copy.deepcopy(call))
            elif mutation == "unsafe_flag":
                call["continueOnFail"] = True
            elif mutation == "read_post":
                read["parameters"]["method"] = "POST"
            with self.subTest(mutation=mutation):
                with self.assertRaises(BindingAuditError):
                    validate_export(data, WORKFLOW_ID, expect_active=True)

    def test_cli_validates_active_only_with_explicit_expectation(self):
        script = pathlib.Path(__file__).parent / "scripts/n8n/verify_parallel_shadow_bindings_export.py"
        data = fixture()
        data["active"] = True
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "private.json"
            path.write_text(json.dumps([data]), encoding="utf-8")
            base = [
                sys.executable, str(script),
                "--workflow", str(path), "--workflow-id", WORKFLOW_ID,
            ]
            blocked = subprocess.run(
                base, capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(blocked.returncode, 2)
            self.assertEqual(
                json.loads(blocked.stdout)["reason"],
                "SHADOW_WORKFLOW_NOT_INACTIVE",
            )
            allowed = subprocess.run(
                base + ["--expect-active"],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(allowed.returncode, 0, allowed.stderr)
            self.assertTrue(json.loads(allowed.stdout)["workflow_active"])
            self.assertNotIn("do-not-echo", allowed.stdout)
            self.assertNotIn("shadow-internal", allowed.stdout)
            data["active"] = False
            path.write_text(json.dumps(data), encoding="utf-8")
            bad = subprocess.run(
                base + ["--expect-active"],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(bad.returncode, 2)
            self.assertEqual(
                json.loads(bad.stdout)["reason"],
                "SHADOW_WORKFLOW_NOT_ACTIVE",
            )

    def test_accepts_imported_node_ids_and_implicit_reader_get(self):
        d = fixture()
        for index, node in enumerate(d["nodes"]):
            node["id"] = f"imported-node-{index + 1}"
        read = next(n for n in d["nodes"] if n["name"] == "Read Correlated Evidence")
        del read["parameters"]["method"]
        result = validate_export(d, WORKFLOW_ID)
        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["credentials_values_verified"])

    def test_rejects_drift_and_unbound_or_misbound_credentials(self):
        for mutation in (
            "wrong_id", "active", "archived", "no_webhook_cred", "no_http_cred",
            "mismatched_http_creds", "shared_webhook_s2s", "inline_secret",
            "extra_node", "disabled", "code_drift", "http_url_drift",
            "env_expression", "public_endpoint", "topology", "save_execution",
            "pinned_data", "unwanted_credential", "bad_credential_shape",
            "duplicate_node_id", "missing_node_id", "malformed_node_id",
            "read_post_method", "read_head_method", "read_null_method",
            "call_method_missing",
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
            elif mutation == "duplicate_node_id": read["id"] = call["id"]
            elif mutation == "missing_node_id": del read["id"]
            elif mutation == "malformed_node_id": read["id"] = "invalid id"
            elif mutation == "read_post_method": read["parameters"]["method"] = "POST"
            elif mutation == "read_head_method": read["parameters"]["method"] = "HEAD"
            elif mutation == "read_null_method": read["parameters"]["method"] = None
            elif mutation == "call_method_missing": del call["parameters"]["method"]
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

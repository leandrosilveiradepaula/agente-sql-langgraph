from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest import mock

OPERATIONS = Path(__file__).resolve().parent / "scripts" / "operations"
FAKE = types.ModuleType("g1_readonly_rollout")


class RolloutError(RuntimeError):
    pass


FAKE.RolloutError = RolloutError
FAKE.N8nApi = object
FAKE.assert_binding_id = lambda *args: None
FAKE.load_config = lambda *args: None
FAKE.read_n8n_runtime_version = lambda *args: None
FAKE.validate_workflow = lambda *args, **kwargs: None
FAKE.workflow_fingerprint = lambda *args: "0eee554daf77abc"
with mock.patch.dict(sys.modules, {"g1_readonly_rollout": FAKE}):
    spec = importlib.util.spec_from_file_location(
        "g1_partial_reconcile_readonly", OPERATIONS / "g1_partial_reconcile_readonly.py"
    )
    assert spec and spec.loader
    partial = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(partial)


class ReconcileProbeTests(unittest.TestCase):
    def setUp(self):
        self.credential = {
            "id": "new-credential",
            "name": "finance_g1_readonly-20261027130900",
            "type": "postgres",
            "data": "VERY-SENSITIVE-ENCRYPTED-CIPHERTEXT",
        }
        self.other = {
            "id": "old", "name": "Postgres account 2",
            "type": "postgres", "data": "SECRET",
        }

    def test_parser_counts_only_target_credential_and_never_returns_data(self):
        raw = "info " + json.dumps([self.credential, self.other]) + "\n"
        self.assertEqual(partial.parse_encrypted_export(raw, "finance_g1_readonly", "postgres"), 1)
        self.assertEqual(partial.parse_encrypted_export(
            json.dumps([self.other]), "finance_g1_readonly", "postgres"), 0)
        self.assertEqual(partial.parse_encrypted_export(
            json.dumps([self.credential, self.credential]), "finance_g1_readonly", "postgres"), 2)

    def test_parser_fails_closed_on_malformed_without_exposing_export(self):
        examples = (
            "", "info nothing", '[{"data":"SECRET"}]',
            "[not JSON", json.dumps([self.credential]) + "\n" + json.dumps([self.other]),
        )
        for raw in examples:
            with self.subTest(raw=raw[:10]), self.assertRaises(RolloutError) as err:
                partial.parse_encrypted_export(raw, "finance_g1_readonly", "postgres")
            self.assertNotIn("SECRET", str(err.exception))

    def test_inventory_invokes_encrypted_cli_without_decryption_or_logging(self):
        fake = types.SimpleNamespace(stdout=json.dumps([self.credential]))
        with mock.patch.object(partial.subprocess, "run", return_value=fake) as run:
            self.assertEqual(partial.inventory_credentials("n8n", "finance_g1_readonly", "postgres"), 1)
            arguments = run.call_args.args[0]
            self.assertEqual(arguments, [
                "docker", "exec", "-u", "node", "n8n", "n8n", "export:credentials", "--all",
            ])
            self.assertNotIn("--decrypted", arguments)
            self.assertTrue(run.call_args.kwargs["capture_output"])

    def test_container_discovery_rejects_ambiguity_and_bad_identifier(self):
        with mock.patch.object(partial.subprocess, "run",
                               return_value=types.SimpleNamespace(
                                   stdout="n8n-1 docker.n8n.io/n8nio/n8n:2.4.8\nrandom foo:1\n")):
            self.assertEqual(partial.find_n8n_container(""), "n8n-1")
        with self.assertRaises(RolloutError):
            partial.find_n8n_container("n8n;bad")
        with mock.patch.object(partial.subprocess, "run",
                               return_value=types.SimpleNamespace(
                                   stdout="n8n1 n8nio/n8n:2.4.8\nn8n2 n8nio/n8n:2.4.8\n")):
            with self.assertRaises(RolloutError):
                partial.find_n8n_container("")


if __name__ == "__main__":
    unittest.main()

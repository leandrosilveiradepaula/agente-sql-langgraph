from __future__ import annotations

import copy
import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import testar_n8n_official_sql_infodive_provider_candidate as fixture

SCRIPT = Path(__file__).parent / "scripts" / "n8n" / "official_sql_infodive_provider_rollout.py"
spec = importlib.util.spec_from_file_location("n8n_provider_rollout", SCRIPT)
m = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(m)


def current_workflow():
    result = fixture.sample()
    result["versionId"] = "v-current"
    result["activeVersionId"] = "v-current"
    return result


class FakeN8nApi:
    def __init__(self, workflow):
        self.workflow = copy.deepcopy(workflow)
        self.writes = 0
        self.calls = []

    def request(self, method, path, body=None):
        self.calls.append((method, path))
        if method == "GET" and path == "/api/v1/credentials":
            return {"data": [
                {"id": "cred-a", "name": "Private Provider Credential",
                 "type": "httpBearerAuth"},
            ]}
        if method == "GET":
            return copy.deepcopy(self.workflow)
        if method == "PUT":
            self.writes += 1
            self.workflow.update(copy.deepcopy(body))
            self.workflow["versionId"] = "v-after-" + str(self.writes)
            self.workflow["activeVersionId"] = self.workflow["versionId"]
            self.workflow["active"] = True
            return copy.deepcopy(self.workflow)
        raise ValueError("not supported")


class Tests(unittest.TestCase):
    def test_dry_run_without_n8n_api_and_writes(self):
        before = current_workflow()
        with patch.object(m, "_read_export", return_value=before):
            result = m.dry_run(
                container="safe-n8n", workflow_id="workflow-a",
                config=fixture.configuration(),
                expected_sha=m.fingerprint(before),
            )
        self.assertEqual(result["status"], "READY")
        self.assertEqual(result["changed_nodes"], 4)
        self.assertEqual(result["n8n_modified"], False)
        self.assertEqual(result["provider_calls"], 0)
        self.assertEqual(result["sql_executed"], False)

    def test_unpublished_fails_closed(self):
        workflow = current_workflow()
        workflow["activeVersionId"] = "older"
        with patch.object(m, "_read_export", return_value=workflow):
            with self.assertRaises(m.Blocked):
                m.dry_run(
                    container="safe-n8n", workflow_id="workflow-a",
                    config=fixture.configuration(),
                    expected_sha=m.fingerprint(workflow),
                )

    def test_drift_fails_closed(self):
        workflow = current_workflow()
        with patch.object(m, "_read_export", return_value=workflow):
            with self.assertRaises(m.Blocked):
                m.dry_run(
                    container="safe-n8n", workflow_id="workflow-a",
                    config=fixture.configuration(),
                    expected_sha="0" * 64,
                )

    def test_snapshot_directory_requires_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            if os.name == "posix":
                root.chmod(0o755)
                with self.assertRaises(m.Blocked):
                    m._validate_private_directory(root)
                root.chmod(0o700)
                m._validate_private_directory(root)

    def test_credential_type_required(self):
        api = FakeN8nApi(current_workflow())
        config = fixture.configuration()
        config["credential_type"] = "httpHeaderAuth"
        with self.assertRaises(m.Blocked):
            m._check_credential(api, config)

    def test_cli_api_revision_mismatch_blocks(self):
        workflow = current_workflow()
        api = copy.deepcopy(workflow)
        api["versionId"] = "other"
        api["activeVersionId"] = "other"
        with self.assertRaises(m.Blocked):
            m._assert_baseline(workflow, api, "workflow-a")

    def test_tampered_node_fails_post_apply_comparison(self):
        workflow = current_workflow()
        candidate, _ = m.prepare_candidate(workflow, "workflow-a",
                                           fixture.configuration())
        wrong = copy.deepcopy(candidate)
        wrong["nodes"][0]["parameters"]["extra_unreviewed"] = True
        with self.assertRaises(m.Blocked):
            m._assert_only_four_changes(workflow, wrong, candidate)

    @unittest.skipUnless(os.name == "posix", "Private POSIX snapshots required")
    def test_apply_and_operator_gated_rollback_with_no_provider_or_sql(self):
        before = current_workflow()
        api = FakeN8nApi(before)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.chmod(0o700)
            with patch.object(m, "_read_export", return_value=before), \
                 patch.object(m, "_n8n_provider_tcp_reachable", return_value=True):
                applied = m.apply(
                    api=api, container="safe-n8n", workflow_id="workflow-a",
                    config=fixture.configuration(),
                    expected_sha=m.fingerprint(before),
                    backup_dir=root,
                )
                self.assertEqual(applied["status"], "APPLIED_AND_VERIFIED")
                self.assertEqual(api.writes, 1)
                self.assertFalse(applied["sql_executed_by_script"])
                self.assertEqual(applied["provider_calls_by_script"], 0)
                receipt = root / ("official-llm-receipt-" + m.fingerprint(before)[:16] + ".json")
                snapshot = root / ("official-llm-before-" + m.fingerprint(before)[:16] + ".json")
                self.assertEqual(receipt.stat().st_mode & 0o077, 0)
                self.assertEqual(snapshot.stat().st_mode & 0o077, 0)
                with self.assertRaises(m.Blocked):
                    m.apply(
                        api=api, container="safe-n8n", workflow_id="workflow-a",
                        config=fixture.configuration(),
                        expected_sha="f" * 64,
                        backup_dir=root,
                    )
                rolled_back = m.rollback(
                    api=api, container="safe-n8n", workflow_id="workflow-a",
                    baseline_sha=m.fingerprint(before),
                    backup_dir=root,
                )
                self.assertEqual(rolled_back["status"], "RESTORED_AND_VERIFIED")
                self.assertEqual(api.writes, 2)
                self.assertEqual(api.workflow["nodes"], before["nodes"])

    @unittest.skipUnless(os.name == "posix", "Private POSIX snapshots required")
    def test_post_put_failure_retains_receipt_and_allows_exact_rollback(self):
        baseline = current_workflow()
        api = FakeN8nApi(baseline)
        original_request = api.request

        def normalize_settings_after_put(method, path, body=None):
            response = original_request(method, path, body)
            if method == "PUT" and api.writes == 1:
                api.workflow["settings"] = {"executionOrder": "v1", "drift": "unapproved"}
            return response

        api.request = normalize_settings_after_put
        with tempfile.TemporaryDirectory() as directory:
            private = Path(directory)
            private.chmod(0o700)
            with patch.object(m, "_read_export", return_value=baseline), \
                 patch.object(m, "_n8n_provider_tcp_reachable", return_value=True):
                with self.assertRaises(m.Blocked) as failure:
                    m.apply(
                        api=api, container="safe-n8n", workflow_id="workflow-a",
                        config=fixture.configuration(),
                        expected_sha=m.fingerprint(baseline), backup_dir=private,
                    )
                self.assertEqual(str(failure.exception), "POST_APPLY_SETTINGS_DRIFT")
                self.assertEqual(api.writes, 1)
                prefix = m.fingerprint(baseline)[:16]
                self.assertTrue((private / ("official-llm-receipt-" + prefix + ".json")).is_file())
                result = m.rollback(
                    api=api, container="safe-n8n", workflow_id="workflow-a",
                    baseline_sha=m.fingerprint(baseline), backup_dir=private,
                )
                self.assertEqual(result["status"], "RESTORED_AND_VERIFIED")
                self.assertEqual(api.writes, 2)

    @unittest.skipUnless(os.name == "posix", "Private POSIX snapshots required")
    def test_apply_rejects_unreachable_provider_before_put(self):
        before = current_workflow()
        api = FakeN8nApi(before)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.chmod(0o700)
            with patch.object(m, "_read_export", return_value=before), \
                 patch.object(m, "_n8n_provider_tcp_reachable", return_value=False):
                with self.assertRaises(m.Blocked):
                    m.apply(
                        api=api, container="safe-n8n", workflow_id="workflow-a",
                        config=fixture.configuration(),
                        expected_sha=m.fingerprint(before),
                        backup_dir=root,
                    )
                self.assertEqual(api.writes, 0)


if __name__ == "__main__":
    unittest.main()

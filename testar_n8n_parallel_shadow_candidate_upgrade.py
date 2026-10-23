"""Offline contract checks for exact n8n candidate upgrade, never network."""
from __future__ import annotations

import copy
import json
import pathlib
import stat
import tempfile
import unittest

from scripts.n8n.reconcile_parallel_shadow_candidate import (
    CODE_NAMES, READ_NAME, HISTORICAL_CANDIDATE_COMMITS, ReconcileError,
    _historical_code, _old_read_url, _sha, build_reconciliation,
    reconcile, N8nApi, _public_update_payload,
)
from testar_n8n_parallel_shadow_binding_audit import (
    VERSION_ONE, VERSION_TWO, WORKFLOW_ID, fixture,
)


def old_candidate():
    data = fixture()
    data["active"] = True
    data["versionId"] = VERSION_ONE
    data["activeVersionId"] = VERSION_ONE
    historical = _historical_code()
    current = {node["name"]: node for node in data["nodes"]}
    for name in CODE_NAMES:
        old = [code for code in historical[name] if code != current[name]["parameters"]["jsCode"]]
        assert old, name
        current[name]["parameters"]["jsCode"] = old[0]
    current[READ_NAME]["parameters"]["url"] = _old_read_url(
        current[READ_NAME]["parameters"]["url"],
    )
    del current[READ_NAME]["parameters"]["method"]  # normal n8n GET serialization
    return data


class FakeApi:
    def __init__(self, workflow):
        self.workflow = copy.deepcopy(workflow)
        self.calls = []

    def exchange(self, workflow_id, method, payload=None):
        assert workflow_id == WORKFLOW_ID
        self.calls.append(method)
        if method == "PUT":
            self.workflow["nodes"] = copy.deepcopy(payload["nodes"])
            self.workflow["settings"] = copy.deepcopy(payload["settings"])
            self.workflow["versionId"] = VERSION_TWO
            self.workflow["activeVersionId"] = VERSION_TWO
        return copy.deepcopy(self.workflow)


class CandidateReconciliationTests(unittest.TestCase):
    def test_old_known_contract_upgrades_only_four_params_and_preserves_credentials(self):
        before = old_candidate()
        snapshot = copy.deepcopy(before)
        revised, changes = build_reconciliation(before, WORKFLOW_ID, _historical_code())
        self.assertEqual({x["node"] for x in changes}, set(CODE_NAMES) | {READ_NAME})
        self.assertEqual(before, snapshot)
        self.assertTrue(revised["active"])
        self.assertEqual(revised["versionId"], VERSION_ONE)
        self.assertEqual(revised["activeVersionId"], VERSION_ONE)
        self.assertEqual(revised["connections"], before["connections"])
        self.assertEqual(revised["settings"], before["settings"])
        for old, new in zip(before["nodes"], revised["nodes"]):
            self.assertEqual(old["id"], new["id"])
            self.assertEqual(old.get("credentials"), new.get("credentials"))
            self.assertEqual(old["type"], new["type"])
            self.assertEqual(old.get("webhookId"), new.get("webhookId"))
        self.assertNotIn("method", next(
            n["parameters"] for n in revised["nodes"] if n["name"] == READ_NAME
        ))
        self.assertFalse(build_reconciliation(revised, WORKFLOW_ID, _historical_code())[1])

    def test_no_unknown_code_or_read_url_is_guessed(self):
        for change, expected in (
            ("unknown_code", "UNKNOWN_CODE_REVISION"),
            ("unknown_url", "UNKNOWN_READ_URL_REVISION"),
            ("malformed_url", "UNKNOWN_READ_URL_REVISION"),
            ("credential", "OTHER_BINDING_GUARD_FAILED"),
            ("published_mismatch", "OTHER_BINDING_GUARD_FAILED"),
        ):
            d = old_candidate()
            nodes = {n["name"]: n for n in d["nodes"]}
            if change == "unknown_code":
                nodes[CODE_NAMES[0]]["parameters"]["jsCode"] += "// operator change"
            elif change == "unknown_url":
                nodes[READ_NAME]["parameters"]["url"] = "https://example.com"
            elif change == "malformed_url":
                nodes[READ_NAME]["parameters"]["url"] = 42
            elif change == "credential":
                nodes["Read Correlated Evidence"]["credentials"] = {}
            elif change == "published_mismatch":
                d["activeVersionId"] = VERSION_TWO
            with self.subTest(change=change):
                with self.assertRaisesRegex(ReconcileError, expected):
                    build_reconciliation(d, WORKFLOW_ID, _historical_code())

    def test_disallowed_extra_node_and_settings_stay_blocked(self):
        for where in ("node", "settings"):
            data = old_candidate()
            if where == "node":
                data["nodes"][1]["unexpected_field"] = "secret"
            else:
                data["settings"]["unexpected_field"] = "secret"
            with self.subTest(where=where):
                try:
                    updated, _ = build_reconciliation(data, WORKFLOW_ID, _historical_code())
                    with self.assertRaisesRegex(ReconcileError, "N8N_UPDATE_SCHEMA_UNSUPPORTED"):
                        _public_update_payload(updated)
                except ReconcileError as exc:
                    self.assertEqual(str(exc), "OTHER_BINDING_GUARD_FAILED")

    def test_n8n_248_read_only_node_metadata_not_put_back(self):
        data = old_candidate()
        node = data["nodes"][2]
        # Node public API schema marks these attributes readOnly. Real n8n
        # exports may include them, even though a subsequent PUT must not.
        node["createdAt"] = "2026-10-22T09:13:10.000Z"
        node["updatedAt"] = "2026-10-23T09:13:10.000Z"
        original = copy.deepcopy(data)
        revised, changes = build_reconciliation(data, WORKFLOW_ID, _historical_code())
        self.assertEqual(len(changes), 4)
        payload = _public_update_payload(revised)
        self.assertNotIn("createdAt", payload["nodes"][2])
        self.assertNotIn("updatedAt", payload["nodes"][2])
        self.assertEqual(
            payload["nodes"][2],
            {k: v for k, v in revised["nodes"][2].items()
             if k not in ("createdAt", "updatedAt")},
        )
        self.assertEqual(original, data)
        # The original private backup and version fingerprint remain intact.
        fake = FakeApi(data)
        report = reconcile(fake, WORKFLOW_ID, known=_historical_code())
        self.assertEqual(report["status"], "ready")
        self.assertEqual(fake.calls, ["GET"])

    def test_n8n_248_time_saved_mode_retained_outside_public_put(self):
        for mode in ("fixed", "dynamic"):
            with self.subTest(mode=mode):
                data = old_candidate()
                data["settings"]["timeSavedMode"] = mode
                original = copy.deepcopy(data)
                revised, changes = build_reconciliation(
                    data, WORKFLOW_ID, _historical_code(),
                )
                self.assertEqual(len(changes), 4)
                payload = _public_update_payload(revised)
                self.assertNotIn("timeSavedMode", payload["settings"])
                self.assertEqual(
                    payload["settings"],
                    {k: v for k, v in original["settings"].items()
                     if k != "timeSavedMode"},
                )
                self.assertEqual(data, original)
                api = FakeApi(data)
                report = reconcile(api, WORKFLOW_ID, known=_historical_code())
                self.assertEqual(report["status"], "ready")
                self.assertEqual(api.calls, ["GET"])

    def test_n8n_248_time_saved_mode_invalid_fails_closed(self):
        for invalid in ("automatic", "", None, 15, True, {}, []):
            with self.subTest(invalid=invalid):
                data = old_candidate()
                data["settings"]["timeSavedMode"] = invalid
                with self.assertRaisesRegex(
                    ReconcileError,
                    "N8N_UPDATE_SCHEMA_UNSUPPORTED_SETTINGS_TIME_SAVED_MODE",
                ):
                    reconcile(FakeApi(data), WORKFLOW_ID,
                              known=_historical_code())

    def test_apply_rejects_settings_drift_after_public_put(self):
        class DriftApi(FakeApi):
            def exchange(self, workflow_id, method, payload=None):
                result = super().exchange(workflow_id, method, payload)
                if method == "PUT":
                    self.workflow["settings"]["timeSavedMode"] = "dynamic"
                return result

        api = DriftApi(old_candidate())
        api.workflow["settings"]["timeSavedMode"] = "fixed"
        report = reconcile(api, WORKFLOW_ID, known=_historical_code())
        with tempfile.TemporaryDirectory() as temp:
            directory = pathlib.Path(temp)
            directory.chmod(0o700)
            if __import__("os").name == "posix":
                with self.assertRaisesRegex(
                    ReconcileError, "POST_APPLY_VERIFY_FAILED_BACKUP_REQUIRED",
                ):
                    reconcile(
                        api, WORKFLOW_ID, apply=True, approved=True,
                        expected_hash=report["snapshot_sha256"],
                        backup_dir=directory, known=_historical_code(),
                    )
                self.assertEqual(api.calls.count("PUT"), 1)
                self.assertEqual(len(list(directory.glob("g1-candidate-*.json"))), 1)

    def test_schema_fails_closed_for_unknown_settings_or_node_fields(self):
        for kind, code in (
            ("node", "N8N_UPDATE_SCHEMA_UNSUPPORTED_NODE_FIELDS"),
            ("settings", "N8N_UPDATE_SCHEMA_UNSUPPORTED_SETTINGS_FIELDS"),
        ):
            data = old_candidate()
            if kind == "node":
                data["nodes"][1]["unexpected_field"] = "untrusted-sensitive-value"
            else:
                data["settings"]["unexpected_setting"] = "untrusted-sensitive-value"
            with self.subTest(kind=kind):
                with self.assertRaisesRegex(ReconcileError, code):
                    reconcile(FakeApi(data), WORKFLOW_ID,
                              known=_historical_code())

    def test_plan_is_read_only_and_apply_needs_explicit_version_identity(self):
        api = FakeApi(old_candidate())
        report = reconcile(api, WORKFLOW_ID, known=_historical_code())
        self.assertEqual(report["status"], "ready")
        self.assertEqual(api.calls, ["GET"])
        self.assertEqual(len(report["changed_nodes"]), 4)
        self.assertNotIn("http://", json.dumps(report))
        self.assertNotIn("do-not-echo", json.dumps(report))
        with self.assertRaisesRegex(ReconcileError, "EXPLICIT_OPERATIONAL_APPROVAL_REQUIRED"):
            reconcile(api, WORKFLOW_ID, apply=True,
                      expected_hash=report["snapshot_sha256"],
                      known=_historical_code())
        self.assertEqual(api.calls, ["GET", "GET"])

    def test_apply_requires_matching_snapshot_and_private_backup(self):
        api = FakeApi(old_candidate())
        before = reconcile(api, WORKFLOW_ID, known=_historical_code())
        with tempfile.TemporaryDirectory() as temp:
            p = pathlib.Path(temp)
            p.chmod(0o700)
            with self.assertRaisesRegex(ReconcileError, "WORKFLOW_SNAPSHOT_CHANGED"):
                reconcile(api, WORKFLOW_ID, apply=True, approved=True,
                          expected_hash="0" * 64, backup_dir=p,
                          known=_historical_code())
            if __import__("os").name != "posix":
                with self.assertRaisesRegex(ReconcileError, "APPLY_REQUIRES_POSIX_HOST"):
                    reconcile(api, WORKFLOW_ID, apply=True, approved=True,
                              expected_hash=before["snapshot_sha256"],
                              backup_dir=p, known=_historical_code())
                self.assertEqual(api.calls.count("PUT"), 0)
                return
            report = reconcile(api, WORKFLOW_ID, apply=True, approved=True,
                               expected_hash=before["snapshot_sha256"],
                               backup_dir=p, known=_historical_code())
            self.assertEqual(report["status"], "applied")
            self.assertEqual(api.calls.count("PUT"), 1)
            backup = list(p.glob("g1-candidate-*.json"))
            self.assertEqual(len(backup), 1)
            self.assertEqual(backup[0].stat().st_mode & 0o077, 0)
            self.assertEqual(len(build_reconciliation(
                api.workflow, WORKFLOW_ID, _historical_code())[1]), 0)

    def test_offline_export_mode_requires_no_api_key_and_never_writes(self):
        import subprocess
        import sys
        script = pathlib.Path(__file__).parent / "scripts/n8n/reconcile_parallel_shadow_candidate.py"
        data = old_candidate()
        with tempfile.TemporaryDirectory() as temp:
            path = pathlib.Path(temp) / "private.json"
            path.write_text(json.dumps([data]), encoding="utf-8")
            base = [
                sys.executable, str(script), "--workflow-file", str(path),
                "--workflow-id", WORKFLOW_ID,
            ]
            import os
            env = dict(os.environ)
            env.pop("N8N_API_KEY", None)
            result = subprocess.run(
                base, capture_output=True, text=True, timeout=15, env=env,
            )
            self.assertEqual(result.returncode, 0, result.stdout)
            self.assertEqual(json.loads(result.stdout)["status"], "ready")
            self.assertNotIn("do-not-echo", result.stdout + result.stderr)
            blocked = subprocess.run(
                base + ["--apply"], capture_output=True, text=True,
                timeout=15, env=env,
            )
            self.assertEqual(blocked.returncode, 2)
            self.assertEqual(
                json.loads(blocked.stdout)["reason"], "OFFLINE_EXPORT_CANNOT_APPLY",
            )

    def test_api_rejects_insecure_or_redirecting_configuration(self):
        for base in ("http://n8n.example.org", "https://user:pass@n8n.example.org",
                     "https://n8n.example.org/path", "https://n8n.example.org/#frag"):
            with self.subTest(base=base):
                with self.assertRaisesRegex(ReconcileError, "N8N_API_CONFIGURATION_INVALID"):
                    N8nApi(base, "placeholder_api_key_very_long")
        with self.assertRaisesRegex(ReconcileError, "N8N_API_CONFIGURATION_INVALID"):
            N8nApi("https://n8n.example.org", "")


if __name__ == "__main__":
    unittest.main()

"""Offline tests for authenticated VPS administrator operations.

Does not run root commands, start services, access the network or modify the
real VPS. All privileged interactions are mocked or use tmp directories.
"""
from __future__ import annotations

from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vps_admin as admin
import operations_broker as broker


class AdminArguments(unittest.TestCase):
    def test_rejects_shell_text_as_executable(self):
        with self.assertRaises(admin.Refused):
            admin._check_argv(["git status && curl example.com"])
        with self.assertRaises(admin.Refused):
            admin._check_argv(["/does/not/exist"])
        with self.assertRaises(admin.Refused):
            admin._check_argv(["/usr/bin/true", "invalid\x00input"])
        with self.assertRaises(admin.Refused):
            admin._check_argv(["/usr/bin/true"] * 65)

    def test_timeouts_are_bounded(self):
        for value in (0, 121, -1, True, 1.2, "20"):
            with self.assertRaises(admin.Refused):
                admin._check_timeout(value, maximum=120)
        self.assertEqual(admin._check_timeout(60, maximum=120), 60)

    def test_job_ids_are_strict(self):
        with tempfile.TemporaryDirectory() as work:
            with mock.patch.object(admin, "BASE", Path(work)), \
                 mock.patch.object(admin, "_state", return_value=Path(work)):
                with self.assertRaises(admin.Refused):
                    admin._job_dir("../../etc/passwd")
                with self.assertRaises(admin.Refused):
                    admin._job_dir("x" * 32)
                self.assertEqual(
                    admin._job_dir("a"*32),
                    Path(work) / ("a"*32),
                )

    def test_redacts_sensitive_diagnostics(self):
        message, _ = admin._sanitize(
            "Authorization: Bearer abcABC999\n"
            "DATABASE_URL=postgres://root:pass@host/db\n"
            "password=supersecret\n"
            "api_key=some-secret-token\n"
        )
        for secret in ("abcABC999", "root:pass", "supersecret", "some-secret-token"):
            self.assertNotIn(secret, message)

    def test_rejects_broker_admin_unexpected_parameters(self):
        self.assertEqual(
            broker.dispatch("admin_exec", params={"argv": ["/usr/bin/id"]}),
            {"status":"blocked", "reason":"admin_arguments_invalid"},
        )
        self.assertEqual(
            broker.dispatch("admin_cancel", params={"job_id": "x", "sudo": True}),
            {"status":"blocked", "reason":"admin_arguments_invalid"},
        )
        self.assertEqual(
            broker.dispatch("unknown", params={}).get("status"), "rejected",
        )

    def test_admin_broker_dispatch_is_typed(self):
        with mock.patch.object(broker.vps_admin, "execute",
                               return_value={"status":"completed","exit_code":0}) as execute:
            result = broker.dispatch("admin_exec", params={
                "argv":["/usr/bin/true"],"cwd":"/",
                "timeout_seconds":10,"show_output":False,
            })
        self.assertEqual(result["status"],"completed")
        execute.assert_called_once_with(
            argv=["/usr/bin/true"],cwd="/",timeout_seconds=10,show_output=False,
        )


class PrivateState(unittest.TestCase):
    def test_short_command_and_digest_only_audit(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            root.chmod(0o700)
            with mock.patch.object(admin, "BASE", root), \
                 mock.patch.object(admin, "_state", return_value=root):
                result = admin.execute(
                    [sys.executable, "-c", "print('SAFE_STATUS=PASS')"],
                    cwd=str(root), timeout_seconds=10,
                )
                self.assertEqual(result["status"], "completed", result)
                self.assertEqual(result["exit_code"], 0, result)
                self.assertIn("SAFE_STATUS=PASS", result["output"])
                self.assertNotIn("SAFE_STATUS=PASS",
                                 (root/"audit.jsonl").read_text())
                self.assertFalse(list(root.glob("sync-*.log")))
                audit = json.loads((root/"audit.jsonl").read_text().splitlines()[-1])
                self.assertIn("command_sha256", audit)
                self.assertNotIn("argv", audit)

    def test_job_status_and_cancel_refuse_unknown(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            root.chmod(0o700)
            with mock.patch.object(admin, "BASE", root), \
                 mock.patch.object(admin, "_state", return_value=root):
                self.assertEqual(admin.status("a"*32)["status"], "blocked")
                self.assertEqual(admin.cancel("a"*32)["status"], "blocked")
                (root/("b"*32)).mkdir(mode=0o700)
                admin._write_json(root/("b"*32)/"status.json", {
                    "state":"completed", "exit_code":0,
                }, exclusive=True)
                result = admin.status("b"*32, show_output=False)
                self.assertEqual(result["status"], "completed")
                self.assertEqual(result["exit_code"], 0)
                self.assertEqual(admin.cancel("b"*32).get("reason"),"job_not_active")

    def test_job_spawn_requires_explicit_systemd_run(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            root.chmod(0o700)
            process = types.SimpleNamespace(returncode=0)
            with mock.patch.object(admin, "BASE", root), \
                 mock.patch.object(admin, "_state", return_value=root), \
                 mock.patch.object(admin.subprocess, "run", return_value=process) as run:
                result = admin.start(
                    [sys.executable, "-c", "print('hello')"],
                    cwd=str(root), timeout_seconds=60,
                )
            self.assertEqual(result["status"],"queued",result)
            self.assertEqual(len(result["job_id"]),32)
            cmd = run.call_args.args[0]
            self.assertEqual(cmd[0],admin.SYSTEMD_RUN)
            self.assertIn("--property=Type=oneshot", cmd)
            self.assertIn("--property=TimeoutStartSec=180", cmd)
            self.assertEqual(run.call_args.kwargs["shell"],False)

    def test_rejects_unauthorized_directory(self):
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            root.chmod(0o755)
            with mock.patch.object(admin, "BASE", root):
                self.assertEqual(
                    admin.execute(["/usr/bin/true"],cwd="/",show_output=False)["status"],
                    "blocked",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)

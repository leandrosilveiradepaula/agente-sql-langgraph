"""Static audit of the OFF-by-default D284/#557 read-only release path.

Never exercises a release, touches systemd, reaches a network or changes data.
"""
from __future__ import annotations

from hashlib import sha1
from pathlib import Path
import re
import subprocess
import unittest

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "upgrade_cia_j1_recurrent_auditor_once.sh"
AUDITOR = HERE / "crypto_j1_readonly.py"


def blob_sha(raw: bytes) -> str:
    return sha1(f"blob {len(raw)}\0".encode("ascii") + raw).hexdigest()


class RecurringAuditorReleaseTests(unittest.TestCase):
    def test_script_bash_syntax_without_running_it(self):
        result = subprocess.run(
            ["bash", "-n", str(SCRIPT)], check=False,
            capture_output=True, text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_new_source_hash_exact_and_fixed_commit(self):
        source = SCRIPT.read_text(encoding="utf-8")
        target = blob_sha(AUDITOR.read_bytes())
        self.assertEqual(target, "c01c55e381ce444eacb31be70eb5613326b09d21")
        self.assertIn(f"NEW_AUDIT={target}", source)
        self.assertIn(
            "OLD_AUDIT=e876c2ae46d1164b05b76b323a527f2a31dcceea",
            source,
        )
        self.assertIn(
            "SOURCE_COMMIT=955eda46015d35dbe44a40f9240b821b1f493201",
            source,
        )
        self.assertIn('hash_is "$TMP/crypto_j1_readonly.py" "$NEW_AUDIT"', source)
        self.assertNotIn("/main/deploy/vps-mcp-g5/", source)

    def test_preflight_off_and_two_release_flags_required(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('test "$(id -u)" = 0', source)
        self.assertIn('test "$(hostname)" = srv1319424', source)
        self.assertIn('test "$#" -eq 2', source)
        self.assertIn('"--confirm-owner-auditor-release"', source)
        self.assertIn('"--allow-service-restarts"', source)
        self.assertIn('RELEASE_AUTHORIZATION_REQUIRED=true', source)
        self.assertIn('MODIFICATIONS=none', source)
        self.assertIn('trap cleanup EXIT', source)
        self.assertIn('ROLLED_BACK', source)
        self.assertIn('BACKUP_PATH_ALREADY_PRESENT', source)

    def test_only_auditor_writes_and_restarts_two_readers(self):
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('changed=1', source)
        self.assertIn('completed=1', source)
        self.assertIn('/usr/bin/systemctl restart "$OWNER_SERVICE"', source)
        self.assertIn('/usr/bin/systemctl restart "$OPS_SERVICE"', source)
        self.assertNotIn('/usr/bin/systemctl restart "$TUNNEL_SERVICE"', source)
        self.assertNotRegex(
            source, r"/usr/bin/systemctl\s+(?:enable|disable|stop|start)\b"
        )
        self.assertNotRegex(source, r"\b(?:CREATE TABLE|DROP TABLE|DELETE FROM|UPDATE\s+candles|INSERT INTO)\b")
        self.assertNotIn("api.bybit.com", source)
        self.assertNotIn("systemctl restart cia-j1-n50-managed", source)
        self.assertNotIn("chmod 777", source)
        self.assertIn('hash_is "$FINANCE" "$FINANCE_BLOB"', source)
        self.assertIn('hash_is "$SIDECAR" "$SIDECAR_BLOB"', source)
        self.assertIn('hash_is "$OWNER_UNIT" "$OWNER_UNIT_BLOB"', source)
        self.assertIn('hash_is "$SOCKET_UNIT" "$SOCKET_UNIT_BLOB"', source)

    def test_existing_replay_and_proxy_contract_retained(self):
        source = AUDITOR.read_text(encoding="utf-8")
        self.assertIn("MAX_RECURRING_HOURS = 4096", source)
        self.assertIn("MAX_RECONCILE_GAP_HOURS = 48", source)
        self.assertIn('{"op": "cia_sqlite"}', source)
        self.assertIn('sqlite_audit_via_owner', source)
        self.assertNotIn("approved_for_live_use", source)
        self.assertIn("PRAGMA query_only=ON", source)


if __name__ == "__main__":
    unittest.main()

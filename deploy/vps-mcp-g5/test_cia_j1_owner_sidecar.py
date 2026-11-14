"""Offline tests for CIA owner-only socket and broker read-only projection."""
from __future__ import annotations

import importlib.util
import json
import stat
import struct
import time
from pathlib import Path
import unittest
from unittest.mock import patch, Mock


def _load(name: str):
    path = Path(__file__).with_name(name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reader = _load("crypto_j1_readonly")
ws = _load("crypto_j1_ws_d323")
sidecar = _load("cia_j1_sqlite_owner_sidecar")


class FakeSocket:
    def __init__(self, response: dict | bytes):
        self.payload = (
            json.dumps(response, separators=(",", ":")).encode("ascii") + b"\n"
            if type(response) is dict else response
        )
        self.sent = None
        self.connected = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def settimeout(self, timeout):
        self.timeout = timeout

    def connect(self, path):
        self.connected = path

    def sendall(self, data):
        self.sent = data

    def recv(self, _amount):
        chunk, self.payload = self.payload, b""
        return chunk


def valid_report():
    return {
        "status": "pass",
        "contracts": 2, "stored_candles": 100,
        "published_checkpoints": 26,
        "last_published_end_ms": reader.EXPECT[-1],
        "sqlite_integrity": True,
        "contiguous_candles": True,
        "digest_replay": True, "halted": False,
        "trading_enabled": False,
        "marketwide_top50_verified": False,
    }



def valid_recurring_report():
    report = valid_report()
    report["stored_candles"] = 142
    report["published_checkpoints"] = 27
    report["last_published_end_ms"] = reader.EXPECT[-1] + 21 * reader.HOUR_MS
    return report


class SidecarTests(unittest.TestCase):
    def test_literal_allowlisted_request_only_from_root_broker(self):
        ok = b'{"op":"cia_sqlite"}\n'
        self.assertTrue(sidecar._authorized(ok, 0))
        for payload, uid in [
            (ok, 1000),
            (b'{"op":"cia_sqlite","path":"/etc/shadow"}\n', 0),
            (b'{"op":"orders"}\n', 0),
            (b'{"op":"cia_sqlite"}', 0),
            (b'{"op":"cia_sqlite"}\nextra', 0),
            (b"x" * 150 + b"\n", 0),
            (b'["cia_sqlite"]\n', 0),
            (b'{"op":"cia_sqlite","sql":"SELECT *"}\n', 0),
        ]:
            with self.subTest(payload=payload, uid=uid):
                self.assertFalse(sidecar._authorized(payload, uid))

    def test_owner_reader_wiring_is_restricted(self):
        with patch.object(sidecar, "sqlite_audit", return_value=valid_report()) as audit:
            self.assertEqual(sidecar.sqlite_audit()["status"], "pass")
            audit.assert_called_once_with()

    def test_broker_socket_success_and_exact_audit_schema(self):
        fake = FakeSocket(valid_report())
        with patch.object(reader.socket, "socket", return_value=fake):
            report = reader.sqlite_audit_via_owner()
        self.assertEqual(report, valid_report())
        self.assertEqual(fake.connected, reader.OWNER_SOCKET)
        self.assertEqual(fake.sent, b'{"op": "cia_sqlite"}\n')
        self.assertFalse(report["trading_enabled"])

    def test_broker_accepts_recurring_only_with_consistent_count_and_no_extra_data(self):
        fake = FakeSocket(valid_recurring_report())
        with patch.object(reader.socket, "socket", return_value=fake):
            actual = reader.sqlite_audit_via_owner()
        self.assertEqual(actual, valid_recurring_report())
        self.assertEqual(actual["last_published_end_ms"],
                         reader.EXPECT[-1] + 21*reader.HOUR_MS)
        self.assertNotIn("BTCUSDT", json.dumps(actual))

    def test_broker_rejects_extra_fields_and_misleading_passes(self):
        samples = [
            {**valid_recurring_report(), "stored_candles": 140},
            {**valid_recurring_report(), "published_checkpoints": 48},
            {**valid_recurring_report(), "published_checkpoints": 26},
            {**valid_recurring_report(), "last_published_end_ms": reader.EXPECT[-1]},
            {**valid_recurring_report(), "last_published_end_ms":
                reader.EXPECT[-1] + 49*reader.HOUR_MS, "stored_candles": 142},
            {**valid_recurring_report(), "digest_replay": False},
            {**valid_recurring_report(), "trading_enabled": True},
            {**valid_report(), "prices": [100, 200]},
            {**valid_report(), "orders_sent": True},
            {**valid_report(), "stored_candles": 99},
            {**valid_report(), "marketwide_top50_verified": True},
            b"secret\n",
            b"",
            b'{"status":"pass","trading_enabled":false}\n',
            b'{"status":"pass"}\n{"status":"pass"}\n',
            b"x" * 4098,
        ]
        for payload in samples:
            with self.subTest(payload=str(payload)[:60]):
                with patch.object(reader.socket, "socket",
                                  return_value=FakeSocket(payload)):
                    report = reader.sqlite_audit_via_owner()
                self.assertEqual(report["status"], "blocked")
                self.assertFalse(report["trading_enabled"])
                self.assertNotIn("prices", report)

    def test_unavailable_owner_does_not_leak_credentials_or_paths(self):
        fake = FakeSocket(valid_report())
        def denied(_):
            raise PermissionError("private-secret-token")
        fake.connect = denied
        with patch.object(reader.socket, "socket", return_value=fake):
            report = reader.sqlite_audit_via_owner()
        self.assertEqual(report["reason"], "sqlite_owner_service_unavailable")
        self.assertNotIn("private-secret-token", json.dumps(report))
        with patch.object(reader.socket, "socket", side_effect=OSError("no socket")):
            self.assertEqual(reader.sqlite_audit_via_owner()["status"], "blocked")



def valid_ws_report():
    closed_end = (time.time_ns() // 1_000_000 // reader.HOUR_MS) * reader.HOUR_MS
    return {
        "schema_version": "j1-n50-ws-closed24h-owner-witness-v1",
        "status": "ws_24h_local_evidence_verified",
        "latest_eligible_closed_end_ms": closed_end,
        "verified_closed_hours": 24, "expected_closed_hours": 24,
        "verified_contracts_per_hour": 50, "expected_contracts_per_hour": 50,
        "persisted_ws_rows": 1200,
        "ranked_scope_sha256": "a" * 64,
        "ws_metadata_sha256": "b" * 64,
        "ws_journal_sha256": "c" * 64,
        "last_hour_sha256": "d" * 64,
        "ws_timer_active_enabled": True,
        "rotation_timer_active_enabled": True,
        "n2_quiesced": True, "old_rest_n50_quiesced": True,
        "ws_service_not_failed": True,
        "ws_journal_integrity_verified": True,
        "ws_closed_24h_local_verified": True,
        "rotation_36h_live_verified": False,
        "continuous_collector_verified": False,
        "marketwide_top50_verified": False,
        "crypto_identity_independently_verified": False,
        "source_authenticated": False, "approved_for_signals": False,
        "live_trading_authorized": False, "orders_sent": False,
        "network_requests": 0, "database_mutation_statements": 0,
        "systemd_modified": False,
    }


def accumulating_ws_report():
    report = valid_ws_report()
    report.update(
        status="accumulating_or_incomplete_ws_24h",
        verified_closed_hours=0, verified_contracts_per_hour=0,
        ws_closed_24h_local_verified=False, last_hour_sha256=None,
    )
    return report


class D323OwnerTests(unittest.TestCase):
    def test_fixed_ws_operation_authenticates_root_and_rejects_extra_arguments(self):
        literal = b'{"op":"cia_ws_d323"}\n'
        self.assertTrue(sidecar._authorized(literal, 0))
        for data, uid in (
            (literal, 1000),
            (b'{"op":"cia_ws_d323","path":"/tmp/db"}\n', 0),
            (b'{"op":"cia_ws_d323","sql":"SELECT *"}\n', 0),
            (b'{"op":"cia_ws_d323","enable_live":true}\n', 0),
            (b'{"op":"cia_ws_d323"}\n\n', 1000),
        ):
            with self.subTest(data=data):
                self.assertFalse(sidecar._authorized(data, uid))

    def test_exact_ws_witness_and_no_trading_promotion(self):
        self.assertTrue(ws.validate_ws_d323_report(valid_ws_report()))
        self.assertTrue(reader.validate_ws_d323_report(accumulating_ws_report()))
        bad = [
            {**valid_ws_report(), "orders_sent": True},
            {**valid_ws_report(), "marketwide_top50_verified": True},
            {**valid_ws_report(), "rotation_36h_live_verified": True},
            {**valid_ws_report(), "source_authenticated": True},
            {**valid_ws_report(), "approved_for_signals": True},
            {**valid_ws_report(), "network_requests": 1},
            {**valid_ws_report(), "persisted_ws_rows": 1199},
            {**valid_ws_report(), "verified_closed_hours": 23},
            {**valid_ws_report(), "ws_journal_integrity_verified": False},
            {**valid_ws_report(), "last_hour_sha256": "1notahash"},
            {**valid_ws_report(), "persisted_ws_rows": True},
            {**valid_ws_report(), "symbol": "BTCUSDT"},
            {**valid_ws_report(), "status": "unknown_status"},
            {**accumulating_ws_report(), "ws_closed_24h_local_verified": True},
        ]
        for altered in bad:
            with self.subTest(keys=altered):
                self.assertFalse(reader.validate_ws_d323_report(altered))

    def test_proxy_accepts_only_exact_json_from_owner_socket(self):
        for payload in (valid_ws_report(), accumulating_ws_report()):
            fake = FakeSocket(payload)
            with patch.object(reader.socket, "socket", return_value=fake):
                self.assertEqual(ws.ws_d323_audit_via_owner(), payload)
            self.assertEqual(fake.sent, b'{"op":"cia_ws_d323"}\n')
            self.assertEqual(fake.connected, reader.OWNER_SOCKET)
        for payload in (
            {**valid_ws_report(), "orders_sent": True},
            {**valid_ws_report(), "prices": [1, 2]},
            b'{"status":"pass"}\n',
            b'{"status":"pass"}\n{"status":"pass"}\n',
            b"private-secret-token",
            b"x" * 4097,
        ):
            with patch.object(reader.socket, "socket",
                              return_value=FakeSocket(payload)):
                response = reader.ws_d323_audit_via_owner()
            self.assertEqual(response["status"], "blocked")
            self.assertFalse(response["trading_enabled"])
            self.assertNotIn("private-secret-token", json.dumps(response))

    def test_sidecar_invokes_only_owner_pinned_no_network_witness(self):
        uid = 2468
        folder = Mock(st_mode=stat.S_IFDIR | 0o700, st_uid=uid)
        script = Mock(st_mode=stat.S_IFREG | 0o600, st_uid=uid, st_nlink=1)
        run = Mock(returncode=0, stdout=(
            json.dumps(valid_ws_report(), separators=(",", ":")).encode("ascii") + b"\n"
        ))
        with patch.object(sidecar.pwd, "getpwnam",
                          return_value=Mock(pw_uid=uid)), \
             patch.object(sidecar.os, "getuid", return_value=uid), \
             patch.object(sidecar.os, "geteuid", return_value=uid), \
             patch.object(sidecar.os, "lstat", side_effect=[folder, script]), \
             patch.object(sidecar.subprocess, "run", return_value=run) as proc:
            result = sidecar.ws_d323_audit()
        self.assertEqual(result["status"], "ws_24h_local_evidence_verified")
        args, kwargs = proc.call_args
        self.assertIn("--allow-private-readonly-audit", args[0])
        self.assertIn("--enable-ws-24h-witness", args[0])
        self.assertEqual(kwargs["cwd"], sidecar.WS_D323_CODE)
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(kwargs["timeout"], 90)
        self.assertNotIn("http", " ".join(args[0]))
        self.assertNotIn("SQL", " ".join(args[0]))

    def test_sidecar_abstention_exit65_is_not_fabricated_pass(self):
        uid = 2468
        folder = Mock(st_mode=stat.S_IFDIR | 0o700, st_uid=uid)
        script = Mock(st_mode=stat.S_IFREG | 0o600, st_uid=uid, st_nlink=1)
        raw = json.dumps(accumulating_ws_report()).encode("ascii") + b"\n"
        with patch.object(sidecar.pwd, "getpwnam",
                          return_value=Mock(pw_uid=uid)), \
             patch.object(sidecar.os, "getuid", return_value=uid), \
             patch.object(sidecar.os, "geteuid", return_value=uid), \
             patch.object(sidecar.os, "lstat", side_effect=[folder, script]), \
             patch.object(sidecar.subprocess, "run",
                          return_value=Mock(returncode=65, stdout=raw)):
            self.assertEqual(sidecar.ws_d323_audit()["status"],
                             "accumulating_or_incomplete_ws_24h")
        with patch.object(sidecar.pwd, "getpwnam",
                          return_value=Mock(pw_uid=uid)), \
             patch.object(sidecar.os, "getuid", return_value=uid), \
             patch.object(sidecar.os, "geteuid", return_value=uid), \
             patch.object(sidecar.os, "lstat", side_effect=[folder, script]), \
             patch.object(sidecar.subprocess, "run",
                          return_value=Mock(returncode=0, stdout=raw)):
            self.assertEqual(sidecar.ws_d323_audit()["status"], "blocked")

    def test_sidecar_socket_never_accepts_untrusted_peer_or_missing_fields(self):
        for op in (b'{"op":"cia_ws_d323"}\n',
                   b'{"op":"cia_ws_d323","sql":"SELECT 1"}\n'):
            conn = Mock()
            conn.getsockopt.return_value = struct.pack("3i", 1234, 1000, 1000)
            conn.recv.return_value = op
            sidecar._serve_client(conn)
            response = json.loads(conn.sendall.call_args.args[0])
            self.assertEqual(response["status"], "blocked")
            self.assertFalse(response["trading_enabled"])
        conn = Mock()
        conn.getsockopt.return_value = struct.pack("3i", 1234, 0, 0)
        conn.recv.return_value = b'{"op":"cia_ws_d323"}\n'
        with patch.object(sidecar, "ws_d323_audit",
                          return_value=accumulating_ws_report()) as witness:
            sidecar._serve_client(conn)
        self.assertEqual(witness.call_count, 1)
        self.assertEqual(json.loads(conn.sendall.call_args.args[0])["status"],
                         "accumulating_or_incomplete_ws_24h")


if __name__ == "__main__":
    unittest.main()

"""Offline tests for CIA owner-only socket and broker read-only projection."""
from __future__ import annotations

import importlib.util
import json
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


if __name__ == "__main__":
    unittest.main()

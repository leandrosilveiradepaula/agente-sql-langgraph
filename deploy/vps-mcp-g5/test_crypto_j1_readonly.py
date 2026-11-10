"""Offline, no VPS/network, for the fixed Crypto Intelligence J1 MCP boundary."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import json
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "crypto_j1_readonly", Path(__file__).with_name("crypto_j1_readonly.py")
)
j1 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(j1)


class J1AuditTests(unittest.TestCase):
    def test_systemd_requires_allowlisted_status_and_never_returns_raw(self):
        responses = iter([
            "LoadState=loaded\nActiveState=active\nSubState=waiting\nNextElapseUSecRealtime=\n",
            "Result=success\nExecMainStatus=0\n",
        ])
        with patch.object(j1, "_run_fixed", side_effect=lambda argv: next(responses)) as run:
            result = j1.timer_status()
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["timer_active"])
        self.assertEqual(run.call_count, 2)
        self.assertFalse(result["trading_enabled"])
        self.assertNotIn("symbol", json.dumps(result))

    def test_journal_exact_24_and_denial(self):
        records = []
        for i, end in enumerate(j1.EXPECT):
            records.append(json.dumps({
                "schema_version": "j1-m1-rest-hourly-research-v1",
                "decision_end_ms": end, "status": "research_sample_closed_hour_persisted",
                "failure_category": None, "selected_research_contracts": 2,
                "contracts_at_decision": 2, "orders_sent": False,
                "marketwide_top50_verified": False,
                "new_closed_candles": 4 if i == 0 else 2,
                "requests_attempted": 2,
            }))
        with patch.object(j1, "_run_fixed", return_value="\n".join(records)):
            ok = j1.journal_summary()
        self.assertEqual(ok["status"], "pass", ok)
        self.assertEqual((ok["new_candles"], ok["public_gets"]), (50, 48))
        self.assertNotIn("symbol", json.dumps(ok))
        records[3] = records[3].replace("research_sample_closed_hour_persisted", "provider_denied")
        with patch.object(j1, "_run_fixed", return_value="\n".join(records)):
            self.assertEqual(j1.journal_summary()["status"], "incomplete")

    def test_sqlite_replays_all_rows_and_rejects_tampering(self):
        with TemporaryDirectory() as temp:
            dbpath = Path(temp) / "j1.sqlite"
            init = j1.EXPECT[0] - 3*j1.HOUR_MS
            symbols = ["BTCUSDT", "ETHUSDT"]
            with sqlite3.connect(dbpath) as db:
                db.executescript("""
                CREATE TABLE scope(id INTEGER,scope_digest TEXT,members_json TEXT,
                                   initial_end_ms INTEGER,halted_reason TEXT);
                CREATE TABLE published_hour(end_ms INTEGER, observed_contracts INTEGER);
                CREATE TABLE cursor(symbol TEXT,next_open_ms INTEGER);
                CREATE TABLE candles(symbol TEXT,open_ms INTEGER,
                  open TEXT,high TEXT,low TEXT,close TEXT,
                  base_volume TEXT,quote_turnover TEXT,received_at_ms INTEGER,
                  digest_sha256 TEXT);
                """)
                db.execute("INSERT INTO scope VALUES(1,?,?,?,NULL)",
                           ("a"*64, json.dumps(symbols), init))
                pubs = [init, init+j1.HOUR_MS, *j1.EXPECT]
                db.executemany("INSERT INTO published_hour VALUES(?,2)",
                               ((end,) for end in pubs))
                for symbol in symbols:
                    db.execute("INSERT INTO cursor VALUES(?,?)",
                               (symbol,j1.EXPECT[-1]))
                    for i in range(50):
                        opened = init - 24*j1.HOUR_MS + i*j1.HOUR_MS
                        row=[str(opened), "1", "2", "1", "2", "20", "40"]
                        from hashlib import sha256
                        digest=sha256(json.dumps(
                            [symbol,row],sort_keys=True,separators=(",",":"),
                            ensure_ascii=True).encode("ascii")).hexdigest()
                        db.execute("INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?)",
                                   (symbol,opened,*row[1:],opened+j1.HOUR_MS,digest))
                db.commit()
            with patch.object(j1,"DB",dbpath),patch.object(j1,"_private_file"):
                good=j1.sqlite_audit()
                self.assertEqual(good["status"],"pass",good)
                self.assertEqual(good["stored_candles"],100)
                self.assertNotIn("BTCUSDT",json.dumps(good))
                with sqlite3.connect(dbpath) as db:
                    db.execute("UPDATE candles SET close='9' WHERE open_ms=?",(
                        init-24*j1.HOUR_MS,))
                    db.commit()
                bad=j1.sqlite_audit()
                self.assertEqual(bad["status"],"blocked")
                self.assertEqual(bad["reason"],"sqlite_audit_unavailable")

    def test_unavailable_does_not_leak_exceptions(self):
        with patch.object(j1,"_run_fixed",side_effect=j1.Rejected("secret_token")):
            self.assertEqual(j1.timer_status()["status"],"blocked")
            self.assertNotIn("secret_token",json.dumps(j1.journal_summary()))


if __name__ == "__main__":
    unittest.main()

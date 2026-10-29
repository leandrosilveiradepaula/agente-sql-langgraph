"""Offline, no SQL connections. Tests P3 approval and financial-result contract."""
from __future__ import annotations

from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import tempfile
from unittest import TestCase, main
from unittest.mock import patch

from scripts.operations import p3_numeric_parity_readonly as p3


def h(x: str) -> str:
    return hashlib.sha256(x.encode()).hexdigest()


class Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.description = [type("Column", (), {"type_code": 1700})()]
        self.batch_used = False

    def execute(self, sql, *, prepare=False):
        if not prepare:
            raise AssertionError("SQL must use prepared extended protocol")

    def fetchmany(self, count):
        if self.batch_used:
            return []
        self.batch_used = True
        return self.rows


class Contract(TestCase):
    def setUp(self):
        self.org = "11111111-1111-4111-8111-111111111111"
        self.run = "22222222-2222-4222-8222-222222222222"
        self.policy = {
            "contract_version": "1", "organization_id": self.org,
            "expected_database": "fixture_db", "expected_role": "fixture_reader",
            "authorized_relations": ["alpha.balance", "beta.cash"],
            "authorized_functions": ["sum"],
            "max_rows": 20, "max_result_bytes": 5000,
            "statement_timeout_ms": 4000, "lock_timeout_ms": 1000,
        }
        def side(sql, run):
            return {
                "sql": sql, "sql_sha256": h(sql), "run_id": run,
                "provider_key": "fixture", "model_key": "offline",
                "config_version": "v1", "question_sha256": h("question"),
            }
        self.pair = {
            "contract_version": "1", "agent_run_id": self.run,
            "organization_id": self.org, "question_sha256": h("question"),
            "context_version": "catalog-v1",
            "official": side("SELECT SUM(amount) FROM alpha.balance", "official-1"),
            "shadow": {
                **side("SELECT SUM(amount) FROM alpha.balance", "shadow-1"),
                "shadow_record_id": "shadow-fixture-1",
                "gates": {"security": "approved", "contract": "approved", "preflight": "approved"},
                "preflight_executed": False, "requires_reapproval": False,
                "real_sql_executed": False,
            },
        }

    def test_valid_pair_and_authorized_sql(self):
        policy, pair = p3.prepare(self.policy, self.pair)
        self.assertEqual(pair["organization_id"], policy["organization_id"])

    def test_wrong_tenant_or_provider_or_hash_or_unapproved_gate(self):
        for key, value in [
            ("organization_id", "33333333-3333-4333-8333-333333333333"),
            ("question_sha256", "0"*64),
        ]:
            with self.subTest(key=key):
                pair = json.loads(json.dumps(self.pair))
                pair[key] = value
                with self.assertRaises(p3.P3Blocked):
                    p3.prepare(self.policy, pair)
        for field, value in [
            ("model_key", "other"), ("sql_sha256", "0"*64),
            ("real_sql_executed", True),
        ]:
            with self.subTest(field=field):
                pair = json.loads(json.dumps(self.pair))
                pair["shadow"][field] = value
                with self.assertRaises(p3.P3Blocked):
                    p3.prepare(self.policy, pair)
        for gate in ("security", "contract", "preflight"):
            pair = json.loads(json.dumps(self.pair))
            pair["shadow"]["gates"][gate] = "not_run"
            with self.assertRaises(p3.P3Blocked):
                p3.prepare(self.policy, pair)

    def test_rejects_sql_outside_authorized_catalog(self):
        bad = [
            "SELECT amount FROM gamma.private",
            "SELECT amount FROM balance",
            "DELETE FROM alpha.balance",
            "SELECT pg_sleep(2) FROM alpha.balance",
            "SELECT * FROM alpha.balance",
            "SELECT amount FROM alpha.balance; SELECT amount FROM beta.cash",
        ]
        for sql in bad:
            with self.subTest(sql=sql):
                pair = json.loads(json.dumps(self.pair))
                pair["shadow"]["sql"] = sql
                pair["shadow"]["sql_sha256"] = h(sql)
                with self.assertRaises(p3.P3Blocked):
                    p3.prepare(self.policy, pair)

    @__import__("unittest").skipUnless(os.name == "posix", "POSIX-only file permission contract")
    def test_no_remote_call_without_opt_in(self):
        with tempfile.TemporaryDirectory() as root:
            policy_path = Path(root) / "policy.json"
            pair_path = Path(root) / "pair.json"
            policy_path.write_text(json.dumps(self.policy))
            pair_path.write_text(json.dumps(self.pair))
            policy_path.chmod(0o600)
            pair_path.chmod(0o600)
            with patch.object(p3, "compare_readonly") as execute:
                self.assertEqual(p3.main(["--policy", str(policy_path), "--pair", str(pair_path)]), 0)
                execute.assert_not_called()
            with patch.object(p3, "compare_readonly") as execute:
                self.assertEqual(p3.main(["--policy", str(policy_path), "--pair", str(pair_path),
                                         "--execute-readonly"]), 3)
                execute.assert_not_called()

    def test_non_posix_private_files_fail_closed(self):
        with patch.object(p3.os, "name", "nt"):
            with self.assertRaises(p3.P3Blocked) as caught:
                p3._private_json(Path("unused-private-policy.json"))
            self.assertEqual(caught.exception.code, "PRIVATE_FILES_POSIX_REQUIRED")

    @__import__("unittest").skipUnless(os.name == "posix", "POSIX-only file permission contract")
    def test_non_private_input_is_denied(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "policy.json"
            path.write_text(json.dumps(self.policy))
            path.chmod(0o644)
            with self.assertRaises(p3.P3Blocked):
                p3._private_json(path)

    def test_different_financial_values_and_order_independence(self):
        policy = p3._parse_policy(self.policy)
        a = p3._collect(Cursor([(Decimal("10.00"),), (Decimal("20.00"),)]), "SQL", policy)
        b = p3._collect(Cursor([(Decimal("20.0"),), (Decimal("10.0"),)]), "SQL", policy)
        self.assertEqual(a["row_hashes"], b["row_hashes"])
        c = p3._collect(Cursor([(Decimal("10.0"),), (Decimal("20.01"),)]), "SQL", policy)
        self.assertNotEqual(a["row_hashes"], c["row_hashes"])
        with self.assertRaises(p3.P3Blocked):
            p3._collect(Cursor([(Decimal(i),) for i in range(21)]), "SQL", policy)


if __name__ == "__main__":
    main()

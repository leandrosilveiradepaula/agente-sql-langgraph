"""Fail-closed offline tests; no live credentials or database I/O."""
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parent / "operations" / "check_supabase_retirement_gate.py"
spec = importlib.util.spec_from_file_location("retirement_gate", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def evidence(destination="DEMO"):
    return {
        "schema_version": 1,
        "consumers": [
            {"consumer": name, "destination": destination,
             "verified_at": "2026-10-28T05:00:00Z",
             "evidence_sha": "a" * 40, "probe_id": "private-sanitized-probe"}
            for name in sorted(module.ALLOWED_CONSUMERS)
        ],
        "archive_verified": True,
        "rollback_verified": True,
        "observation_verified": True,
        "retirement_explicitly_approved": True,
    }


class RetirementSafetyTests(unittest.TestCase):
    def test_only_fully_verified_manifest_may_pass(self):
        self.assertEqual(module.analyze(evidence()), ("READY", []))

    def test_source_and_unknown_block(self):
        for value in ("SOURCE", "UNKNOWN"):
            with self.subTest(value=value):
                data = evidence()
                data["consumers"][0]["destination"] = value
                self.assertEqual(module.analyze(data)[0], "BLOCKED")

    def test_other_external_warehouse_is_allowed_if_attested(self):
        data = evidence()
        data["consumers"][2]["destination"] = "OTHER"
        self.assertEqual(module.analyze(data)[0], "READY")

    def test_missing_one_consumer_blocks(self):
        data = evidence()
        data["consumers"].pop()
        self.assertEqual(module.analyze(data), ("BLOCKED", ["INCOMPLETE_CONSUMERS"]))

    def test_duplicate_consumer_blocks(self):
        data = evidence()
        data["consumers"][0] = dict(data["consumers"][1])
        self.assertEqual(module.analyze(data)[0], "BLOCKED")

    def test_explicit_retirement_approval_never_implicit(self):
        data = evidence()
        data["retirement_explicitly_approved"] = False
        self.assertEqual(module.analyze(data)[0], "BLOCKED")

    def test_unaudited_sensitive_fields_block(self):
        data = evidence()
        data["consumers"][0]["dsn"] = "REDACTED"
        self.assertEqual(module.analyze(data), ("BLOCKED", ["INVALID_CONSUMER_RECORD"]))

    def test_unverified_metadata_blocks(self):
        data = evidence()
        data["consumers"][0]["evidence_sha"] = ""
        self.assertEqual(module.analyze(data), ("BLOCKED", ["UNVERIFIED_CONSUMER"]))

    def test_string_booleans_are_not_accepted(self):
        data = evidence()
        data["archive_verified"] = "true"
        self.assertEqual(module.analyze(data), ("BLOCKED", ["INVALID_ATTESTATION"]))


if __name__ == "__main__":
    unittest.main()

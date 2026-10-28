"""Retirement gate v2: separate evidence for restore, offsite and cutover.

All tests synthetic/offline. No Supabase, n8n, Docker, SQL or production writes.
"""
import copy
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parent / "operations" / "check_supabase_retirement_gate.py"
spec = importlib.util.spec_from_file_location("retirement_gate", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SHA = "a" * 64


def evidence(destination="DEMO"):
    return {
        "schema_version": 2,
        "consumers": [
            {"consumer": name, "destination": destination,
             "verified_at": "2026-10-28T18:24:24Z",
             "evidence_sha": "b" * 40,
             "probe_id": "private-sanitized-probe"}
            for name in sorted(module.ALLOWED_CONSUMERS)
        ],
        "gates": [
            {"gate": name, "status": "PASS",
             "verified_at": "2026-10-28T18:24:24Z",
             "evidence_sha": SHA,
             "probe_id": "synthetic-test-evidence"}
            for name in sorted(module.REQUIRED_GATES)
        ],
    }


class RetirementSafetyTests(unittest.TestCase):
    def test_only_completely_attested_v2_manifest_passes_synthetically(self):
        self.assertEqual(module.analyze(evidence()), ("READY", []))

    def test_legacy_v1_archive_true_can_never_approve_source_retirement(self):
        legacy = {
            "schema_version": 1,
            "consumers": evidence()["consumers"],
            "archive_verified": True,
            "rollback_verified": True,
            "observation_verified": True,
            "retirement_explicitly_approved": True,
        }
        self.assertEqual(module.analyze(legacy), ("BLOCKED", ["INVALID_VERSION"]))

    def test_missing_offsite_custody_cannot_be_conflated_with_restore_success(self):
        data = evidence()
        for gate in data["gates"]:
            if gate["gate"] == "offsite_ciphertext_custody":
                gate.update(status="PENDING", verified_at=None,
                            evidence_sha=None, probe_id=None)
        self.assertEqual(
            module.analyze(data),
            ("BLOCKED", ["GATE_NOT_ATTESTED:offsite_ciphertext_custody"]),
        )

    def test_each_non_archive_recovery_gate_blocks_independently(self):
        for required in module.REQUIRED_GATES:
            with self.subTest(gate=required):
                data = evidence()
                for item in data["gates"]:
                    if item["gate"] == required:
                        item.update(status="PENDING", verified_at=None,
                                    evidence_sha=None, probe_id=None)
                status, blockers = module.analyze(data)
                self.assertEqual(status, "BLOCKED")
                self.assertEqual(blockers, ["GATE_NOT_ATTESTED:" + required])

    def test_source_and_unknown_consumers_block(self):
        for value in ("SOURCE", "UNKNOWN"):
            with self.subTest(value=value):
                data = evidence()
                data["consumers"][0]["destination"] = value
                self.assertEqual(module.analyze(data)[0], "BLOCKED")

    def test_other_warehouse_requires_complete_attestations(self):
        data = evidence()
        data["consumers"][2]["destination"] = "OTHER"
        self.assertEqual(module.analyze(data)[0], "READY")

    def test_missing_and_duplicate_consumers_rejected(self):
        data = evidence()
        data["consumers"].pop()
        self.assertEqual(module.analyze(data), ("BLOCKED", ["INCOMPLETE_CONSUMERS"]))
        data = evidence()
        data["consumers"][0] = copy.deepcopy(data["consumers"][1])
        self.assertEqual(module.analyze(data)[0], "BLOCKED")

    def test_missing_and_duplicate_gates_rejected(self):
        data = evidence()
        data["gates"].pop()
        self.assertEqual(module.analyze(data), ("BLOCKED", ["INCOMPLETE_GATES"]))
        data = evidence()
        data["gates"][0] = dict(data["gates"][1])
        self.assertEqual(module.analyze(data)[0], "BLOCKED")

    def test_unverified_gate_evidence_rejected(self):
        for field, bad in (("evidence_sha", ""), ("evidence_sha", "a" * 40),
                           ("verified_at", ""), ("probe_id", "")):
            with self.subTest(field=field, bad=bad):
                data = evidence()
                data["gates"][0][field] = bad
                self.assertEqual(module.analyze(data)[0], "BLOCKED")

    def test_pending_gate_cannot_include_fake_pass_evidence(self):
        data = evidence()
        data["gates"][0]["status"] = "PENDING"
        self.assertEqual(module.analyze(data), ("BLOCKED", ["INVALID_PENDING_GATE"]))

    def test_attested_gate_never_accepts_sensitive_or_extra_fields(self):
        for field in ("dsn", "authorization", "secret", "sql"):
            with self.subTest(field=field):
                data = evidence()
                data["gates"][0][field] = "private-data"
                self.assertEqual(module.analyze(data), ("BLOCKED", ["INVALID_GATE_RECORD"]))
        data = evidence()
        data["consumers"][0]["dsn"] = "postgresql://PRIVATE"
        self.assertEqual(module.analyze(data), ("BLOCKED", ["INVALID_CONSUMER_RECORD"]))

    def test_gate_failure_modes_and_unknown_status_rejected(self):
        for value in ("pass", "FAIL", "NOT_VERIFIED", True, None):
            with self.subTest(status=value):
                data = evidence()
                data["gates"][0]["status"] = value
                self.assertEqual(module.analyze(data), ("BLOCKED", ["INVALID_GATE_STATUS"]))
        data = evidence()
        data["gates"][0]["gate"] = "unknown_client_rule"
        self.assertEqual(module.analyze(data), ("BLOCKED", ["INVALID_GATE_IDENTITY"]))

    def test_invalid_consumer_evidence_rejected(self):
        data = evidence()
        data["consumers"][0]["evidence_sha"] = ""
        self.assertEqual(module.analyze(data), ("BLOCKED", ["UNVERIFIED_CONSUMER"]))

    def test_malformed_payloads_are_fail_closed(self):
        for invalid in (None, [], {"schema_version": True},
                        {"schema_version": 2, "consumers": [], "gates": []}):
            with self.subTest(value=invalid):
                self.assertEqual(module.analyze(invalid)[0], "BLOCKED")
        data = evidence()
        data["gates"][0]["gate"] = ["unexpected", "list"]
        self.assertEqual(module.analyze(data), ("BLOCKED", ["INVALID_GATE_IDENTITY"]))


if __name__ == "__main__":
    unittest.main()

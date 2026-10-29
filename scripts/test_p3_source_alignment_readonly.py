"""Offline safety and portability proof for P3 physical-source alignment."""
from __future__ import annotations

from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from io import StringIO

from scripts.operations import p3_source_alignment_readonly as p3


class SourceGate(unittest.TestCase):
    def setUp(self):
        self.policy = {
            "database": "fixture_db", "role_name": "fixture_reader",
            "schema": "ledger_alpha", "relations": ["entries", "orgs"],
            "n8n": {
                "workflow_id": "workflow-1", "expected_node_count": 7,
                "binding_node_ids": ["node-a", "node-b"],
            },
        }
        self.context = [("ledger_alpha", "entries"), ("ledger_alpha", "orgs")]
        self.physical = [
            ("ledger_alpha", "entries", "entry_id", "int8"),
            ("ledger_alpha", "entries", "amount", "numeric"),
            ("ledger_alpha", "orgs", "id", "int8"),
            ("ledger_beta", "invoices", "invoice_id", "uuid"),
            ("ledger_beta", "invoices", "amount", "numeric"),
        ]
        self.grants = [
            ("ledger_alpha", "entries", True, False),
            ("ledger_alpha", "orgs", True, False),
        ]
        self.identity = (
            "fixture_reader", True, False, False, False, False,
            False, False, False, False, False, 0, 0, 0,
        )
        self.g1 = {
            "G1_AUDIT_MODE": "LOCAL_CLI_READ_ONLY",
            "G1_AUDIT_RESULT": "N8N_248_NORMALIZED_PASS",
            "G1_PUBLISHED_VERSION": "ACTIVE_MATCH",
            "G1_WORKFLOW_CONTRACT": "PASS",
            "G1_CREDENTIAL": "ENCRYPTED_RECORD_MATCH",
            "G1_NEW_BINDINGS": "2", "G1_OLD_BINDINGS": "0",
            "G1_OTHER_BINDINGS": "0", "G1_UNAUTHORIZED_NODE_DRIFT": "0",
        }
        self.deps = {
            "SUPABASE_DEPENDENCY_AUDIT": "READ_ONLY",
            "SUPABASE_N8N_OFFICIAL_CREDENTIAL_TARGET": "DEMO",
            "SUPABASE_SHADOW_CONTEXT_TARGET": "DEMO",
            "SUPABASE_SHADOW_EVIDENCE_TARGET": "DEMO",
            "SUPABASE_SHADOW_REAL_SQL_EXECUTION_DISABLED": "PASS",
            "SUPABASE_N8N_OFFICIAL_NODE_COUNT": "7",
        }

    def evaluate(self, **changes):
        args = dict(policy=self.policy, version="fixture-v1",
                    context=self.context, physical=self.physical,
                    role_rows=self.grants, role_identity=self.identity,
                    g1=self.g1, deps=self.deps)
        args.update(changes)
        return p3.evaluate(**args)

    def test_equal_physical_source_is_not_business_parity(self):
        report = self.evaluate()
        self.assertEqual(report["status"], "ready_for_semantic_review")
        self.assertEqual(report["blockers"], [])
        self.assertFalse(report["semantic_mapping_approved"])
        self.assertFalse(report["numeric_parity_proven"])
        self.assertFalse(report["financial_sql_executed"])
        self.assertEqual(report["llm_calls"], 0)

    def test_materially_different_second_context_rejected(self):
        context = [("ledger_beta", "invoices")]
        result = self.evaluate(context=context)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("CONTEXT_SOURCE_MISMATCH", result["blockers"])
        self.assertNotEqual(result["official_fingerprint"], result["catalog_fingerprint"])

    def test_same_table_names_other_schema_are_not_same_dataset(self):
        result = self.evaluate(context=[
            ("ledger_beta", "entries"), ("ledger_beta", "orgs"),
        ])
        self.assertIn("CONTEXT_SOURCE_MISMATCH", result["blockers"])

    def test_additional_effective_select_is_not_least_privilege(self):
        result = self.evaluate(role_rows=self.grants + [
            ("ledger_beta", "invoices", True, False)
        ])
        self.assertIn("ROLE_SCOPE_MISMATCH", result["blockers"])

    def test_missing_select_rejected(self):
        result = self.evaluate(role_rows=self.grants[:1])
        self.assertIn("ROLE_SCOPE_MISMATCH", result["blockers"])

    def test_extra_write_privilege_rejected_even_outside_catalog(self):
        result = self.evaluate(role_rows=self.grants + [
            ("ledger_beta", "invoices", False, True)
        ])
        self.assertIn("ROLE_WRITE_PRIVILEGE", result["blockers"])

    def test_missing_schema_or_columns_block(self):
        result = self.evaluate(physical=[x for x in self.physical
                                          if x[1] != "orgs"])
        self.assertIn("PHYSICAL_COLUMNS_MISSING", result["blockers"])

    def test_rejects_all_unsafe_role_attributes(self):
        for field in range(2, 11):
            role = list(self.identity)
            role[field] = True
            with self.subTest(field=field), self.assertRaises(p3.AlignmentBlocked):
                self.evaluate(role_identity=tuple(role))
        for field in range(11, 14):
            role = list(self.identity)
            role[field] = 1
            with self.subTest(field=field), self.assertRaises(p3.AlignmentBlocked):
                self.evaluate(role_identity=tuple(role))
        role = list(self.identity)
        role[1] = False
        with self.assertRaises(p3.AlignmentBlocked):
            self.evaluate(role_identity=tuple(role))

    def test_g1_proof_missing_or_drifted(self):
        for field, value in [
            ("G1_PUBLISHED_VERSION", "UNVERIFIED"),
            ("G1_AUDIT_RESULT", "SETTINGS_DRIFT_REVIEW"),
            ("G1_NEW_BINDINGS", "1"),
            ("G1_OTHER_BINDINGS", "1"),
            ("G1_UNAUTHORIZED_NODE_DRIFT", "1"),
        ]:
            with self.subTest(field=field):
                result = self.evaluate(g1={**self.g1, field:value})
                self.assertIn("N8N_PUBLISHED_NOT_ATTESTED", result["blockers"])
        self.assertIn("N8N_PUBLISHED_NOT_ATTESTED",
                      self.evaluate(g1=None)["blockers"])

    def test_dependency_proof_wrong_database_or_shadow_execution(self):
        for field, value in [
            ("SUPABASE_N8N_OFFICIAL_CREDENTIAL_TARGET", "SOURCE"),
            ("SUPABASE_SHADOW_CONTEXT_TARGET", "SOURCE"),
            ("SUPABASE_SHADOW_EVIDENCE_TARGET", "UNKNOWN"),
            ("SUPABASE_SHADOW_REAL_SQL_EXECUTION_DISABLED", "BLOCKED"),
            ("SUPABASE_N8N_OFFICIAL_NODE_COUNT", "8"),
        ]:
            with self.subTest(field=field):
                result = self.evaluate(deps={**self.deps,field:value})
                self.assertIn("N8N_DATASOURCE_NOT_ATTESTED",result["blockers"])
        self.assertIn("N8N_DATASOURCE_NOT_ATTESTED",
                      self.evaluate(deps=None)["blockers"])

    def test_wrong_policy_or_catalog_identifier_rejected(self):
        with self.assertRaises(p3.AlignmentBlocked):
            p3.validate_policy({**self.policy,"schema":"bad;drop"})
        with self.assertRaises(p3.AlignmentBlocked):
            p3.validate_policy({**self.policy,"relations":["entries","entries"]})
        with self.assertRaises(p3.AlignmentBlocked):
            self.evaluate(context=self.context + self.context[:1])
        with self.assertRaises(p3.AlignmentBlocked):
            self.evaluate(physical=self.physical + [("x","y","z;","int8")])

    @unittest.skipUnless(os.name == "posix", "POSIX permission model")
    def test_private_proof_owner_only_and_duplicate_keys_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"proof"
            path.write_text("G1_AUDIT_RESULT=STRICT_PASS\n")
            path.chmod(0o600)
            self.assertEqual(p3.read_private_proof(path),
                             {"G1_AUDIT_RESULT":"STRICT_PASS"})
            path.write_text("G1_AUDIT_RESULT=PASS\nG1_AUDIT_RESULT=PASS\n")
            with self.assertRaises(p3.AlignmentBlocked):
                p3.read_private_proof(path)
            path.chmod(0o644)
            with self.assertRaises(p3.AlignmentBlocked):
                p3.read_private_proof(path)

    def test_private_schema_draft_has_no_financial_semantics(self):
        draft = p3.schema_draft(self.policy, self.physical)
        self.assertFalse(draft["can_import_into_semantic_catalog"])
        self.assertFalse(draft["can_execute_financial_sql"])
        self.assertEqual(len(draft["tables"]), 2)
        for row in draft["tables"]:
            self.assertIsNone(row["approved_metrics"])
            self.assertIsNone(row["approved_joins"])
            self.assertIsNone(row["approved_date_semantics"])
            self.assertIsNone(row["approved_sign_conventions"])
            self.assertEqual(row["review"], "UNMAPPED")

    @unittest.skipUnless(os.name == "posix", "POSIX permission model")
    def test_probe_snapshot_rejects_wrong_database_role_or_version(self):
        raw = {
            "contract": "p3-metadata-snapshot-v1",
            "database": self.policy["database"],
            "role_name": self.policy["role_name"],
            "context_version": "fixture-v1",
            "context": self.context,
            "physical": self.physical,
            "grants": self.grants,
            "identity": self.identity,
            "sql_executed": False,
            "llm_calls": 0,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"snapshot.json"
            path.write_text(json.dumps(raw))
            path.chmod(0o600)
            loaded = p3.verify_probe_snapshot(p3.read_private_snapshot(path),
                                              self.policy, "fixture-v1")
            self.assertEqual(len(loaded), 4)
            for field, wrong in (
                ("database", "wrong"), ("role_name", "admin"),
                ("context_version", "other-v1"), ("sql_executed", True),
                ("llm_calls", 1),
            ):
                with self.subTest(field=field):
                    changed = {**raw, field: wrong}
                    path.write_text(json.dumps(changed))
                    with self.assertRaises(p3.AlignmentBlocked):
                        p3.verify_probe_snapshot(p3.read_private_snapshot(path),
                                                 self.policy, "fixture-v1")
            path.chmod(0o644)
            with self.assertRaises(p3.AlignmentBlocked):
                p3.read_private_snapshot(path)

    def test_live_shadow_probe_denies_mismatched_context_and_execution_flag(self):
        with patch.dict(os.environ, {
            "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "false",
            "SEMANTIC_AGENT_VERSION": "other",
        }):
            with self.assertRaises(p3.AlignmentBlocked) as caught:
                p3.probe_existing_shadow("fixture-v1","semantic_context",
                                         "ai_ducklake_table_catalog")
            self.assertEqual(caught.exception.reason, "SHADOW_CONTEXT_VERSION_MISMATCH")
        with patch.dict(os.environ, {
            "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "true",
            "SEMANTIC_AGENT_VERSION": "fixture-v1",
        }):
            with self.assertRaises(p3.AlignmentBlocked) as caught:
                p3.probe_existing_shadow("fixture-v1","semantic_context",
                                         "ai_ducklake_table_catalog")
            self.assertEqual(caught.exception.reason, "SHADOW_EXECUTION_FLAG_UNVERIFIED")

    @unittest.skipUnless(os.name == "posix", "POSIX permission model")
    def test_unmapped_schema_draft_requires_private_directory_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)/"private"
            parent.mkdir(mode=0o700)
            destination = parent/"draft.json"
            draft = p3.schema_draft(self.policy, self.physical)
            p3.create_private_draft(destination, draft)
            self.assertEqual(destination.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(destination.read_text()), draft)
            with self.assertRaises(p3.AlignmentBlocked):
                p3.create_private_draft(destination, draft)
            open_parent = Path(directory)/"open"
            open_parent.mkdir(mode=0o755)
            with self.assertRaises(p3.AlignmentBlocked):
                p3.create_private_draft(open_parent/"draft.json",draft)

    def test_cli_without_dsn_never_connects(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"policy.json"
            path.write_text(json.dumps(self.policy))
            with patch.dict(os.environ, {"P3_METADATA_DSN":""}):
                output = StringIO()
                with redirect_stdout(output):
                    rc = p3.main(["--policy",str(path),
                                  "--context-version","fixture-v1"])
                self.assertEqual(rc,2)
                report = json.loads(output.getvalue())
                self.assertEqual(report["reason"],"P3_METADATA_DSN_MISSING")
                self.assertFalse(report["financial_sql_executed"])
                self.assertEqual(report["llm_calls"],0)


if __name__ == "__main__":
    unittest.main()

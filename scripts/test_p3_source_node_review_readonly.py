"""Offline fail-closed proof for the P3 stored-dependency review draft."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
import unittest

from scripts.operations import p3_source_node_review_readonly as review


def fixture():
    old = "credential-old"
    nodes = [
        {"id": "trigger", "name": "start", "type": "n8n-nodes-base.webhook"},
        {"id": "route", "name": "route", "type": "n8n-nodes-base.if"},
    ]
    for i in range(4):
        nodes.append({
            "id": f"source-{i}", "name": f"data operation {i}",
            "type": "n8n-nodes-base.postgres",
            "parameters": {"operation": "executeQuery", "query": "SELECT secret_value FROM private_data"},
            "credentials": {"postgres": {"id": old}},
        })
    nodes.extend([
        {"id": "exec-a", "name": "approved-executor-a", "type": "n8n-nodes-base.postgres",
         "credentials": {"postgres": {"id": old}}},
        {"id": "exec-b", "name": "approved-executor-b", "type": "n8n-nodes-base.postgres",
         "credentials": {"postgres": {"id": old}}},
        {"id": "dead", "name": "unused operation", "type": "n8n-nodes-base.postgres",
         "credentials": {"postgres": {"id": old}}},
    ])
    connections = {
        "start": {"main": [[{"node": "route"}]]},
        "route": {"main": [
            [{"node": f"data operation {i}"} for i in range(4)],
            [{"node": "approved-executor-a"}, {"node": "approved-executor-b"}],
        ]},
    }
    policy = {"n8n": {
        "workflow_id": "workflow-1", "expected_node_count": len(nodes),
        "binding_node_ids": ["exec-a", "exec-b"],
        "old_credential_id": old,
    }}
    snapshot = {"workflow": {"id": "workflow-1", "nodes": nodes,
                              "connections": connections},
                "old_credential_id": old, "credential_id": "credential-new",
                "fingerprint": "a" * 64}
    g1 = dict(
        G1_AUDIT_MODE="LOCAL_CLI_READ_ONLY", G1_WORKFLOW_CONTRACT="PASS",
        G1_CREDENTIAL="ENCRYPTED_RECORD_MATCH",
        G1_PUBLISHED_VERSION="ACTIVE_MATCH", G1_NODE_SET="PASS",
        G1_NODE_ORDER="UNCHANGED", G1_NEW_BINDINGS="2",
        G1_OLD_BINDINGS="0", G1_OTHER_BINDINGS="0",
        G1_UNAUTHORIZED_NODE_DRIFT="0", G1_FIELD_CONNECTIONS="UNCHANGED",
        G1_AUDIT_RESULT="SETTINGS_DRIFT_REVIEW",
        G1_SETTINGS_REVIEW_COUNT="1", G1_SETTINGS_EQUIVALENCE="REVIEW_REQUIRED",
    )
    deps = dict(
        SUPABASE_DEPENDENCY_AUDIT="READ_ONLY", SUPABASE_N8N_OFFICIAL_NODE_COUNT=str(len(nodes)),
        SUPABASE_N8N_POSTGRES_CREDENTIAL_COUNT="2",
        SUPABASE_N8N_EXECUTION_ROLE_ATTESTED="PASS",
        SUPABASE_N8N_EXECUTION_CREDENTIAL_TARGET="DEMO",
        SUPABASE_SHADOW_REAL_SQL_EXECUTION_DISABLED="PASS",
        SUPABASE_N8N_REACHABLE_UNKNOWN_POSTGRES_NODES="0",
        SUPABASE_N8N_REACHABLE_OTHER_SUPABASE_UNVERIFIED_POSTGRES_NODES="0",
        SUPABASE_N8N_REACHABLE_SOURCE_POSTGRES_NODES="4",
        SUPABASE_N8N_REACHABLE_DEMO_POSTGRES_NODES="2",
        SUPABASE_SHADOW_EVIDENCE_TARGET="SOURCE",
    )
    return policy, snapshot, g1, deps


class SourceReview(unittest.TestCase):
    def run_review(self, *, change=None):
        policy, snapshot, g1, deps = fixture()
        if change:
            change(policy, snapshot, g1, deps)
        return review.review_existing_proofs(policy=policy, snapshot=snapshot,
                                             g1=g1, deps=deps)

    def test_exact_reachable_legacy_nodes_and_protected_executor(self):
        result = self.run_review()
        self.assertEqual(result["status"], "REVIEW_ONLY_NOT_A_CUTOVER_GATE")
        self.assertEqual(result["source_node_ordinals"], [3, 4, 5, 6])
        self.assertEqual(result["demo_executor_ordinals"], [7, 8])
        self.assertEqual(result["source_node_count"], 4)
        self.assertEqual(result["demo_executor_count"], 2)
        self.assertEqual(len(result["node_review"]), 6)
        self.assertEqual(result["shadow_evidence_target_at_p3_audit"], "SOURCE")
        self.assertFalse(result["mapping_approved"])
        self.assertFalse(result["operational_cutover_authorized"])
        self.assertFalse(result["real_financial_sql_executed"])
        serialized = json.dumps(result)
        self.assertNotIn("secret_value", serialized)
        self.assertNotIn("private_data", serialized)
        self.assertNotIn("password", serialized)
        self.assertNotIn("credential-old", serialized)
        self.assertNotIn("credential-new", serialized)
        self.assertTrue(all(x["cutover_disposition"] is None
                            for x in result["node_review"]))

    def test_strict_g1_still_does_not_authorize_cutover(self):
        result = self.run_review(change=lambda p,s,g,d: g.update({
            "G1_AUDIT_RESULT": "STRICT_PASS",
            "G1_SETTINGS_EQUIVALENCE": "EXACT",
        }))
        self.assertFalse(result["operational_cutover_authorized"])
        self.assertNotEqual(result["published_attestation"], "PASS")

    def test_two_materially_different_node_graphs_same_engine(self):
        def swap(p, s, g, d):
            nodes = s["workflow"]["nodes"]
            nodes[2]["name"] = "unidade-different-source"
            s["workflow"]["connections"]["route"]["main"][0][0]["node"] = "unidade-different-source"
            nodes[2]["parameters"]["operation"] = {"expression": "dynamic"}
        result = self.run_review(change=swap)
        self.assertEqual(result["source_node_count"], 4)
        self.assertEqual(result["node_review"][0]["operation_class"], "UNKNOWN")

    def test_decrypted_or_wrong_credential_in_pre_put_snapshot_rejected(self):
        def drift(p,s,g,d):
            s["workflow"]["nodes"][2]["credentials"]["postgres"]["id"] = "other"
        with self.assertRaises(review.ReviewBlocked) as error:
            self.run_review(change=drift)
        self.assertEqual(error.exception.code, "UNEXPECTED_SNAPSHOT_CREDENTIAL")

    def test_missing_two_execution_nodes_blocks(self):
        def drift(p,s,g,d):
            s["workflow"]["nodes"][7]["disabled"] = True
        with self.assertRaises(review.ReviewBlocked) as error:
            self.run_review(change=drift)
        self.assertEqual(error.exception.code, "EXECUTOR_NOT_REACHABLE")

    def test_source_counts_must_agree_with_p3_local_audit(self):
        def drift(p,s,g,d):
            d["SUPABASE_N8N_REACHABLE_SOURCE_POSTGRES_NODES"] = "5"
        with self.assertRaises(review.ReviewBlocked) as error:
            self.run_review(change=drift)
        self.assertEqual(error.exception.code, "P3_SOURCE_COUNT_MISMATCH")

    def test_g1_drift_cannot_be_silently_normalized(self):
        for key,value in [
            ("G1_UNAUTHORIZED_NODE_DRIFT", "1"),
            ("G1_NODE_ORDER", "CHANGED"),
            ("G1_FIELD_CONNECTIONS", "CHANGED"),
            ("G1_PUBLISHED_VERSION", "NOT_ATTESTED"),
        ]:
            def drift(p,s,g,d, key=key, value=value): g[key] = value
            with self.subTest(key=key), self.assertRaises(review.ReviewBlocked):
                self.run_review(change=drift)

    def test_unsupported_g1_state_fails_closed(self):
        def drift(p,s,g,d): g["G1_AUDIT_RESULT"] = "STRUCTURAL_REVIEW_REQUIRED"
        with self.assertRaises(review.ReviewBlocked) as error:
            self.run_review(change=drift)
        self.assertEqual(error.exception.code, "G1_NOT_ELIGIBLE_FOR_INVENTORY")

    def test_source_or_other_project_identity_unverified_blocks(self):
        def drift(p,s,g,d): d["SUPABASE_N8N_REACHABLE_OTHER_SUPABASE_UNVERIFIED_POSTGRES_NODES"] = "1"
        with self.assertRaises(review.ReviewBlocked):
            self.run_review(change=drift)

    def test_connection_to_unknown_target_refuses_inventory(self):
        def drift(p,s,g,d):
            s["workflow"]["connections"]["route"]["main"][0].append({"node": "missing-node"})
        with self.assertRaises(review.ReviewBlocked) as error:
            self.run_review(change=drift)
        self.assertEqual(error.exception.code, "WORKFLOW_GRAPH_INVALID")

    @unittest.skipUnless(os.name == "posix", "POSIX ownership")
    def test_report_private_atomic_and_not_overwritten(self):
        report = self.run_review()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "p3-source-node-review.json"
            review._write_private_draft(path, report)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(path.read_text())["source_node_count"], 4)
            with self.assertRaises(review.ReviewBlocked):
                review._write_private_draft(path, report)
            with tempfile.TemporaryDirectory() as other:
                parent = Path(other) / "open"
                parent.mkdir(mode=0o755)
                with self.assertRaises(review.ReviewBlocked):
                    review._write_private_draft(parent / "draft.json", report)


if __name__ == "__main__":
    unittest.main()

"""Offline regression/portability contract for physical-to-semantic review."""
from __future__ import annotations

import unittest
from scripts.operations import p3_semantic_mapping_review_readonly as review


def fixture(schema="operations_alpha"):
    if schema == "operations_alpha":
        pol = {"schema": schema, "database": "db_alpha", "role_name": "reader_alpha",
               "relations": ["entries", "departments"]}
        physical = [(schema, "entries", "pk", "int8"),
                    (schema, "entries", "amount", "numeric"),
                    (schema, "entries", "event_day", "date"),
                    (schema, "entries", "dept_id", "text"),
                    (schema, "departments", "code", "text"),
                    (schema, "departments", "name", "text")]
        src, dim, metric, tm, pk, from_col, to_col = (
            "entries", "departments", "amount", "event_day", "pk", "dept_id", "code"
        )
    else:
        pol = {"schema": schema, "database": "db_beta", "role_name": "reader_beta",
               "relations": ["invoices", "regions"]}
        physical = [(schema, "invoices", "invoice_uuid", "uuid"),
                    (schema, "invoices", "gross_total", "float8"),
                    (schema, "invoices", "created_at", "timestamptz"),
                    (schema, "invoices", "region_ref", "text"),
                    (schema, "regions", "region_id", "text"),
                    (schema, "regions", "label", "text")]
        src, dim, metric, tm, pk, from_col, to_col = (
            "invoices", "regions", "gross_total", "created_at",
            "invoice_uuid", "region_ref", "region_id"
        )
    draft = review.create_review(pol, physical, "version-1")
    draft["candidate_version"] = "version-2"
    draft["organization_id"] = "tenant-from-product"
    draft["review_evidence"] = {"reviewer": "accounting-authority",
                                "source_definition_ref": "owner-approved-file",
                                "review_timestamp": "2026-10-30"}
    draft["intent_definitions"] = [{"concept": "dynamic-from-versioned-context"}]
    draft["entity_aliases"] = []
    draft["business_rules"] = []
    for row in draft["tables"]:
        is_src = row["table"] == src
        row["grain"] = "one row per approved unique ID"
        row["primary_key"] = pk if is_src else to_col
        row["key_columns"] = [row["primary_key"], from_col] if is_src else [to_col]
        row["business_evidence"] = "approved documentation reference"
        row["metric_bindings"] = ([{"concept": "approved measure", "column": metric,
                                    "aggregation": "sum",
                                    "sign_convention": "as documented by accounting",
                                    "evidence": "approved documentation reference"}]
                                  if is_src else [])
        row["date_bindings"] = ([{"column": tm, "reference": "approved financial period",
                                  "evidence": "approved documentation reference"}]
                                if is_src else [])
        row["dimension_bindings"] = []
        row["join_bindings"] = ([{"from_column": from_col, "to_table": dim,
                                  "to_column": to_col, "cardinality": "many_to_one",
                                  "evidence": "approved documentation reference"}]
                                if is_src else [])
        row["dre_mappings"] = []
    return pol, physical, draft


class MappingReviewTests(unittest.TestCase):
    def test_unreviewed_template_has_no_business_guesses(self):
        pol, physical, _ = fixture()
        draft = review.create_review(pol, physical, "version-1")
        self.assertFalse(draft["can_execute_financial_sql"])
        self.assertFalse(draft["can_import_into_semantic_catalog"])
        self.assertTrue(all(t["grain"] is None and t["metric_bindings"] is None
                            and t["join_bindings"] is None for t in draft["tables"]))
        result = review.check_review(draft, pol, physical, "version-1")
        self.assertEqual(result["status"], "blocked")
        self.assertIn("NEW_VERSION_REQUIRED", result["issue_codes"])

    def test_two_materially_distinct_clients_no_if_per_tenant(self):
        for schema in ("operations_alpha", "billing_beta"):
            with self.subTest(schema=schema):
                pol, physical, draft = fixture(schema)
                result = review.check_review(draft, pol, physical, "version-1")
                self.assertEqual(result["status"], "structural_preview_only", result["issues"])
                self.assertEqual(result["table_count"], 2)
                self.assertEqual(result["mapped_table_count"], 2)
                self.assertEqual(result["metric_binding_count"], 1)
                self.assertEqual(len(result["table_catalog_preview"]), 2)
                self.assertFalse(result["finance_semantics_verified"])
                self.assertFalse(result["activation_authorized"])
                self.assertFalse(result["financial_sql_authorized"])
                self.assertFalse(result["financial_sql_executed"])
                self.assertEqual(result["llm_calls"], 0)

    def test_incomplete_grain_is_rejected(self):
        pol, physical, draft = fixture()
        draft["tables"][0]["grain"] = None
        r = review.check_review(draft, pol, physical, "version-1")
        self.assertIn("GRAIN_REQUIRED", r["issue_codes"])
        self.assertIsNone(r["table_catalog_preview"])

    def test_invalid_numeric_type(self):
        pol, physical, draft = fixture()
        target = next(t for t in draft["tables"] if t["table"] == "entries")
        target["metric_bindings"][0]["column"] = "dept_id"
        r = review.check_review(draft, pol, physical, "version-1")
        self.assertIn("METRIC_COLUMN_OR_TYPE_INVALID", r["issue_codes"])

    def test_invalid_temporal_type(self):
        pol, physical, draft = fixture()
        target = next(t for t in draft["tables"] if t["table"] == "entries")
        target["date_bindings"][0]["column"] = "amount"
        r = review.check_review(draft, pol, physical, "version-1")
        self.assertIn("DATE_REFERENCE_INVALID", r["issue_codes"])

    def test_cross_tenant_join_denied(self):
        pol, physical, draft = fixture()
        target = next(t for t in draft["tables"] if t["table"] == "entries")
        target["join_bindings"][0]["to_table"] = "other_schema.secret_table"
        r = review.check_review(draft, pol, physical, "version-1")
        self.assertIn("JOIN_PHYSICAL_REFERENCE_INVALID", r["issue_codes"])

    def test_join_type_mismatch_denied(self):
        pol, physical, draft = fixture()
        target = next(t for t in draft["tables"] if t["table"] == "entries")
        target["join_bindings"][0]["from_column"] = "pk"
        r = review.check_review(draft, pol, physical, "version-1")
        self.assertIn("JOIN_PHYSICAL_REFERENCE_INVALID", r["issue_codes"])

    def test_fanout_always_requires_separate_review(self):
        pol, physical, draft = fixture()
        target = next(t for t in draft["tables"] if t["table"] == "entries")
        target["join_bindings"][0]["cardinality"] = "one_to_many"
        r = review.check_review(draft, pol, physical, "version-1")
        self.assertIn("JOIN_FANOUT_REVIEW_REQUIRED", r["issue_codes"])

    def test_reviewer_missing_is_not_accepted(self):
        pol, physical, draft = fixture()
        draft["review_evidence"] = None
        r = review.check_review(draft, pol, physical, "version-1")
        self.assertIn("BUSINESS_REVIEW_EVIDENCE_REQUIRED", r["issue_codes"])

    def test_tenant_and_version_required(self):
        pol, physical, draft = fixture()
        draft["organization_id"] = None
        draft["candidate_version"] = "version-1"
        r = review.check_review(draft, pol, physical, "version-1")
        self.assertIn("TENANT_REQUIRED", r["issue_codes"])
        self.assertIn("NEW_VERSION_REQUIRED", r["issue_codes"])

    def test_cannot_enable_sql_or_catalog_import_by_editing_review(self):
        pol, physical, draft = fixture()
        for key in ("can_execute_financial_sql", "can_import_into_semantic_catalog"):
            with self.subTest(key=key):
                edited = dict(draft, **{key: True})
                with self.assertRaises(review.MappingBlocked):
                    review.check_review(edited, pol, physical, "version-1")

    def test_physical_fingerprint_detects_column_drift(self):
        pol, physical, draft = fixture()
        physical.append((pol["schema"], "entries", "new_column", "text"))
        with self.assertRaises(review.MappingBlocked):
            review.check_review(draft, pol, physical, "version-1")

    def test_credentials_scope_changes_rejected(self):
        pol, physical, draft = fixture()
        with self.assertRaises(review.MappingBlocked):
            review.check_review(draft, dict(pol, role_name="postgres"),
                                physical, "version-1")

    def test_no_extra_table(self):
        pol, physical, draft = fixture()
        draft["tables"][0]["table"] = "hidden_relation"
        with self.assertRaises(review.MappingBlocked):
            review.check_review(draft, pol, physical, "version-1")

    def test_no_metric_bindings(self):
        pol, physical, draft = fixture()
        for row in draft["tables"]:
            row["metric_bindings"] = []
        r = review.check_review(draft, pol, physical, "version-1")
        self.assertIn("NO_FINANCIAL_METRIC_BINDINGS", r["issue_codes"])

    def test_intent_required(self):
        pol, physical, draft = fixture()
        draft["intent_definitions"] = []
        r = review.check_review(draft, pol, physical, "version-1")
        self.assertIn("SEMANTIC_COLLECTION_UNREVIEWED", r["issue_codes"])

    def test_duplicate_physical_column_blocked(self):
        pol, physical, _ = fixture()
        physical.append(physical[0])
        with self.assertRaises(review.MappingBlocked):
            review.create_review(pol, physical, "version-1")


if __name__ == "__main__":
    unittest.main()

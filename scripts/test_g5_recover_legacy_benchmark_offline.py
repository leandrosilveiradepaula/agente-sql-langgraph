"""Offline and no-network tests of the legacy n8n benchmark recovery boundary."""
import unittest
from unittest.mock import patch

from scripts.operations.g5_archive_supabase_source import ArchiveBlocked
from scripts.operations.g5_recover_legacy_benchmark_offline import (
    _documents, _select_group, _archive_manifest, EXPECTED_QUESTIONS,
)


class G5LegacyBenchmarkRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.version = "v2.2.31-benchmark-historico-cliente"
        self.run_id = "a1111111-b222-4333-8444-555555555555"
        self.other_run_id = "a1111111-b222-4333-8444-666666666666"
        self.questions = [{"id": i, "pergunta": "Question " + str(i),
                           "agent_version": self.version, "ativo": True}
                          for i in range(1, EXPECTED_QUESTIONS + 1)]
        self.results = [{"benchmark_id": i, "run_id": self.run_id,
                         "agent_version": self.version,
                         "sql_gerado": "SELECT 1", "intent_detectada": "aggregate",
                         "passou": i % 2 == 0, "status_teste": "historical"}
                        for i in range(1, EXPECTED_QUESTIONS + 1)]

    def test_latest_complete_group_by_time_not_score(self):
        questions = [{"version": self.version, "rows": 63, "distinct": 63}]
        groups = [
            {"version": self.version, "rows": 63, "distinct": 63,
             "run_id": self.run_id, "latest": "2026-09-01T00:00:00Z"},
            {"version": self.version, "rows": 63, "distinct": 63,
             "run_id": self.other_run_id, "latest": "2026-09-02T00:00:00Z"},
            {"version": self.version, "rows": 62, "distinct": 62,
             "run_id": self.run_id, "latest": "2026-10-01T00:00:00Z"},
        ]
        self.assertEqual(_select_group(questions, groups),
                         (self.version, self.other_run_id))

    def test_ambiguous_and_missing_runs_fail_closed(self):
        counts = [{"version": self.version, "rows": 63, "distinct": 63}]
        with self.assertRaises(ArchiveBlocked):
            _select_group(counts, [])
        groups = [{"version": self.version, "rows": 63, "distinct": 63,
                   "run_id": run_id, "latest": "2026-09-02T00:00:00Z"}
                  for run_id in (self.run_id, self.other_run_id)]
        with self.assertRaises(ArchiveBlocked):
            _select_group(counts, groups)

    def test_bad_version_cannot_reach_dynamic_sql(self):
        with self.assertRaises(ArchiveBlocked):
            _select_group([{"version": "x';drop table t;--", "rows": 63,
                            "distinct": 63}],
                          [{"version": "x';drop table t;--", "rows": 63,
                            "distinct": 63, "run_id": self.run_id,
                            "latest": "2026-09-01T00:00:00Z"}])

    def test_blind_manifest_never_receives_historical_gold(self):
        baseline, manifest, freeze, witness = _documents(
            self.version, self.run_id, self.questions, self.results)
        self.assertEqual(len(baseline["cases"]), 63)
        self.assertEqual(len(manifest["cases"]), 63)
        self.assertEqual(set(manifest["cases"][0]), {"case_id", "question"})
        self.assertEqual(manifest["cases"][0]["question"], "Question 1")
        self.assertNotIn("official_sql", str(manifest))
        self.assertNotIn("agent_run_id", str(manifest))
        self.assertEqual(baseline["cases"][0]["official_sql"], "SELECT 1")
        self.assertEqual(witness["source_run_id"], self.run_id)
        self.assertEqual(freeze["case_count"], 63)

    def test_missing_sql_stays_missing_not_fabricated(self):
        self.results[0]["sql_gerado"] = None
        baseline, _, _, _ = _documents(
            self.version, self.run_id, self.questions, self.results)
        self.assertNotIn("official_sql", baseline["cases"][0])

    def test_duplicate_and_missing_result_fail(self):
        self.results[0]["benchmark_id"] = 2
        with self.assertRaises(ArchiveBlocked):
            _documents(self.version, self.run_id, self.questions, self.results)

    def test_inactive_or_foreign_version_fail(self):
        self.questions[0]["ativo"] = False
        with self.assertRaises(ArchiveBlocked):
            _documents(self.version, self.run_id, self.questions, self.results)


if __name__ == "__main__":
    unittest.main()
from __future__ import annotations

import unittest

from app.domain.sql_analysis import analyze_sql


class TypedTemporalLiteralTests(unittest.TestCase):
    def test_ansi_temporal_literal_prefix_is_not_column(self):
        for kind in ("DATE", "TIME", "TIMESTAMP"):
            with self.subTest(kind=kind):
                sql = (
                    "SELECT SUM(amount) FROM finance_events "
                    f"WHERE posted_at >= {kind} '2026-09-01' "
                    f"AND posted_at < {kind} '2026-10-01'"
                )
                analysis = analyze_sql(sql)
                columns = [item["column"] for item in analysis["column_references"]]
                self.assertIn("posted_at", columns)
                self.assertNotIn(kind.casefold(), columns)
                self.assertEqual(2, len([
                    item for item in analysis["predicates"]
                    if item.get("column") == "posted_at" and item.get("supported")
                ]))

    def test_bare_temporal_words_are_not_silently_ignored(self):
        analysis = analyze_sql("SELECT date, time, timestamp FROM finance_events")
        columns = [item["column"] for item in analysis["column_references"]]
        self.assertTrue({"date", "time", "timestamp"}.issubset(columns))

    def test_quoted_identifiers_remain_columns(self):
        analysis = analyze_sql('SELECT "date" FROM finance_events')
        self.assertIn("date", [
            item["column"] for item in analysis["column_references"]
        ])

    def test_unrelated_unknown_identifier_is_preserved(self):
        analysis = analyze_sql(
            "SELECT amount FROM finance_events WHERE unknown_field >= DATE '2026-09-01'"
        )
        columns = [item["column"] for item in analysis["column_references"]]
        self.assertIn("unknown_field", columns)
        self.assertNotIn("date", columns)


if __name__ == "__main__":
    unittest.main()

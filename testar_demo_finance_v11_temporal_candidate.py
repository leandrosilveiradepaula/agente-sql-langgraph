from __future__ import annotations

from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parent
    / "scripts/migrations/021_prepare_demo_finance_context_v11.sql"
)


def test_temporal_candidate_has_explicit_source_binding() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "'date_binding_strategy', 'configured_metric_source_date'" in sql
    assert "'date_bindings', jsonb_build_array(" in sql
    assert "'metric_concept', 'amount'" in sql
    assert "'target_table', 'demo_lakehouse.gold_orcamento'" in sql
    assert "'target_column', 'competencia'" in sql
    assert "'date_binding_strategy', 'unique_metric_source_catalog_date'" not in sql
    assert "'demo_lakehouse.gold_lancamentos_contabeis'" not in sql.split(
        "'date_bindings', jsonb_build_array(", 1
    )[1].split("'granularities'", 1)[0]


def test_candidate_remains_immutable_and_non_promoting() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "demo-finance-v11 already exists; immutable context not modified" in sql
    assert "demo-finance-v10 source context is missing" in sql
    assert "SEMANTIC_AGENT_VERSION=" not in sql
    assert "COMMIT;" in sql


if __name__ == "__main__":
    test_temporal_candidate_has_explicit_source_binding()
    test_candidate_remains_immutable_and_non_promoting()
    print("DEMO_V11_TEMPORAL_CANDIDATE=PASS")

from __future__ import annotations

from pathlib import Path

MIGRATION = Path("scripts/migrations/015_prepare_demo_finance_context_v5.sql")
RUNNER = Path("scripts/apply_demo_finance_v5.sh")


def test_linhagem_v4_para_v5() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "'demo-finance-v4'::text AS source_version" in text
    assert "'demo-finance-v5'::text AS target_version" in text


def test_comparacao_explicita_exige_operacao_e_dois_cenarios() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "'comparison_operation_primary'" in text
    assert "'analytical_operation'" in text
    assert "'budget_scenario'" in text
    assert "'realized_scenario'" in text
    assert "'minimum_concept_matches', 3" in text
    assert "'score', 80" in text


def test_trend_suprime_default_realizado() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "default_realized_scenario_for_financial_metric" in text
    assert "UNION ALL SELECT 'trend'" in text


def test_nao_altera_thresholds_benchmark_ou_runtime() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    for value in (
        "minimum_score",
        "ambiguity_margin",
        "ai_ducklake_benchmarks",
        "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=true",
    ):
        assert value not in text


def test_runner_fail_closed() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert 'SOURCE_VERSION="demo-finance-v4"' in text
    assert 'TARGET_VERSION="demo-finance-v5"' in text
    assert 'CONFIRM_VALUE="APLICAR_DEMO_FINANCE_V5"' in text
    assert "No write performed" in text
    assert "docker compose" not in text
    assert "SEMANTIC_AGENT_VERSION=" not in text


def main() -> None:
    tests = [
        ("linhagem v4 para v5", test_linhagem_v4_para_v5),
        ("comparison composita", test_comparacao_explicita_exige_operacao_e_dois_cenarios),
        ("trend sem default realizado", test_trend_suprime_default_realizado),
        ("sem thresholds benchmark runtime", test_nao_altera_thresholds_benchmark_ou_runtime),
        ("runner fail closed", test_runner_fail_closed),
    ]
    for index, (name, fn) in enumerate(tests, start=1):
        fn()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

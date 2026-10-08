from __future__ import annotations

from pathlib import Path

MIGRATION = Path("scripts/migrations/018_prepare_demo_finance_context_v8.sql")
RUNNER = Path("scripts/apply_demo_finance_v8.sh")


def test_linhagem_v7_para_v8() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "'demo-finance-v7'::text AS source_version" in text
    assert "'demo-finance-v8'::text AS target_version" in text


def test_default_realizado_nao_e_suprimido_por_operacao_ou_trend() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "default_realized_scenario_for_financial_metric" in text
    assert "term NOT IN ('analytical_operation', 'trend')" in text


def test_normaliza_metadata_legada_de_comparison() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "'{operation,output_behavior}'" in text
    assert "'{operation,combination_strategy}'" in text
    assert "'presentation'" in text
    assert "'combination'" in text


def test_sem_threshold_benchmark_runtime() -> None:
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
    assert 'SOURCE_VERSION="demo-finance-v7"' in text
    assert 'TARGET_VERSION="demo-finance-v8"' in text
    assert 'CONFIRM_VALUE="APLICAR_DEMO_FINANCE_V8"' in text
    assert "No write performed" in text
    assert "SEMANTIC_AGENT_VERSION=" not in text


def main() -> None:
    tests = [
        ("linhagem v7 para v8", test_linhagem_v7_para_v8),
        ("default realizado", test_default_realizado_nao_e_suprimido_por_operacao_ou_trend),
        ("comparison metadata", test_normaliza_metadata_legada_de_comparison),
        ("sem thresholds benchmark runtime", test_sem_threshold_benchmark_runtime),
        ("runner fail closed", test_runner_fail_closed),
    ]
    for index, (name, fn) in enumerate(tests, start=1):
        fn()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

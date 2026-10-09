from __future__ import annotations

from pathlib import Path

MIGRATION = Path("scripts/migrations/019_prepare_demo_finance_context_v9.sql")
RUNNER = Path("scripts/apply_demo_finance_v9.sh")


def test_linhagem_v8_para_v9() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "'demo-finance-v8'::text AS source_version" in text
    assert "'demo-finance-v9'::text AS target_version" in text


def test_restaura_supressao_de_default_para_intents_especializadas() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "UNION ALL SELECT 'analytical_operation'" in text
    assert "UNION ALL SELECT 'trend'" in text


def test_metric_binding_usa_regras_de_fonte_versionadas() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "WHEN 'realized_scenario' THEN 'realized_source'" in text
    assert "WHEN 'budget_scenario' THEN 'budget_source'" in text
    assert "entity_type = 'metric_binding'" in text


def test_sem_threshold_benchmark_runtime() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    for value in (
        "minimum_score",
        "ambiguity_margin",
        "ai_ducklake_benchmarks",
        "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=true",
    ):
        assert value not in text


def test_runner_persistente_fail_closed() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert 'SOURCE_VERSION="demo-finance-v8"' in text
    assert 'TARGET_VERSION="demo-finance-v9"' in text
    assert 'CONFIRM_VALUE="APLICAR_DEMO_FINANCE_V9"' in text
    assert "load_semantic_migration_env.sh" in text
    assert "No write performed" in text


def main() -> None:
    tests = [
        ("linhagem v8 para v9", test_linhagem_v8_para_v9),
        ("default especializado", test_restaura_supressao_de_default_para_intents_especializadas),
        ("metric binding por source rules", test_metric_binding_usa_regras_de_fonte_versionadas),
        ("sem thresholds benchmark runtime", test_sem_threshold_benchmark_runtime),
        ("runner persistente fail closed", test_runner_persistente_fail_closed),
    ]
    for index, (name, fn) in enumerate(tests, start=1):
        fn()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

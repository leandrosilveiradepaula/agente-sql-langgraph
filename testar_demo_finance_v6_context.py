from __future__ import annotations

from pathlib import Path

MIGRATION = Path("scripts/migrations/016_prepare_demo_finance_context_v6.sql")
RUNNER = Path("scripts/apply_demo_finance_v6.sh")


def test_linhagem_v5_para_v6() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert "'demo-finance-v5'::text AS source_version" in text
    assert "'demo-finance-v6'::text AS target_version" in text


def test_remove_colisoes_pos_normalizacao() -> None:
    text = MIGRATION.read_text(encoding="utf-8")
    assert '["compare","comparar","comparação","comparativo","versus","vs"]' in text
    assert '["orçamento","orçado","orçada"]' in text
    assert "'comparacao'" not in text
    assert "'orcamento'" not in text
    assert "'orcado'" not in text
    assert "'orcada'" not in text


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
    assert 'SOURCE_VERSION="demo-finance-v5"' in text
    assert 'TARGET_VERSION="demo-finance-v6"' in text
    assert 'CONFIRM_VALUE="APLICAR_DEMO_FINANCE_V6"' in text
    assert "No write performed" in text
    assert "SEMANTIC_AGENT_VERSION=" not in text


def main() -> None:
    tests = [
        ("linhagem v5 para v6", test_linhagem_v5_para_v6),
        ("dedup normalizado", test_remove_colisoes_pos_normalizacao),
        ("sem thresholds benchmark runtime", test_sem_threshold_benchmark_runtime),
        ("runner fail closed", test_runner_fail_closed),
    ]
    for index, (name, fn) in enumerate(tests, start=1):
        fn()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

from __future__ import annotations

from pathlib import Path


MIGRATION = Path("scripts/migrations/014_prepare_demo_finance_context_v4.sql")
RUNNER = Path("scripts/apply_demo_finance_v4.sh")


def _migration() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _runner() -> str:
    return RUNNER.read_text(encoding="utf-8")


def test_linhagem_demo_v3_para_v4() -> None:
    text = _migration()
    assert "'demo-finance-v3'::text AS source_version" in text
    assert "'demo-finance-v4'::text AS target_version" in text
    assert "ai_ducklake_benchmarks" not in text


def test_semantic_default_e_alterado_em_agent_rules() -> None:
    text = _migration()
    assert "UPDATE ai_ducklake_agent_rules target" in text
    assert "rule_content::jsonb" in text
    assert "default_realized_scenario_for_financial_metric" in text
    assert "UNION ALL SELECT 'analytical_operation'" in text


def test_nao_altera_thresholds_runtime_ou_sql() -> None:
    text = _migration()
    forbidden = (
        "minimum_score",
        "ambiguity_margin",
        "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=true",
        "ai_ducklake_benchmarks",
    )
    for value in forbidden:
        assert value not in text


def test_runner_fail_closed() -> None:
    text = _runner()
    assert 'SOURCE_VERSION="demo-finance-v3"' in text
    assert 'TARGET_VERSION="demo-finance-v4"' in text
    assert 'CONFIRM_VALUE="APLICAR_DEMO_FINANCE_V4"' in text
    assert 'if [[ "${target_count}" != "0" ]]' in text
    assert "No write performed" in text
    assert "docker compose" not in text
    assert "SEMANTIC_AGENT_VERSION=" not in text


def main() -> None:
    tests = [
        ("linhagem v3 para v4", test_linhagem_demo_v3_para_v4),
        ("semantic default em agent rules", test_semantic_default_e_alterado_em_agent_rules),
        ("sem thresholds runtime ou SQL", test_nao_altera_thresholds_runtime_ou_sql),
        ("runner fail closed", test_runner_fail_closed),
    ]
    for index, (name, function) in enumerate(tests, start=1):
        function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

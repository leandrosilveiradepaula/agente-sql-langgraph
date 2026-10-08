from __future__ import annotations

from pathlib import Path


MIGRATION = Path("scripts/migrations/013_prepare_demo_finance_context_v3.sql")
RUNNER = Path("scripts/apply_demo_finance_v3.sh")


def _migration() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def _runner() -> str:
    return RUNNER.read_text(encoding="utf-8")


def test_linhagem_demo_v2_para_v3() -> None:
    text = _migration()
    assert "'demo-finance-v2'::text AS source_version" in text
    assert "'demo-finance-v3'::text AS target_version" in text
    assert "ai_ducklake_benchmarks" not in text


def test_nao_altera_thresholds_ou_runtime() -> None:
    text = _migration()
    forbidden = (
        "minimum_score",
        "ambiguity_margin",
        "SEMANTIC_AGENT_VERSION",
        "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=true",
    )
    for value in forbidden:
        assert value not in text


def test_comparacao_e_ampliada_no_contexto() -> None:
    text = _migration()
    for term in ("compare", "comparando", "comparado", "comparada"):
        assert f"'{term}'" in text
    assert "analytical_operation" in text
    assert "comparison" in text


def test_default_realizado_respeita_operacao_explicita() -> None:
    text = _migration()
    assert "default_realized_scenario_for_financial_metric" in text
    assert "UNION ALL SELECT 'analytical_operation'" in text


def test_runner_falha_fechado_e_nao_ativa_runtime() -> None:
    text = _runner()
    assert 'SOURCE_VERSION="demo-finance-v2"' in text
    assert 'TARGET_VERSION="demo-finance-v3"' in text
    assert 'CONFIRM_VALUE="APLICAR_DEMO_FINANCE_V3"' in text
    assert 'if [[ "${target_count}" != "0" ]]' in text
    assert "No write performed" in text
    assert "docker compose" not in text
    assert "SEMANTIC_AGENT_VERSION=" not in text


def main() -> None:
    tests = [
        ("linhagem demo v2 para v3", test_linhagem_demo_v2_para_v3),
        ("sem thresholds ou runtime", test_nao_altera_thresholds_ou_runtime),
        ("comparacao ampliada", test_comparacao_e_ampliada_no_contexto),
        ("default realizado respeita operacao", test_default_realizado_respeita_operacao_explicita),
        ("runner fail closed", test_runner_falha_fechado_e_nao_ativa_runtime),
    ]
    for index, (name, function) in enumerate(tests, start=1):
        function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

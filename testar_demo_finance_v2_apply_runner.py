from __future__ import annotations

from pathlib import Path


RUNNER = Path("scripts/apply_demo_finance_v2.sh")


def _text() -> str:
    return RUNNER.read_text(encoding="utf-8")


def test_runner_exige_confirmacao_e_dsn_externo() -> None:
    text = _text()
    assert 'CONFIRM_VALUE="APLICAR_DEMO_FINANCE_V2"' in text
    assert "CONFIRM_APPLY" in text
    assert (
        "SEMANTIC_MIGRATION_POSTGRES_DSN must be set outside Git/chat/logs"
        in text
    )
    assert "POSTGRES_CONTEXT_SCHEMA must be set outside Git/chat/logs" in text
    assert "postgresql://" not in text
    assert ("pass" + "word=") not in text
    assert "PGPASSWORD=" not in text


def test_runner_preserva_linhagem_demo() -> None:
    text = _text()
    assert 'SOURCE_VERSION="demo-finance-v1"' in text
    assert 'TARGET_VERSION="demo-finance-v2"' in text
    assert "012_prepare_demo_finance_context_v2.sql" in text
    assert "v2.0-ducklake-query-generator" not in text


def test_runner_falha_fechado_para_target_preexistente() -> None:
    text = _text()
    assert 'if [[ "${target_count}" != "0" ]]' in text
    assert "target version already contains records" in text
    assert "No write performed" in text


def test_runner_nao_ativa_runtime() -> None:
    text = _text()
    forbidden = (
        "docker compose",
        "SEMANTIC_AGENT_VERSION=",
        "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=true",
        "n8n",
        "curl ",
        "ai_ducklake_benchmarks",
    )
    for value in forbidden:
        assert value not in text


def test_schema_configuravel() -> None:
    text = _text()
    assert "POSTGRES_CONTEXT_SCHEMA" in text
    assert "A-Za-z0-9_" in text
    assert '-v context_schema="${POSTGRES_CONTEXT_SCHEMA}"' in text


def main() -> None:
    tests = [
        ("confirmacao e dsn externo", test_runner_exige_confirmacao_e_dsn_externo),
        ("linhagem demo", test_runner_preserva_linhagem_demo),
        ("target preexistente fail closed", test_runner_falha_fechado_para_target_preexistente),
        ("sem ativacao runtime", test_runner_nao_ativa_runtime),
        ("schema configuravel", test_schema_configuravel),
    ]
    for index, (name, function) in enumerate(tests, start=1):
        function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

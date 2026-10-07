from __future__ import annotations

from pathlib import Path


RUNNER = Path("scripts/apply_semantic_context_v10.sh")


def _text() -> str:
    return RUNNER.read_text(encoding="utf-8")


def test_runner_exige_confirmacao_e_dsn_externo() -> None:
    text = _text()

    assert 'CONFIRM_VALUE="APLICAR_CONTEXT_V10"' in text
    assert 'CONFIRM_APPLY' in text
    assert 'SEMANTIC_MIGRATION_POSTGRES_DSN must be set outside Git/chat/logs' in text
    assert "postgresql://" not in text
    assert "password=" not in text
    assert "PGPASSWORD=" not in text
    assert 'POSTGRES_DSN:?POSTGRES_DSN' not in text


def test_runner_preserva_sequencia_versionada() -> None:
    text = _text()

    source = "v2.0-ducklake-query-generator-semantic-operations-v7"
    v9 = (
        "v2.0-ducklake-query-generator-semantic-operations-"
        "v9-period-coverage"
    )
    v10 = (
        "v2.0-ducklake-query-generator-semantic-operations-"
        "v10-curated-intents"
    )

    assert source in text
    assert v9 in text
    assert v10 in text
    assert "010_prepare_semantic_period_coverage_context_v9.sql" in text
    assert "011_prepare_semantic_curated_intents_context_v10.sql" in text


def test_runner_falha_fechado_para_v10_preexistente() -> None:
    text = _text()

    assert 'if [[ "${v10_count}" != "0" ]]' in text
    assert "v10 already contains records" in text
    assert "No write performed" in text


def test_runner_nao_altera_runtime_ou_official() -> None:
    text = _text()

    forbidden = (
        "docker compose",
        "SEMANTIC_AGENT_VERSION=",
        "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=true",
        "n8n",
        "curl ",
    )
    for value in forbidden:
        assert value not in text


def main() -> None:
    tests = [
        ("confirmacao e dsn externo", test_runner_exige_confirmacao_e_dsn_externo),
        ("sequencia versionada", test_runner_preserva_sequencia_versionada),
        ("v10 preexistente fail closed", test_runner_falha_fechado_para_v10_preexistente),
        ("sem ativacao runtime", test_runner_nao_altera_runtime_ou_official),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

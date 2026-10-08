from __future__ import annotations

from pathlib import Path


MIGRATION = Path(
    "scripts/migrations/012_prepare_demo_finance_context_v2.sql"
)


def _text() -> str:
    return MIGRATION.read_text(encoding="utf-8")


def test_preserva_linhagem_demo() -> None:
    text = _text()
    assert "'demo-finance-v1'::text AS source_version" in text
    assert "'demo-finance-v2'::text AS target_version" in text
    assert "v2.0-ducklake-query-generator" not in text


def test_schema_e_configuravel() -> None:
    text = _text()
    assert 'SET LOCAL search_path TO :"context_schema";' in text
    assert "public.ai_ducklake_" not in text


def test_nao_altera_threshold_runtime_ou_benchmark() -> None:
    text = _text().casefold()
    forbidden = (
        "semantic_agent_version=",
        "langgraph_allow_real_sql_execution=true",
        "ai_ducklake_benchmarks",
        "golden answer",
        "tabelas_obrigatorias",
        "filtros_obrigatorios",
        "deve_conter_sql",
        "nao_deve_conter_sql",
    )
    for value in forbidden:
        assert value not in text

    assert "update ai_ducklake_agent_rules" not in text


def test_ranking_e_configurado_como_operacao_generica() -> None:
    text = _text()
    for term in (
        "'ranking'",
        "'maior'",
        "'maiores'",
        "'top'",
        "'principais'",
        "'menor'",
        "'menores'",
    ):
        assert term in text
    assert '"operation_type":"ranking"' in text
    assert '"direction":"descending"' in text
    assert '"direction":"ascending"' in text


def test_periodo_e_ampliado_sem_reescrever_intents() -> None:
    text = _text()
    assert "period_reference" in text
    assert "explicit_period_reference" in text
    assert "minimum_score" not in text
    assert "ambiguity_margin" not in text
    assert "UPDATE ai_ducklake_entity_aliases" in text
    assert "canonical_value IN (" not in text


def test_business_rule_text_e_convertido_explicitamente_para_jsonb() -> None:
    text = _text()
    assert "(business_rule::jsonb) -> 'intent_catalog' -> 'rules'" in text
    assert "(business_rule::jsonb) ? 'intent_catalog'" in text
    assert "SET business_rule = transformed.new_business_rule::text" in text


def main() -> None:
    tests = [
        ("preserva linhagem demo", test_preserva_linhagem_demo),
        ("schema configuravel", test_schema_e_configuravel),
        (
            "sem threshold runtime ou benchmark",
            test_nao_altera_threshold_runtime_ou_benchmark,
        ),
        (
            "ranking como operacao generica",
            test_ranking_e_configurado_como_operacao_generica,
        ),
        (
            "periodo sem reescrever intents",
            test_periodo_e_ampliado_sem_reescrever_intents,
        ),
        (
            "business_rule text com cast jsonb",
            test_business_rule_text_e_convertido_explicitamente_para_jsonb,
        ),
    ]
    for index, (name, function) in enumerate(tests, start=1):
        function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

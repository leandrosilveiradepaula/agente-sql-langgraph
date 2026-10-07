from __future__ import annotations

import json
from pathlib import Path


CATALOG_PATH = Path("semantic_context/intent_catalog_curado_v1.json")
MIGRATION_PATH = Path(
    "scripts/migrations/011_prepare_semantic_curated_intents_context_v10.sql"
)
SOURCE_VERSION = (
    "v2.0-ducklake-query-generator-semantic-operations-v9-period-coverage"
)
TARGET_VERSION = (
    "v2.0-ducklake-query-generator-semantic-operations-v10-curated-intents"
)


def _catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def test_catalogo_curado_tem_somente_definicoes_sem_alvo_fisico() -> None:
    definitions = _catalog()["definitions"]
    assert len(definitions) == 9

    intents = set()
    for definition in definitions:
        assert definition["entity_type"] == "intent_definition"
        assert definition["target_table"] is None
        assert definition["target_column"] is None
        assert definition["sql_filter_hint"] is None
        assert definition["canonical_value"] not in intents
        intents.add(definition["canonical_value"])

        payload = definition["business_rule"]["intent_catalog"]
        assert payload["semantic_description"]
        assert payload["rules"]


def test_migration_v10_deriva_da_v9_sem_ativacao_automatica() -> None:
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    assert SOURCE_VERSION in sql
    assert TARGET_VERSION in sql
    assert sql.count("source.is_active = TRUE") == 4
    assert sql.count("source.is_allowed = TRUE") == 1
    assert "UPDATE " not in sql
    assert "DELETE " not in sql
    assert "SEMANTIC_AGENT_VERSION" not in sql
    assert "SET LOCAL search_path TO :\"context_schema\";" in sql
    assert "public.ai_ducklake_" not in sql
    assert sql.rstrip().endswith("COMMIT;")


def test_migration_v10_persiste_catalogo_curado_sem_lookup() -> None:
    catalog = _catalog()
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    for definition in catalog["definitions"]:
        assert f"'{definition['user_term']}'" in sql
        assert f"'{definition['canonical_value']}'" in sql

    assert "'metric_total_by_period'" not in sql.split(
        "source.canonical_value IN (", 1
    )[1].split(")", 1)[0]

    forbidden = (
        "ai_ducklake_benchmarks",
        "benchmark_target",
        "golden_answer",
        "expected_sql",
        "generated_sql",
    )
    for value in forbidden:
        assert value not in sql


def test_migration_v10_nao_cria_regra_de_negocio_no_motor() -> None:
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "INSERT INTO ai_ducklake_entity_aliases" in sql
    assert "INSERT INTO ai_ducklake_agent_rules" in sql
    assert "INSERT INTO ai_ducklake_sql_patterns" in sql
    assert "INSERT INTO ai_ducklake_dre_mapping" in sql
    assert "INSERT INTO ai_ducklake_table_catalog" in sql

    definitions_block = sql.split(
        "INSERT INTO ai_ducklake_entity_aliases", 2
    )[2].split("ON CONFLICT DO NOTHING;", 1)[0]
    assert "'intent_definition'" in definitions_block
    assert "NULL,\n  NULL,\n  NULL," in definitions_block


def main() -> None:
    tests = [
        (
            "catalogo curado sem alvo fisico",
            test_catalogo_curado_tem_somente_definicoes_sem_alvo_fisico,
        ),
        (
            "migration v10 versionada",
            test_migration_v10_deriva_da_v9_sem_ativacao_automatica,
        ),
        (
            "migration v10 sem lookup",
            test_migration_v10_persiste_catalogo_curado_sem_lookup,
        ),
        (
            "migration v10 contexto, nao motor",
            test_migration_v10_nao_cria_regra_de_negocio_no_motor,
        ),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

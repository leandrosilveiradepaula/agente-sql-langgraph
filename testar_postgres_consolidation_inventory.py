from __future__ import annotations

from pathlib import Path


SCRIPT = Path("scripts/inventory_postgres_readonly.sh")


def _text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_inventory_exige_dsn_externo_sem_imprimir_valor() -> None:
    text = _text()

    assert "INVENTORY_POSTGRES_DSN must be set outside Git/chat/logs" in text
    assert 'psql "${INVENTORY_POSTGRES_DSN}"' in text
    assert "echo ${INVENTORY_POSTGRES_DSN}" not in text
    assert "postgresql://" not in text
    assert ("pass" + "word=") not in text


def test_inventory_e_estritamente_read_only() -> None:
    text = _text()

    assert "BEGIN READ ONLY;" in text
    assert "ROLLBACK;" in text

    forbidden = (
        "INSERT ",
        "UPDATE ",
        "DELETE ",
        "TRUNCATE ",
        "ALTER ",
        "DROP ",
        "CREATE TABLE",
        "GRANT ",
        "REVOKE ",
        "COPY ",
    )
    upper = text.upper()
    for value in forbidden:
        assert value not in upper


def test_inventory_coleta_apenas_metadados_estruturais() -> None:
    text = _text()

    assert "information_schema.schemata" in text
    assert "information_schema.tables" in text
    assert "pg_stat_user_tables" in text
    assert "pg_total_relation_size" in text
    assert "pg_extension" in text
    assert "estimated_rows" in text
    assert "total_bytes" in text

    forbidden = (
        "SELECT * FROM",
        "LIMIT 10",
        "sample_rows",
        "preview_rows",
    )
    for value in forbidden:
        assert value not in text


def test_inventory_nao_hardcoda_schema_de_negocio() -> None:
    text = _text()

    assert "semantic_context" not in text
    assert "demo_lakehouse" not in text
    assert "main_gold" not in text
    assert "ai_ducklake_" not in text
    assert "gold_" not in text


def main() -> None:
    tests = [
        ("dsn externo", test_inventory_exige_dsn_externo_sem_imprimir_valor),
        ("somente leitura", test_inventory_e_estritamente_read_only),
        (
            "metadados estruturais",
            test_inventory_coleta_apenas_metadados_estruturais,
        ),
        (
            "sem schema de negocio hardcoded",
            test_inventory_nao_hardcoda_schema_de_negocio,
        ),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

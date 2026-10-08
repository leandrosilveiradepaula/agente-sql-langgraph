from __future__ import annotations

from pathlib import Path


HELPER = Path("scripts/load_semantic_migration_env.sh")


def test_loader_usa_arquivo_local_protegido() -> None:
    text = HELPER.read_text(encoding="utf-8")
    assert "/docker/agente-sql-langgraph/semantic-migration.env" in text
    assert "SEMANTIC_MIGRATION_ENV_FILE" in text
    assert 'mode 600' in text
    assert "SEMANTIC_MIGRATION_POSTGRES_DSN" in text
    assert "POSTGRES_CONTEXT_SCHEMA" in text


def test_loader_nao_embute_segredos() -> None:
    text = HELPER.read_text(encoding="utf-8")
    assert "postgresql://" not in text
    assert ("pass" + "word=") not in text.casefold()
    assert "PGPASSWORD=" not in text


def main() -> None:
    tests = [
        ("arquivo local protegido", test_loader_usa_arquivo_local_protegido),
        ("sem segredo embutido", test_loader_nao_embute_segredos),
    ]
    for index, (name, fn) in enumerate(tests, start=1):
        fn()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

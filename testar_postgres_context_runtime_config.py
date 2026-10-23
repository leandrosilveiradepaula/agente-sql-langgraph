from __future__ import annotations

from app.config.postgres_context import (
    DEFAULT_POSTGRES_CONTEXT_SCHEMA,
    DEFAULT_POSTGRES_CONNECT_TIMEOUT_SECONDS,
    PostgresContextRuntimeConfig,
    RuntimeConfigError,
    load_postgres_context_runtime_config,
)


FAKE_DSN = "postgresql://example.invalid/database"


def test_carrega_configuracao_completa() -> None:
    config = load_postgres_context_runtime_config(
        {
            "POSTGRES_DSN": f"  {FAKE_DSN}  ",
            "SEMANTIC_AGENT_VERSION": "  semantic-test-v1  ",
            "POSTGRES_CONNECT_TIMEOUT_SECONDS": " 7 ",
        }
    )

    assert config == PostgresContextRuntimeConfig(
        dsn=FAKE_DSN,
        semantic_agent_version="semantic-test-v1",
        context_schema=DEFAULT_POSTGRES_CONTEXT_SCHEMA,
        connect_timeout_seconds=7,
    )


def test_aplica_timeout_padrao_quando_ausente() -> None:
    config = load_postgres_context_runtime_config(
        {
            "POSTGRES_DSN": FAKE_DSN,
            "SEMANTIC_AGENT_VERSION": "semantic-test-v1",
        }
    )

    assert config.connect_timeout_seconds == (
        DEFAULT_POSTGRES_CONNECT_TIMEOUT_SECONDS
    )
    assert config.context_schema == DEFAULT_POSTGRES_CONTEXT_SCHEMA


def test_carrega_schema_de_contexto_configurado() -> None:
    config = load_postgres_context_runtime_config(
        {
            "POSTGRES_DSN": FAKE_DSN,
            "SEMANTIC_AGENT_VERSION": "semantic-test-v1",
            "POSTGRES_CONTEXT_SCHEMA": "  semantic_context  ",
        }
    )

    assert config.context_schema == "semantic_context"


def test_rejeita_schema_de_contexto_invalido() -> None:
    invalid_values = [
        "",
        " ",
        "public.foo",
        "public;drop_table_x",
        '"public"',
        "public schema",
        "--comment",
        "1public",
    ]

    for invalid_value in invalid_values:
        try:
            load_postgres_context_runtime_config(
                {
                    "POSTGRES_DSN": FAKE_DSN,
                    "SEMANTIC_AGENT_VERSION": "semantic-test-v1",
                    "POSTGRES_CONTEXT_SCHEMA": invalid_value,
                }
            )
        except RuntimeConfigError as error:
            message = str(error)
            assert "POSTGRES_CONTEXT_SCHEMA" in message
            assert FAKE_DSN not in message
        else:
            raise AssertionError(
                "Era esperado RuntimeConfigError."
            )


def test_rejeita_variaveis_obrigatorias_ausentes() -> None:
    cases = [
        (
            {
                "SEMANTIC_AGENT_VERSION": "semantic-test-v1",
            },
            "A variável POSTGRES_DSN não está definida.",
        ),
        (
            {
                "POSTGRES_DSN": FAKE_DSN,
            },
            (
                "A variável SEMANTIC_AGENT_VERSION "
                "não está definida."
            ),
        ),
    ]

    for environ, expected_message in cases:
        try:
            load_postgres_context_runtime_config(environ)
        except RuntimeConfigError as error:
            assert str(error) == expected_message
        else:
            raise AssertionError(
                "Era esperado RuntimeConfigError."
            )


def test_rejeita_variaveis_obrigatorias_vazias() -> None:
    cases = [
        (
            {
                "POSTGRES_DSN": " ",
                "SEMANTIC_AGENT_VERSION": "semantic-test-v1",
            },
            "A variável POSTGRES_DSN não pode estar vazia.",
        ),
        (
            {
                "POSTGRES_DSN": FAKE_DSN,
                "SEMANTIC_AGENT_VERSION": " ",
            },
            (
                "A variável SEMANTIC_AGENT_VERSION "
                "não pode estar vazia."
            ),
        ),
    ]

    for environ, expected_message in cases:
        try:
            load_postgres_context_runtime_config(environ)
        except RuntimeConfigError as error:
            assert str(error) == expected_message
        else:
            raise AssertionError(
                "Era esperado RuntimeConfigError."
            )


def test_rejeita_timeout_invalido_sem_expor_dsn() -> None:
    invalid_values = [
        "",
        " ",
        "zero",
        "0",
        "-1",
        "1.5",
    ]

    for invalid_value in invalid_values:
        try:
            load_postgres_context_runtime_config(
                {
                    "POSTGRES_DSN": FAKE_DSN,
                    "SEMANTIC_AGENT_VERSION": "semantic-test-v1",
                    "POSTGRES_CONNECT_TIMEOUT_SECONDS": (
                        invalid_value
                    ),
                }
            )
        except RuntimeConfigError as error:
            message = str(error)

            assert (
                "POSTGRES_CONNECT_TIMEOUT_SECONDS"
                in message
            )
            assert FAKE_DSN not in message
        else:
            raise AssertionError(
                "Era esperado RuntimeConfigError."
            )


def test_mapping_injetado_nao_depende_do_ambiente_real() -> None:
    config = load_postgres_context_runtime_config(
        {
            "POSTGRES_DSN": FAKE_DSN,
            "SEMANTIC_AGENT_VERSION": "semantic-test-v1",
            "POSTGRES_CONNECT_TIMEOUT_SECONDS": "3",
        }
    )

    assert config.dsn == FAKE_DSN
    assert config.semantic_agent_version == (
        "semantic-test-v1"
    )
    assert config.context_schema == DEFAULT_POSTGRES_CONTEXT_SCHEMA
    assert config.connect_timeout_seconds == 3


def test_fingerprint_pin_config_explicit_and_strict() -> None:
    fingerprint = "a" * 64
    env = {
        "POSTGRES_DSN": FAKE_DSN,
        "SEMANTIC_AGENT_VERSION": "semantic-test-v1",
        "SEMANTIC_CONTEXT_EXPECTED_FINGERPRINT": fingerprint,
    }
    config = load_postgres_context_runtime_config(env)
    assert config.expected_context_fingerprint == fingerprint
    assert load_postgres_context_runtime_config({
        "POSTGRES_DSN": FAKE_DSN,
        "SEMANTIC_AGENT_VERSION": "semantic-test-v1",
    }).expected_context_fingerprint is None

    for invalid in ("", "a" * 63, "A" * 64, " " + fingerprint,
                    "random-tenant", "a" * 65, fingerprint + ";DROP"):
        env["SEMANTIC_CONTEXT_EXPECTED_FINGERPRINT"] = invalid
        try:
            load_postgres_context_runtime_config(env)
        except RuntimeConfigError as error:
            assert str(error) == (
                "A variável SEMANTIC_CONTEXT_EXPECTED_FINGERPRINT é inválida."
            )
            assert FAKE_DSN not in str(error)
        else:
            raise AssertionError("Invalid fingerprint pin must fail closed.")


def main() -> None:
    tests = [
        (
            "carrega configuração completa",
            test_carrega_configuracao_completa,
        ),
        (
            "aplica timeout padrão quando ausente",
            test_aplica_timeout_padrao_quando_ausente,
        ),
        (
            "carrega schema de contexto configurado",
            test_carrega_schema_de_contexto_configurado,
        ),
        (
            "rejeita schema de contexto inválido",
            test_rejeita_schema_de_contexto_invalido,
        ),
        (
            "rejeita variáveis obrigatórias ausentes",
            test_rejeita_variaveis_obrigatorias_ausentes,
        ),
        (
            "rejeita variáveis obrigatórias vazias",
            test_rejeita_variaveis_obrigatorias_vazias,
        ),
        (
            "rejeita timeout inválido sem expor DSN",
            test_rejeita_timeout_invalido_sem_expor_dsn,
        ),
        (
            "mapping injetado independe do ambiente real",
            test_mapping_injetado_nao_depende_do_ambiente_real,
        ),
        ("fingerprint do contexto configurado", test_fingerprint_pin_config_explicit_and_strict),
    ]

    for index, (name, test_function) in enumerate(
        tests,
        start=1,
    ):
        test_function()
        print(f"TESTE {index} — {name}: OK")


if __name__ == "__main__":
    main()

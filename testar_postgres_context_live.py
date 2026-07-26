from __future__ import annotations

import getpass
import socket
import sys
from collections.abc import Mapping
from typing import Any

import psycopg
from psycopg.conninfo import make_conninfo

from app.adapters.postgres.context_repository import (
    PostgresContextRepository,
)
from app.domain.context_validator import (
    ContextValidationIssue,
    validate_context_snapshot,
)
from app.ports.context_repository import ContextRepositoryError


LIVE_TEST_USER_PROFILE = "runtime_validation"
DEFAULT_PORT = 5432
DEFAULT_DATABASE = "postgres"
DEFAULT_CONNECT_TIMEOUT_SECONDS = 10
SSL_MODE = "require"


SQLSTATE_CATEGORIES = {
    "08001": (
        "CONNECTION_UNAVAILABLE",
        "O servidor PostgreSQL não ficou disponível para a conexão.",
    ),
    "08004": (
        "CONNECTION_REJECTED",
        "O servidor PostgreSQL rejeitou a conexão.",
    ),
    "08006": (
        "CONNECTION_FAILURE",
        "A conexão PostgreSQL falhou.",
    ),
    "28P01": (
        "INVALID_PASSWORD",
        "O PostgreSQL rejeitou a senha informada.",
    ),
    "28000": (
        "INVALID_AUTHORIZATION",
        "O PostgreSQL rejeitou as credenciais informadas.",
    ),
    "3D000": (
        "DATABASE_NOT_FOUND",
        "O banco de dados informado não existe.",
    ),
    "42501": (
        "INSUFFICIENT_PRIVILEGE",
        "O usuário não possui permissão para executar a consulta.",
    ),
    "42P01": (
        "TABLE_NOT_FOUND",
        "Uma tabela usada pela consulta não existe.",
    ),
    "42703": (
        "COLUMN_NOT_FOUND",
        "Uma coluna usada pela consulta não existe.",
    ),
    "42601": (
        "SQL_SYNTAX_ERROR",
        "O PostgreSQL rejeitou a sintaxe da consulta.",
    ),
}


def _required_input(label: str) -> str:
    value = input(f"{label}: ").strip()

    if not value:
        raise ValueError(f"{label} não pode estar vazio.")

    return value


def _hidden_required_input(label: str) -> str:
    value = getpass.getpass(
        f"{label} (entrada oculta): "
    ).strip()

    if not value:
        raise ValueError(f"{label} não pode estar vazio.")

    return value


def _positive_integer_input(
    label: str,
    *,
    default: int,
) -> int:
    raw_value = input(
        f"{label} (Enter para usar {default}): "
    ).strip()

    if not raw_value:
        return default

    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(
            f"{label} deve ser um inteiro positivo."
        ) from error

    if value <= 0:
        raise ValueError(
            f"{label} deve ser um inteiro positivo."
        )

    return value


def _text_input_with_default(
    label: str,
    *,
    default: str,
) -> str:
    value = input(
        f"{label} (Enter para usar {default}): "
    ).strip()

    return value or default


def _issue_summary(
    issue: ContextValidationIssue,
) -> str:
    details = issue.get("details", {})
    path = details.get("validation_path", "-")

    return (
        f"{issue['severity'].upper()} "
        f"{issue['code']} "
        f"path={path}: "
        f"{issue['message']}"
    )


def _print_safe_psycopg_diagnostic(
    error: BaseException,
) -> None:
    sqlstate = getattr(error, "sqlstate", None)
    error_type = type(error).__name__

    print(f"TIPO_TECNICO: {error_type}")
    print(f"SQLSTATE: {sqlstate or 'NAO_DISPONIVEL'}")

    if sqlstate in SQLSTATE_CATEGORIES:
        category, explanation = SQLSTATE_CATEGORIES[sqlstate]
        print(f"CATEGORIA: {category}")
        print(f"DIAGNOSTICO: {explanation}")
        return

    if isinstance(error, psycopg.OperationalError):
        print("CATEGORIA: CONNECTION_ERROR")
        print(
            "DIAGNOSTICO: Falha de conexão sem SQLSTATE. "
            "As causas mais comuns são rede, SSL, porta, "
            "usuário ou senha."
        )
        return

    print("CATEGORIA: DATABASE_ERROR")
    print(
        "DIAGNOSTICO: O PostgreSQL retornou um erro não classificado "
        "pelo teste seguro."
    )


def _root_cause(error: BaseException) -> BaseException:
    current = error

    while current.__cause__ is not None:
        current = current.__cause__

    return current


def _connection_preflight(
    *,
    host: str,
    port: int,
    dsn: str,
    connect_timeout_seconds: int,
) -> bool:
    try:
        socket.getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
        )
        print("DNS: OK")
    except OSError:
        print("DNS: ERRO")
        print(
            "DIAGNOSTICO: O host informado não pôde ser resolvido."
        )
        return False

    try:
        with psycopg.connect(
            dsn,
            connect_timeout=connect_timeout_seconds,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                result = cursor.fetchone()

        if result != (1,):
            print("CONEXAO_BASICA: ERRO")
            print(
                "DIAGNOSTICO: A consulta básica não retornou "
                "o valor esperado."
            )
            return False

        print("CONEXAO_BASICA: OK")
        return True

    except psycopg.Error as error:
        print("CONEXAO_BASICA: ERRO")
        _print_safe_psycopg_diagnostic(error)
        return False


def _print_safe_snapshot_summary(
    snapshot: Mapping[str, Any],
) -> None:
    counts = snapshot.get("counts", {})
    allowed_schemas = snapshot.get("allowed_schemas", [])

    print()
    print("=" * 70)
    print("POSTGRES CONTEXT LIVE CHECK — RESULTADO")
    print("=" * 70)
    print("CONSULTA_CONTEXTO: OK")
    print(f"VERSAO: {snapshot.get('version', '')}")
    print(f"FONTE: {snapshot.get('source', '')}")
    print(f"FINGERPRINT: {snapshot.get('fingerprint', '')}")
    print(
        "CONTAGENS: "
        f"rules={counts.get('rules', 0)}, "
        f"entities={counts.get('entities', 0)}, "
        f"dre_mappings={counts.get('dre_mappings', 0)}, "
        f"query_patterns={counts.get('query_patterns', 0)}, "
        f"table_catalog={counts.get('table_catalog', 0)}"
    )
    print(
        "SCHEMAS_AUTORIZADOS: "
        f"{len(allowed_schemas)}"
    )


def main() -> int:
    print("=" * 70)
    print("POSTGRES CONTEXT LIVE CHECK — CAMPOS SEPARADOS")
    print("=" * 70)
    print(
        "Teste somente leitura. "
        "A senha e a conexão completa não serão exibidas."
    )
    print(
        "O DSN será montado internamente; "
        "não é necessário codificar caracteres da senha."
    )
    print()

    try:
        host = _required_input("POSTGRES_HOST")
        port = _positive_integer_input(
            "POSTGRES_PORT",
            default=DEFAULT_PORT,
        )
        database = _text_input_with_default(
            "POSTGRES_DATABASE",
            default=DEFAULT_DATABASE,
        )
        user = _required_input("POSTGRES_USER")
        password = _hidden_required_input("POSTGRES_PASSWORD")
        semantic_agent_version = _required_input(
            "SEMANTIC_AGENT_VERSION"
        )
        connect_timeout_seconds = _positive_integer_input(
            "POSTGRES_CONNECT_TIMEOUT_SECONDS",
            default=DEFAULT_CONNECT_TIMEOUT_SECONDS,
        )

        dsn = make_conninfo(
            host=host,
            port=port,
            dbname=database,
            user=user,
            password=password,
            sslmode=SSL_MODE,
        )

        if not _connection_preflight(
            host=host,
            port=port,
            dsn=dsn,
            connect_timeout_seconds=connect_timeout_seconds,
        ):
            return 3

        repository = PostgresContextRepository(
            dsn=dsn,
            semantic_agent_version=semantic_agent_version,
            connect_timeout_seconds=connect_timeout_seconds,
        )

        try:
            snapshot = repository.load_active_context(
                user_profile=LIVE_TEST_USER_PROFILE,
            )
        except ContextRepositoryError as error:
            print("CONSULTA_CONTEXTO: ERRO")
            print(f"REPOSITORIO: {error}")

            cause = _root_cause(error)
            if isinstance(cause, psycopg.Error):
                _print_safe_psycopg_diagnostic(cause)
            else:
                print("CATEGORIA: CONTEXT_NORMALIZATION_ERROR")
                print(
                    "DIAGNOSTICO: A conexão funcionou, mas o snapshot "
                    "retornado não pôde ser normalizado."
                )

            return 4

        validation_result = validate_context_snapshot(snapshot)

        _print_safe_snapshot_summary(snapshot)

        for warning in validation_result["warnings"]:
            print(_issue_summary(warning))

        if validation_result["status"] != "valid":
            print("VALIDACAO: INVALIDA")

            for error in validation_result["errors"]:
                print(_issue_summary(error))

            return 5

        print(
            "VALIDACAO: OK"
            if not validation_result["warnings"]
            else "VALIDACAO: OK COM AVISOS"
        )
        return 0

    except ValueError as error:
        print()
        print(f"CONFIGURACAO: ERRO — {error}")
        return 2

    except KeyboardInterrupt:
        print()
        print("TESTE: CANCELADO")
        return 130

    except Exception:
        print()
        print(
            "TESTE: ERRO INESPERADO. "
            "Detalhes sensíveis foram omitidos."
        )
        return 6


if __name__ == "__main__":
    sys.exit(main())

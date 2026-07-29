from __future__ import annotations

import getpass
import socket
import sys
from collections.abc import Mapping
from typing import Any

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row


DEFAULT_PORT = 5432
DEFAULT_DATABASE = "postgres"
DEFAULT_CONNECT_TIMEOUT_SECONDS = 10
SSL_MODE = "require"

CONTEXT_TABLES = (
    "ai_ducklake_agent_rules",
    "ai_ducklake_entity_aliases",
    "ai_ducklake_dre_mapping",
    "ai_ducklake_sql_patterns",
    "ai_ducklake_table_catalog",
)

ACTIVATION_COLUMN_BY_TABLE = {
    "ai_ducklake_agent_rules": "is_active",
    "ai_ducklake_entity_aliases": "is_active",
    "ai_ducklake_dre_mapping": "is_active",
    "ai_ducklake_sql_patterns": "is_active",
    "ai_ducklake_table_catalog": "is_allowed",
}


def _required_input(label: str) -> str:
    value = input(f"{label}: ").strip()
    if not value:
        raise ValueError(f"{label} não pode ficar vazio.")
    return value


def _text_input_with_default(
    label: str,
    *,
    default: str,
) -> str:
    raw = input(f"{label} (Enter para usar {default}): ").strip()
    return raw or default


def _positive_integer_input(
    label: str,
    *,
    default: int,
) -> int:
    raw = input(f"{label} (Enter para usar {default}): ").strip()
    if not raw:
        return default

    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{label} deve ser inteiro.") from error

    if value <= 0:
        raise ValueError(f"{label} deve ser positivo.")

    return value


def _hidden_required_input(label: str) -> str:
    value = getpass.getpass(f"{label} (entrada oculta): ").strip()
    if not value:
        raise ValueError(f"{label} não pode ficar vazio.")
    return value


def _connection_preflight(
    *,
    host: str,
    port: int,
    dsn: str,
    connect_timeout_seconds: int,
) -> bool:
    try:
        socket.getaddrinfo(host, port)
        print("DNS: OK")
    except OSError:
        print("DNS: ERRO")
        return False

    try:
        with psycopg.connect(
            dsn,
            connect_timeout=connect_timeout_seconds,
            row_factory=dict_row,
        ) as connection:
            connection.read_only = True
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 AS ok")
                row = cursor.fetchone()
                if not row or row.get("ok") != 1:
                    print("CONEXAO_BASICA: ERRO")
                    return False

        print("CONEXAO_BASICA: OK")
        return True

    except psycopg.Error as error:
        print("CONEXAO_BASICA: ERRO")
        print(f"TIPO_TECNICO: {type(error).__name__}")
        print(f"SQLSTATE: {getattr(error, 'sqlstate', None) or '-'}")
        return False


def _fetch_all(
    cursor: Any,
    query: str,
    parameters: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    cursor.execute(query, parameters or {})
    rows = cursor.fetchall()
    return [dict(row) for row in rows]


def _fetch_one(
    cursor: Any,
    query: str,
    parameters: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    cursor.execute(query, parameters or {})
    row = cursor.fetchone()
    return dict(row) if row is not None else None


def _print_table_columns(
    *,
    table_name: str,
    rows: list[dict[str, Any]],
) -> None:
    print(f"- TABLE {table_name}: columns={len(rows)}")
    for row in rows:
        default_value = row.get("column_default")
        print(
            "  "
            f"{row.get('ordinal_position')}: "
            f"{row.get('column_name')} "
            f"type={row.get('data_type')} "
            f"udt={row.get('udt_name')} "
            f"nullable={row.get('is_nullable')} "
            f"default={default_value if default_value is not None else '-'}"
        )


def _print_constraints(
    *,
    table_name: str,
    rows: list[dict[str, Any]],
) -> None:
    print(f"- TABLE {table_name}: constraints={len(rows)}")
    for row in rows:
        print(
            "  "
            f"{row.get('constraint_name')}: "
            f"type={row.get('constraint_type')} "
            f"definition={row.get('definition')}"
        )


def _print_indexes(
    *,
    table_name: str,
    rows: list[dict[str, Any]],
) -> None:
    print(f"- TABLE {table_name}: indexes={len(rows)}")
    for row in rows:
        print(
            "  "
            f"{row.get('indexname')}: "
            f"{row.get('indexdef')}"
        )


def _print_triggers(
    *,
    table_name: str,
    rows: list[dict[str, Any]],
) -> None:
    print(f"- TABLE {table_name}: triggers={len(rows)}")
    for row in rows:
        print(
            "  "
            f"{row.get('trigger_name')}: "
            f"event={row.get('event_manipulation')} "
            f"timing={row.get('action_timing')}"
        )


def _safe_identifier(table_name: str) -> str:
    if table_name not in CONTEXT_TABLES:
        raise ValueError("Tabela não autorizada para o diagnóstico.")
    return f"public.{table_name}"


def _safe_activation_column(table_name: str) -> str:
    try:
        return ACTIVATION_COLUMN_BY_TABLE[table_name]
    except KeyError as error:
        raise ValueError(
            "Tabela sem coluna de ativação configurada."
        ) from error


def main() -> int:
    print("=" * 70)
    print("POSTGRES CONTEXT VERSION CLONE DIAGNOSTIC — READ ONLY")
    print("=" * 70)
    print(
        "Diagnóstico somente leitura para preparar a clonagem de uma "
        "versão semântica. Nenhum registro será criado ou alterado."
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
        source_version = _required_input("SOURCE_AGENT_VERSION")
        target_version = _required_input("TARGET_AGENT_VERSION")
        connect_timeout_seconds = _positive_integer_input(
            "POSTGRES_CONNECT_TIMEOUT_SECONDS",
            default=DEFAULT_CONNECT_TIMEOUT_SECONDS,
        )

        if source_version == target_version:
            raise ValueError(
                "SOURCE_AGENT_VERSION e TARGET_AGENT_VERSION "
                "devem ser diferentes."
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

        with psycopg.connect(
            dsn,
            connect_timeout=connect_timeout_seconds,
            row_factory=dict_row,
        ) as connection:
            connection.read_only = True

            with connection.cursor() as cursor:
                session = _fetch_one(
                    cursor,
                    """
                    SELECT
                      current_database() AS database_name,
                      current_user AS database_user,
                      current_setting(
                        'transaction_read_only'
                      ) AS transaction_read_only
                    """,
                )

                print()
                print("=" * 70)
                print("CONEXAO_E_TRANSACAO")
                print("=" * 70)
                print(
                    f"- database={session.get('database_name') if session else '-'}"
                )
                print(
                    f"- database_user={session.get('database_user') if session else '-'}"
                )
                print(
                    "- transaction_read_only="
                    f"{session.get('transaction_read_only') if session else '-'}"
                )
                print(f"- source_version={source_version}")
                print(f"- target_version={target_version}")

                print()
                print("=" * 70)
                print("ESTRUTURA_DE_COLUNAS")
                print("=" * 70)

                columns_by_table: dict[str, list[dict[str, Any]]] = {}
                for table_name in CONTEXT_TABLES:
                    rows = _fetch_all(
                        cursor,
                        """
                        SELECT
                          ordinal_position,
                          column_name,
                          data_type,
                          udt_name,
                          is_nullable,
                          column_default
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = %(table_name)s
                        ORDER BY ordinal_position
                        """,
                        {"table_name": table_name},
                    )
                    columns_by_table[table_name] = rows
                    _print_table_columns(
                        table_name=table_name,
                        rows=rows,
                    )

                print()
                print("=" * 70)
                print("RESTRICOES")
                print("=" * 70)

                for table_name in CONTEXT_TABLES:
                    rows = _fetch_all(
                        cursor,
                        """
                        SELECT
                          con.conname AS constraint_name,
                          CASE con.contype
                            WHEN 'p' THEN 'PRIMARY KEY'
                            WHEN 'u' THEN 'UNIQUE'
                            WHEN 'f' THEN 'FOREIGN KEY'
                            WHEN 'c' THEN 'CHECK'
                            WHEN 'x' THEN 'EXCLUSION'
                            ELSE con.contype::text
                          END AS constraint_type,
                          pg_get_constraintdef(con.oid) AS definition
                        FROM pg_constraint con
                        JOIN pg_class rel
                          ON rel.oid = con.conrelid
                        JOIN pg_namespace nsp
                          ON nsp.oid = rel.relnamespace
                        WHERE nsp.nspname = 'public'
                          AND rel.relname = %(table_name)s
                        ORDER BY con.conname
                        """,
                        {"table_name": table_name},
                    )
                    _print_constraints(
                        table_name=table_name,
                        rows=rows,
                    )

                print()
                print("=" * 70)
                print("INDICES")
                print("=" * 70)

                for table_name in CONTEXT_TABLES:
                    rows = _fetch_all(
                        cursor,
                        """
                        SELECT
                          indexname,
                          indexdef
                        FROM pg_indexes
                        WHERE schemaname = 'public'
                          AND tablename = %(table_name)s
                        ORDER BY indexname
                        """,
                        {"table_name": table_name},
                    )
                    _print_indexes(
                        table_name=table_name,
                        rows=rows,
                    )

                print()
                print("=" * 70)
                print("TRIGGERS")
                print("=" * 70)

                for table_name in CONTEXT_TABLES:
                    rows = _fetch_all(
                        cursor,
                        """
                        SELECT
                          trigger_name,
                          event_manipulation,
                          action_timing
                        FROM information_schema.triggers
                        WHERE event_object_schema = 'public'
                          AND event_object_table = %(table_name)s
                        ORDER BY trigger_name, event_manipulation
                        """,
                        {"table_name": table_name},
                    )
                    _print_triggers(
                        table_name=table_name,
                        rows=rows,
                    )

                print()
                print("=" * 70)
                print("PERMISSOES")
                print("=" * 70)

                for table_name in CONTEXT_TABLES:
                    permission_row = _fetch_one(
                        cursor,
                        """
                        SELECT
                          has_table_privilege(
                            current_user,
                            %(qualified_table)s,
                            'SELECT'
                          ) AS can_select,
                          has_table_privilege(
                            current_user,
                            %(qualified_table)s,
                            'INSERT'
                          ) AS can_insert,
                          has_table_privilege(
                            current_user,
                            %(qualified_table)s,
                            'UPDATE'
                          ) AS can_update
                        """,
                        {
                            "qualified_table": (
                                f"public.{table_name}"
                            )
                        },
                    )
                    print(
                        f"- {table_name}: "
                        f"SELECT={permission_row.get('can_select') if permission_row else '-'} "
                        f"INSERT={permission_row.get('can_insert') if permission_row else '-'} "
                        f"UPDATE={permission_row.get('can_update') if permission_row else '-'}"
                    )

                print()
                print("=" * 70)
                print("COBERTURA_DAS_VERSOES")
                print("=" * 70)

                source_total = 0
                target_total = 0
                clone_columns: dict[str, list[str]] = {}
                activation_columns_valid = True

                for table_name in CONTEXT_TABLES:
                    qualified_table = _safe_identifier(table_name)
                    activation_column = _safe_activation_column(
                        table_name
                    )

                    physical_columns = [
                        str(row.get("column_name"))
                        for row in columns_by_table[table_name]
                        if row.get("column_name")
                    ]

                    if activation_column not in physical_columns:
                        activation_columns_valid = False

                    source_row = _fetch_one(
                        cursor,
                        f"""
                        SELECT
                          COUNT(*) AS total,
                          COUNT(*) FILTER (
                            WHERE COALESCE(
                              {activation_column},
                              TRUE
                            ) = TRUE
                          ) AS active
                        FROM {qualified_table}
                        WHERE agent_version = %(agent_version)s
                        """,
                        {"agent_version": source_version},
                    )
                    target_row = _fetch_one(
                        cursor,
                        f"""
                        SELECT
                          COUNT(*) AS total,
                          COUNT(*) FILTER (
                            WHERE COALESCE(
                              {activation_column},
                              TRUE
                            ) = TRUE
                          ) AS active
                        FROM {qualified_table}
                        WHERE agent_version = %(agent_version)s
                        """,
                        {"agent_version": target_version},
                    )

                    source_count = int(
                        source_row.get("total", 0)
                        if source_row
                        else 0
                    )
                    target_count = int(
                        target_row.get("total", 0)
                        if target_row
                        else 0
                    )
                    source_total += source_count
                    target_total += target_count

                    print(
                        f"- {table_name}: "
                        f"activation_column={activation_column} "
                        f"source_total={source_count} "
                        f"source_active={source_row.get('active', 0) if source_row else 0} "
                        f"target_total={target_count} "
                        f"target_active={target_row.get('active', 0) if target_row else 0}"
                    )

                    excluded = {
                        "id",
                        "created_at",
                    }
                    copy_columns = [
                        column_name
                        for column_name in physical_columns
                        if column_name not in excluded
                    ]
                    clone_columns[table_name] = copy_columns

                print()
                print("=" * 70)
                print("COLUNAS_CANDIDATAS_PARA_CLONAGEM")
                print("=" * 70)

                for table_name in CONTEXT_TABLES:
                    print(
                        f"- {table_name}: "
                        + ", ".join(clone_columns[table_name])
                    )

                print()
                print("=" * 70)
                print("FATOS_PARA_PROXIMA_ETAPA")
                print("=" * 70)
                print(f"- source_total_records={source_total}")
                print(f"- target_total_records={target_total}")
                print(
                    "- source_version_exists="
                    f"{source_total > 0}"
                )
                print(
                    "- target_version_is_empty="
                    f"{target_total == 0}"
                )
                print(
                    "- all_tables_found="
                    f"{all(columns_by_table[name] for name in CONTEXT_TABLES)}"
                )
                print(
                    "- all_tables_have_agent_version="
                    f"{all('agent_version' in clone_columns[name] for name in CONTEXT_TABLES)}"
                )
                print(
                    "- all_activation_columns_valid="
                    f"{activation_columns_valid}"
                )
                print(
                    "- activation_columns="
                    + ", ".join(
                        f"{table}={column}"
                        for table, column in (
                            ACTIVATION_COLUMN_BY_TABLE.items()
                        )
                    )
                )
                print(
                    "- observacao=este diagnostico nao cria, altera "
                    "ou remove registros"
                )

        print()
        print("DIAGNOSTICO_CONCLUIDO: OK")
        return 0

    except ValueError as error:
        print(f"VALIDACAO: ERRO — {error}")
        return 2

    except psycopg.Error as error:
        print("POSTGRES: ERRO")
        print(f"TIPO_TECNICO: {type(error).__name__}")
        print(f"SQLSTATE: {getattr(error, 'sqlstate', None) or '-'}")
        return 4

    except KeyboardInterrupt:
        print()
        print("DIAGNOSTICO: CANCELADO")
        return 130

    except Exception:
        print()
        print(
            "DIAGNOSTICO: ERRO INESPERADO. "
            "Detalhes sensíveis foram omitidos."
        )
        return 6


if __name__ == "__main__":
    sys.exit(main())

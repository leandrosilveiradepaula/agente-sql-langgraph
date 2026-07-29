from __future__ import annotations

import json
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from testar_postgres_context_live import (
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_DATABASE,
    DEFAULT_PORT,
    SSL_MODE,
    _connection_preflight,
    _hidden_required_input,
    _positive_integer_input,
    _print_safe_psycopg_diagnostic,
    _required_input,
    _root_cause,
    _text_input_with_default,
)


TARGET_SCHEMA = "public"
ENTITY_TABLE = "ai_ducklake_entity_aliases"
PATTERN_TABLE = "ai_ducklake_sql_patterns"

REQUIRED_ENTITY_COLUMNS = {
    "agent_version",
    "entity_type",
    "user_term",
    "canonical_value",
    "target_table",
    "target_column",
    "sql_filter_hint",
    "business_rule",
    "priority",
    "is_active",
}

CONTEXT_COLLECTIONS = (
    (
        "agent_rules",
        "ai_ducklake_agent_rules",
        "is_active",
    ),
    (
        "entity_aliases",
        "ai_ducklake_entity_aliases",
        "is_active",
    ),
    (
        "dre_mapping",
        "ai_ducklake_dre_mapping",
        "is_active",
    ),
    (
        "sql_patterns",
        "ai_ducklake_sql_patterns",
        "is_active",
    ),
    (
        "table_catalog",
        "ai_ducklake_table_catalog",
        "is_allowed",
    ),
)

TABLE_EXISTS_SQL = """
SELECT EXISTS (
  SELECT 1
  FROM information_schema.tables
  WHERE table_schema = %(schema_name)s
    AND table_name = %(table_name)s
) AS table_exists
"""

TABLE_COLUMNS_SQL = """
SELECT
  ordinal_position,
  column_name,
  data_type,
  udt_name,
  is_nullable,
  column_default,
  character_maximum_length
FROM information_schema.columns
WHERE table_schema = %(schema_name)s
  AND table_name = %(table_name)s
ORDER BY ordinal_position
"""

TABLE_CONSTRAINTS_SQL = """
SELECT
  constraint_name,
  constraint_type,
  constraint_definition
FROM (
  SELECT
    c.conname AS constraint_name,
    CASE c.contype
      WHEN 'p' THEN 'PRIMARY KEY'
      WHEN 'u' THEN 'UNIQUE'
      WHEN 'f' THEN 'FOREIGN KEY'
      WHEN 'c' THEN 'CHECK'
      WHEN 'x' THEN 'EXCLUSION'
      ELSE c.contype::text
    END AS constraint_type,
    pg_get_constraintdef(c.oid, TRUE) AS constraint_definition
  FROM pg_constraint c
  JOIN pg_class t
    ON t.oid = c.conrelid
  JOIN pg_namespace n
    ON n.oid = t.relnamespace
  WHERE n.nspname = %(schema_name)s
    AND t.relname = %(table_name)s
) constraints
ORDER BY constraint_type, constraint_name
"""

TABLE_INDEXES_SQL = """
SELECT
  indexname AS index_name,
  indexdef AS index_definition
FROM pg_indexes
WHERE schemaname = %(schema_name)s
  AND tablename = %(table_name)s
ORDER BY indexname
"""

TABLE_TRIGGERS_SQL = """
SELECT
  trigger_name,
  event_manipulation,
  action_timing,
  action_orientation
FROM information_schema.triggers
WHERE event_object_schema = %(schema_name)s
  AND event_object_table = %(table_name)s
ORDER BY trigger_name, event_manipulation
"""

CONNECTION_CONTEXT_SQL = """
WITH target AS (
  SELECT to_regclass(
    'public.ai_ducklake_entity_aliases'
  ) AS relation_oid
)
SELECT
  current_database() AS database_name,
  current_user AS database_user,
  current_setting('transaction_read_only') AS transaction_read_only,
  CASE
    WHEN target.relation_oid IS NULL THEN FALSE
    ELSE has_table_privilege(
      current_user,
      target.relation_oid,
      'SELECT'
    )
  END AS can_select,
  CASE
    WHEN target.relation_oid IS NULL THEN FALSE
    ELSE has_table_privilege(
      current_user,
      target.relation_oid,
      'INSERT'
    )
  END AS can_insert,
  CASE
    WHEN target.relation_oid IS NULL THEN FALSE
    ELSE has_table_privilege(
      current_user,
      target.relation_oid,
      'UPDATE'
    )
  END AS can_update
FROM target
"""

SELECTED_VERSION_INTENTS_SQL = """
SELECT
  intent_name,
  COUNT(*) AS active_pattern_count,
  MIN(priority) AS best_priority
FROM public.ai_ducklake_sql_patterns
WHERE agent_version = %(agent_version)s
  AND is_active = TRUE
GROUP BY intent_name
ORDER BY MIN(priority) NULLS LAST, intent_name
"""

SELECTED_VERSION_ENTITY_TYPES_SQL = """
SELECT
  COALESCE(NULLIF(BTRIM(entity_type), ''), '<empty>') AS entity_type,
  COUNT(*) AS total_records,
  COUNT(*) FILTER (WHERE is_active = TRUE) AS active_records
FROM public.ai_ducklake_entity_aliases
WHERE agent_version = %(agent_version)s
GROUP BY COALESCE(NULLIF(BTRIM(entity_type), ''), '<empty>')
ORDER BY entity_type
"""

SELECTED_VERSION_ENTITIES_SQL = """
SELECT
  entity_type,
  user_term,
  canonical_value,
  target_table,
  target_column,
  sql_filter_hint,
  business_rule,
  priority,
  is_active
FROM public.ai_ducklake_entity_aliases
WHERE agent_version = %(agent_version)s
  AND is_active = TRUE
ORDER BY priority NULLS LAST, entity_type, canonical_value, user_term
"""


class DiagnosticError(RuntimeError):
    """
    Falha conhecida durante o diagnóstico somente leitura.
    """


def _fetch_all(
    cursor: Any,
    query: str,
    parameters: Mapping[str, Any] | None = None,
) -> list[Mapping[str, Any]]:
    cursor.execute(query, parameters or {})
    rows = cursor.fetchall()
    return [row for row in rows if isinstance(row, Mapping)]


def _fetch_one(
    cursor: Any,
    query: str,
    parameters: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    cursor.execute(query, parameters or {})
    row = cursor.fetchone()
    if not isinstance(row, Mapping):
        raise DiagnosticError(
            "A consulta de diagnóstico não retornou um objeto."
        )
    return row


def _parse_json_mapping(value: Any) -> tuple[Mapping[str, Any] | None, bool]:
    """
    Converte um valor JSON/JSONB ou texto JSON em objeto sem lançar erro.

    Retorna (objeto, invalid_json). Valores nulos não são considerados
    JSON inválido. Estruturas que não sejam objeto também são tratadas
    como conteúdo não utilizável, mas sem interromper o diagnóstico.
    """

    if value is None:
        return None, False

    if isinstance(value, Mapping):
        return value, False

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None, False
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None, True
        if isinstance(parsed, Mapping):
            return parsed, False
        return None, False

    return None, False


def _analyze_selected_version_entities(
    rows: Sequence[Mapping[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, int],
]:
    """
    Analisa hints e definições em Python para evitar casts JSON inseguros.
    """

    signals_by_intent: dict[str, dict[str, Any]] = {}
    definitions: list[dict[str, Any]] = []
    diagnostics = {
        "invalid_sql_filter_hint_json": 0,
        "invalid_business_rule_json": 0,
    }

    for row in rows:
        intent_name = str(row.get("canonical_value") or "").strip()
        entity_type = str(row.get("entity_type") or "").strip().casefold()

        hint, invalid_hint = _parse_json_mapping(
            row.get("sql_filter_hint")
        )
        if invalid_hint:
            diagnostics["invalid_sql_filter_hint_json"] += 1

        resolver = hint.get("resolver") if isinstance(hint, Mapping) else None
        if isinstance(resolver, Mapping):
            signal = signals_by_intent.setdefault(
                intent_name,
                {
                    "intent_name": intent_name,
                    "signal_count": 0,
                    "positive_count": 0,
                    "negative_count": 0,
                },
            )
            signal["signal_count"] += 1
            polarity = str(resolver.get("polarity") or "").strip().casefold()
            if polarity == "positive":
                signal["positive_count"] += 1
            elif polarity == "negative":
                signal["negative_count"] += 1

        if entity_type != "intent_definition":
            continue

        business_rule, invalid_business_rule = _parse_json_mapping(
            row.get("business_rule")
        )
        if invalid_business_rule:
            diagnostics["invalid_business_rule_json"] += 1

        definitions.append(
            {
                "intent_name": intent_name,
                "definition_name": row.get("user_term"),
                "priority": row.get("priority"),
                "has_target_table": row.get("target_table") is not None,
                "has_target_column": row.get("target_column") is not None,
                "has_resolver": isinstance(resolver, Mapping),
                "has_intent_catalog": (
                    isinstance(business_rule, Mapping)
                    and "intent_catalog" in business_rule
                ),
            }
        )

    signals = sorted(
        signals_by_intent.values(),
        key=lambda item: str(item.get("intent_name", "")).casefold(),
    )
    definitions.sort(
        key=lambda item: (
            item.get("priority") is None,
            item.get("priority") if item.get("priority") is not None else 0,
            str(item.get("intent_name", "")).casefold(),
            str(item.get("definition_name", "")).casefold(),
        )
    )
    return signals, definitions, diagnostics


def _table_exists(
    cursor: Any,
    table_name: str,
) -> bool:
    row = _fetch_one(
        cursor,
        TABLE_EXISTS_SQL,
        {
            "schema_name": TARGET_SCHEMA,
            "table_name": table_name,
        },
    )
    return bool(row.get("table_exists", False))


def _collection_version_counts(
    cursor: Any,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for collection_name, table_name, active_column in CONTEXT_COLLECTIONS:
        if not _table_exists(cursor, table_name):
            records.append(
                {
                    "collection": collection_name,
                    "table_name": table_name,
                    "table_exists": False,
                    "agent_version": None,
                    "total_records": 0,
                    "active_records": 0,
                }
            )
            continue

        query = f"""
SELECT
  agent_version,
  COUNT(*) AS total_records,
  COUNT(*) FILTER (WHERE {active_column} = TRUE) AS active_records
FROM public.{table_name}
GROUP BY agent_version
ORDER BY agent_version
"""
        for row in _fetch_all(cursor, query):
            records.append(
                {
                    "collection": collection_name,
                    "table_name": table_name,
                    "table_exists": True,
                    "agent_version": row.get("agent_version"),
                    "total_records": row.get("total_records", 0),
                    "active_records": row.get("active_records", 0),
                }
            )

    return records


def _print_connection_context(
    connection_context: Mapping[str, Any],
    semantic_agent_version: str,
) -> None:
    print("CONEXAO_E_TRANSACAO:")
    print(
        f"- database={connection_context.get('database_name', '-')}"
    )
    print(
        f"- database_user={connection_context.get('database_user', '-')}"
    )
    print(
        "- transaction_read_only="
        f"{connection_context.get('transaction_read_only', '-')}"
    )
    print(f"- semantic_agent_version={semantic_agent_version}")
    print(
        "- privileges.entity_aliases="
        f"SELECT:{bool(connection_context.get('can_select', False))} "
        f"INSERT:{bool(connection_context.get('can_insert', False))} "
        f"UPDATE:{bool(connection_context.get('can_update', False))}"
    )


def _print_columns(columns: Sequence[Mapping[str, Any]]) -> set[str]:
    names: set[str] = set()

    print()
    print("ESTRUTURA_DE_COLUNAS:")
    print(f"- column_count={len(columns)}")

    for column in columns:
        column_name = str(column.get("column_name", "")).strip()
        if column_name:
            names.add(column_name)

        default_value = column.get("column_default")
        default_label = "-" if default_value is None else str(default_value)
        max_length = column.get("character_maximum_length")
        max_length_label = "-" if max_length is None else str(max_length)

        print(
            f"- {column.get('ordinal_position', '-')}: "
            f"{column_name or '-'} "
            f"type={column.get('data_type', '-')} "
            f"udt={column.get('udt_name', '-')} "
            f"nullable={column.get('is_nullable', '-')} "
            f"max_length={max_length_label} "
            f"default={default_label}"
        )

    missing = sorted(REQUIRED_ENTITY_COLUMNS - names)
    extra = sorted(names - REQUIRED_ENTITY_COLUMNS)

    print()
    print("CONTRATO_DE_COLUNAS:")
    print(f"- required_columns={len(REQUIRED_ENTITY_COLUMNS)}")
    print(f"- missing_required_columns={len(missing)}")
    for column_name in missing:
        print(f"  - {column_name}")
    print(f"- additional_columns={len(extra)}")
    for column_name in extra:
        print(f"  - {column_name}")

    return names


def _print_constraints(
    constraints: Sequence[Mapping[str, Any]],
) -> None:
    print()
    print("RESTRICOES:")
    print(f"- constraint_count={len(constraints)}")
    for constraint in constraints:
        print(
            f"- {constraint.get('constraint_name', '-')}: "
            f"type={constraint.get('constraint_type', '-')} | "
            f"definition={constraint.get('constraint_definition', '-')}"
        )


def _print_indexes(indexes: Sequence[Mapping[str, Any]]) -> None:
    print()
    print("INDICES:")
    print(f"- index_count={len(indexes)}")
    for index in indexes:
        print(
            f"- {index.get('index_name', '-')}: "
            f"{index.get('index_definition', '-')}"
        )


def _print_triggers(triggers: Sequence[Mapping[str, Any]]) -> None:
    print()
    print("TRIGGERS:")
    print(f"- trigger_event_count={len(triggers)}")
    for trigger in triggers:
        print(
            f"- {trigger.get('trigger_name', '-')}: "
            f"timing={trigger.get('action_timing', '-')} "
            f"event={trigger.get('event_manipulation', '-')} "
            f"orientation={trigger.get('action_orientation', '-')}"
        )


def _print_version_counts(
    rows: Sequence[Mapping[str, Any]],
    selected_version: str,
) -> None:
    by_version: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    missing_tables: list[str] = []

    for row in rows:
        if not bool(row.get("table_exists", False)):
            missing_tables.append(str(row.get("table_name", "")))
            continue

        version = row.get("agent_version")
        version_label = "<null>" if version is None else str(version)
        by_version[version_label].append(row)

    print()
    print("COBERTURA_DE_VERSOES:")
    print(f"- discovered_versions={len(by_version)}")
    print(f"- missing_context_tables={len(missing_tables)}")
    for table_name in sorted(name for name in missing_tables if name):
        print(f"  - {TARGET_SCHEMA}.{table_name}")

    for version in sorted(by_version, key=str.casefold):
        selected = "sim" if version == selected_version else "nao"
        print(f"- VERSION {version} selected={selected}")
        for row in sorted(
            by_version[version],
            key=lambda item: str(item.get("collection", "")),
        ):
            print(
                f"  - {row.get('collection', '-')}: "
                f"total={row.get('total_records', 0)} "
                f"active={row.get('active_records', 0)}"
            )


def _print_selected_version(
    intents: Sequence[Mapping[str, Any]],
    entity_types: Sequence[Mapping[str, Any]],
    signals: Sequence[Mapping[str, Any]],
    definitions: Sequence[Mapping[str, Any]],
    entity_diagnostics: Mapping[str, int],
) -> None:
    print()
    print("VERSAO_SELECIONADA:")
    print(f"- active_intents={len(intents)}")
    for row in intents:
        print(
            f"  - {row.get('intent_name', '-')}: "
            f"active_patterns={row.get('active_pattern_count', 0)} "
            f"best_priority={row.get('best_priority', '-')}"
        )

    print(f"- entity_types={len(entity_types)}")
    for row in entity_types:
        print(
            f"  - {row.get('entity_type', '-')}: "
            f"total={row.get('total_records', 0)} "
            f"active={row.get('active_records', 0)}"
        )

    print(f"- signal_intents={len(signals)}")
    for row in signals:
        print(
            f"  - {row.get('intent_name') or '<empty>'}: "
            f"signals={row.get('signal_count', 0)} "
            f"positive={row.get('positive_count', 0)} "
            f"negative={row.get('negative_count', 0)}"
        )

    print(
        "- invalid_sql_filter_hint_json="
        f"{entity_diagnostics.get('invalid_sql_filter_hint_json', 0)}"
    )
    print(
        "- invalid_business_rule_json="
        f"{entity_diagnostics.get('invalid_business_rule_json', 0)}"
    )

    print(f"- active_intent_definitions={len(definitions)}")
    for row in definitions:
        print(
            f"  - intent={row.get('intent_name') or '<empty>'} "
            f"definition={row.get('definition_name') or '<empty>'} "
            f"priority={row.get('priority', '-')} "
            f"target_table={bool(row.get('has_target_table', False))} "
            f"target_column={bool(row.get('has_target_column', False))} "
            f"resolver={bool(row.get('has_resolver', False))} "
            f"intent_catalog={bool(row.get('has_intent_catalog', False))}"
        )


def _print_readiness_facts(
    *,
    table_exists: bool,
    available_columns: set[str],
    intents: Sequence[Mapping[str, Any]],
    definitions: Sequence[Mapping[str, Any]],
) -> None:
    missing_columns = REQUIRED_ENTITY_COLUMNS - available_columns
    malformed_definitions = [
        row
        for row in definitions
        if bool(row.get("has_target_table", False))
        or bool(row.get("has_target_column", False))
        or bool(row.get("has_resolver", False))
        or not bool(row.get("has_intent_catalog", False))
    ]

    print()
    print("FATOS_PARA_PROXIMA_ETAPA:")
    print(f"- entity_table_exists={table_exists}")
    print(f"- required_columns_present={not missing_columns}")
    print(f"- selected_version_has_active_intents={bool(intents)}")
    print(
        "- selected_version_has_intent_definitions="
        f"{bool(definitions)}"
    )
    print(
        "- malformed_active_intent_definitions="
        f"{len(malformed_definitions)}"
    )
    print(
        "- observacao=este diagnostico nao cria, altera ou desativa "
        "registros"
    )


def main() -> int:
    print("=" * 70)
    print("POSTGRES INTENT CATALOG SCHEMA DIAGNOSTIC — READ ONLY")
    print("=" * 70)
    print(
        "Diagnóstico somente leitura. Credenciais, senha e DSN não serão "
        "exibidos."
    )
    print(
        "Nenhum registro será criado, alterado, desativado ou removido."
    )
    print()

    current_stage = "input_configuration"

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

        current_stage = "connection_preflight"
        if not _connection_preflight(
            host=host,
            port=port,
            dsn=dsn,
            connect_timeout_seconds=connect_timeout_seconds,
        ):
            return 3

        current_stage = "connect_read_only"
        with psycopg.connect(
            dsn,
            connect_timeout=connect_timeout_seconds,
            row_factory=dict_row,
        ) as connection:
            connection.read_only = True

            with connection.cursor() as cursor:
                current_stage = "connection_context"
                connection_context = _fetch_one(
                    cursor,
                    CONNECTION_CONTEXT_SQL,
                )

                current_stage = "table_existence"
                entity_table_exists = _table_exists(
                    cursor,
                    ENTITY_TABLE,
                )
                pattern_table_exists = _table_exists(
                    cursor,
                    PATTERN_TABLE,
                )

                if not entity_table_exists:
                    raise DiagnosticError(
                        "A tabela public.ai_ducklake_entity_aliases "
                        "não existe."
                    )

                current_stage = "entity_table_columns"
                columns = _fetch_all(
                    cursor,
                    TABLE_COLUMNS_SQL,
                    {
                        "schema_name": TARGET_SCHEMA,
                        "table_name": ENTITY_TABLE,
                    },
                )
                current_stage = "entity_table_constraints"
                constraints = _fetch_all(
                    cursor,
                    TABLE_CONSTRAINTS_SQL,
                    {
                        "schema_name": TARGET_SCHEMA,
                        "table_name": ENTITY_TABLE,
                    },
                )
                current_stage = "entity_table_indexes"
                indexes = _fetch_all(
                    cursor,
                    TABLE_INDEXES_SQL,
                    {
                        "schema_name": TARGET_SCHEMA,
                        "table_name": ENTITY_TABLE,
                    },
                )
                current_stage = "entity_table_triggers"
                triggers = _fetch_all(
                    cursor,
                    TABLE_TRIGGERS_SQL,
                    {
                        "schema_name": TARGET_SCHEMA,
                        "table_name": ENTITY_TABLE,
                    },
                )
                current_stage = "context_version_counts"
                version_counts = _collection_version_counts(cursor)

                current_stage = "selected_version_intents"
                if pattern_table_exists:
                    intents = _fetch_all(
                        cursor,
                        SELECTED_VERSION_INTENTS_SQL,
                        {"agent_version": semantic_agent_version},
                    )
                else:
                    intents = []

                current_stage = "selected_version_entity_types"
                entity_types = _fetch_all(
                    cursor,
                    SELECTED_VERSION_ENTITY_TYPES_SQL,
                    {"agent_version": semantic_agent_version},
                )
                current_stage = "selected_version_entities"
                selected_entities = _fetch_all(
                    cursor,
                    SELECTED_VERSION_ENTITIES_SQL,
                    {"agent_version": semantic_agent_version},
                )
                current_stage = "analyze_selected_version_entities"
                (
                    signals,
                    definitions,
                    entity_diagnostics,
                ) = _analyze_selected_version_entities(selected_entities)

        print()
        print("=" * 70)
        print("DIAGNOSTICO")
        print("=" * 70)

        _print_connection_context(
            connection_context,
            semantic_agent_version,
        )
        available_columns = _print_columns(columns)
        _print_constraints(constraints)
        _print_indexes(indexes)
        _print_triggers(triggers)
        _print_version_counts(
            version_counts,
            semantic_agent_version,
        )
        _print_selected_version(
            intents,
            entity_types,
            signals,
            definitions,
            entity_diagnostics,
        )
        _print_readiness_facts(
            table_exists=entity_table_exists,
            available_columns=available_columns,
            intents=intents,
            definitions=definitions,
        )

        print()
        print("DIAGNOSTICO_CONCLUIDO: OK")

        if REQUIRED_ENTITY_COLUMNS - available_columns:
            return 7
        if not pattern_table_exists or not intents:
            return 8
        return 0

    except psycopg.Error as error:
        print("CONSULTA_DIAGNOSTICO: ERRO")
        print(f"ETAPA_SEGURA: {current_stage}")
        cause = _root_cause(error)
        if isinstance(cause, BaseException):
            _print_safe_psycopg_diagnostic(cause)
        return 4

    except DiagnosticError as error:
        print(f"DIAGNOSTICO: ERRO — {error}")
        return 5

    except ValueError as error:
        print(f"CONFIGURACAO: ERRO — {error}")
        return 2

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

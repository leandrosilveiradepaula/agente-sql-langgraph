from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.domain.context import ContextSnapshot
from app.domain.context_normalizer import (
    ContextNormalizationError,
    normalize_context_snapshot,
)
from app.ports.context_repository import ContextRepositoryError


_POSTGRES_IDENTIFIER_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*$"
)


LOAD_SEMANTIC_CONTEXT_RELATIONS_SQL_TEMPLATE = """
WITH cfg AS (
  SELECT
    %(agent_version)s::text AS agent_version
),

regras AS (
  SELECT
    r.rule_group,
    r.rule_name,
    r.rule_content,
    r.applies_to_intents,
    r.validation_hint,
    r.severity,
    r.priority
  FROM {rules_relation} r
  JOIN cfg
    ON cfg.agent_version = r.agent_version
  WHERE r.is_active = TRUE
  ORDER BY
    r.priority,
    r.rule_group,
    r.rule_name
),

entidades AS (
  SELECT
    e.entity_type,
    e.user_term,
    e.canonical_value,
    e.target_table,
    e.target_column,
    e.sql_filter_hint,
    e.business_rule,
    e.priority
  FROM {entities_relation} e
  JOIN cfg
    ON cfg.agent_version = e.agent_version
  WHERE e.is_active = TRUE
  ORDER BY
    e.priority,
    e.entity_type,
    e.user_term
),

dre AS (
  SELECT
    d.dre_code,
    d.nivel_1_bi,
    d.business_description,
    d.sign_convention,
    d.category,
    d.is_revenue,
    d.is_deduction,
    d.is_cost,
    d.is_opex,
    d.is_financial_result,
    d.sql_filter_hint,
    d.sort_order
  FROM {dre_relation} d
  JOIN cfg
    ON cfg.agent_version = d.agent_version
  WHERE d.is_active = TRUE
  ORDER BY
    d.sort_order,
    d.dre_code
),

padroes AS (
  SELECT
    p.intent_name,
    p.pattern_name,
    p.business_question_examples,
    p.required_tables,
    p.required_rules,
    p.sql_pattern,
    p.notes,
    p.priority
  FROM {patterns_relation} p
  JOIN cfg
    ON cfg.agent_version = p.agent_version
  WHERE p.is_active = TRUE
  ORDER BY
    p.priority,
    p.intent_name,
    p.pattern_name
),

catalogo AS (
  SELECT
    t.table_name,
    t.schema_name,
    t.table_type,
    t.description,
    t.grain,
    t.primary_key,
    t.key_columns,
    t.metric_columns,
    t.date_columns,
    t.join_rules,
    t.ai_hint,
    t.priority
  FROM {catalog_relation} t
  JOIN cfg
    ON cfg.agent_version = t.agent_version
  WHERE t.is_allowed = TRUE
  ORDER BY
    t.priority,
    t.table_name
)

SELECT
  cfg.agent_version AS semantic_agent_version,

  'postgres_versioned_semantic_context'
    AS semantic_context_source,

  COALESCE(
    (
      SELECT jsonb_agg(
        to_jsonb(regras)
        ORDER BY
          regras.priority,
          regras.rule_group,
          regras.rule_name
      )
      FROM regras
    ),
    '[]'::jsonb
  ) AS regras,

  COALESCE(
    (
      SELECT jsonb_agg(
        to_jsonb(entidades)
        ORDER BY
          entidades.priority,
          entidades.entity_type,
          entidades.user_term
      )
      FROM entidades
    ),
    '[]'::jsonb
  ) AS entidades,

  COALESCE(
    (
      SELECT jsonb_agg(
        to_jsonb(dre)
        ORDER BY
          dre.sort_order,
          dre.dre_code
      )
      FROM dre
    ),
    '[]'::jsonb
  ) AS dre,

  COALESCE(
    (
      SELECT jsonb_agg(
        to_jsonb(padroes)
        ORDER BY
          padroes.priority,
          padroes.intent_name,
          padroes.pattern_name
      )
      FROM padroes
    ),
    '[]'::jsonb
  ) AS padroes,

  COALESCE(
    (
      SELECT jsonb_agg(
        to_jsonb(catalogo)
        ORDER BY
          catalogo.priority,
          catalogo.table_name
      )
      FROM catalogo
    ),
    '[]'::jsonb
  ) AS catalogo,

  jsonb_build_object(
    'regras',
      (SELECT COUNT(*) FROM regras),

    'entidades',
      (SELECT COUNT(*) FROM entidades),

    'dre',
      (SELECT COUNT(*) FROM dre),

    'padroes',
      (SELECT COUNT(*) FROM padroes),

    'catalogo',
      (SELECT COUNT(*) FROM catalogo)
  ) AS context_counts

FROM cfg
"""

# Preserve the previously public `LOAD_SEMANTIC_CONTEXT_SQL_TEMPLATE`
# contract: callers can still render the historical defaults with only
# `context_schema` and receive the exact SQL used before this change.
LOAD_SEMANTIC_CONTEXT_SQL_TEMPLATE = LOAD_SEMANTIC_CONTEXT_RELATIONS_SQL_TEMPLATE.format(
    rules_relation="{context_schema}.ai_ducklake_agent_rules",
    entities_relation="{context_schema}.ai_ducklake_entity_aliases",
    dre_relation="{context_schema}.ai_ducklake_dre_mapping",
    patterns_relation="{context_schema}.ai_ducklake_sql_patterns",
    catalog_relation="{context_schema}.ai_ducklake_table_catalog",
)


# Adapter-owned canonical collections; business schema/aliases/metrics are
# loaded from versioned data. Table identities are configurable per tenant and
# are never taken from prompts, generated SQL, or benchmark expectations.
DEFAULT_CONTEXT_TABLES: dict[str, str] = {
    "rules": "ai_ducklake_agent_rules",
    "entities": "ai_ducklake_entity_aliases",
    "dre": "ai_ducklake_dre_mapping",
    "patterns": "ai_ducklake_sql_patterns",
    "catalog": "ai_ducklake_table_catalog",
}

# Disabled optional mapping yields an empty typed relation. The DRE concept
# is *optional*, never guessed for tenants whose accounting model lacks it.
_EMPTY_DRE_RELATION = """(
  SELECT
    NULL::text AS agent_version,
    FALSE::boolean AS is_active,
    NULL::text AS dre_code,
    NULL::text AS nivel_1_bi,
    NULL::text AS business_description,
    NULL::text AS sign_convention,
    NULL::text AS category,
    NULL::boolean AS is_revenue,
    NULL::boolean AS is_deduction,
    NULL::boolean AS is_cost,
    NULL::boolean AS is_opex,
    NULL::boolean AS is_financial_result,
    NULL::jsonb AS sql_filter_hint,
    NULL::integer AS sort_order
  WHERE FALSE
)"""


def render_versioned_context_sql(
    *,
    context_schema: str,
    catalog_tables: Mapping[str, str | None] | None = None,
) -> str:
    """Compile only allowlisted, externally configured catalog identifiers.

    `dre=None` is the only supported omission: all remaining collections
    are required structural metadata, not financial-business fallbacks.
    Unrecognized keys, SQL expressions and cross-schema identifiers fail closed.
    """
    if not isinstance(context_schema, str) or not _POSTGRES_IDENTIFIER_PATTERN.fullmatch(context_schema):
        raise ValueError("context_schema deve ser um identificador PostgreSQL simples.")
    configured: dict[str, str | None] = dict(DEFAULT_CONTEXT_TABLES)
    if catalog_tables is not None:
        if not isinstance(catalog_tables, Mapping):
            raise ValueError("catalog_tables deve ser um mapeamento.")
        if set(catalog_tables) - set(DEFAULT_CONTEXT_TABLES):
            raise ValueError("catalog_tables contém fonte desconhecida.")
        configured.update(catalog_tables)

    relations: dict[str, str] = {}
    for key, table in configured.items():
        if key == "dre" and table is None:
            relations[key] = _EMPTY_DRE_RELATION
            continue
        if not isinstance(table, str) or not _POSTGRES_IDENTIFIER_PATTERN.fullmatch(table):
            raise ValueError("catalog_tables contém identificador inválido.")
        relations[key] = f"{context_schema}.{table}"

    return LOAD_SEMANTIC_CONTEXT_RELATIONS_SQL_TEMPLATE.format(
        rules_relation=relations["rules"],
        entities_relation=relations["entities"],
        dre_relation=relations["dre"],
        patterns_relation=relations["patterns"],
        catalog_relation=relations["catalog"],
    )


LOAD_SEMANTIC_CONTEXT_SQL = render_versioned_context_sql(context_schema="public")


ConnectCallable = Callable[..., Any]


class PostgresContextRepository:
    """
    Implementação PostgreSQL do contrato ContextRepository.

    A versão semântica e a conexão são recebidas externamente.
    O adapter executa uma consulta parametrizada, normaliza o registro
    físico retornado e entrega um ContextSnapshot canônico ao grafo.
    """

    def __init__(
        self,
        *,
        dsn: str,
        semantic_agent_version: str,
        context_schema: str = "public",
        catalog_tables: Mapping[str, str | None] | None = None,
        connect_timeout_seconds: int = 10,
        connect: ConnectCallable = psycopg.connect,
    ) -> None:
        normalized_dsn = dsn.strip()
        normalized_version = semantic_agent_version.strip()
        normalized_schema = context_schema.strip()

        if not normalized_dsn:
            raise ValueError("dsn não pode estar vazio.")

        if not normalized_version:
            raise ValueError(
                "semantic_agent_version não pode estar vazio."
            )

        if not normalized_schema:
            raise ValueError("context_schema não pode estar vazio.")

        if not _POSTGRES_IDENTIFIER_PATTERN.fullmatch(normalized_schema):
            raise ValueError(
                "context_schema deve ser um identificador PostgreSQL simples."
            )

        if (
            not isinstance(connect_timeout_seconds, int)
            or isinstance(connect_timeout_seconds, bool)
            or connect_timeout_seconds <= 0
        ):
            raise ValueError(
                "connect_timeout_seconds deve ser um inteiro positivo."
            )

        self._dsn = normalized_dsn
        self._semantic_agent_version = normalized_version
        self._context_schema = normalized_schema
        self._load_sql = render_versioned_context_sql(
            context_schema=normalized_schema,
            catalog_tables=catalog_tables,
        )
        self._connect_timeout_seconds = connect_timeout_seconds
        self._connect = connect

    def load_active_context(
        self,
        *,
        user_profile: str,
    ) -> ContextSnapshot:
        """
        Carrega e normaliza o snapshot da versão configurada.

        user_profile permanece no contrato para futura aplicação de
        políticas por perfil. Nesta onda ele não altera a consulta.
        """

        del user_profile

        try:
            with self._connect(
                self._dsn,
                connect_timeout=self._connect_timeout_seconds,
                row_factory=dict_row,
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        self._load_sql,
                        {
                            "agent_version": (
                                self._semantic_agent_version
                            )
                        },
                    )
                    raw_snapshot = cursor.fetchone()

        except psycopg.Error as error:
            raise ContextRepositoryError(
                "Falha ao consultar o contexto semântico no PostgreSQL."
            ) from error

        if raw_snapshot is None:
            raise ContextRepositoryError(
                "A consulta de contexto não retornou um snapshot."
            )

        try:
            return normalize_context_snapshot(raw_snapshot)

        except ContextNormalizationError as error:
            raise ContextRepositoryError(
                "O PostgreSQL retornou um snapshot semântico inválido."
            ) from error

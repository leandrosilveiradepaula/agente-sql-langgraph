from __future__ import annotations

from collections.abc import Callable
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.domain.context import ContextSnapshot
from app.domain.context_normalizer import (
    ContextNormalizationError,
    normalize_context_snapshot,
)
from app.ports.context_repository import ContextRepositoryError


LOAD_SEMANTIC_CONTEXT_SQL = """
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
  FROM public.ai_ducklake_agent_rules r
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
  FROM public.ai_ducklake_entity_aliases e
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
  FROM public.ai_ducklake_dre_mapping d
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
  FROM public.ai_ducklake_sql_patterns p
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
  FROM public.ai_ducklake_table_catalog t
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
        connect_timeout_seconds: int = 10,
        connect: ConnectCallable = psycopg.connect,
    ) -> None:
        normalized_dsn = dsn.strip()
        normalized_version = semantic_agent_version.strip()

        if not normalized_dsn:
            raise ValueError("dsn não pode estar vazio.")

        if not normalized_version:
            raise ValueError(
                "semantic_agent_version não pode estar vazio."
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
                        LOAD_SEMANTIC_CONTEXT_SQL,
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

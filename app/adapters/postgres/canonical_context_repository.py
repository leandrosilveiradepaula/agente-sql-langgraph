"""Versioned, tenant-bound canonical semantic context; independent of client schemas.

This repository reads an externally approved canonical snapshot. It never
discovers schemas from an arbitrary prompt, executes financial SQL, approves
business rules or imports historical benchmark material. One repository is
bound to one authorized tenant by the application composition layer.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.config.context_fingerprint import validate_expected_context_fingerprint
from app.domain.context import ContextSnapshot
from app.domain.context_normalizer import (
    ContextNormalizationError,
    normalize_context_snapshot,
)
from app.domain.context_validator import validate_context_snapshot
from app.domain.canonical_source_boundary import (
    CanonicalSourceBoundaryError,
    require_structural_patterns_only,
)
from app.ports.context_repository import ContextRepositoryError

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_TENANT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")

# A stable platform contract, not the schema of any customer's accounting DB.
# The catalog must be provisioned/approved separately; this adapter never DDLs.
def canonical_snapshot_select(*, context_schema: str, table_name: str) -> str:
    for value in (context_schema, table_name):
        if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
            raise ValueError("Identificador da tabela de contexto inválido.")
    return (
        "SELECT snapshot_payload, count(*) OVER () AS matching_rows "
        f"FROM {context_schema}.{table_name} "
        "WHERE tenant_id = %(tenant_id)s "
        "AND semantic_agent_version = %(agent_version)s "
        "AND is_active = TRUE AND is_approved = TRUE "
        "LIMIT 2"
    )


class CanonicalContextRepository:
    """Read approved, immutable per-tenant semantics in a generic JSON format.

    Different customers can have unrelated physical accounting schemas; their
    authorized versioned snapshots express schemas, metrics, relationships and
    financial meanings. The engine cannot infer or supply missing meanings.
    """

    def __init__(
        self,
        *,
        dsn: str,
        tenant_id: str,
        semantic_agent_version: str,
        expected_context_fingerprint: str,
        context_schema: str,
        context_table: str,
        connect_timeout_seconds: int = 10,
        connect: Callable[..., Any] = psycopg.connect,
    ) -> None:
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("Conexão do catálogo não configurada.")
        if (
            not isinstance(tenant_id, str)
            or not _TENANT_ID.fullmatch(tenant_id)
        ):
            raise ValueError("Identificação do tenant inválida.")
        if (
            not isinstance(semantic_agent_version, str)
            or not semantic_agent_version.strip()
        ):
            raise ValueError("Versão semântica não configurada.")
        if (
            type(connect_timeout_seconds) is not int
            or connect_timeout_seconds <= 0
        ):
            raise ValueError("Timeout do catálogo inválido.")
        fingerprint = validate_expected_context_fingerprint(
            expected_context_fingerprint
        )
        if fingerprint is None:
            raise ValueError("Fingerprint aprovado do contexto obrigatório.")
        self._dsn = dsn.strip()
        self._tenant_id = tenant_id
        self._version = semantic_agent_version.strip()
        self._expected_fingerprint = fingerprint
        self._timeout = connect_timeout_seconds
        self._connect = connect
        self._select = canonical_snapshot_select(
            context_schema=context_schema,
            table_name=context_table,
        )

    def load_active_context(self, *, user_profile: str) -> ContextSnapshot:
        # Trusted tenant binding happens during application composition,
        # NOT by trusting user-supplied question/profile or SQL.
        del user_profile
        try:
            with self._connect(
                self._dsn,
                connect_timeout=self._timeout,
                row_factory=dict_row,
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        self._select,
                        {
                            "tenant_id": self._tenant_id,
                            "agent_version": self._version,
                        },
                    )
                    row = cursor.fetchone()
        except psycopg.Error:
            raise ContextRepositoryError(
                "Falha ao consultar o catálogo semântico autorizado."
            ) from None
        except Exception:
            raise ContextRepositoryError(
                "Catálogo semântico indisponível."
            ) from None
        if (
            not isinstance(row, Mapping)
            or type(row.get("matching_rows")) is not int
            or row["matching_rows"] != 1
        ):
            raise ContextRepositoryError(
                "Versão semântica única e aprovada não encontrada."
            )
        raw = row.get("snapshot_payload")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (ValueError, TypeError):
                raise ContextRepositoryError(
                    "Snapshot do catálogo inválido."
                ) from None
        if not isinstance(raw, Mapping):
            raise ContextRepositoryError("Snapshot do catálogo inválido.")
        if (
            raw.get("tenant_id") != self._tenant_id
            or raw.get("semantic_agent_version") != self._version
            or raw.get("source_approval_status") != "APPROVED"
            or raw.get("historical_evaluation_sql_excluded") is not True
        ):
            raise ContextRepositoryError(
                "Proveniência e aprovação do snapshot não verificadas."
            )
        try:
            require_structural_patterns_only(raw)
        except CanonicalSourceBoundaryError:
            raise ContextRepositoryError(
                "Material de avaliação ou origem não aprovada no contexto."
            ) from None
        try:
            snapshot = normalize_context_snapshot(raw)
        except (ContextNormalizationError, TypeError, ValueError):
            raise ContextRepositoryError(
                "Falha na normalização do contexto semântico."
            ) from None
        if snapshot["fingerprint"] != self._expected_fingerprint:
            raise ContextRepositoryError(
                "Fingerprint do contexto não corresponde ao aprovado."
            )
        report = validate_context_snapshot(snapshot)
        if report["status"] != "valid":
            raise ContextRepositoryError(
                "Contexto semântico aprovado não atende ao contrato."
            )
        return snapshot

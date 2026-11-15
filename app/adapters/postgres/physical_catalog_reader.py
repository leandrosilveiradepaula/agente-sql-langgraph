"""Read-only PostgreSQL schema discovery for tenant-scoped onboarding.

No customer data rows, SQL generation, DDL or semantic inference. The
operator supplies a dedicated least-privilege PostgreSQL connection and
the exact allowlisted schemas. This adapter is never invoked by a prompt.
"""
from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any

import psycopg
from psycopg.rows import dict_row

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_MAX_SCHEMAS = 32
_MAX_COLUMNS = 65536
_DISCOVERY_QUERY = """
SELECT table_schema, table_name, column_name
FROM information_schema.columns
WHERE table_schema = ANY(%(allowed_schemas)s::text[])
ORDER BY table_schema, table_name, ordinal_position
LIMIT 65537
"""


class PhysicalCatalogReadError(RuntimeError):
    """Fails closed without leaking SQL, passwords or source identifiers."""


class PostgresPhysicalCatalogReader:
    """Provide physical schema evidence for one authorized tenant source."""

    def __init__(
        self,
        *,
        dsn: str,
        allowed_schemas: Iterable[str],
        connect_timeout_seconds: int = 10,
        connect: Callable[..., Any] = psycopg.connect,
    ) -> None:
        if not isinstance(dsn, str) or not dsn.strip():
            raise ValueError("Credencial de leitura de metadados ausente.")
        if isinstance(allowed_schemas, (str, bytes)):
            raise ValueError("Lista de schemas autorizados inválida.")
        schemas = list(allowed_schemas)
        if (
            not 1 <= len(schemas) <= _MAX_SCHEMAS
            or any(
                not isinstance(name, str)
                or _IDENTIFIER.fullmatch(name) is None
                or name in ("pg_catalog", "information_schema")
                or name.startswith("pg_toast")
                for name in schemas
            )
            or len(set(schemas)) != len(schemas)
        ):
            raise ValueError("Lista de schemas autorizados inválida.")
        if type(connect_timeout_seconds) is not int or connect_timeout_seconds <= 0:
            raise ValueError("Timeout do leitor de metadados inválido.")
        self._dsn = dsn.strip()
        self._schemas = tuple(schemas)
        self._timeout = connect_timeout_seconds
        self._connect = connect

    def inspect(self) -> list[dict[str, object]]:
        """Read catalog metadata only, with a read-only transaction."""
        try:
            with self._connect(
                self._dsn,
                connect_timeout=self._timeout,
                row_factory=dict_row,
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SET TRANSACTION READ ONLY")
                    cursor.execute(
                        _DISCOVERY_QUERY,
                        {"allowed_schemas": list(self._schemas)},
                    )
                    rows = cursor.fetchall()
        except Exception:
            raise PhysicalCatalogReadError(
                "Falha ao ler o catálogo físico autorizado."
            ) from None
        if not isinstance(rows, list) or not 1 <= len(rows) <= _MAX_COLUMNS:
            raise PhysicalCatalogReadError(
                "Catálogo físico vazio ou maior que o limite seguro."
            )
        groups: dict[tuple[str, str], list[str]] = {}
        seen: set[tuple[str, str, str]] = set()
        for row in rows:
            if not isinstance(row, Mapping):
                raise PhysicalCatalogReadError("Linha de catálogo inválida.")
            schema = row.get("table_schema")
            table = row.get("table_name")
            column = row.get("column_name")
            if (
                not isinstance(schema, str)
                or schema not in self._schemas
                or not isinstance(table, str)
                or _IDENTIFIER.fullmatch(table) is None
                or not isinstance(column, str)
                or _IDENTIFIER.fullmatch(column) is None
            ):
                raise PhysicalCatalogReadError(
                    "Identificador fora do escopo do catálogo."
                )
            ident = (schema, table, column)
            if ident in seen:
                raise PhysicalCatalogReadError(
                    "Coluna duplicada no catálogo físico."
                )
            seen.add(ident)
            groups.setdefault((schema, table), []).append(column)
        return [
            {
                "schema_name": schema,
                "table_name": table,
                "columns": sorted(columns),
            }
            for (schema, table), columns in sorted(groups.items())
        ]

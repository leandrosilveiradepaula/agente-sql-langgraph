from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

from app.config.context_fingerprint import (
    EXPECTED_CONTEXT_FINGERPRINT_ENV,
    validate_expected_context_fingerprint,
)


POSTGRES_DSN_ENV = "POSTGRES_DSN"
POSTGRES_CONTEXT_SOURCE_MODE_ENV = "POSTGRES_CONTEXT_SOURCE_MODE"
CONTEXT_TENANT_ID_ENV = "CONTEXT_TENANT_ID"
POSTGRES_CANONICAL_CONTEXT_TABLE_ENV = "POSTGRES_CANONICAL_CONTEXT_TABLE"
SEMANTIC_AGENT_VERSION_ENV = "SEMANTIC_AGENT_VERSION"
POSTGRES_CONTEXT_SCHEMA_ENV = "POSTGRES_CONTEXT_SCHEMA"
POSTGRES_CONNECT_TIMEOUT_ENV = (
    "POSTGRES_CONNECT_TIMEOUT_SECONDS"
)

DEFAULT_POSTGRES_CONTEXT_SCHEMA = "public"
DEFAULT_POSTGRES_CONNECT_TIMEOUT_SECONDS = 10
_POSTGRES_IDENTIFIER_PATTERN = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*$"
)


class RuntimeConfigError(ValueError):
    """
    Erro conhecido ao carregar configuração externa de runtime.
    """


@dataclass(frozen=True, slots=True)
class PostgresContextRuntimeConfig:
    """
    Configuração necessária para o adapter PostgreSQL de contexto.

    Os valores são fornecidos externamente. A classe não lê arquivos,
    não registra credenciais e não mantém valores padrão de conexão.
    """

    dsn: str
    semantic_agent_version: str
    context_schema: str
    connect_timeout_seconds: int
    expected_context_fingerprint: str | None = None
    context_source_mode: str = "legacy_tables"
    tenant_id: str | None = None
    canonical_context_table: str | None = None


def load_postgres_context_runtime_config(
    environ: Mapping[str, str] | None = None,
) -> PostgresContextRuntimeConfig:
    """
    Carrega e valida a configuração a partir de variáveis do processo.

    Um mapping pode ser injetado para testes ou outros mecanismos de
    configuração. Quando omitido, utiliza os.environ.
    """

    source = os.environ if environ is None else environ

    dsn = _required_text(
        source,
        POSTGRES_DSN_ENV,
    )
    semantic_agent_version = _required_text(
        source,
        SEMANTIC_AGENT_VERSION_ENV,
    )
    context_schema = validate_postgres_context_schema(
        source,
        POSTGRES_CONTEXT_SCHEMA_ENV,
        default=DEFAULT_POSTGRES_CONTEXT_SCHEMA,
    )
    connect_timeout_seconds = _positive_integer(
        source,
        POSTGRES_CONNECT_TIMEOUT_ENV,
        default=DEFAULT_POSTGRES_CONNECT_TIMEOUT_SECONDS,
    )

    try:
        expected_context_fingerprint = validate_expected_context_fingerprint(
            source.get(EXPECTED_CONTEXT_FINGERPRINT_ENV)
        )
    except ValueError:
        raise RuntimeConfigError(
            f"A variável {EXPECTED_CONTEXT_FINGERPRINT_ENV} é inválida."
        ) from None

    context_source_mode = source.get(
        POSTGRES_CONTEXT_SOURCE_MODE_ENV, "legacy_tables"
    )
    if context_source_mode not in ("legacy_tables", "canonical_snapshot"):
        raise RuntimeConfigError(
            f"A variável {POSTGRES_CONTEXT_SOURCE_MODE_ENV} é inválida."
        )
    tenant_id: str | None = None
    canonical_context_table: str | None = None
    if context_source_mode == "canonical_snapshot":
        tenant_id = _required_text(source, CONTEXT_TENANT_ID_ENV)
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", tenant_id):
            raise RuntimeConfigError(
                f"A variável {CONTEXT_TENANT_ID_ENV} é inválida."
            )
        canonical_context_table = _required_text(
            source, POSTGRES_CANONICAL_CONTEXT_TABLE_ENV
        )
        if not _POSTGRES_IDENTIFIER_PATTERN.fullmatch(canonical_context_table):
            raise RuntimeConfigError(
                f"A variável {POSTGRES_CANONICAL_CONTEXT_TABLE_ENV} é inválida."
            )
        if expected_context_fingerprint is None:
            raise RuntimeConfigError(
                f"A variável {EXPECTED_CONTEXT_FINGERPRINT_ENV} é obrigatória "
                "para contexto canônico."
            )
    elif (source.get(CONTEXT_TENANT_ID_ENV) is not None
          or source.get(POSTGRES_CANONICAL_CONTEXT_TABLE_ENV) is not None):
        raise RuntimeConfigError(
            "Campos de contexto canônico exigem modo canonical_snapshot."
        )

    return PostgresContextRuntimeConfig(
        dsn=dsn,
        semantic_agent_version=semantic_agent_version,
        context_schema=context_schema,
        connect_timeout_seconds=connect_timeout_seconds,
        expected_context_fingerprint=expected_context_fingerprint,
        context_source_mode=context_source_mode,
        tenant_id=tenant_id,
        canonical_context_table=canonical_context_table,
    )


def _required_text(
    source: Mapping[str, str],
    variable_name: str,
) -> str:
    raw_value = source.get(variable_name)

    if raw_value is None:
        raise RuntimeConfigError(
            f"A variável {variable_name} não está definida."
        )

    normalized_value = str(raw_value).strip()

    if not normalized_value:
        raise RuntimeConfigError(
            f"A variável {variable_name} não pode estar vazia."
        )

    return normalized_value


def _positive_integer(
    source: Mapping[str, str],
    variable_name: str,
    *,
    default: int,
) -> int:
    raw_value = source.get(variable_name)

    if raw_value is None:
        return default

    normalized_value = str(raw_value).strip()

    if not normalized_value:
        raise RuntimeConfigError(
            f"A variável {variable_name} não pode estar vazia."
        )

    try:
        parsed_value = int(normalized_value)
    except ValueError as error:
        raise RuntimeConfigError(
            f"A variável {variable_name} deve ser um inteiro positivo."
        ) from error

    if parsed_value <= 0:
        raise RuntimeConfigError(
            f"A variável {variable_name} deve ser um inteiro positivo."
        )

    return parsed_value


def validate_postgres_context_schema(
    source: Mapping[str, str],
    variable_name: str,
    *,
    default: str,
) -> str:
    raw_value = source.get(variable_name)

    if raw_value is None:
        normalized_value = default
    else:
        normalized_value = str(raw_value).strip()

    if not normalized_value:
        raise RuntimeConfigError(
            f"A variável {variable_name} não pode estar vazia."
        )

    if not _POSTGRES_IDENTIFIER_PATTERN.fullmatch(normalized_value):
        raise RuntimeConfigError(
            f"A variável {variable_name} deve ser um identificador PostgreSQL simples."
        )

    return normalized_value

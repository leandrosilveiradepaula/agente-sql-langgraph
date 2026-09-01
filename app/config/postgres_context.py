from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass


POSTGRES_DSN_ENV = "POSTGRES_DSN"
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

    return PostgresContextRuntimeConfig(
        dsn=dsn,
        semantic_agent_version=semantic_agent_version,
        context_schema=context_schema,
        connect_timeout_seconds=connect_timeout_seconds,
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

from typing import Any, TypedDict


class ContextVersions(TypedDict, total=False):
    """
    Versões dos conjuntos de informações carregados.
    """

    catalog: str
    rules: str
    aliases: str
    dre_mapping: str
    sql_patterns: str


class CatalogColumn(TypedDict, total=False):
    """
    Coluna disponível no catálogo SQL.
    """

    name: str
    data_type: str
    nullable: bool
    description: str


class CatalogTable(TypedDict, total=False):
    """
    Tabela autorizada para geração de SQL.
    """

    schema: str
    name: str
    description: str
    columns: list[CatalogColumn]


class ContextSnapshot(TypedDict, total=False):
    """
    Snapshot imutável do contexto usado em uma execução.

    No futuro, o conteúdo será carregado do Supabase/Postgres.
    """

    version: str
    versions: ContextVersions

    allowed_schemas: list[str]
    tables: list[CatalogTable]

    rules: list[dict[str, Any]]
    aliases: dict[str, str]
    dre_mappings: list[dict[str, Any]]
    sql_patterns: list[dict[str, Any]]
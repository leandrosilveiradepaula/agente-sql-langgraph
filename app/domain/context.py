from typing import Any, TypedDict


class ContextVersions(TypedDict, total=False):
    """
    Estrutura legada mantida temporariamente para compatibilidade.

    O snapshot real do n8n não fornece versões independentes para
    catálogo, regras, aliases, DRE e padrões. Este tipo será removido
    quando todos os consumidores estiverem migrados para o contrato
    canônico.
    """

    catalog: str
    rules: str
    aliases: str
    dre_mapping: str
    sql_patterns: str


class ContextCounts(TypedDict, total=False):
    """
    Contagens das coleções normalizadas do snapshot.
    """

    rules: int
    entities: int
    dre_mappings: int
    query_patterns: int
    table_catalog: int


class AgentRule(TypedDict, total=False):
    """
    Regra semântica ou configuração versionada do agente.
    """

    rule_group: str
    rule_name: str
    rule_content: Any
    applies_to_intents: list[str]
    validation_hint: Any
    severity: str
    priority: int


class EntityAlias(TypedDict, total=False):
    """
    Alias, entidade ou sinal configurável carregado do contexto.
    """

    entity_type: str
    user_term: str
    canonical_value: str
    target_table: str | None
    target_column: str | None
    sql_filter_hint: Any
    business_rule: Any
    priority: int


class DreMapping(TypedDict, total=False):
    """
    Mapeamento versionado de grupos e categorias DRE.
    """

    dre_code: str
    nivel_1_bi: str
    business_description: str
    sign_convention: Any
    category: str
    is_revenue: bool
    is_deduction: bool
    is_cost: bool
    is_opex: bool
    is_financial_result: bool
    sql_filter_hint: Any
    sort_order: int


class QueryPattern(TypedDict, total=False):
    """
    Padrão de consulta carregado do contexto semântico.

    O campo sql_pattern é preservado temporariamente para
    compatibilidade, mas não representa o contrato canônico
    de planejamento.
    """

    intent_name: str
    pattern_name: str
    business_question_examples: list[str]
    required_tables: list[str]
    required_rules: list[str]
    sql_pattern: str
    notes: str | None
    priority: int


class CatalogColumn(TypedDict, total=False):
    """
    Coluna disponível no catálogo SQL.

    A estrutura ainda é compatível com a baseline local, que utiliza
    uma lista simplificada de colunas nos testes.
    """

    name: str
    data_type: str
    nullable: bool
    description: str | None


class TableCatalogEntry(TypedDict, total=False):
    """
    Tabela autorizada e seus metadados físicos versionados.
    """

    table_name: str
    schema_name: str
    table_type: str
    description: str | None
    grain: Any
    primary_key: Any
    key_columns: Any
    metric_columns: Any
    date_columns: Any
    join_rules: Any
    ai_hint: Any
    priority: int
    columns: list[CatalogColumn]


class CatalogTable(TypedDict, total=False):
    """
    Estrutura legada usada pela baseline antes do contrato canônico.

    Será removida depois que load_context e os testes passarem a usar
    table_catalog.
    """

    schema: str
    name: str
    description: str | None
    columns: list[CatalogColumn]


class IntentResolutionSignal(TypedDict, total=False):
    """
    Sinal normalizado para o resolvedor determinístico de intenção.

    A intenção é obtida de canonical_value. O padrão bruto vem de
    user_term e os parâmetros de resolução são obtidos de
    sql_filter_hint.resolver.
    """

    intent_name: str
    raw_pattern: str
    normalized_pattern: str
    match_mode: str
    polarity: str
    score: float
    priority: float | None
    entity_type: str | None
    target_table: str | None
    target_column: str | None


class IntentResolutionContext(TypedDict, total=False):
    """
    Configuração e sinais derivados para resolução de intenção.
    """

    config: dict[str, Any]
    signals: list[IntentResolutionSignal]


class ContextSnapshot(TypedDict, total=False):
    """
    Snapshot imutável do contexto usado em uma execução.

    Os campos canônicos representam a arquitetura-alvo documentada em
    docs/migration/context-contract.md.

    Os campos legados permanecem temporariamente para manter a baseline
    funcional enquanto normalizador, validador e load_context são
    migrados em incrementos separados.
    """

    # Identificação canônica
    version: str
    source: str
    fingerprint: str

    # Contagens e coleções canônicas
    counts: ContextCounts
    rules: list[AgentRule]
    entities: list[EntityAlias]
    dre_mappings: list[DreMapping]
    query_patterns: list[QueryPattern]
    table_catalog: list[TableCatalogEntry]

    # Projeções derivadas
    allowed_schemas: list[str]
    component_configs: dict[str, dict[str, Any]]
    intent_resolution: IntentResolutionContext

    # Compatibilidade temporária com a baseline existente
    versions: ContextVersions
    tables: list[CatalogTable]
    aliases: dict[str, str]
    sql_patterns: list[dict[str, Any]]

from typing import Any, Literal, TypedDict


IntentMatchMode = Literal[
    "exact",
    "contains",
    "starts_with",
    "ends_with",
    "all_tokens",
    "any_token",
    "regex",
]

IntentSignalPolarity = Literal[
    "positive",
    "negative",
]

IntentCatalogRuleEffect = Literal[
    "positive_score",
    "negative_score",
    "require",
    "exclude",
]


class FilterBindingDefinition(TypedDict):
    """Binding fisico versionado de uma obrigacao semantica de filtro."""

    binding_ref: str
    filter_concept: str
    required: bool
    scope: Literal["row", "where"]
    target_table: str
    target_column: str
    operator: str
    value: Any
    join_path: list[Any]


class FilterBindingBusinessRule(TypedDict):
    """Envelope canonico do binding mantido na entidade semantica."""

    filter_binding: FilterBindingDefinition


class FilterConceptEntity(TypedDict, total=False):
    """Alias versionado que associa evidencia textual a um conceito."""

    entity_type: Literal["filter_concept"]
    user_term: str
    canonical_value: str
    priority: int


class FilterBindingEntity(TypedDict, total=False):
    """Entidade versionada que separa o binding fisico do conceito."""

    entity_type: Literal["filter_binding"]
    canonical_value: str
    business_rule: FilterBindingBusinessRule
    priority: int


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


class IntentTokenFallbackConfig(TypedDict, total=False):
    """
    Configuração genérica do fallback por cobertura de tokens.

    Os valores são carregados do contexto versionado. O Python não
    define termos de negócio, stop words ou limiares escondidos.
    """

    enabled: bool
    apply_to_polarities: list[IntentSignalPolarity]
    apply_to_match_modes: list[IntentMatchMode]
    ignored_tokens: list[str]
    minimum_pattern_tokens: int
    minimum_matched_tokens: int
    minimum_pattern_coverage: float
    maximum_unmatched_pattern_tokens: int
    allow_prefix_equivalence: bool
    minimum_prefix_length: int
    minimum_prefix_ratio: float


class IntentResolverConfig(TypedDict, total=False):
    """
    Configuração operacional do resolvedor determinístico de intenção.
    """

    component: str
    minimum_score: float
    ambiguity_margin: float
    applied_confidence: float
    fallback_to_previous_intent: bool
    token_fallback: IntentTokenFallbackConfig | None


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
    match_mode: IntentMatchMode
    polarity: IntentSignalPolarity
    score: float
    priority: float | None
    entity_type: str | None
    target_table: str | None
    target_column: str | None


class IntentCatalogConcept(TypedDict, total=False):
    """
    Conceito semântico configurável usado por uma regra composta.

    terms representa alternativas semânticas do mesmo conceito, e não
    perguntas completas ou frases literais de benchmark.
    """

    concept_name: str
    terms: list[str]
    normalized_terms: list[str]
    match_mode: IntentMatchMode
    minimum_term_matches: int


class IntentCatalogRule(TypedDict, total=False):
    """
    Regra composta e configurável de uma intenção.

    minimum_concept_matches permite expressar combinações determinísticas
    sem nomes de intenções, termos de negócio ou limiares no Python.
    """

    rule_name: str
    effect: IntentCatalogRuleEffect
    concepts: list[IntentCatalogConcept]
    minimum_concept_matches: int
    score: float | None
    priority: float | None


class IntentCatalogEntry(TypedDict, total=False):
    """
    Definição semântica derivada de uma entidade intent_definition.

    A entrada aponta para uma intenção já existente em query_patterns.
    """

    intent_name: str
    definition_name: str
    semantic_description: str
    rules: list[IntentCatalogRule]
    priority: float | None


class IntentResolutionContext(TypedDict, total=False):
    """
    Configuração, sinais e catálogo derivados para resolução de intenção.
    """

    config: IntentResolverConfig
    signals: list[IntentResolutionSignal]
    intent_catalog: list[IntentCatalogEntry]
    semantic_defaults: dict[str, Any]


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
    entities: list[EntityAlias | FilterConceptEntity | FilterBindingEntity]
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

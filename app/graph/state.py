from typing import Any, Literal, TypedDict

from app.domain.intent_resolver import (
    IntentResolutionResult,
)


class UserContext(TypedDict, total=False):
    """
    Identificação do usuário recebida do Next.js.

    O LangGraph não autentica o usuário.
    Ele recebe um contexto já validado pelo backend.
    """

    id: str
    email: str
    profile: str


class GenerateOptions(TypedDict, total=False):
    """
    Opções controladas da execução.
    """

    use_cache: bool
    max_repair_attempts: int
    shadow_mode: bool


class AgentError(TypedDict, total=False):
    """
    Formato comum para erros de qualquer estágio.
    """

    code: str
    message: str
    source: str
    stage: str
    repairable: bool
    details: dict[str, Any]


class GateResult(TypedDict, total=False):
    """
    Resultado comum dos gates de validação.
    """

    status: Literal[
        "not_run",
        "approved",
        "rejected",
        "error",
    ]

    errors: list[AgentError]
    warnings: list[str]
    duration_ms: int
    validator_version: str


class RepairRecord(TypedDict, total=False):
    """
    Registro de uma tentativa de reparo.
    """

    attempt: int
    failed_stage: str

    sql_before: str
    sql_after: str

    errors: list[AgentError]


class GraphState(TypedDict, total=False):
    """
    Estado compartilhado pelo grafo do Agente SQL Financeiro.

    Os nodes devem retornar somente os campos que modificaram.
    """

    # Identificação da execução
    request_id: str
    run_id: str

    # Entrada original
    question: str
    normalized_question: str
    user: UserContext
    options: GenerateOptions

    # Contexto carregado do banco
    context: dict[str, Any]
    context_version: str

    # Entendimento e planejamento
    intent: str | None
    intent_confidence: float | None
    intent_resolution_result: IntentResolutionResult
    query_plan: dict[str, Any]

    # SQL
    generated_sql: str
    current_sql: str
    preflight_sql: str
    sql_fingerprint: str

    # Controle de tentativas
    repair_attempts: int
    max_repair_attempts: int
    repair_history: list[RepairRecord]

    # Resultados dos gates
    security_result: GateResult
    contract_result: GateResult
    engine_preflight_result: GateResult

    # Resultado geral
    errors: list[AgentError]
    warnings: list[str]

    current_stage: str

    final_status: Literal[
        "processing",
        "approved",
        "rejected",
        "invalid_request",
        "infrastructure_error",
    ]

    failure_stage: str

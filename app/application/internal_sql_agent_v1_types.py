from __future__ import annotations

from typing import Any, Literal, TypedDict


INTERNAL_SQL_AGENT_CONTRACT_VERSION = "1"

InternalSqlAgentStatus = Literal[
    "success",
    "rejected",
    "infrastructure_error",
]


class InternalSqlAgentPrincipal(TypedDict, total=False):
    id: str
    email: str
    profile: str
    organization_id: str


class InternalSqlAgentError(TypedDict, total=False):
    code: str
    stage: str
    message: str
    retryable: bool


class InternalSqlAgentGateSummary(TypedDict, total=False):
    status: str
    code: str | None
    repairable: bool | None
    executed: bool | None


class InternalLlmSelection(TypedDict):
    provider_key: str
    model_key: str
    config_version: str


class GenerateSqlV1Request(TypedDict, total=False):
    contract_version: str
    agent_run_id: str
    question: str
    principal: InternalSqlAgentPrincipal
    llm_selection: InternalLlmSelection
    correlation_metadata: dict[str, str | int | bool | None]


class GenerateSqlV1Response(TypedDict, total=False):
    contract_version: str
    response_id: str
    agent_run_id: str
    run_id: str
    status: InternalSqlAgentStatus
    message: str
    sql: str | None
    intent: str | None
    plan_status: str | None
    gates: dict[str, InternalSqlAgentGateSummary]
    preflight: InternalSqlAgentGateSummary
    repair_attempts: int
    errors: list[InternalSqlAgentError]
    metadata: dict[str, Any]
    response_fingerprint: str


class ExecuteApprovedSqlShadowV1Request(TypedDict, total=False):
    contract_version: str
    agent_run_id: str
    approved_sql: str
    principal: InternalSqlAgentPrincipal
    correlation_metadata: dict[str, str | int | bool | None]


class ExecuteApprovedSqlShadowV1Response(TypedDict, total=False):
    contract_version: str
    response_id: str
    agent_run_id: str
    run_id: str
    status: InternalSqlAgentStatus
    message: str
    approved_sql_original: str | None
    validation: dict[str, InternalSqlAgentGateSummary]
    repaired_sql_proposal: str | None
    requires_reapproval: bool
    errors: list[InternalSqlAgentError]
    metadata: dict[str, Any]
    response_fingerprint: str

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Literal, TypedDict

from app.domain.planning import QueryPlan


SQL_GENERATION_CONTRACT_VERSION = (
    "v1.0.0-query-plan-sql-generation"
)
MAX_SQL_RESPONSE_LENGTH = 20000

SqlGenerationErrorCode = Literal[
    "SQL_GENERATION_PLAN_MISSING",
    "SQL_GENERATION_PLAN_INVALID",
    "SQL_GENERATION_REQUEST_INVALID",
    "SQL_GENERATION_PROVIDER_FAILED",
    "SQL_GENERATION_RESPONSE_EMPTY",
    "SQL_GENERATION_RESPONSE_INVALID",
    "SQL_GENERATION_MULTIPLE_STATEMENTS",
    "SQL_GENERATION_NON_READ_ONLY",
    "SQL_GENERATION_UNEXPECTED_ERROR",
]

SqlGenerationStatus = Literal[
    "generated",
    "rejected",
    "contract_error",
    "provider_error",
]


class SqlGenerationInstruction(TypedDict):
    name: str
    content: str


class SqlGenerationContext(TypedDict):
    context_version: str
    context_fingerprint: str
    planner_version: str
    intent_name: str
    normalized_question: str
    selected_pattern: dict[str, Any]
    applicable_rules: list[dict[str, Any]]
    authorized_tables: list[dict[str, Any]]
    allowed_schemas: list[str]
    catalog_columns: dict[str, list[dict[str, Any]]]
    authorized_joins: list[dict[str, Any]]
    operational_entities: list[dict[str, Any]]
    dre_mappings: list[dict[str, Any]]
    pattern_metadata: dict[str, Any]


class SqlGenerationRequest(TypedDict):
    contract_version: str
    generation_context: SqlGenerationContext
    instructions: list[SqlGenerationInstruction]
    output_constraints: list[str]


class SqlGenerationProviderResult(TypedDict, total=False):
    provider_name: str
    output_text: str
    raw_response: Any
    duration_ms: int


class SqlGenerationDiagnostic(TypedDict):
    generator_contract_version: str
    provider_name: str
    request_fingerprint: str
    response_fingerprint: str | None
    request_size: int
    response_size: int
    generation_applied: bool
    reason: str
    duration_ms: int | None
    attempt: int
    plan_fields_used: list[str]
    structural_validations: list[str]


class SqlGenerationError(TypedDict):
    code: SqlGenerationErrorCode
    message: str
    details: dict[str, Any]


class SqlGenerationResult(TypedDict):
    status: SqlGenerationStatus
    sql: str | None
    diagnostic: SqlGenerationDiagnostic
    error: SqlGenerationError | None
    provider_result: SqlGenerationProviderResult | None


class SqlGenerationInputError(ValueError):
    """
    Indica plano ou requisicao fora do contrato minimo esperado.
    """


class SqlGenerationValidationError(ValueError):
    """
    Indica resposta estruturalmente inutilizavel para esta fase.
    """

    def __init__(
        self,
        code: SqlGenerationErrorCode,
        message: str,
        *,
        reason: str,
    ) -> None:
        self.code = code
        self.message = message
        self.reason = reason
        super().__init__(message)


class SqlGenerationProviderError(RuntimeError):
    """
    Indica falha conhecida do adapter de geracao SQL.
    """


_PLAN_FIELDS_USED = [
    "planner_version",
    "context_version",
    "context_fingerprint",
    "intent_name",
    "normalized_question",
    "selected_pattern",
    "planning_context.rules",
    "planning_context.required_tables",
    "planning_context.relevant_columns",
    "planning_context.authorized_joins",
    "planning_context.relevant_entities",
    "planning_context.relevant_dre_mappings",
    "sql_pattern_metadata",
]

_OUTPUT_CONSTRAINTS = [
    "Retorne exatamente uma instrucao SQL de leitura.",
    "Nao use Markdown ou bloco fenced.",
    "Nao inclua explicacoes antes ou depois da SQL.",
    "Nao inclua mais de uma consulta.",
    "Nao use comandos de escrita ou DDL.",
    "Use apenas schemas, tabelas, colunas e joins autorizados.",
    "Nao invente tabelas, colunas, filtros ou regras.",
    "Nao aplique LIMIT automatico quando nao configurado.",
]

_STRUCTURAL_VALIDATIONS = [
    "text_response",
    "non_empty",
    "no_markdown_fence",
    "control_characters",
    "maximum_length",
    "single_statement",
    "read_only_statement",
    "no_disallowed_commands_outside_literals",
]

_FORBIDDEN_COMMANDS = {
    "insert",
    "update",
    "delete",
    "drop",
    "alter",
    "truncate",
    "create",
    "grant",
    "revoke",
    "copy",
    "call",
    "do",
    "merge",
}


def build_sql_generation_request(
    query_plan: QueryPlan,
) -> SqlGenerationRequest:
    """
    Constroi uma requisicao deterministica usando somente o QueryPlan.
    """

    if not isinstance(query_plan, Mapping):
        raise SqlGenerationInputError(
            "query_plan deve ser um objeto."
        )

    planning_context = query_plan.get("planning_context")
    if not isinstance(planning_context, Mapping):
        raise SqlGenerationInputError(
            "query_plan.planning_context esta ausente ou invalido."
        )

    selected_pattern = query_plan.get("selected_pattern")
    if not isinstance(selected_pattern, Mapping):
        raise SqlGenerationInputError(
            "query_plan.selected_pattern esta ausente ou invalido."
        )

    request: SqlGenerationRequest = {
        "contract_version": SQL_GENERATION_CONTRACT_VERSION,
        "generation_context": {
            "context_version": _required_text(
                query_plan,
                "context_version",
            ),
            "context_fingerprint": _required_text(
                query_plan,
                "context_fingerprint",
            ),
            "planner_version": _required_text(
                query_plan,
                "planner_version",
            ),
            "intent_name": _required_text(
                query_plan,
                "intent_name",
            ),
            "normalized_question": _required_text(
                query_plan,
                "normalized_question",
            ),
            "selected_pattern": _stable_mapping_copy(
                selected_pattern,
            ),
            "applicable_rules": _sorted_mappings(
                planning_context.get("rules", []),
                text_fields=("rule_group", "rule_name"),
                priority_field="priority",
            ),
            "authorized_tables": _sorted_mappings(
                planning_context.get("required_tables", []),
                text_fields=("schema_name", "table_name"),
                priority_field="priority",
            ),
            "allowed_schemas": _sorted_text_list(
                planning_context.get("allowed_schemas", [])
            ),
            "catalog_columns": _stable_columns(
                planning_context.get("relevant_columns", {})
            ),
            "authorized_joins": _sorted_mappings(
                planning_context.get("authorized_joins", []),
                text_fields=("source_table",),
            ),
            "operational_entities": _sorted_mappings(
                planning_context.get("relevant_entities", []),
                text_fields=("entity_type", "user_term"),
                priority_field="priority",
            ),
            "dre_mappings": _sorted_mappings(
                planning_context.get("relevant_dre_mappings", []),
                text_fields=("dre_code", "nivel_1_bi"),
                priority_field="sort_order",
            ),
            "pattern_metadata": {
                "pattern_name": selected_pattern.get(
                    "pattern_name",
                    "",
                ),
                "notes": selected_pattern.get("notes"),
                "sql_pattern_metadata": query_plan.get(
                    "sql_pattern_metadata",
                    "",
                ),
            },
        },
        "instructions": [
            {
                "name": "output_format",
                "content": (
                    "Retorne somente SQL de leitura como texto puro."
                ),
            },
            {
                "name": "authorized_context",
                "content": (
                    "Use exclusivamente os objetos e regras presentes "
                    "na requisicao."
                ),
            },
        ],
        "output_constraints": list(_OUTPUT_CONSTRAINTS),
    }

    _validate_request(request)
    return deepcopy(request)


def request_fingerprint(
    request: SqlGenerationRequest,
) -> str:
    return _stable_fingerprint(request)


def response_fingerprint(
    value: str,
) -> str:
    return _stable_fingerprint({"response": value})


def request_size(
    request: SqlGenerationRequest,
) -> int:
    return len(_stable_json(request))


def validate_sql_generation_response(
    provider_result: SqlGenerationProviderResult,
) -> str:
    """
    Extrai e valida SQL de leitura sem tentar atuar como Security Gate.
    """

    if not isinstance(provider_result, Mapping):
        raise SqlGenerationValidationError(
            "SQL_GENERATION_RESPONSE_INVALID",
            "A resposta do provedor deve ser um objeto.",
            reason="provider_result_not_mapping",
        )

    output = provider_result.get("output_text")
    if not isinstance(output, str):
        raise SqlGenerationValidationError(
            "SQL_GENERATION_RESPONSE_INVALID",
            "A resposta textual do provedor e invalida.",
            reason="non_text_response",
        )

    if _has_forbidden_control_character(output):
        raise SqlGenerationValidationError(
            "SQL_GENERATION_RESPONSE_INVALID",
            "A resposta contem caracteres de controle nao permitidos.",
            reason="control_character",
        )

    if len(output) > MAX_SQL_RESPONSE_LENGTH:
        raise SqlGenerationValidationError(
            "SQL_GENERATION_RESPONSE_INVALID",
            "A resposta SQL excede o tamanho maximo permitido.",
            reason="response_too_large",
        )

    stripped = output.strip()
    if not stripped or stripped == ";":
        raise SqlGenerationValidationError(
            "SQL_GENERATION_RESPONSE_EMPTY",
            "A resposta SQL nao pode estar vazia.",
            reason="empty_response",
        )

    if "```" in stripped:
        raise SqlGenerationValidationError(
            "SQL_GENERATION_RESPONSE_INVALID",
            "A resposta SQL nao pode conter bloco Markdown.",
            reason="markdown_fence",
        )

    normalized = _remove_single_final_semicolon(stripped)
    if not normalized:
        raise SqlGenerationValidationError(
            "SQL_GENERATION_RESPONSE_EMPTY",
            "A resposta SQL nao pode estar vazia.",
            reason="empty_after_normalization",
        )

    semicolon_positions = _semicolon_positions_outside_literals(stripped)
    if semicolon_positions:
        if len(semicolon_positions) > 1 or semicolon_positions[0] != (
            len(stripped) - 1
        ):
            raise SqlGenerationValidationError(
                "SQL_GENERATION_MULTIPLE_STATEMENTS",
                "A resposta deve conter exatamente uma instrucao SQL.",
                reason="multiple_statements",
            )

    first_keyword = _first_keyword(normalized)
    if first_keyword not in {"select", "with"}:
        code: SqlGenerationErrorCode = (
            "SQL_GENERATION_NON_READ_ONLY"
            if first_keyword in _FORBIDDEN_COMMANDS
            else "SQL_GENERATION_RESPONSE_INVALID"
        )
        raise SqlGenerationValidationError(
            code,
            "A resposta deve iniciar com SELECT ou WITH.",
            reason="not_read_only_start",
        )

    without_literals = _replace_literals_with_space(normalized)
    forbidden = _forbidden_commands_in_text(without_literals)
    if forbidden:
        raise SqlGenerationValidationError(
            "SQL_GENERATION_NON_READ_ONLY",
            "A resposta contem comando nao permitido.",
            reason=f"forbidden_command:{forbidden[0]}",
        )

    return normalized


def create_success_result(
    *,
    sql: str,
    request: SqlGenerationRequest,
    provider_result: SqlGenerationProviderResult,
    attempt: int,
) -> SqlGenerationResult:
    output_text = provider_result.get("output_text", "")
    return {
        "status": "generated",
        "sql": sql,
        "diagnostic": _diagnostic(
            request=request,
            provider_result=provider_result,
            response_text=output_text,
            generation_applied=True,
            reason="sql_generation_applied",
            attempt=attempt,
        ),
        "error": None,
        "provider_result": _provider_summary(provider_result),
    }


def create_error_result(
    *,
    status: SqlGenerationStatus,
    code: SqlGenerationErrorCode,
    message: str,
    request: SqlGenerationRequest | None,
    provider_result: SqlGenerationProviderResult | None,
    reason: str,
    attempt: int,
    details: dict[str, Any] | None = None,
) -> SqlGenerationResult:
    return {
        "status": status,
        "sql": None,
        "diagnostic": _diagnostic(
            request=request,
            provider_result=provider_result,
            response_text=(
                provider_result.get("output_text")
                if isinstance(provider_result, Mapping)
                and isinstance(provider_result.get("output_text"), str)
                else None
            ),
            generation_applied=False,
            reason=reason,
            attempt=attempt,
        ),
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
        "provider_result": (
            _provider_summary(provider_result)
            if provider_result is not None
            else None
        ),
    }


def _diagnostic(
    *,
    request: SqlGenerationRequest | None,
    provider_result: SqlGenerationProviderResult | None,
    response_text: str | None,
    generation_applied: bool,
    reason: str,
    attempt: int,
) -> SqlGenerationDiagnostic:
    provider_name = (
        str(provider_result.get("provider_name", "unknown"))
        if isinstance(provider_result, Mapping)
        else "unknown"
    )
    duration = (
        provider_result.get("duration_ms")
        if isinstance(provider_result, Mapping)
        else None
    )
    return {
        "generator_contract_version": (
            SQL_GENERATION_CONTRACT_VERSION
        ),
        "provider_name": provider_name,
        "request_fingerprint": (
            request_fingerprint(request)
            if request is not None
            else ""
        ),
        "response_fingerprint": (
            response_fingerprint(response_text)
            if isinstance(response_text, str)
            else None
        ),
        "request_size": request_size(request) if request else 0,
        "response_size": (
            len(response_text) if isinstance(response_text, str) else 0
        ),
        "generation_applied": generation_applied,
        "reason": reason,
        "duration_ms": (
            int(duration) if isinstance(duration, int) else None
        ),
        "attempt": attempt,
        "plan_fields_used": list(_PLAN_FIELDS_USED),
        "structural_validations": list(_STRUCTURAL_VALIDATIONS),
    }


def _provider_summary(
    provider_result: SqlGenerationProviderResult,
) -> SqlGenerationProviderResult:
    summary: SqlGenerationProviderResult = {
        "provider_name": str(provider_result.get("provider_name", "")),
        "output_text": "",
    }
    if "duration_ms" in provider_result:
        summary["duration_ms"] = provider_result["duration_ms"]
    if "raw_response" in provider_result:
        summary["raw_response"] = {
            "present": provider_result.get("raw_response") is not None
        }
    return summary


def _validate_request(
    request: SqlGenerationRequest,
) -> None:
    context = request.get("generation_context")
    if not isinstance(context, Mapping):
        raise SqlGenerationInputError(
            "generation_context e obrigatorio."
        )

    for field_name in (
        "context_version",
        "context_fingerprint",
        "planner_version",
        "intent_name",
        "normalized_question",
    ):
        _required_text(context, field_name)

    for field_name in (
        "applicable_rules",
        "authorized_tables",
        "allowed_schemas",
        "authorized_joins",
        "operational_entities",
        "dre_mappings",
    ):
        if not isinstance(context.get(field_name), list):
            raise SqlGenerationInputError(
                f"generation_context.{field_name} deve ser lista."
            )

    if not isinstance(context.get("catalog_columns"), Mapping):
        raise SqlGenerationInputError(
            "generation_context.catalog_columns deve ser objeto."
        )


def _required_text(
    value: Mapping[str, Any],
    field_name: str,
) -> str:
    field_value = value.get(field_name)
    if not isinstance(field_value, str) or not field_value.strip():
        raise SqlGenerationInputError(
            f"{field_name} deve ser texto nao vazio."
        )
    return field_value


def _sorted_mappings(
    values: Any,
    *,
    text_fields: tuple[str, ...],
    priority_field: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        raise SqlGenerationInputError(
            "colecao esperada como lista."
        )
    copied = [
        _stable_mapping_copy(value)
        for value in values
        if isinstance(value, Mapping)
    ]
    copied.sort(
        key=lambda item: (
            _priority_sort_value(item.get(priority_field))
            if priority_field
            else 0.0,
            *(
                str(item.get(field_name, "")).casefold()
                for field_name in text_fields
            ),
            _stable_json(item),
        )
    )
    return copied


def _sorted_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise SqlGenerationInputError(
            "colecao de textos esperada como lista."
        )
    return sorted(
        [
            item
            for item in value
            if isinstance(item, str) and item.strip()
        ],
        key=str.casefold,
    )


def _stable_columns(value: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, Mapping):
        raise SqlGenerationInputError(
            "relevant_columns deve ser objeto."
        )
    output: dict[str, list[dict[str, Any]]] = {}
    for table_name in sorted(value, key=str.casefold):
        columns = value[table_name]
        if not isinstance(columns, list):
            raise SqlGenerationInputError(
                "cada entrada de relevant_columns deve ser lista."
            )
        output[str(table_name)] = _sorted_mappings(
            columns,
            text_fields=("name",),
        )
    return output


def _stable_mapping_copy(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        str(key): deepcopy(item)
        for key, item in sorted(
            value.items(),
            key=lambda pair: str(pair[0]).casefold(),
        )
    }


def _stable_fingerprint(value: Any) -> str:
    return hashlib.sha256(
        _stable_json(value).encode("utf-8")
    ).hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    )


def _priority_sort_value(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return float("inf")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("inf")


def _has_forbidden_control_character(value: str) -> bool:
    return any(
        ord(character) < 32 and character not in "\r\n\t"
        for character in value
    )


def _remove_single_final_semicolon(value: str) -> str:
    semicolons = _semicolon_positions_outside_literals(value)
    if semicolons == [len(value) - 1]:
        return value[:-1].strip()
    return value


def _semicolon_positions_outside_literals(value: str) -> list[int]:
    positions: list[int] = []
    in_single = False
    in_double = False
    index = 0
    while index < len(value):
        character = value[index]
        next_character = (
            value[index + 1] if index + 1 < len(value) else ""
        )
        if in_single:
            if character == "'" and next_character == "'":
                index += 2
                continue
            if character == "'":
                in_single = False
            index += 1
            continue
        if in_double:
            if character == '"' and next_character == '"':
                index += 2
                continue
            if character == '"':
                in_double = False
            index += 1
            continue
        if character == "'":
            in_single = True
        elif character == '"':
            in_double = True
        elif character == ";":
            positions.append(index)
        index += 1
    return positions


def _replace_literals_with_space(value: str) -> str:
    output: list[str] = []
    in_single = False
    in_double = False
    index = 0
    while index < len(value):
        character = value[index]
        next_character = (
            value[index + 1] if index + 1 < len(value) else ""
        )
        if in_single:
            output.append(" ")
            if character == "'" and next_character == "'":
                output.append(" ")
                index += 2
                continue
            if character == "'":
                in_single = False
            index += 1
            continue
        if in_double:
            output.append(" ")
            if character == '"' and next_character == '"':
                output.append(" ")
                index += 2
                continue
            if character == '"':
                in_double = False
            index += 1
            continue
        if character == "'":
            in_single = True
            output.append(" ")
        elif character == '"':
            in_double = True
            output.append(" ")
        else:
            output.append(character)
        index += 1
    return "".join(output)


def _first_keyword(value: str) -> str:
    stripped = value.lstrip()
    keyword: list[str] = []
    for character in stripped:
        if character.isalpha():
            keyword.append(character)
            continue
        break
    return "".join(keyword).casefold()


def _forbidden_commands_in_text(value: str) -> list[str]:
    tokens = []
    token: list[str] = []
    for character in value.casefold():
        if character.isalnum() or character == "_":
            token.append(character)
            continue
        if token:
            tokens.append("".join(token))
            token = []
    if token:
        tokens.append("".join(token))
    return [
        token
        for token in tokens
        if token in _FORBIDDEN_COMMANDS
    ]

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


class GroupingDimension(TypedDict):
    canonical_value: str
    target_table: str
    target_column: str
    grouping_requested: bool
    source: str


class AnalyticalOperation(TypedDict):
    operation_type: str
    canonical_value: str
    direction: str
    requested_limit: int | None
    metric_ref: str
    binding_cardinality: dict[str, Any]
    detection_source: str
    mapping_source: str


class PlannedMetric(TypedDict, total=False):
    metric_ref: str
    metric_concept: str
    target_table: str
    target_column: str
    aggregate: None
    detection_source: str
    mapping_source: str
    binding_ref: str
    binding_conditions: dict[str, list[str]]
    binding_source: str


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
    grouping_dimensions: list[GroupingDimension]
    analytical_operations: list[AnalyticalOperation]
    planned_metrics: list[PlannedMetric]
    pattern_metadata: dict[str, Any]


class SqlGenerationRequest(TypedDict):
    contract_version: str
    generation_context: SqlGenerationContext
    instructions: list[SqlGenerationInstruction]
    output_constraints: list[str]


class SqlGenerationProviderResult(TypedDict, total=False):
    provider_name: str
    provider_model: str
    output_text: str
    raw_response: Any
    duration_ms: int
    token_usage: dict[str, int | str | None]


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
    "planning_context.detected_dimensions",
    "planning_context.analytical_operations",
    "planning_context.planned_metrics",
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

    grouping_dimensions = _grouping_dimensions(
        planning_context.get("detected_dimensions", [])
    )
    planned_metrics = _planned_metrics(
        planning_context.get("planned_metrics", [])
    )
    analytical_operations = _analytical_operations(
        planning_context.get("analytical_operations", []),
        valid_metric_refs={
            metric["metric_ref"]
            for metric in planned_metrics
            if metric.get("metric_ref")
        },
    )
    instructions: list[SqlGenerationInstruction] = [
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
    ]
    if any(
        operation.get("operation_type") == "ranking"
        and operation.get("metric_ref")
        for operation in analytical_operations
    ):
        instructions.append(
            {
                "name": "analytical_operations",
                "content": (
                    "Quando analytical_operations incluir ranking com "
                    "metric_ref, gere ORDER BY na direcao solicitada para "
                    "a planned_metric referenciada por metric_ref. Use "
                    "DESC para descending e ASC para ascending. Quando a "
                    "planned_metric tiver aggregate null, nao invente a "
                    "agregacao a partir do contrato de ranking. Nao "
                    "adicione LIMIT quando requested_limit for null."
                ),
            }
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
            "grouping_dimensions": grouping_dimensions,
            "analytical_operations": analytical_operations,
            "planned_metrics": planned_metrics,
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
        "instructions": instructions,
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
    if isinstance(provider_result.get("provider_model"), str):
        summary["provider_model"] = str(provider_result["provider_model"])
    if "duration_ms" in provider_result:
        summary["duration_ms"] = provider_result["duration_ms"]
    token_usage = provider_result.get("token_usage")
    if isinstance(token_usage, Mapping):
        summary["token_usage"] = _token_usage_summary(token_usage)
    if "raw_response" in provider_result:
        summary["raw_response"] = {
            "present": provider_result.get("raw_response") is not None
        }
    return summary


def _token_usage_summary(
    token_usage: Mapping[str, Any],
) -> dict[str, int | str | None]:
    return {
        "provider": _optional_public_text(token_usage.get("provider")),
        "model": _optional_public_text(token_usage.get("model")),
        "prompt_tokens": _optional_non_negative_int(
            token_usage.get("prompt_tokens")
        ),
        "response_tokens": _optional_non_negative_int(
            token_usage.get("response_tokens")
        ),
        "total_tokens": _optional_non_negative_int(
            token_usage.get("total_tokens")
        ),
    }


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
        "grouping_dimensions",
        "analytical_operations",
        "planned_metrics",
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


def _grouping_dimensions(value: Any) -> list[GroupingDimension]:
    if not isinstance(value, list):
        raise SqlGenerationInputError(
            "detected_dimensions deve ser lista."
        )
    output: list[GroupingDimension] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        if item.get("grouping_requested") is not True:
            continue
        target_table = _optional_clean_text(item.get("target_table"))
        target_column = _optional_clean_text(item.get("target_column"))
        if not target_table or not target_column:
            continue
        output.append(
            {
                "canonical_value": _optional_clean_text(
                    item.get("canonical_value")
                ),
                "target_table": target_table,
                "target_column": target_column,
                "grouping_requested": True,
                "source": _optional_clean_text(item.get("source")),
            }
        )
    output.sort(
        key=lambda dimension: (
            dimension["canonical_value"].casefold(),
            dimension["target_table"].casefold(),
            dimension["target_column"].casefold(),
            dimension["source"].casefold(),
        )
    )
    return output


def _analytical_operations(
    value: Any,
    *,
    valid_metric_refs: set[str],
) -> list[AnalyticalOperation]:
    if not isinstance(value, list):
        raise SqlGenerationInputError(
            "analytical_operations deve ser lista."
        )
    output: list[AnalyticalOperation] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        operation_type = _optional_clean_text(item.get("operation_type"))
        direction = _optional_clean_text(item.get("direction"))
        if operation_type != "ranking":
            continue
        if direction not in {"ascending", "descending"}:
            continue
        requested_limit = item.get("requested_limit")
        if requested_limit is not None and (
            isinstance(requested_limit, bool)
            or not isinstance(requested_limit, int)
            or requested_limit <= 0
        ):
            continue
        canonical_value = _optional_clean_text(
            item.get("canonical_value")
        )
        if canonical_value != operation_type:
            continue
        metric_ref = _optional_clean_text(item.get("metric_ref"))
        if metric_ref and metric_ref not in valid_metric_refs:
            continue
        output.append(
            {
                "operation_type": operation_type,
                "canonical_value": canonical_value,
                "direction": direction,
                "requested_limit": requested_limit,
                "metric_ref": metric_ref,
                "binding_cardinality": _binding_cardinality(
                    item.get("binding_cardinality")
                ),
                "detection_source": _optional_clean_text(
                    item.get("detection_source")
                ),
                "mapping_source": _optional_clean_text(
                    item.get("mapping_source")
                ),
            }
        )
    output.sort(
        key=lambda operation: (
            operation["operation_type"],
            operation["direction"],
            operation["canonical_value"].casefold(),
            operation["metric_ref"].casefold(),
            operation["requested_limit"] or 0,
        )
    )
    return output


def _planned_metrics(value: Any) -> list[PlannedMetric]:
    if not isinstance(value, list):
        raise SqlGenerationInputError(
            "planned_metrics deve ser lista."
        )
    output: list[PlannedMetric] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        metric_ref = _optional_clean_text(item.get("metric_ref"))
        metric_concept = _optional_clean_text(item.get("metric_concept"))
        target_table = _optional_clean_text(item.get("target_table"))
        target_column = _optional_clean_text(item.get("target_column"))
        if not (
            metric_ref
            and metric_concept
            and target_table
            and target_column
        ):
            continue
        if item.get("aggregate") is not None:
            continue
        output.append(
            {
                "metric_ref": metric_ref,
                "metric_concept": metric_concept,
                "target_table": target_table,
                "target_column": target_column,
                "aggregate": None,
                "detection_source": _optional_clean_text(
                    item.get("detection_source")
                ),
                "mapping_source": _optional_clean_text(
                    item.get("mapping_source")
                ),
                **_planned_metric_binding_fields(item),
            }
        )
    output.sort(
        key=lambda metric: (
            metric["metric_ref"].casefold(),
            metric["metric_concept"].casefold(),
            metric["target_table"].casefold(),
            metric["target_column"].casefold(),
        )
    )
    return output


def _binding_cardinality(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {
            "mode": "single",
            "minimum": 1,
            "maximum": 1,
            "same_metric_concept": True,
            "distinct_bindings": True,
        }
    return {
        "mode": _optional_clean_text(value.get("mode")) or "single",
        "minimum": value.get("minimum", 1),
        "maximum": value.get("maximum", 1),
        "same_metric_concept": value.get("same_metric_concept", True),
        "distinct_bindings": value.get("distinct_bindings", True),
    }


def _planned_metric_binding_fields(
    item: Mapping[str, Any],
) -> dict[str, Any]:
    if item.get("mapping_source") != "metric_binding":
        return {}
    binding_ref = _optional_clean_text(item.get("binding_ref"))
    conditions = item.get("binding_conditions")
    binding_source = _optional_clean_text(item.get("binding_source"))
    if not binding_ref or not isinstance(conditions, Mapping):
        return {}
    return {
        "binding_ref": binding_ref,
        "binding_conditions": {
            "when_present": _string_list(conditions.get("when_present")),
            "when_absent": _string_list(conditions.get("when_absent")),
        },
        "binding_source": binding_source,
    }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [
        item.strip()
        for item in value
        if isinstance(item, str) and item.strip()
    ]


def _optional_clean_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


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


def _optional_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _optional_public_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    lowered = text.casefold()
    if any(
        marker in lowered
        for marker in ("bearer", "apikey", "api_key", "token", "secret")
    ):
        return None
    return text[:128]


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

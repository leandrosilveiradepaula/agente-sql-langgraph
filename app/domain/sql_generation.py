from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Literal, TypedDict

from app.domain.planning import QueryPlan


SQL_GENERATION_CONTRACT_VERSION = (
    "v1.1.0-planned-filter-generation"
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


class AnalyticalOperation(TypedDict, total=False):
    operation_type: str
    canonical_value: str
    direction: str
    requested_limit: int | None
    metric_ref: str
    operand_metric_refs: list[str]
    output_behavior: str
    combination_strategy: str
    multiple_metric_sources: bool
    join_semantics: str
    combine_strategy: str
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


class PlannedFilter(TypedDict, total=False):
    filter_ref: str
    filter_concept: str
    binding_ref: str
    required: bool
    scope: str
    detection_source: str
    mapping_source: str
    matched_user_term: str
    provenance: dict[str, Any]


class FilterBinding(TypedDict):
    binding_ref: str
    filter_concept: str
    target_table: str
    target_column: str
    operator: str
    value: Any
    join_path: list[dict[str, Any]]
    required: bool
    scope: str


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
    planned_filters: list[PlannedFilter]
    filter_bindings: list[FilterBinding]
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
    "planning_context.planned_filters",
    "planning_context.resolved_filter_bindings",
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
    planned_filters = _planned_filters(
        planning_context.get("planned_filters", [])
    )
    filter_bindings = _filter_bindings(
        planning_context.get("resolved_filter_bindings", []),
        planned_filters=planned_filters,
    )
    analytical_operations = _analytical_operations(
        planning_context.get("analytical_operations", []),
        planned_metrics=planned_metrics,
        has_grouping_dimensions=bool(grouping_dimensions),
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
    if any(item.get("required") is True for item in planned_filters):
        instructions.append(
            {
                "name": "required_filters",
                "content": (
                    "Aplique todos os planned_filters com required=true no WHERE "
                    "usando exclusivamente o filter_binding correlacionado por "
                    "binding_ref. Nao infira tabela, coluna, operador ou valor a "
                    "partir de normalized_question e nao adicione filtros extras "
                    "deduzidos do texto."
                ),
            }
        )
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
    if any(
        operation.get("operation_type") == "comparison"
        for operation in analytical_operations
    ):
        instructions.append(
            {
                "name": "comparison_operations",
                "content": (
                    "Quando analytical_operations incluir comparison, gere "
                    "somente uma comparacao side_by_side entre os operands "
                    "referenciados por operand_metric_refs. Cada operand_ref "
                    "deve corresponder exatamente a uma planned_metric. Nao "
                    "calcule diferenca, percentual, razao, baseline ou "
                    "metrica derivada. Para multiple_metric_sources=true sem "
                    "grouping_dimensions, agregue cada operand em escopo/CTE "
                    "separado como resultado single-row e combine os operands "
                    "agregados com CROSS JOIN; e proibido join direto entre "
                    "source tables de metricas antes da agregacao. Para "
                    "multiple_metric_sources=true com grouping_dimensions, "
                    "agregue cada operand independentemente no mesmo grain "
                    "logico, preserve todas as dimensoes planejadas e combine "
                    "os operands agregados conforme join_semantics. "
                    "join_semantics "
                    "preserve_all_operand_categories exige preservacao "
                    "bilateral das categorias, compativel com FULL OUTER "
                    "JOIN entre operands agregados. join_semantics "
                    "common_operand_categories_only exige somente categorias "
                    "comuns, compativel com INNER JOIN entre operands "
                    "agregados."
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
            "planned_filters": planned_filters,
            "filter_bindings": filter_bindings,
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
        "planned_filters",
        "filter_bindings",
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
    planned_metrics: list[PlannedMetric],
    has_grouping_dimensions: bool,
) -> list[AnalyticalOperation]:
    if not isinstance(value, list):
        raise SqlGenerationInputError(
            "analytical_operations deve ser lista."
        )
    output: list[AnalyticalOperation] = []
    metrics_by_ref = _metrics_by_ref(planned_metrics)
    for item in value:
        if not isinstance(item, Mapping):
            continue
        operation_type = _optional_clean_text(item.get("operation_type"))
        operation: AnalyticalOperation | None = None
        if operation_type == "ranking":
            operation = _ranking_operation(item, metrics_by_ref)
        elif operation_type == "comparison":
            operation = _comparison_operation(
                item,
                metrics_by_ref,
                has_grouping_dimensions=has_grouping_dimensions,
            )
        if operation is not None:
            output.append(operation)
    output.sort(
        key=lambda operation: (
            operation["operation_type"],
            operation.get("direction", ""),
            operation.get("output_behavior", ""),
            operation.get("combination_strategy", ""),
            operation["canonical_value"].casefold(),
            operation.get("metric_ref", "").casefold(),
            ",".join(operation.get("operand_metric_refs", [])),
            operation.get("requested_limit") or 0,
        )
    )
    return output


def _ranking_operation(
    item: Mapping[str, Any],
    metrics_by_ref: Mapping[str, PlannedMetric],
) -> AnalyticalOperation | None:
    direction = _optional_clean_text(item.get("direction"))
    if direction not in {"ascending", "descending"}:
        return None
    requested_limit = item.get("requested_limit")
    if not _valid_requested_limit(requested_limit):
        return None
    canonical_value = _optional_clean_text(item.get("canonical_value"))
    if canonical_value != "ranking":
        return None
    metric_ref = _optional_clean_text(item.get("metric_ref"))
    if metric_ref and metric_ref not in metrics_by_ref:
        return None
    return {
        "operation_type": "ranking",
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
        "mapping_source": _optional_clean_text(item.get("mapping_source")),
    }


def _comparison_operation(
    item: Mapping[str, Any],
    metrics_by_ref: Mapping[str, PlannedMetric],
    *,
    has_grouping_dimensions: bool,
) -> AnalyticalOperation | None:
    canonical_value = _optional_clean_text(item.get("canonical_value"))
    if canonical_value != "comparison":
        return None
    if _optional_clean_text(item.get("output_behavior")) != "side_by_side":
        return None
    if (
        _optional_clean_text(item.get("combination_strategy"))
        != "aggregate_then_combine"
    ):
        return None
    operand_metric_refs = _operand_metric_refs(item.get("operand_metric_refs"))
    if not operand_metric_refs:
        return None
    if len(operand_metric_refs) != len(set(operand_metric_refs)):
        return None
    if any(ref not in metrics_by_ref for ref in operand_metric_refs):
        return None
    operand_metrics = [metrics_by_ref[ref] for ref in operand_metric_refs]
    metric_sources: list[str] = []
    for metric in operand_metrics:
        target_table = metric.get("target_table")
        if not isinstance(target_table, str) or not target_table.strip():
            return None
        metric_sources.append(target_table.strip())
    normalized_metric_sources = {
        source.casefold() for source in metric_sources
    }
    derived_multiple_metric_sources = len(normalized_metric_sources) > 1
    planned_multiple_metric_sources = item.get("multiple_metric_sources")
    if not isinstance(planned_multiple_metric_sources, bool):
        return None
    if planned_multiple_metric_sources != derived_multiple_metric_sources:
        return None
    join_semantics = _optional_clean_text(item.get("join_semantics"))
    if join_semantics and join_semantics not in {
        "preserve_all_operand_categories",
        "common_operand_categories_only",
    }:
        return None
    if derived_multiple_metric_sources:
        if has_grouping_dimensions and join_semantics not in {
            "preserve_all_operand_categories",
            "common_operand_categories_only",
        }:
            return None
    combine_strategy = ""
    if derived_multiple_metric_sources and not has_grouping_dimensions:
        combine_strategy = "cross_join"
    elif (
        derived_multiple_metric_sources
        and join_semantics == "preserve_all_operand_categories"
    ):
        combine_strategy = "full_outer_join"
    elif (
        derived_multiple_metric_sources
        and join_semantics == "common_operand_categories_only"
    ):
        combine_strategy = "inner_join"
    elif has_grouping_dimensions and derived_multiple_metric_sources:
        return None
    return {
        "operation_type": "comparison",
        "canonical_value": canonical_value,
        "output_behavior": "side_by_side",
        "combination_strategy": "aggregate_then_combine",
        "operand_metric_refs": operand_metric_refs,
        "multiple_metric_sources": derived_multiple_metric_sources,
        "join_semantics": join_semantics,
        "combine_strategy": combine_strategy,
        "binding_cardinality": _binding_cardinality(
            item.get("binding_cardinality")
        ),
        "detection_source": _optional_clean_text(
            item.get("detection_source")
        ),
        "mapping_source": _optional_clean_text(item.get("mapping_source")),
    }


def _valid_requested_limit(value: Any) -> bool:
    return value is None or (
        not isinstance(value, bool)
        and isinstance(value, int)
        and value > 0
    )


def _operand_metric_refs(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    refs: list[str] = []
    for item in value:
        ref = _optional_clean_text(item)
        if not ref:
            return []
        refs.append(ref)
    return refs


def _metrics_by_ref(
    planned_metrics: list[PlannedMetric],
) -> dict[str, PlannedMetric]:
    output: dict[str, PlannedMetric] = {}
    duplicates: set[str] = set()
    for metric in planned_metrics:
        metric_ref = metric.get("metric_ref")
        if not isinstance(metric_ref, str) or not metric_ref.strip():
            continue
        if metric_ref in output:
            duplicates.add(metric_ref)
            continue
        output[metric_ref] = metric
    for metric_ref in duplicates:
        output.pop(metric_ref, None)
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


def _planned_filters(value: Any) -> list[PlannedFilter]:
    if not isinstance(value, list):
        raise SqlGenerationInputError("planned_filters deve ser lista.")
    physical_fields = {
        "target_table", "target_column", "operator", "value", "join_path"
    }
    output: list[PlannedFilter] = []
    seen_refs: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            raise SqlGenerationInputError("planned_filters contem item invalido.")
        if physical_fields & set(item):
            raise SqlGenerationInputError(
                "planned_filter nao pode conter detalhes fisicos."
            )
        filter_ref = _optional_clean_text(item.get("filter_ref"))
        filter_concept = _optional_clean_text(item.get("filter_concept"))
        binding_ref = _optional_clean_text(item.get("binding_ref"))
        scope = _optional_clean_text(item.get("scope"))
        required = item.get("required")
        if not (filter_ref and filter_concept and binding_ref and scope):
            raise SqlGenerationInputError("planned_filter esta incompleto.")
        if not isinstance(required, bool):
            raise SqlGenerationInputError("planned_filter.required deve ser booleano.")
        key = binding_ref.casefold()
        if key in seen_refs:
            raise SqlGenerationInputError("planned_filter.binding_ref duplicado.")
        seen_refs.add(key)
        output.append(
            {
                "filter_ref": filter_ref,
                "filter_concept": filter_concept,
                "binding_ref": binding_ref,
                "required": required,
                "scope": scope,
                "detection_source": _optional_clean_text(item.get("detection_source")),
                "mapping_source": _optional_clean_text(item.get("mapping_source")),
                "matched_user_term": _optional_clean_text(item.get("matched_user_term")),
                "provenance": _stable_mapping_copy(item.get("provenance", {}))
                if isinstance(item.get("provenance", {}), Mapping)
                else {},
            }
        )
    output.sort(key=lambda item: (item["binding_ref"].casefold(), item["filter_ref"].casefold()))
    return output


def _filter_bindings(
    value: Any,
    *,
    planned_filters: list[PlannedFilter],
) -> list[FilterBinding]:
    if not isinstance(value, list):
        raise SqlGenerationInputError("resolved_filter_bindings deve ser lista.")
    referenced = {item["binding_ref"].casefold(): item for item in planned_filters}
    grouped: dict[str, list[FilterBinding]] = {key: [] for key in referenced}
    for item in value:
        if not isinstance(item, Mapping):
            raise SqlGenerationInputError("resolved_filter_bindings contem item invalido.")
        binding_ref = _optional_clean_text(item.get("binding_ref"))
        if not binding_ref or binding_ref.casefold() not in referenced:
            continue
        target_table = _optional_clean_text(item.get("target_table"))
        target_column = _optional_clean_text(item.get("target_column"))
        operator = _optional_clean_text(item.get("operator"))
        filter_concept = _optional_clean_text(item.get("filter_concept"))
        scope = _optional_clean_text(item.get("scope"))
        required = item.get("required")
        raw_value = item.get("value")
        join_path = item.get("join_path")
        planned = referenced[binding_ref.casefold()]
        if not (
            target_table and target_column and operator and filter_concept and scope
            and isinstance(required, bool)
            and _valid_filter_binding_value(operator, raw_value)
            and _is_valid_join_path(join_path)
        ):
            raise SqlGenerationInputError("filter_binding esta incompleto ou invalido.")
        if (
            filter_concept.casefold() != planned["filter_concept"].casefold()
            or scope.casefold() != planned["scope"].casefold()
            or required is not planned["required"]
        ):
            raise SqlGenerationInputError("filter_binding diverge da obrigacao semantica.")
        grouped[binding_ref.casefold()].append(
            {
                "binding_ref": binding_ref,
                "filter_concept": filter_concept,
                "target_table": target_table,
                "target_column": target_column,
                "operator": operator,
                "value": deepcopy(raw_value),
                "join_path": deepcopy(join_path),
                "required": required,
                "scope": scope,
            }
        )
    output: list[FilterBinding] = []
    for key in sorted(grouped):
        candidates = grouped[key]
        planned = referenced[key]
        if len(candidates) > 1:
            raise SqlGenerationInputError("filter_binding ambiguo para binding_ref.")
        if planned["required"] is True and len(candidates) != 1:
            raise SqlGenerationInputError("filter_binding obrigatorio ausente.")
        if candidates:
            output.append(candidates[0])
    return output


def _valid_filter_binding_value(
    operator: str,
    value: Any,
) -> bool:
    normalized = operator.casefold()
    if normalized == "in":
        if not isinstance(value, list) or not value:
            return False
        literal_types = [_filter_literal_type(item) for item in value]
        if any(item is None for item in literal_types):
            return False
        if len(set(literal_types)) != 1:
            return False
        identities = [(_filter_literal_type(item), item) for item in value]
        return len(identities) == len(set(identities))
    return (
        normalized in {"=", "<>", "<", "<=", ">", ">="}
        and _filter_literal_type(value) is not None
    )


def _filter_literal_type(value: Any) -> str | None:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, str):
        return "string" if value.strip() else None
    if isinstance(value, int):
        return "number"
    if isinstance(value, float):
        return "number" if math.isfinite(value) else None
    return None


def _is_filled_json_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, bool) or isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return bool(value) and all(_is_filled_json_value(item) for item in value)
    if isinstance(value, Mapping):
        return bool(value) and all(
            isinstance(key, str) and bool(key.strip()) and _is_filled_json_value(item)
            for key, item in value.items()
        )
    return False


def _is_valid_join_path(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    return all(
        isinstance(step, Mapping)
        and bool(step)
        and all(
            isinstance(key, str) and bool(key.strip()) and _is_filled_json_value(item)
            for key, item in step.items()
        )
        for step in value
    )


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

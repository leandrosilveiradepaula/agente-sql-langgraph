from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, cast

from app.domain.engine_preflight import EnginePreflightResult
from app.domain.engine_preflight_sanitization import (
    safe_message,
    safe_optional_text,
    safe_provider_name,
    safe_warnings,
)
from app.domain.planning import QueryPlan
from app.domain.sql_generation import (
    SqlGenerationProviderResult,
    SqlGenerationValidationError,
    validate_sql_generation_response,
)
from app.domain.sql_repair_types import (
    SQL_REPAIR_CONTRACT_VERSION,
    SQL_REPAIR_REASONS,
    SqlRepairDiagnostic,
    SqlRepairErrorCode,
    SqlRepairFailure,
    SqlRepairHistoryEntry,
    SqlRepairInputError,
    SqlRepairProviderError,
    SqlRepairProviderResult,
    SqlRepairReason,
    SqlRepairRequest,
    SqlRepairResult,
    SqlRepairStatus,
)


_OUTPUT_CONSTRAINTS = [
    "Retorne somente uma SQL de leitura.",
    "Nao use Markdown.",
    "Nao inclua explicacoes.",
    "Nao inclua comentarios introdutorios.",
    "Nao inclua multiplos statements.",
    "Use somente SELECT ou WITH.",
    "Preserve a intencao e o QueryPlan.",
    "Corrija apenas o erro estruturado informado.",
    "Nao invente tabelas, schemas ou colunas.",
    "Nao remova filtros ou regras para fazer a SQL passar.",
    "Nao adicione LIMIT automatico.",
    "Nao mude o objetivo da consulta.",
    "Use somente objetos autorizados.",
    "Nao repita SQL identica a tentativa anterior.",
]

_INSTRUCTIONS = [
    {
        "name": "output_format",
        "content": "Retorne exatamente uma SQL de leitura como texto puro.",
    },
    {
        "name": "repair_scope",
        "content": (
            "Corrija somente a falha estruturada informada e preserve o "
            "plano autorizado."
        ),
    },
]

_GENERATION_TO_REPAIR_CODE: dict[str, SqlRepairErrorCode] = {
    "SQL_GENERATION_RESPONSE_EMPTY": "SQL_REPAIR_RESPONSE_EMPTY",
    "SQL_GENERATION_RESPONSE_INVALID": "SQL_REPAIR_RESPONSE_INVALID",
    "SQL_GENERATION_MULTIPLE_STATEMENTS": "SQL_REPAIR_MULTIPLE_STATEMENTS",
    "SQL_GENERATION_NON_READ_ONLY": "SQL_REPAIR_NON_READ_ONLY",
}

_GENERATION_TO_REPAIR_REASON: dict[str, SqlRepairReason] = {
    "SQL_GENERATION_RESPONSE_EMPTY": "sql_repair_response_empty",
    "SQL_GENERATION_RESPONSE_INVALID": "sql_repair_response_invalid",
    "SQL_GENERATION_MULTIPLE_STATEMENTS": "sql_repair_multiple_statements",
    "SQL_GENERATION_NON_READ_ONLY": "sql_repair_non_read_only",
}


def build_sql_repair_request(
    *,
    current_sql: str,
    query_plan: QueryPlan,
    engine_preflight_result: EnginePreflightResult,
    repair_attempts: int,
    max_repair_attempts: int,
    repair_history: list[Mapping[str, Any]] | None,
) -> SqlRepairRequest:
    if not isinstance(current_sql, str) or not current_sql.strip():
        raise SqlRepairInputError(
            "SQL_REPAIR_REQUEST_INVALID",
            "current_sql esta ausente para reparo.",
        )
    if not isinstance(query_plan, Mapping) or not query_plan:
        raise SqlRepairInputError(
            "SQL_REPAIR_REQUEST_INVALID",
            "query_plan esta ausente para reparo.",
        )
    if not isinstance(engine_preflight_result, Mapping):
        raise SqlRepairInputError(
            "SQL_REPAIR_REQUEST_INVALID",
            "engine_preflight_result deve ser objeto.",
        )
    if engine_preflight_result.get("status") != "rejected":
        raise SqlRepairInputError(
            "SQL_REPAIR_PREFLIGHT_NOT_REPAIRABLE",
            "Reparo exige preflight rejeitado.",
            reason="sql_repair_preflight_not_repairable",
        )
    if engine_preflight_result.get("repairable") is not True:
        raise SqlRepairInputError(
            "SQL_REPAIR_PREFLIGHT_NOT_REPAIRABLE",
            "Falha de preflight nao e reparavel.",
            reason="sql_repair_preflight_not_repairable",
        )
    if not _failure_category(engine_preflight_result):
        raise SqlRepairInputError(
            "SQL_REPAIR_REQUEST_INVALID",
            "Categoria de falha reparavel ausente.",
        )
    if not _valid_counter(repair_attempts) or not _valid_counter(
        max_repair_attempts
    ):
        raise SqlRepairInputError(
            "SQL_REPAIR_REQUEST_INVALID",
            "Contadores de reparo invalidos.",
        )
    if max_repair_attempts <= 0:
        raise SqlRepairInputError(
            "SQL_REPAIR_DISABLED",
            "Reparo SQL esta desabilitado.",
            reason="sql_repair_disabled",
        )
    if repair_attempts >= max_repair_attempts:
        raise SqlRepairInputError(
            "SQL_REPAIR_LIMIT_REACHED",
            "Limite de tentativas de reparo atingido.",
            reason="sql_repair_limit_reached",
        )

    planning_context = query_plan.get("planning_context")
    selected_pattern = query_plan.get("selected_pattern")
    if not isinstance(planning_context, Mapping) or not isinstance(
        selected_pattern,
        Mapping,
    ):
        raise SqlRepairInputError(
            "SQL_REPAIR_REQUEST_INVALID",
            "query_plan nao contem contexto minimo de reparo.",
        )

    request: SqlRepairRequest = {
        "contract_version": SQL_REPAIR_CONTRACT_VERSION,
        "current_sql": current_sql,
        "current_sql_fingerprint": sql_fingerprint(current_sql),
        "attempt": repair_attempts + 1,
        "max_attempts": max_repair_attempts,
        "repair_context": {
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
            "intent_name": _required_text(query_plan, "intent_name"),
            "selected_pattern": _stable_mapping_copy(selected_pattern),
            "allowed_schemas": _sorted_text_list(
                planning_context.get("allowed_schemas", [])
            ),
            "authorized_tables": _sorted_mappings(
                planning_context.get("required_tables", []),
                text_fields=("schema_name", "table_name"),
                priority_field="priority",
            ),
            "catalog_columns": _stable_columns(
                planning_context.get("relevant_columns", {})
            ),
            "authorized_joins": _sorted_mappings(
                planning_context.get("authorized_joins", []),
                text_fields=("source_table",),
            ),
        },
        "failure": _repair_failure(
            engine_preflight_result,
            forbidden_texts=(current_sql,),
        ),
        "previous_attempts": _safe_history(
            repair_history or [],
            forbidden_texts=(current_sql,),
        ),
        "instructions": deepcopy(_INSTRUCTIONS),
        "output_constraints": list(_OUTPUT_CONSTRAINTS),
        "request_fingerprint": "",
    }
    request["request_fingerprint"] = request_fingerprint(request)
    return deepcopy(request)


def validate_sql_repair_response(
    *,
    provider_result: SqlRepairProviderResult,
    current_sql: str,
    repair_history: list[Mapping[str, Any]] | None = None,
) -> str:
    try:
        sql = validate_sql_generation_response(
            cast(SqlGenerationProviderResult, provider_result)
        )
    except SqlGenerationValidationError as error:
        raise SqlRepairInputError(
            _GENERATION_TO_REPAIR_CODE.get(
                error.code,
                "SQL_REPAIR_RESPONSE_INVALID",
            ),
            error.message,
            reason=_GENERATION_TO_REPAIR_REASON.get(
                error.code,
                "sql_repair_response_invalid",
            ),
        ) from error

    if sql_fingerprint(sql) == sql_fingerprint(current_sql):
        raise SqlRepairInputError(
            "SQL_REPAIR_UNCHANGED_SQL",
            "SQL reparada e identica a SQL atual.",
            reason="sql_repair_unchanged_sql",
        )

    previous = _previous_sql_after_fingerprints(repair_history or [])
    if sql_fingerprint(sql) in previous:
        raise SqlRepairInputError(
            "SQL_REPAIR_REPEATED_SQL",
            "SQL reparada ja foi produzida em tentativa anterior.",
            reason="sql_repair_repeated_sql",
        )
    return sql


def create_sql_repair_success_result(
    *,
    request: SqlRepairRequest,
    repaired_sql: str,
    provider_result: SqlRepairProviderResult,
) -> SqlRepairResult:
    provider_name = safe_provider_name(
        provider_result.get("provider_name"),
        forbidden_texts=(request["current_sql"], repaired_sql),
    )
    duration_ms = _optional_non_negative_int(
        provider_result.get("duration_ms")
    )
    response_fp = response_fingerprint(
        str(provider_result.get("output_text", ""))
    )
    after_fp = sql_fingerprint(repaired_sql)
    history = _history_entry(
        attempt=request["attempt"],
        failed_stage="engine_preflight",
        failure_category=request["failure"]["category"],
        provider_code=request["failure"].get("provider_code"),
        error_code=None,
        sql_before_fingerprint=request["current_sql_fingerprint"],
        sql_after_fingerprint=after_fp,
        request_fingerprint=request["request_fingerprint"],
        response_fingerprint=response_fp,
        repair_applied=True,
        reason="sql_repair_applied",
        provider_name=provider_name,
        duration_ms=duration_ms,
        errors=[],
        warnings=safe_warnings(
            provider_result.get("warnings"),
            forbidden_texts=(request["current_sql"], repaired_sql),
        ),
    )
    return {
        "status": "repaired",
        "sql": repaired_sql,
        "error_code": None,
        "message": "SQL reparada estruturalmente.",
        "repair_applied": True,
        "reason": "sql_repair_applied",
        "diagnostic": _diagnostic(
            request=request,
            response_fingerprint_value=response_fp,
            sql_after_fingerprint=after_fp,
            repair_applied=True,
            reason="sql_repair_applied",
            provider_name=provider_name,
            duration_ms=duration_ms,
        ),
        "history_entry": history,
        "warnings": history["warnings"],
    }


def create_sql_repair_error_result(
    *,
    request: SqlRepairRequest | None,
    code: SqlRepairErrorCode,
    message: str,
    reason: SqlRepairReason,
    status: SqlRepairStatus,
    current_sql: str,
    attempt: int,
    max_attempts: int,
    provider_result: SqlRepairProviderResult | None = None,
) -> SqlRepairResult:
    provider_name = safe_provider_name(
        provider_result.get("provider_name") if provider_result else None,
        forbidden_texts=(current_sql,),
    )
    duration_ms = _optional_non_negative_int(
        provider_result.get("duration_ms") if provider_result else None
    )
    response_text = (
        provider_result.get("output_text")
        if provider_result and isinstance(provider_result.get("output_text"), str)
        else None
    )
    response_fp = (
        response_fingerprint(response_text)
        if isinstance(response_text, str)
        else None
    )
    request_fp = request["request_fingerprint"] if request else ""
    before_fp = (
        request["current_sql_fingerprint"]
        if request
        else (sql_fingerprint(current_sql) if current_sql else "")
    )
    safe_message_text = safe_message(
        message,
        forbidden_texts=(current_sql,),
    )
    history = _history_entry(
        attempt=attempt,
        failed_stage="engine_preflight",
        failure_category=(
            request["failure"].get("category", "")
            if request
            else ""
        ),
        provider_code=(
            request["failure"].get("provider_code") if request else None
        ),
        error_code=code,
        sql_before_fingerprint=before_fp,
        sql_after_fingerprint=None,
        request_fingerprint=request_fp,
        response_fingerprint=response_fp,
        repair_applied=False,
        reason=reason,
        provider_name=provider_name,
        duration_ms=duration_ms,
        errors=[
            {
                "code": code,
                "message": safe_message_text,
                "details": {},
            }
        ],
        warnings=safe_warnings(
            provider_result.get("warnings") if provider_result else None,
            forbidden_texts=(current_sql,),
        ),
    )
    return {
        "status": status,
        "sql": None,
        "error_code": code,
        "message": safe_message_text,
        "repair_applied": False,
        "reason": reason,
        "diagnostic": {
            "repair_contract_version": SQL_REPAIR_CONTRACT_VERSION,
            "request_fingerprint": request_fp,
            "response_fingerprint": response_fp,
            "sql_before_fingerprint": before_fp,
            "sql_after_fingerprint": None,
            "repair_applied": False,
            "reason": reason,
            "attempt": attempt,
            "max_attempts": max_attempts,
            "provider_name": provider_name,
            "duration_ms": duration_ms,
        },
        "history_entry": history,
        "warnings": history["warnings"],
    }


def request_fingerprint(request: SqlRepairRequest) -> str:
    payload = deepcopy(request)
    payload.pop("request_fingerprint", None)
    return _stable_fingerprint(payload)


def response_fingerprint(value: str) -> str:
    return _stable_fingerprint({"response": value})


def sql_fingerprint(sql: str) -> str:
    return hashlib.sha256(sql.strip().encode("utf-8")).hexdigest()


def _diagnostic(
    *,
    request: SqlRepairRequest,
    response_fingerprint_value: str | None,
    sql_after_fingerprint: str | None,
    repair_applied: bool,
    reason: SqlRepairReason,
    provider_name: str,
    duration_ms: int | None,
) -> SqlRepairDiagnostic:
    return {
        "repair_contract_version": SQL_REPAIR_CONTRACT_VERSION,
        "request_fingerprint": request["request_fingerprint"],
        "response_fingerprint": response_fingerprint_value,
        "sql_before_fingerprint": request["current_sql_fingerprint"],
        "sql_after_fingerprint": sql_after_fingerprint,
        "repair_applied": repair_applied,
        "reason": reason,
        "attempt": request["attempt"],
        "max_attempts": request["max_attempts"],
        "provider_name": provider_name,
        "duration_ms": duration_ms,
    }


def _repair_failure(
    engine_preflight_result: Mapping[str, Any],
    *,
    forbidden_texts: tuple[str, ...],
) -> SqlRepairFailure:
    error = _first_preflight_error(engine_preflight_result)
    category = _failure_category(engine_preflight_result)
    return {
        "stage": "engine_preflight",
        "category": category,
        "code": safe_message(
            error.get("code", ""),
            forbidden_texts=forbidden_texts,
        ),
        "message": safe_message(
            error.get("message", ""),
            forbidden_texts=forbidden_texts,
        ),
        "provider_code": safe_optional_text(
            error.get("provider_code"),
            forbidden_texts=forbidden_texts,
        ),
        "sqlstate": safe_optional_text(error.get("sqlstate")),
        "position": _optional_int(error.get("position")),
        "line": _optional_int(error.get("line")),
        "column": _optional_int(error.get("column")),
        "related_object": safe_optional_text(
            error.get("related_object"),
            forbidden_texts=forbidden_texts,
        ),
        "sanitized_hint": safe_optional_text(
            error.get("sanitized_hint"),
            forbidden_texts=forbidden_texts,
        ),
        "repairable": True,
    }


def _first_preflight_error(result: Mapping[str, Any]) -> Mapping[str, Any]:
    for field_name in ("errors", "findings"):
        values = result.get(field_name)
        if isinstance(values, list) and values and isinstance(
            values[0],
            Mapping,
        ):
            return values[0]
    return {}


def _failure_category(result: Mapping[str, Any]) -> str:
    category = result.get("failure_category")
    if isinstance(category, str) and category and category != "none":
        return category
    error_category = _first_preflight_error(result).get("category")
    return error_category if isinstance(error_category, str) else ""


def _safe_history(
    values: list[Mapping[str, Any]],
    *,
    forbidden_texts: tuple[str, ...],
) -> list[SqlRepairHistoryEntry]:
    if not isinstance(values, list):
        raise SqlRepairInputError(
            "SQL_REPAIR_REQUEST_INVALID",
            "repair_history deve ser lista.",
        )
    output: list[SqlRepairHistoryEntry] = []
    for item in values:
        if not isinstance(item, Mapping):
            raise SqlRepairInputError(
                "SQL_REPAIR_REQUEST_INVALID",
                "repair_history contem item invalido.",
            )
        output.append(
            _history_entry(
                attempt=_required_int(item, "attempt"),
                failed_stage=safe_message(
                    item.get("failed_stage", ""),
                    forbidden_texts=forbidden_texts,
                ),
                failure_category=safe_message(
                    item.get("failure_category", ""),
                    forbidden_texts=forbidden_texts,
                ),
                provider_code=safe_optional_text(
                    item.get("provider_code"),
                    forbidden_texts=forbidden_texts,
                ),
                error_code=safe_optional_text(
                    item.get("error_code"),
                    forbidden_texts=forbidden_texts,
                ),
                sql_before_fingerprint=_safe_fingerprint_text(
                    item.get("sql_before_fingerprint")
                ),
                sql_after_fingerprint=_safe_optional_fingerprint_text(
                    item.get("sql_after_fingerprint")
                ),
                request_fingerprint=_safe_fingerprint_text(
                    item.get("request_fingerprint")
                ),
                response_fingerprint=_safe_optional_fingerprint_text(
                    item.get("response_fingerprint")
                ),
                repair_applied=bool(item.get("repair_applied")),
                reason=_safe_reason(item.get("reason")),
                provider_name=safe_provider_name(
                    item.get("provider_name"),
                    forbidden_texts=forbidden_texts,
                ),
                duration_ms=_optional_non_negative_int(
                    item.get("duration_ms")
                ),
                errors=_safe_error_list(
                    item.get("errors"),
                    forbidden_texts=forbidden_texts,
                ),
                warnings=safe_warnings(
                    item.get("warnings"),
                    forbidden_texts=forbidden_texts,
                ),
            )
        )
    output.sort(key=lambda entry: int(entry["attempt"]))
    return output


def _history_entry(
    *,
    attempt: int,
    failed_stage: str,
    failure_category: str,
    provider_code: str | None,
    error_code: str | None,
    sql_before_fingerprint: str,
    sql_after_fingerprint: str | None,
    request_fingerprint: str,
    response_fingerprint: str | None,
    repair_applied: bool,
    reason: SqlRepairReason,
    provider_name: str,
    duration_ms: int | None,
    errors: list[dict[str, Any]],
    warnings: list[str],
) -> SqlRepairHistoryEntry:
    return {
        "attempt": attempt,
        "failed_stage": failed_stage,
        "failure_category": failure_category,
        "provider_code": provider_code,
        "error_code": error_code,
        "sql_before_fingerprint": sql_before_fingerprint,
        "sql_after_fingerprint": sql_after_fingerprint,
        "request_fingerprint": request_fingerprint,
        "response_fingerprint": response_fingerprint,
        "repair_applied": repair_applied,
        "reason": reason,
        "provider_name": provider_name,
        "duration_ms": duration_ms,
        "errors": deepcopy(errors),
        "warnings": list(warnings),
    }


def _previous_sql_after_fingerprints(
    history: list[Mapping[str, Any]],
) -> set[str]:
    return {
        value
        for item in history
        if isinstance(item, Mapping)
        for value in [item.get("sql_after_fingerprint")]
        if isinstance(value, str) and len(value) == 64
    }


def _safe_error_list(
    values: Any,
    *,
    forbidden_texts: tuple[str, ...],
) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    output: list[dict[str, Any]] = []
    for value in values:
        if isinstance(value, Mapping):
            output.append(
                {
                    "code": safe_message(
                        value.get("code", ""),
                        forbidden_texts=forbidden_texts,
                    ),
                    "message": safe_message(
                        value.get("message", ""),
                        forbidden_texts=forbidden_texts,
                    ),
                    "details": {},
                }
            )
    return output


def _safe_reason(value: Any) -> SqlRepairReason:
    if isinstance(value, str) and value in SQL_REPAIR_REASONS:
        return value  # type: ignore[return-value]
    return "sql_repair_request_invalid"


def _required_int(value: Mapping[str, Any], field_name: str) -> int:
    field_value = value.get(field_name)
    if (
        isinstance(field_value, int)
        and not isinstance(field_value, bool)
        and field_value > 0
    ):
        return field_value
    raise SqlRepairInputError(
        "SQL_REPAIR_REQUEST_INVALID",
        f"{field_name} invalido no historico de reparo.",
    )


def _safe_fingerprint_text(value: Any) -> str:
    if isinstance(value, str) and len(value) == 64:
        return value
    return ""


def _safe_optional_fingerprint_text(value: Any) -> str | None:
    if isinstance(value, str) and len(value) == 64:
        return value
    return None


def _required_text(
    value: Mapping[str, Any],
    field_name: str,
) -> str:
    field_value = value.get(field_name)
    if not isinstance(field_value, str) or not field_value.strip():
        raise SqlRepairInputError(
            "SQL_REPAIR_REQUEST_INVALID",
            f"{field_name} deve ser texto nao vazio.",
        )
    return field_value


def _valid_counter(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _sorted_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise SqlRepairInputError(
            "SQL_REPAIR_REQUEST_INVALID",
            "colecao de textos esperada como lista.",
        )
    return sorted(
        [
            item
            for item in value
            if isinstance(item, str) and item.strip()
        ],
        key=str.casefold,
    )


def _sorted_mappings(
    values: Any,
    *,
    text_fields: tuple[str, ...],
    priority_field: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        raise SqlRepairInputError(
            "SQL_REPAIR_REQUEST_INVALID",
            "colecao esperada como lista.",
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


def _stable_columns(value: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, Mapping):
        raise SqlRepairInputError(
            "SQL_REPAIR_REQUEST_INVALID",
            "relevant_columns deve ser objeto.",
        )
    output: dict[str, list[dict[str, Any]]] = {}
    for table_name in sorted(value, key=str.casefold):
        columns = value[table_name]
        if not isinstance(columns, list):
            raise SqlRepairInputError(
                "SQL_REPAIR_REQUEST_INVALID",
                "cada entrada de relevant_columns deve ser lista.",
            )
        output[str(table_name)] = _sorted_mappings(
            columns,
            text_fields=("name",),
        )
    return output


def _stable_mapping_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): deepcopy(item)
        for key, item in sorted(
            value.items(),
            key=lambda pair: str(pair[0]).casefold(),
        )
    }


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _optional_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


def _priority_sort_value(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return float("inf")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("inf")


def _stable_fingerprint(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    )

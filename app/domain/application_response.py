from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from app.domain.application_response_types import (
    APPLICATION_RESPONSE_CONTRACT_VERSION,
    ApplicationResponse,
    ApplicationResponseData,
    ApplicationResponseError,
    ApplicationResponseFinalization,
    ApplicationResponseFinalizationStatus,
    ApplicationResponseLimits,
    ApplicationResponseLineage,
    ApplicationResponseMetadata,
    ApplicationResponseOutcome,
    ApplicationResponsePagination,
    ApplicationResponseStatus,
    ApplicationResponseWarning,
)
from app.domain.result_normalization import canonical_json, stable_fingerprint


class ApplicationResponseBuildError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def default_application_response_limits() -> ApplicationResponseLimits:
    return {
        "max_response_bytes": 1_000_000,
        "max_errors": 32,
        "max_warnings": 32,
        "max_message_length": 160,
        "max_error_message_length": 160,
        "max_warning_message_length": 160,
        "max_lineage_fields": 16,
        "max_data_rows": 10_000,
        "max_data_columns": 500,
        "max_metadata_fields": 16,
    }


def build_application_response(
    *,
    request_id: str,
    run_id: str,
    original_outcome: object,
    finalization_status: object,
    serialized_result: object = None,
    normalized_result: object = None,
    execution_result: object = None,
    run_record: object = None,
    persistence_result: object = None,
    audit_result: object = None,
    observability_result: object = None,
    errors: object = None,
    warnings: object = None,
    limits: Mapping[str, Any],
) -> ApplicationResponse:
    safe_limits = validate_application_response_limits(limits)
    outcome = _outcome(original_outcome)
    finalization = _finalization(
        finalization_status,
        run_record,
        persistence_result,
        audit_result,
        observability_result,
    )
    data_allowed = _data_allowed(
        outcome,
        serialized_result,
        normalized_result,
        execution_result,
        persistence_result,
        audit_result,
        finalization,
    )
    response_errors = _response_errors(
        errors,
        finalization,
        safe_limits,
    )
    response_warnings = _response_warnings(
        warnings,
        finalization,
        safe_limits,
    )
    data: ApplicationResponseData | None = None
    if data_allowed:
        data = _data(serialized_result, safe_limits)
    status = _status(outcome, data, finalization)
    if status != "success":
        data = None
    if (
        outcome == "success"
        and finalization["status"]
        in {"persistence_failed", "audit_failed", "record_failed", "incomplete"}
        and not any(
            error["code"] == "APPLICATION_RESPONSE_FINALIZATION_INCOMPLETE"
            for error in response_errors
        )
    ):
        response_errors.append(
            _error(
                "APPLICATION_RESPONSE_FINALIZATION_INCOMPLETE",
                "finalization",
                "finalization",
                "A finalizacao operacional nao foi concluida.",
                retryable=True,
            )
        )
    message = _message(status)
    metadata = _metadata(
        outcome,
        finalization,
        run_record,
        serialized_result,
        execution_result,
        persistence_result,
        audit_result,
        observability_result,
        safe_limits,
    )
    response: ApplicationResponse = {
        "contract_version": APPLICATION_RESPONSE_CONTRACT_VERSION,
        "response_id": _response_id(request_id, run_id),
        "request_id": str(request_id or ""),
        "run_id": str(run_id or ""),
        "status": status,
        "original_outcome": outcome,
        "message": _safe_text(message, safe_limits["max_message_length"]),
        "data": deepcopy(data),
        "errors": response_errors[: safe_limits["max_errors"]],
        "warnings": response_warnings[: safe_limits["max_warnings"]],
        "metadata": metadata,
        "finalization": finalization,
        "response_fingerprint": "",
    }
    _validate_no_silent_drop(
        response_errors,
        response_warnings,
        safe_limits,
    )
    response = _with_fingerprint(response)
    if _json_size(response) > safe_limits["max_response_bytes"]:
        return _limit_exceeded_response(
            request_id=str(request_id or ""),
            run_id=str(run_id or ""),
            outcome=outcome,
            finalization=finalization,
            metadata=metadata,
            limits=safe_limits,
        )
    return deepcopy(response)


def build_minimal_failure_response(
    *,
    request_id: str = "",
    run_id: str = "",
    original_outcome: object = "infrastructure_error",
    code: str = "APPLICATION_RESPONSE_BUILD_FAILED",
) -> ApplicationResponse:
    limits = default_application_response_limits()
    outcome = _outcome(original_outcome)
    finalization: ApplicationResponseFinalization = {
        "status": "incomplete",
        "run_record_built": False,
        "persisted": False,
        "persistence_record_id": None,
        "audited": False,
        "audit_event_id": None,
        "observability_emitted": False,
        "observability_degraded": False,
        "error_codes": [code],
    }
    metadata: ApplicationResponseMetadata = {
        "persisted": False,
        "audited": False,
        "observability_degraded": False,
        "original_outcome": outcome,
        "finalization_status": "incomplete",
        "contract_versions": {
            "application_response": APPLICATION_RESPONSE_CONTRACT_VERSION
        },
        "lineage": {},
    }
    response: ApplicationResponse = {
        "contract_version": APPLICATION_RESPONSE_CONTRACT_VERSION,
        "response_id": _response_id(request_id, run_id),
        "request_id": str(request_id or ""),
        "run_id": str(run_id or ""),
        "status": "infrastructure_error",
        "original_outcome": outcome,
        "message": _message("infrastructure_error"),
        "data": None,
        "errors": [
            _error(
                code,
                "application_response",
                "build_application_response",
                "A resposta da aplicacao nao pode ser construida.",
                retryable=True,
            )
        ],
        "warnings": [],
        "metadata": metadata,
        "finalization": finalization,
        "response_fingerprint": "",
    }
    return _with_fingerprint(response)


def to_canonical_application_response_json(
    response: Mapping[str, Any],
) -> str:
    return canonical_json(response)


def validate_application_response_limits(
    limits: Mapping[str, Any],
) -> ApplicationResponseLimits:
    required = {
        "max_response_bytes": (1_000, 10_000_000),
        "max_errors": (1, 100),
        "max_warnings": (1, 100),
        "max_message_length": (16, 512),
        "max_error_message_length": (16, 512),
        "max_warning_message_length": (16, 512),
        "max_lineage_fields": (1, 32),
        "max_data_rows": (0, 100_000),
        "max_data_columns": (0, 10_000),
        "max_metadata_fields": (1, 32),
    }
    output: dict[str, int] = {}
    for key, (minimum, maximum) in required.items():
        value = limits.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ApplicationResponseBuildError(
                "APPLICATION_RESPONSE_INPUT_INVALID",
                f"Limite {key} deve ser inteiro.",
            )
        if value < minimum or value > maximum:
            raise ApplicationResponseBuildError(
                "APPLICATION_RESPONSE_LIMIT_EXCEEDED",
                f"Limite {key} fora da faixa permitida.",
            )
        output[key] = value
    return output  # type: ignore[return-value]


def _data_allowed(
    outcome: ApplicationResponseOutcome,
    serialized_result: object,
    normalized_result: object,
    execution_result: object,
    persistence_result: object,
    audit_result: object,
    finalization: ApplicationResponseFinalization,
) -> bool:
    return (
        outcome == "success"
        and _status_of(execution_result) == "success"
        and isinstance(execution_result, Mapping)
        and execution_result.get("executed") is True
        and _status_of(normalized_result) == "success"
        and _status_of(serialized_result) == "success"
        and _persisted(persistence_result)
        and _audited(audit_result)
        and finalization["status"] in {"completed", "observability_degraded"}
    )


def _data(
    serialized_result: object,
    limits: ApplicationResponseLimits,
) -> ApplicationResponseData:
    if not isinstance(serialized_result, Mapping):
        raise ApplicationResponseBuildError(
            "APPLICATION_RESPONSE_INPUT_INVALID",
            "Resultado serializado ausente.",
        )
    columns = deepcopy(serialized_result.get("columns", []))
    rows = deepcopy(serialized_result.get("rows", []))
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise ApplicationResponseBuildError(
            "APPLICATION_RESPONSE_INPUT_INVALID",
            "Resultado serializado invalido.",
        )
    if len(columns) > limits["max_data_columns"]:
        raise ApplicationResponseBuildError(
            "APPLICATION_RESPONSE_LIMIT_EXCEEDED",
            "Quantidade de colunas excede limite.",
        )
    if len(rows) > limits["max_data_rows"]:
        raise ApplicationResponseBuildError(
            "APPLICATION_RESPONSE_LIMIT_EXCEEDED",
            "Quantidade de linhas excede limite.",
        )
    fingerprint = serialized_result.get("result_fingerprint")
    if not isinstance(fingerprint, str) or not fingerprint:
        raise ApplicationResponseBuildError(
            "APPLICATION_RESPONSE_INPUT_INVALID",
            "Resultado serializado sem fingerprint.",
        )
    pagination: ApplicationResponsePagination = {
        "mode": "none",
        "has_more": False,
        "next_cursor": None,
        "total_rows": len(rows),
        "returned_rows": len(rows),
    }
    return {
        "result": {
            "contract_version": str(serialized_result.get("contract_version", "")),
            "columns": columns,
            "rows": rows,
            "result_fingerprint": fingerprint,
        },
        "pagination": pagination,
    }


def _finalization(
    finalization_status: object,
    run_record: object,
    persistence_result: object,
    audit_result: object,
    observability_result: object,
) -> ApplicationResponseFinalization:
    raw_status = str(finalization_status or "")
    status: ApplicationResponseFinalizationStatus
    if raw_status == "record_failed" or not isinstance(run_record, Mapping):
        status = "record_failed"
    elif raw_status == "persistence_failed" or _failed_persistence(
        persistence_result
    ):
        status = "persistence_failed"
    elif raw_status == "audit_failed" or _failed_audit(audit_result):
        status = "audit_failed"
    elif raw_status == "observed" and _persisted(persistence_result) and _audited(audit_result):
        status = "completed"
    elif raw_status == "observability_degraded":
        status = "observability_degraded"
    else:
        status = "incomplete"
    errors = []
    for value in (persistence_result, audit_result, observability_result):
        code = _diagnostic_code(value)
        if code:
            errors.append(code)
    return {
        "status": status,
        "run_record_built": isinstance(run_record, Mapping)
        and run_record.get("status") == "built",
        "persisted": _persisted(persistence_result),
        "persistence_record_id": _safe_id(
            persistence_result.get("record_id")
            if isinstance(persistence_result, Mapping)
            else None
        ),
        "audited": _audited(audit_result),
        "audit_event_id": _safe_id(
            audit_result.get("event_id")
            if isinstance(audit_result, Mapping)
            else None
        ),
        "observability_emitted": isinstance(observability_result, Mapping)
        and observability_result.get("status") == "emitted",
        "observability_degraded": isinstance(observability_result, Mapping)
        and observability_result.get("status") == "degraded",
        "error_codes": sorted(set(errors)),
    }


def _metadata(
    outcome: ApplicationResponseOutcome,
    finalization: ApplicationResponseFinalization,
    run_record: object,
    serialized_result: object,
    execution_result: object,
    persistence_result: object,
    audit_result: object,
    observability_result: object,
    limits: ApplicationResponseLimits,
) -> ApplicationResponseMetadata:
    metrics = run_record.get("metrics", {}) if isinstance(run_record, Mapping) else {}
    lineage = run_record.get("lineage", {}) if isinstance(run_record, Mapping) else {}
    result_lineage = (
        serialized_result.get("lineage", {})
        if isinstance(serialized_result, Mapping)
        else {}
    )
    app_lineage = _lineage(
        lineage,
        run_record,
        persistence_result,
        audit_result,
        limits,
    )
    row_count = _int_metric(metrics, "row_count")
    column_count = _int_metric(metrics, "column_count")
    if isinstance(serialized_result, Mapping) and serialized_result.get("status") == "success":
        row_count = len(serialized_result.get("rows", []))
        column_count = len(serialized_result.get("columns", []))
    metadata: ApplicationResponseMetadata = {
        "context_version": str(lineage.get("context_version", "")),
        "intent": lineage.get("intent_name"),
        "row_count": row_count,
        "column_count": column_count,
        "result_bytes": _int_metric(metrics, "bytes"),
        "truncated": bool(metrics.get("truncated", False))
        if isinstance(metrics, Mapping)
        else False,
        "repair_attempts": _int_metric(metrics, "repair_attempts"),
        "duration_ms": metrics.get("duration_ms")
        if isinstance(metrics, Mapping)
        and isinstance(metrics.get("duration_ms"), int)
        else None,
        "persisted": finalization["persisted"],
        "audited": finalization["audited"],
        "observability_degraded": finalization["observability_degraded"],
        "provider": _safe_provider(result_lineage, execution_result),
        "contract_versions": {
            "application_response": APPLICATION_RESPONSE_CONTRACT_VERSION,
            "serialization": str(
                serialized_result.get("contract_version", "")
                if isinstance(serialized_result, Mapping)
                else ""
            ),
        },
        "original_outcome": outcome,
        "finalization_status": finalization["status"],
        "lineage": app_lineage,
    }
    if len(metadata) > limits["max_metadata_fields"]:
        raise ApplicationResponseBuildError(
            "APPLICATION_RESPONSE_LIMIT_EXCEEDED",
            "Quantidade de metadados excede limite.",
        )
    return metadata


def _lineage(
    lineage: object,
    run_record: object,
    persistence_result: object,
    audit_result: object,
    limits: ApplicationResponseLimits,
) -> ApplicationResponseLineage:
    source = lineage if isinstance(lineage, Mapping) else {}
    output: ApplicationResponseLineage = {}
    for source_key, target_key in [
        ("context_fingerprint", "context_fingerprint"),
        ("query_plan_fingerprint", "query_plan_fingerprint"),
        ("current_sql_fingerprint", "current_sql_fingerprint"),
        ("preflight_result_fingerprint", "preflight_fingerprint"),
        ("execution_request_fingerprint", "execution_request_fingerprint"),
        ("execution_response_fingerprint", "execution_response_fingerprint"),
        ("normalized_result_fingerprint", "normalized_result_fingerprint"),
        ("serialized_result_fingerprint", "serialized_result_fingerprint"),
    ]:
        value = source.get(source_key)
        if isinstance(value, str) and value:
            output[target_key] = _safe_id(value)  # type: ignore[literal-required]
    if isinstance(run_record, Mapping) and isinstance(run_record.get("fingerprint"), str):
        output["run_record_fingerprint"] = str(run_record["fingerprint"])
    if _persisted(persistence_result) and isinstance(persistence_result, Mapping):
        output["persistence_record_id"] = _safe_id(persistence_result.get("record_id"))
        if isinstance(persistence_result.get("persisted_fingerprint"), str):
            output["persistence_fingerprint"] = str(
                persistence_result["persisted_fingerprint"]
            )
    if _audited(audit_result) and isinstance(audit_result, Mapping):
        output["audit_event_id"] = _safe_id(audit_result.get("event_id"))
        if isinstance(audit_result.get("event_fingerprint"), str):
            output["audit_fingerprint"] = str(audit_result["event_fingerprint"])
    if len(output) > limits["max_lineage_fields"]:
        raise ApplicationResponseBuildError(
            "APPLICATION_RESPONSE_LIMIT_EXCEEDED",
            "Quantidade de lineage excede limite.",
        )
    return output


def _response_errors(
    errors: object,
    finalization: ApplicationResponseFinalization,
    limits: ApplicationResponseLimits,
) -> list[ApplicationResponseError]:
    output: list[ApplicationResponseError] = []
    if isinstance(errors, list):
        for item in errors:
            if not isinstance(item, Mapping):
                continue
            output.append(
                _error(
                    _safe_code(item.get("code")),
                    _safe_text(item.get("source"), 64) or "application",
                    _safe_text(item.get("stage"), 64) or "unknown",
                    _public_error_message(item.get("code")),
                    retryable=not bool(item.get("repairable", False)),
                )
            )
    for code in finalization.get("error_codes", []):
        if str(code).startswith("OBSERVABILITY"):
            continue
        output.append(
            _error(
                _safe_code(code),
                "finalization",
                "finalization",
                _public_error_message(code),
                retryable=True,
            )
        )
    return _dedupe_errors(output, limits)


def _response_warnings(
    warnings: object,
    finalization: ApplicationResponseFinalization,
    limits: ApplicationResponseLimits,
) -> list[ApplicationResponseWarning]:
    output: list[ApplicationResponseWarning] = []
    if isinstance(warnings, list):
        for item in warnings:
            code = _safe_code(str(item).split(":", 1)[0])
            if not code:
                continue
            output.append(
                {
                    "code": code,
                    "category": "application",
                    "stage": "unknown",
                    "message": _safe_text(
                        _public_warning_message(code),
                        limits["max_warning_message_length"],
                    ),
                }
            )
    if finalization.get("observability_degraded"):
        output.append(
            {
                "code": "OBSERVABILITY_DEGRADED",
                "category": "observability",
                "stage": "emit_observability",
                "message": "Observabilidade degradada.",
            }
        )
    return _dedupe_warnings(output, limits)


def _status(
    outcome: ApplicationResponseOutcome,
    data: object,
    finalization: ApplicationResponseFinalization,
) -> ApplicationResponseStatus:
    if outcome == "rejected":
        return "rejected"
    if outcome == "infrastructure_error":
        return "infrastructure_error"
    if finalization["status"] in {
        "persistence_failed",
        "audit_failed",
        "record_failed",
        "incomplete",
    }:
        return "infrastructure_error"
    if data is None:
        return "infrastructure_error"
    return "success"


def _limit_exceeded_response(
    *,
    request_id: str,
    run_id: str,
    outcome: ApplicationResponseOutcome,
    finalization: ApplicationResponseFinalization,
    metadata: ApplicationResponseMetadata,
    limits: ApplicationResponseLimits,
) -> ApplicationResponse:
    error = _error(
        "APPLICATION_RESPONSE_LIMIT_EXCEEDED",
        "application_response",
        "build_application_response",
        "A resposta excede os limites permitidos.",
        retryable=False,
    )
    finalization = deepcopy(finalization)
    finalization["error_codes"] = sorted(
        set(
            [
                *finalization.get("error_codes", []),
                "APPLICATION_RESPONSE_LIMIT_EXCEEDED",
            ]
        )
    )
    metadata = deepcopy(metadata)
    metadata["original_outcome"] = outcome
    response: ApplicationResponse = {
        "contract_version": APPLICATION_RESPONSE_CONTRACT_VERSION,
        "response_id": _response_id(request_id, run_id),
        "request_id": request_id,
        "run_id": run_id,
        "status": "infrastructure_error",
        "original_outcome": outcome,
        "message": _safe_text(
            _message("infrastructure_error"),
            limits["max_message_length"],
        ),
        "data": None,
        "errors": [error],
        "warnings": [],
        "metadata": metadata,
        "finalization": finalization,
        "response_fingerprint": "",
    }
    return _with_fingerprint(response)


def _with_fingerprint(response: ApplicationResponse) -> ApplicationResponse:
    payload = deepcopy(response)
    payload.pop("response_fingerprint", None)
    fingerprint = stable_fingerprint(payload)
    return {**deepcopy(payload), "response_fingerprint": fingerprint}


def _validate_no_silent_drop(
    errors: list[ApplicationResponseError],
    warnings: list[ApplicationResponseWarning],
    limits: ApplicationResponseLimits,
) -> None:
    if len(errors) > limits["max_errors"]:
        raise ApplicationResponseBuildError(
            "APPLICATION_RESPONSE_LIMIT_EXCEEDED",
            "Quantidade de erros excede limite.",
        )
    if len(warnings) > limits["max_warnings"]:
        raise ApplicationResponseBuildError(
            "APPLICATION_RESPONSE_LIMIT_EXCEEDED",
            "Quantidade de warnings excede limite.",
        )


def _dedupe_errors(
    errors: list[ApplicationResponseError],
    limits: ApplicationResponseLimits,
) -> list[ApplicationResponseError]:
    seen: set[tuple[str, str, str]] = set()
    output: list[ApplicationResponseError] = []
    for error in errors:
        key = (error["code"], error["category"], error["stage"])
        if key in seen:
            continue
        seen.add(key)
        error["message"] = _safe_text(
            error["message"],
            limits["max_error_message_length"],
        )
        output.append(error)
    return output


def _dedupe_warnings(
    warnings: list[ApplicationResponseWarning],
    limits: ApplicationResponseLimits,
) -> list[ApplicationResponseWarning]:
    seen: set[tuple[str, str, str]] = set()
    output: list[ApplicationResponseWarning] = []
    for warning in warnings:
        key = (warning["code"], warning["category"], warning["stage"])
        if key in seen:
            continue
        seen.add(key)
        warning["message"] = _safe_text(
            warning["message"],
            limits["max_warning_message_length"],
        )
        output.append(warning)
    return output


def _error(
    code: str,
    category: str,
    stage: str,
    message: str,
    *,
    retryable: bool,
) -> ApplicationResponseError:
    return {
        "code": code,
        "category": category,
        "stage": stage,
        "message": message,
        "retryable": retryable,
    }


def _message(status: ApplicationResponseStatus) -> str:
    return {
        "success": "Consulta processada com sucesso.",
        "rejected": "A solicitacao nao pode ser processada.",
        "infrastructure_error": "O processamento nao pode ser concluido.",
    }[status]


def _public_error_message(code: object) -> str:
    code_text = _safe_code(code)
    if code_text.startswith("PERSIST_RUN"):
        return "Persistencia operacional falhou."
    if code_text.startswith("AUDIT"):
        return "Auditoria operacional falhou."
    if code_text.startswith("OBSERVABILITY"):
        return "Observabilidade operacional degradada."
    if code_text.startswith("APPLICATION_RESPONSE"):
        return "Resposta da aplicacao nao pode ser concluida."
    return "A solicitacao nao pode ser processada."


def _public_warning_message(code: str) -> str:
    if code == "OBSERVABILITY_DEGRADED" or code.startswith("OBSERVABILITY"):
        return "Observabilidade degradada."
    if code == "RESULT_TRUNCATED":
        return "Resultado truncado."
    return "Aviso operacional."


def _outcome(value: object) -> ApplicationResponseOutcome:
    if value in {"success", "rejected", "infrastructure_error"}:
        return value  # type: ignore[return-value]
    return "infrastructure_error"


def _status_of(value: object) -> str:
    if isinstance(value, Mapping):
        return str(value.get("status", ""))
    return ""


def _persisted(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("status") in {"persisted", "already_persisted"}
        and isinstance(value.get("record_id"), str)
    )


def _failed_persistence(value: object) -> bool:
    return isinstance(value, Mapping) and value.get("status") in {
        "rejected",
        "error",
    }


def _audited(value: object) -> bool:
    return (
        isinstance(value, Mapping)
        and value.get("status") in {"written", "already_written"}
        and isinstance(value.get("event_id"), str)
    )


def _failed_audit(value: object) -> bool:
    return isinstance(value, Mapping) and value.get("status") in {
        "rejected",
        "error",
    }


def _diagnostic_code(value: object) -> str:
    if not isinstance(value, Mapping):
        return ""
    diagnostic = value.get("diagnostic")
    if isinstance(diagnostic, Mapping):
        return _safe_code(diagnostic.get("code"))
    return ""


def _int_metric(value: object, key: str) -> int:
    if isinstance(value, Mapping):
        item = value.get(key)
        if isinstance(item, int) and not isinstance(item, bool) and item >= 0:
            return item
    return 0


def _safe_provider(
    result_lineage: object,
    execution_result: object,
) -> str:
    if isinstance(result_lineage, Mapping):
        provider = result_lineage.get("execution_provider_name")
        if isinstance(provider, str) and provider:
            return _safe_text(provider, 64)
    if isinstance(execution_result, Mapping):
        provider = execution_result.get("provider_name")
        if isinstance(provider, str) and provider:
            return _safe_text(provider, 64)
    return ""


def _safe_id(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return _safe_text(value, 128)


def _safe_code(value: object) -> str:
    if not isinstance(value, str):
        return "UNKNOWN_ERROR"
    lowered = value.casefold()
    if any(
        term in lowered
        for term in [
            "authorization",
            "bearer",
            "api key",
            "cookie",
            "dsn",
            "header",
            "password",
            "token",
        ]
    ):
        return "SANITIZED"
    text = "".join(
        char if char.isalnum() or char == "_" else "_"
        for char in value.strip().upper()
    )
    return text[:96] or "UNKNOWN_ERROR"


def _safe_text(value: object, max_length: int) -> str:
    if value is None:
        return ""
    text = str(value)
    lowered = text.casefold()
    blocked = [
        "authorization",
        "bearer",
        "api key",
        "cookie",
        "dsn",
        "header",
        "stack trace",
        "traceback",
        "password",
        "token",
    ]
    if any(term in lowered for term in blocked):
        return "sanitized"
    return text[:max_length]


def _response_id(request_id: str, run_id: str) -> str:
    return stable_fingerprint(
        {
            "contract_version": APPLICATION_RESPONSE_CONTRACT_VERSION,
            "request_id": str(request_id or ""),
            "run_id": str(run_id or ""),
        }
    )


def _json_size(value: Any) -> int:
    return len(canonical_json(value).encode("utf-8"))

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.application.internal_sql_agent_v1_types import (
    INTERNAL_SQL_AGENT_CONTRACT_VERSION,
    InternalSqlAgentError,
    InternalSqlAgentPrincipal,
)
from app.domain.result_normalization import stable_fingerprint
from app.domain.shadow_evidence_types import (
    FinalizeShadowRunRequest,
    ShadowRunRecord,
)
from app.ports.shadow_evidence_repository import ShadowEvidenceRepository


IdGenerator = Callable[[], str]

_SAFE_ID_CHARS = set(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "._:-"
)
_SAFE_TEXT_CHARS = set(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "._:@/+ -"
)
_BLOCKED_PAYLOAD_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "cookies",
    "credential",
    "credentials",
    "dsn",
    "headers",
    "password",
    "raw_response",
    "secret",
    "secrets",
    "token",
    "tokens",
}


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def shadow_record_id(
    *,
    agent_run_id: str,
    run_id: str,
    event_type: str,
) -> str:
    fingerprint = stable_fingerprint(
        {
            "agent_run_id": agent_run_id,
            "run_id": run_id,
            "event_type": event_type,
        }
    )
    return f"shadow-{fingerprint[:32]}"


def persist_shadow_record(
    repository: ShadowEvidenceRepository | None,
    record: ShadowRunRecord,
) -> None:
    if repository is None:
        return
    try:
        repository.create(record)
        repository.update_evidence(record)
        repository.finalize(
            FinalizeShadowRunRequest(
                shadow_record_id=record["shadow_record_id"],
                status=record["status"],
                completed_at=record.get("completed_at") or now_utc_iso(),
                evidence_fingerprint=record["evidence_fingerprint"],
            )
        )
    except Exception:
        return


def validate_common_request(request: object) -> list[InternalSqlAgentError]:
    if not isinstance(request, Mapping):
        return [
            error(
                "INTERNAL_REQUEST_INVALID",
                "request",
                "Request must be a JSON object.",
            )
        ]
    errors: list[InternalSqlAgentError] = []
    if _contains_blocked_payload_key(request):
        errors.append(
            error(
                "INTERNAL_REQUEST_SECRET_FIELD_FORBIDDEN",
                "request",
                "Secret-bearing fields are not accepted.",
            )
        )
    if request.get("contract_version") != INTERNAL_SQL_AGENT_CONTRACT_VERSION:
        errors.append(
            error(
                "INTERNAL_CONTRACT_VERSION_UNSUPPORTED",
                "contract_version",
                "Unsupported contract version.",
            )
        )
    if not _valid_identifier(request.get("agent_run_id"), 128):
        errors.append(
            error(
                "INTERNAL_AGENT_RUN_ID_INVALID",
                "agent_run_id",
                "agent_run_id is invalid.",
            )
        )
    if not _valid_principal(request.get("principal")):
        errors.append(
            error(
                "INTERNAL_PRINCIPAL_INVALID",
                "principal",
                "Principal is invalid.",
            )
        )
    if not _valid_metadata(request.get("correlation_metadata", {})):
        errors.append(
            error(
                "INTERNAL_CORRELATION_METADATA_INVALID",
                "correlation_metadata",
                "Correlation metadata is invalid.",
            )
        )
    return errors


def with_response_fingerprints(response: Any) -> Any:
    response["response_id"] = stable_fingerprint(
        {
            "contract_version": response["contract_version"],
            "agent_run_id": response["agent_run_id"],
            "run_id": response["run_id"],
            "status": response["status"],
            "message": response["message"],
        }
    )
    payload = deepcopy(response)
    payload.pop("response_fingerprint", None)
    response["response_fingerprint"] = stable_fingerprint(payload)
    return deepcopy(response)


def summary(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {"status": "not_run", "code": None, "repairable": None}
    errors = value.get("errors", [])
    first_error = errors[0] if isinstance(errors, list) and errors else {}
    code = first_error.get("code") if isinstance(first_error, Mapping) else None
    return {
        "status": str(value.get("status", "not_run")),
        "code": code if isinstance(code, str) else None,
        "repairable": (
            bool(value.get("repairable"))
            if "repairable" in value
            else (
                bool(first_error.get("repairable"))
                if isinstance(first_error, Mapping)
                and "repairable" in first_error
                else None
            )
        ),
        "executed": (
            bool(value.get("executed")) if "executed" in value else None
        ),
    }


def metadata(state: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "shadow_mode": True,
        "current_stage": str(state.get("current_stage", "")),
        "failure_stage": str(state.get("failure_stage", "")),
        "context_version": (
            state.get("context_version")
            if isinstance(state.get("context_version"), str)
            else None
        ),
        "repair_history_count": len(state.get("repair_history", []))
        if isinstance(state.get("repair_history"), list)
        else 0,
        "intent_resolution": _intent_resolution_metadata(state),
        "query_plan": _query_plan_metadata(state),
        "gate_diagnostics": _gate_diagnostics_metadata(state),
        "lineage": _lineage(state),
    }


def _gate_diagnostics_metadata(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    """Projeta apenas diagnostico estrutural seguro dos gates."""

    security = state.get("security_result")
    contract = state.get("contract_result")

    return {
        "security": _security_gate_diagnostic(security),
        "contract": _contract_gate_diagnostic(contract),
    }


def _security_gate_diagnostic(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"available": False}

    tables = [
        str(item)
        for item in value.get("tables", [])[:16]
        if isinstance(item, str) and item
    ]
    findings: list[dict[str, Any]] = []
    for item in value.get("findings", [])[:8]:
        if not isinstance(item, Mapping):
            continue
        details = item.get("details")
        if not isinstance(details, Mapping):
            details = {}
        findings.append(
            {
                "code": str(item.get("code") or "") or None,
                "table": (
                    str(details.get("table"))
                    if isinstance(details.get("table"), str)
                    else None
                ),
                "schema": (
                    str(details.get("schema"))
                    if isinstance(details.get("schema"), str)
                    else None
                ),
            }
        )

    return {
        "available": True,
        "status": str(value.get("status") or "") or None,
        "referenced_tables": tables,
        "findings": findings,
    }


def _contract_gate_diagnostic(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"available": False}

    referenced_tables: list[dict[str, Any]] = []
    for item in value.get("referenced_tables", [])[:16]:
        if not isinstance(item, Mapping):
            continue
        referenced_tables.append(
            {
                "table": str(item.get("table") or "") or None,
                "status": str(item.get("status") or "") or None,
                "reason": str(item.get("reason") or "") or None,
            }
        )

    joins: list[dict[str, Any]] = []
    for item in value.get("joins", [])[:16]:
        if not isinstance(item, Mapping):
            continue
        joins.append(
            {
                "left_table": (
                    str(item.get("left_table"))
                    if isinstance(item.get("left_table"), str)
                    else None
                ),
                "right_table": (
                    str(item.get("right_table"))
                    if isinstance(item.get("right_table"), str)
                    else None
                ),
                "status": str(item.get("status") or "") or None,
                "reason": str(item.get("reason") or "") or None,
            }
        )

    findings: list[dict[str, Any]] = []
    for item in value.get("findings", [])[:8]:
        if not isinstance(item, Mapping):
            continue
        details = item.get("details")
        if not isinstance(details, Mapping):
            details = {}
        findings.append(
            {
                "code": str(item.get("code") or "") or None,
                "table": (
                    str(details.get("table"))
                    if isinstance(details.get("table"), str)
                    else None
                ),
                "reason": (
                    str(details.get("reason"))
                    if isinstance(details.get("reason"), str)
                    else None
                ),
            }
        )

    return {
        "available": True,
        "status": str(value.get("status") or "") or None,
        "referenced_tables": referenced_tables,
        "joins": joins,
        "findings": findings,
    }


def _query_plan_metadata(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Projeta um resumo estrutural do QueryPlan para evidence/benchmark.

    Nao expoe exemplos de perguntas, regras, sql_pattern ou contexto bruto.
    """

    query_plan = state.get("query_plan")
    if not isinstance(query_plan, Mapping):
        return {"available": False}

    planning = query_plan.get("planning_context")
    if not isinstance(planning, Mapping):
        planning = {}

    selected_pattern = query_plan.get("selected_pattern")
    if not isinstance(selected_pattern, Mapping):
        selected_pattern = {}

    def text_value(value: object) -> str | None:
        return str(value) if isinstance(value, str) and value else None

    tables: list[str] = []
    for table in planning.get("required_tables", [])[:16]:
        if not isinstance(table, Mapping):
            continue
        qualified = text_value(table.get("qualified_name"))
        if qualified:
            tables.append(qualified)

    dimensions: list[dict[str, Any]] = []
    for item in planning.get("detected_dimensions", [])[:16]:
        if not isinstance(item, Mapping):
            continue
        dimensions.append(
            {
                "canonical_value": text_value(
                    item.get("canonical_value")
                ),
                "target_table": text_value(item.get("target_table")),
                "target_column": text_value(item.get("target_column")),
                "grouping_requested": (
                    item.get("grouping_requested") is True
                ),
            }
        )

    operations: list[dict[str, Any]] = []
    for item in planning.get("analytical_operations", [])[:16]:
        if not isinstance(item, Mapping):
            continue
        requested_limit = item.get("requested_limit")
        operations.append(
            {
                "operation_type": text_value(
                    item.get("operation_type")
                ),
                "canonical_value": text_value(
                    item.get("canonical_value")
                ),
                "direction": text_value(item.get("direction")),
                "requested_limit": (
                    int(requested_limit)
                    if isinstance(requested_limit, int)
                    and not isinstance(requested_limit, bool)
                    else None
                ),
                "metric_ref": text_value(item.get("metric_ref")),
                "operand_metric_refs": [
                    str(value)
                    for value in item.get("operand_metric_refs", [])[:8]
                    if isinstance(value, str) and value
                ],
            }
        )

    metrics: list[dict[str, Any]] = []
    for item in planning.get("planned_metrics", [])[:16]:
        if not isinstance(item, Mapping):
            continue
        metrics.append(
            {
                "metric_ref": text_value(item.get("metric_ref")),
                "metric_concept": text_value(
                    item.get("metric_concept")
                ),
                "target_table": text_value(item.get("target_table")),
                "target_column": text_value(item.get("target_column")),
            }
        )

    filters: list[dict[str, Any]] = []
    for item in planning.get("planned_filters", [])[:16]:
        if not isinstance(item, Mapping):
            continue
        filters.append(
            {
                "filter_ref": text_value(item.get("filter_ref")),
                "filter_concept": text_value(
                    item.get("filter_concept")
                ),
                "scope": text_value(item.get("scope")),
                "required": item.get("required") is True,
            }
        )

    authorized_joins: list[dict[str, Any]] = []
    for item in planning.get("authorized_joins", [])[:16]:
        if not isinstance(item, Mapping):
            continue
        raw_rules = item.get("join_rules")
        authorized_joins.append(
            {
                "source_table": text_value(item.get("source_table")),
                "interpretation": text_value(item.get("interpretation")),
                "join_rule_count": (
                    len(raw_rules)
                    if isinstance(raw_rules, list)
                    else (
                        0
                        if raw_rules in (None, {}, [])
                        else None
                    )
                ),
            }
        )

    return {
        "available": True,
        "planner_version": text_value(query_plan.get("planner_version")),
        "intent_name": text_value(query_plan.get("intent_name")),
        "selected_pattern_name": text_value(
            selected_pattern.get("pattern_name")
        ),
        "required_tables": tables,
        "detected_dimensions": dimensions,
        "analytical_operations": operations,
        "planned_metrics": metrics,
        "planned_filters": filters,
        "authorized_joins": authorized_joins,
    }


def _intent_resolution_metadata(
    state: Mapping[str, Any],
) -> dict[str, Any]:
    """
    Expõe apenas diagnóstico agregado e seguro da resolução de intenção.

    O objetivo é permitir observabilidade do Shadow sem devolver regras,
    sinais, exemplos de negócio ou o catálogo bruto ao consumidor.
    """

    result = state.get("intent_resolution_result")
    if not isinstance(result, Mapping):
        return {"available": False}

    configuration = result.get("resolver_configuration")
    if not isinstance(configuration, Mapping):
        configuration = {}

    catalog = result.get("intent_catalog")
    if not isinstance(catalog, Mapping):
        catalog = {}

    def candidate_summary(value: object) -> dict[str, Any] | None:
        if not isinstance(value, Mapping):
            return None

        score = value.get("score")
        priority = value.get("best_priority")

        return {
            "intent_name": (
                str(value.get("intent_name"))
                if isinstance(value.get("intent_name"), str)
                else None
            ),
            "score": (
                float(score)
                if isinstance(score, (int, float))
                and not isinstance(score, bool)
                else None
            ),
            "best_priority": (
                float(priority)
                if isinstance(priority, (int, float))
                and not isinstance(priority, bool)
                else None
            ),
        }

    minimum_score = configuration.get("minimum_score")
    ambiguity_margin = configuration.get("ambiguity_margin")
    entries_evaluated = catalog.get("entries_evaluated")

    return {
        "available": True,
        "applied": result.get("applied") is True,
        "reason": (
            str(result.get("reason"))
            if isinstance(result.get("reason"), str)
            else None
        ),
        "resolver_version": (
            str(result.get("resolver_version"))
            if isinstance(result.get("resolver_version"), str)
            else None
        ),
        "minimum_score": (
            float(minimum_score)
            if isinstance(minimum_score, (int, float))
            and not isinstance(minimum_score, bool)
            else None
        ),
        "ambiguity_margin": (
            float(ambiguity_margin)
            if isinstance(ambiguity_margin, (int, float))
            and not isinstance(ambiguity_margin, bool)
            else None
        ),
        "best_candidate": candidate_summary(
            result.get("best_candidate")
        ),
        "second_candidate": candidate_summary(
            result.get("second_candidate")
        ),
        "catalog_available": catalog.get("available") is True,
        "catalog_entries_evaluated": (
            int(entries_evaluated)
            if isinstance(entries_evaluated, int)
            and not isinstance(entries_evaluated, bool)
            and entries_evaluated >= 0
            else None
        ),
    }


def _lineage(state: Mapping[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    for source, target in [
        ("sql_fingerprint", "sql_fingerprint"),
        ("context_fingerprint", "context_fingerprint"),
    ]:
        value = state.get(source)
        if isinstance(value, str) and value:
            output[target] = value
    for source, target in [
        ("security_result", "security_fingerprint"),
        ("contract_result", "contract_fingerprint"),
        ("engine_preflight_result", "preflight_fingerprint"),
    ]:
        value = state.get(source)
        if isinstance(value, Mapping):
            fingerprint = value.get("sql_fingerprint") or value.get(
                "request_fingerprint"
            )
            if isinstance(fingerprint, str) and fingerprint:
                output[target] = fingerprint
    return output


def state_errors(state: Mapping[str, Any]) -> list[InternalSqlAgentError]:
    output: list[InternalSqlAgentError] = []
    raw_errors = state.get("errors", [])
    if isinstance(raw_errors, list):
        for item in raw_errors[:8]:
            if isinstance(item, Mapping):
                output.append(
                    error(
                        str(item.get("code", "INTERNAL_FLOW_ERROR")),
                        str(item.get("stage", state.get("failure_stage", ""))),
                        str(item.get("message", "Flow rejected.")),
                        retryable=state.get("final_status")
                        == "infrastructure_error",
                    )
                )
    if not output and state.get("final_status") not in {"approved", "processing"}:
        output.append(
            error(
                "INTERNAL_FLOW_REJECTED",
                str(state.get("failure_stage", "")),
                "Flow did not complete.",
            )
        )
    return output


def error(
    code: str,
    stage: str,
    message: str,
    *,
    retryable: bool = False,
) -> InternalSqlAgentError:
    return {
        "code": _safe_code(code),
        "stage": _safe_code(stage).lower(),
        "message": _safe_message(message),
        "retryable": retryable,
    }


def status_from_final_status(value: object) -> str:
    if value == "approved":
        return "success"
    if value in {"rejected", "invalid_request"}:
        return "rejected"
    return "infrastructure_error"


def preflight_approved(state: Mapping[str, Any]) -> bool:
    result = state.get("engine_preflight_result")
    return (
        state.get("final_status") == "processing"
        and isinstance(result, Mapping)
        and result.get("status") == "approved"
        and result.get("approved") is True
        and result.get("executed") is False
    )


def preflight_repairable(state: Mapping[str, Any]) -> bool:
    result = state.get("engine_preflight_result")
    return (
        state.get("final_status") == "rejected"
        and isinstance(result, Mapping)
        and result.get("status") == "rejected"
        and result.get("repairable") is True
    )


def principal_to_user(
    value: object,
) -> InternalSqlAgentPrincipal:
    if not isinstance(value, Mapping):
        return {}
    output: InternalSqlAgentPrincipal = {}
    for key in ("id", "email", "profile", "organization_id"):
        item = value.get(key)
        if isinstance(item, str) and item:
            output[key] = item  # type: ignore[literal-required]
    return output


def _valid_principal(value: object) -> bool:
    if not isinstance(value, Mapping) or not value:
        return False
    allowed = {"id", "email", "profile", "organization_id"}
    if set(value) - allowed:
        return False
    return any(
        _valid_safe_text(value.get(key), 254)
        for key in ("id", "email", "profile", "organization_id")
    )


def _valid_metadata(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, Mapping) or len(value) > 16:
        return False
    for key, item in value.items():
        if not _valid_identifier(key, 64):
            return False
        if item is None or isinstance(item, bool):
            continue
        if isinstance(item, int) and not isinstance(item, bool):
            continue
        if isinstance(item, str) and _valid_safe_text(item, 256):
            continue
        return False
    return True


def _contains_blocked_payload_key(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key.casefold() in _BLOCKED_PAYLOAD_KEYS:
                return True
            if _contains_blocked_payload_key(item):
                return True
    elif isinstance(value, list):
        return any(_contains_blocked_payload_key(item) for item in value)
    return False


def _valid_question(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value.strip())
        and not _has_forbidden_question_control(value)
    )


def _has_forbidden_question_control(value: str) -> bool:
    """
    Perguntas podem legitimamente conter tabulação e quebras de linha.

    Outros caracteres de controle continuam bloqueados para evitar
    payloads ambíguos ou invisíveis no contrato interno.
    """

    allowed_whitespace = {"\t", "\n", "\r"}
    return any(
        (ord(char) < 32 or ord(char) == 127)
        and char not in allowed_whitespace
        for char in value
    )


def _valid_identifier(value: object, max_length: int) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > max_length
    ):
        return False
    return all(char in _SAFE_ID_CHARS for char in value)


def _valid_safe_text(value: object, max_length: int) -> bool:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > max_length
    ):
        return False
    if _has_control(value):
        return False
    return all(char.isalnum() or char in _SAFE_TEXT_CHARS for char in value)


def _has_control(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _safe_code(value: object) -> str:
    text = str(value or "").upper()
    return "".join(
        char if char.isalnum() or char == "_" else "_"
        for char in text
    )[:96] or "UNKNOWN"


def _safe_message(value: object) -> str:
    text = str(value or "Request could not be processed.")
    if _has_control(text):
        return "Request could not be processed."
    lowered = text.casefold()
    if any(marker in lowered for marker in ("token", "secret", "password", "dsn")):
        return "Request could not be processed."
    return text[:160]


def _safe_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def string_field(value: object, key: str) -> str:
    if isinstance(value, Mapping) and isinstance(value.get(key), str):
        return str(value[key])
    return ""


def new_run_id(id_generator: IdGenerator) -> str:
    value = id_generator()
    if not _valid_identifier(value, 128):
        raise ValueError("id_generator returned invalid id.")
    return value


def not_run_result() -> dict[str, object]:
    return {"status": "not_run", "errors": [], "warnings": []}

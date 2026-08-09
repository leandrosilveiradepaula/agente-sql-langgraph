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
        "lineage": _lineage(state),
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
    return isinstance(value, str) and bool(value.strip()) and not _has_control(value)


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

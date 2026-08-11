from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any, TypedDict

from app.domain.shadow_evidence_types import ShadowRunRecord, validate_shadow_run_record
from app.domain.shadow_run_visualization import (
    ShadowRunVisualization,
    visualize_shadow_run,
)
from app.ports.shadow_evidence_repository import ShadowEvidenceRepository


SHADOW_READ_CONTRACT_VERSION = "1"
DEFAULT_SHADOW_RUN_LIST_LIMIT = 50
MAX_SHADOW_RUN_LIST_LIMIT = 100


class ShadowReadError(RuntimeError):
    def __init__(self, code: str, status_code: int) -> None:
        self.code = code
        self.status_code = status_code
        super().__init__(code)


class ShadowRunSafeView(TypedDict):
    contract_version: str
    shadow_record_id: str
    agent_run_id: str
    run_id: str
    event_type: str
    status: str
    created_at: str
    completed_at: str | None
    requires_reapproval: bool
    fingerprints: dict[str, str]
    lineage: dict[str, str]
    timings: dict[str, int]
    warnings: list[dict[str, str]]
    errors: list[dict[str, str]]
    gates: dict[str, dict[str, str | int | bool]]
    persistence: dict[str, str | None]


class ShadowRunListItem(TypedDict):
    shadow_record_id: str
    agent_run_id: str
    run_id: str
    event_type: str
    status: str
    created_at: str
    completed_at: str | None
    requires_reapproval: bool
    has_repair: bool
    has_error: bool
    fingerprints: dict[str, str]


class GetShadowRunSafeViewUseCase:
    def __init__(self, *, repository: ShadowEvidenceRepository) -> None:
        _require_repository(repository)
        self._repository = repository

    def execute(self, shadow_record_id: str) -> ShadowRunSafeView:
        record = _fetch_record(self._repository, shadow_record_id)
        return safe_shadow_run_view(record)


class ListAgentShadowRunsUseCase:
    def __init__(self, *, repository: ShadowEvidenceRepository) -> None:
        _require_repository(repository)
        self._repository = repository

    def execute(
        self,
        agent_run_id: str,
        *,
        limit: int = DEFAULT_SHADOW_RUN_LIST_LIMIT,
    ) -> dict[str, Any]:
        safe_limit = validate_shadow_run_list_limit(limit)
        records = _list_records(self._repository, agent_run_id)
        ordered = sorted(
            records,
            key=lambda record: (
                str(record.get("created_at", "")),
                str(record.get("event_type", "")),
                str(record.get("shadow_record_id", "")),
            ),
        )
        return {
            "contract_version": SHADOW_READ_CONTRACT_VERSION,
            "agent_run_id": agent_run_id,
            "limit": safe_limit,
            "items": [shadow_run_list_item(record) for record in ordered[:safe_limit]],
        }


class GetShadowRunVisualizationUseCase:
    def __init__(self, *, repository: ShadowEvidenceRepository) -> None:
        _require_repository(repository)
        self._repository = repository

    def execute(self, shadow_record_id: str) -> dict[str, Any]:
        record = _fetch_record(self._repository, shadow_record_id)
        visualization = visualize_shadow_run(record)
        return safe_shadow_run_visualization(visualization)


def safe_shadow_run_view(record: ShadowRunRecord) -> ShadowRunSafeView:
    captured = validate_shadow_run_record(record)
    evidence = _mapping(captured.get("langgraph_evidence"))
    return {
        "contract_version": SHADOW_READ_CONTRACT_VERSION,
        "shadow_record_id": captured["shadow_record_id"],
        "agent_run_id": captured["agent_run_id"],
        "run_id": captured["run_id"],
        "event_type": captured["event_type"],
        "status": captured["status"],
        "created_at": captured["created_at"],
        "completed_at": captured.get("completed_at"),
        "requires_reapproval": bool(captured.get("requires_reapproval")),
        "fingerprints": _safe_fingerprints(captured.get("fingerprints")),
        "lineage": _safe_lineage(captured.get("lineage")),
        "timings": _safe_timings(evidence.get("timings")),
        "warnings": _safe_diagnostics(evidence.get("warnings")),
        "errors": _safe_diagnostics(evidence.get("errors")),
        "gates": {
            "security": _safe_result_summary(evidence.get("security_result")),
            "contract": _safe_result_summary(evidence.get("contract_result")),
            "preflight": _safe_result_summary(evidence.get("preflight_result")),
        },
        "persistence": {
            "evidence_fingerprint": captured["evidence_fingerprint"],
            "langgraph_version": _safe_text(captured.get("langgraph_version")),
            "langgraph_commit": _safe_text(captured.get("langgraph_commit")),
        },
    }


def shadow_run_list_item(record: ShadowRunRecord) -> ShadowRunListItem:
    captured = validate_shadow_run_record(record)
    visualization = visualize_shadow_run(captured)
    flags = visualization["flags"]
    return {
        "shadow_record_id": captured["shadow_record_id"],
        "agent_run_id": captured["agent_run_id"],
        "run_id": captured["run_id"],
        "event_type": captured["event_type"],
        "status": captured["status"],
        "created_at": captured["created_at"],
        "completed_at": captured.get("completed_at"),
        "requires_reapproval": bool(captured.get("requires_reapproval")),
        "has_repair": bool(flags["has_repair"]),
        "has_error": bool(flags["has_error"]),
        "fingerprints": _safe_fingerprints(captured.get("fingerprints")),
    }


def safe_shadow_run_visualization(
    visualization: ShadowRunVisualization,
) -> dict[str, Any]:
    return {
        "contract_version": SHADOW_READ_CONTRACT_VERSION,
        "run": deepcopy(visualization["run"]),
        "steps": deepcopy(visualization["steps"]),
        "edges": deepcopy(visualization["edges"]),
        "flags": deepcopy(visualization["flags"]),
    }


def validate_shadow_read_id(value: str, *, field: str) -> str:
    text = value.strip()
    if not text or len(text) > 160:
        raise ShadowReadError(f"{field.upper()}_INVALID", 400)
    if text in {".", ".."} or "/" in text or "\\" in text:
        raise ShadowReadError(f"{field.upper()}_INVALID", 400)
    if not all(_is_ascii_id_char(char) for char in text):
        raise ShadowReadError(f"{field.upper()}_INVALID", 400)
    return text


def validate_shadow_run_list_limit(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ShadowReadError("SHADOW_RUN_LIMIT_INVALID", 400)
    if value < 1 or value > MAX_SHADOW_RUN_LIST_LIMIT:
        raise ShadowReadError("SHADOW_RUN_LIMIT_INVALID", 400)
    return value


def _fetch_record(
    repository: ShadowEvidenceRepository,
    shadow_record_id: str,
) -> ShadowRunRecord:
    try:
        result = repository.fetch_by_shadow_record_id(shadow_record_id)
    except Exception as error:
        del error
        raise ShadowReadError("SHADOW_REPOSITORY_UNAVAILABLE", 503) from None
    if not isinstance(result, Mapping):
        raise ShadowReadError("SHADOW_REPOSITORY_UNAVAILABLE", 503)
    status = result.get("status")
    if status == "unavailable":
        raise ShadowReadError("SHADOW_REPOSITORY_UNAVAILABLE", 503)
    if status == "not_found":
        raise ShadowReadError("SHADOW_RECORD_NOT_FOUND", 404)
    if status != "ok":
        raise ShadowReadError("SHADOW_REPOSITORY_UNAVAILABLE", 503)
    record = result.get("record")
    if record is None:
        raise ShadowReadError("SHADOW_REPOSITORY_UNAVAILABLE", 503)
    return validate_shadow_run_record(record)


def _list_records(
    repository: ShadowEvidenceRepository,
    agent_run_id: str,
) -> list[ShadowRunRecord]:
    try:
        result = repository.list_by_agent_run_id(agent_run_id)
    except Exception as error:
        del error
        raise ShadowReadError("SHADOW_REPOSITORY_UNAVAILABLE", 503) from None
    if not isinstance(result, Mapping):
        raise ShadowReadError("SHADOW_REPOSITORY_UNAVAILABLE", 503)
    status = result.get("status")
    if status == "unavailable":
        raise ShadowReadError("SHADOW_REPOSITORY_UNAVAILABLE", 503)
    if status != "ok":
        raise ShadowReadError("SHADOW_REPOSITORY_UNAVAILABLE", 503)
    records = result.get("records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes)):
        raise ShadowReadError("SHADOW_REPOSITORY_UNAVAILABLE", 503)
    return [validate_shadow_run_record(record) for record in records]


def _safe_fingerprints(value: object) -> dict[str, str]:
    raw = _mapping(value)
    output: dict[str, str] = {}
    for key, item in raw.items():
        safe_key = _safe_key(key)
        safe_value = _safe_text(item)
        if safe_key and safe_value:
            output[safe_key] = safe_value
    return output


def _safe_lineage(value: object) -> dict[str, str]:
    raw = _mapping(value)
    allowed = {
        "context_fingerprint",
        "context_version",
        "sql_fingerprint",
        "intent",
        "failure_stage",
        "current_stage",
        "security_fingerprint",
        "contract_fingerprint",
        "preflight_fingerprint",
    }
    output: dict[str, str] = {}
    for key in allowed:
        safe_value = _safe_text(raw.get(key))
        if safe_value:
            output[key] = safe_value
    return output


def _safe_timings(value: object) -> dict[str, int]:
    raw = _mapping(value)
    output: dict[str, int] = {}
    for key, item in raw.items():
        safe_key = _safe_key(key)
        if (
            safe_key
            and isinstance(item, int)
            and not isinstance(item, bool)
            and item >= 0
        ):
            output[safe_key] = item
    return output


def _safe_diagnostics(value: object) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    output: list[dict[str, str]] = []
    for item in value:
        raw = _mapping(item)
        safe: dict[str, str] = {}
        for key in ("code", "stage", "failure_category"):
            text = _safe_text(raw.get(key))
            if text:
                safe[key] = text
        if safe:
            output.append(safe)
    return output[:32]


def _safe_result_summary(value: object) -> dict[str, str | int | bool]:
    raw = _mapping(value)
    output: dict[str, str | int | bool] = {}
    for key in ("status", "failure_category"):
        text = _safe_text(raw.get(key))
        if text:
            output[key] = text
    for key in ("duration_ms",):
        item = raw.get(key)
        if isinstance(item, int) and not isinstance(item, bool) and item >= 0:
            output[key] = item
    for key in ("repairable", "executed", "approved"):
        item = raw.get(key)
        if isinstance(item, bool):
            output[key] = item
    code = _first_diagnostic_code(raw)
    if code:
        output["error_code"] = code
    return output


def _first_diagnostic_code(value: Mapping[str, Any]) -> str:
    for key in ("errors", "warnings", "findings"):
        items = value.get(key)
        if isinstance(items, list) and items and isinstance(items[0], Mapping):
            code = _safe_text(items[0].get("code"))
            if code:
                return code
    return ""


def _require_repository(repository: ShadowEvidenceRepository) -> None:
    if repository is None:
        raise RuntimeError("shadow evidence repository must be injected.")
    if not callable(getattr(repository, "fetch_by_shadow_record_id", None)):
        raise RuntimeError("shadow evidence repository must support fetch.")
    if not callable(getattr(repository, "list_by_agent_run_id", None)):
        raise RuntimeError("shadow evidence repository must support list.")


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_key(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(
        char if _is_ascii_token_char(char, extra="_") else "_"
        for char in value.strip()
    )[:64]


def _safe_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(
        char if _is_ascii_token_char(char, extra="._:-") else "_"
        for char in value.strip()
    )[:128]


def _is_ascii_id_char(char: str) -> bool:
    return _is_ascii_token_char(char, extra="-_")


def _is_ascii_token_char(char: str, *, extra: str) -> bool:
    return (
        len(char) == 1
        and (
            "A" <= char <= "Z"
            or "a" <= char <= "z"
            or "0" <= char <= "9"
            or char in extra
        )
    )

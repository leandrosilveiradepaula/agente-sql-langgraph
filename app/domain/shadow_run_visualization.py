from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any, Literal, TypedDict, cast

from app.domain.result_normalization import stable_fingerprint
from app.domain.shadow_evidence_types import (
    ShadowEventType,
    ShadowRunRecord,
    validate_shadow_run_record,
)


StepStatus = Literal["ok", "warning", "error", "unknown"]
StepType = Literal[
    "input",
    "node",
    "gate",
    "preflight",
    "repair",
    "terminal",
    "persistence",
]
EdgeType = Literal["normal", "conditional", "repair", "terminal"]


class ShadowRunStep(TypedDict):
    id: str
    label: str
    step_type: StepType
    status: StepStatus
    sequence: int
    metadata: dict[str, str | int | bool | None]


class ShadowRunEdge(TypedDict):
    source: str
    target: str
    edge_type: EdgeType


class ShadowRunFlags(TypedDict):
    requires_reapproval: bool
    has_repair: bool
    has_error: bool
    persistence_failure: bool
    has_unknown_evidence: bool


class ShadowRunSummary(TypedDict):
    shadow_record_id: str
    agent_run_id: str
    run_id: str
    event_type: ShadowEventType
    final_status: str
    created_at: str
    completed_at: str | None
    duration_ms: int | None


class ShadowRunVisualization(TypedDict):
    run: ShadowRunSummary
    steps: list[ShadowRunStep]
    edges: list[ShadowRunEdge]
    flags: ShadowRunFlags


class ShadowAgentRunItem(TypedDict):
    shadow_record_id: str
    run_id: str
    event_type: ShadowEventType
    final_status: str


class ShadowAgentRunCorrelation(TypedDict):
    agent_run_id: str
    records: list[ShadowAgentRunItem]


_ALLOWED_METADATA_KEYS = {
    "approved_sql_fingerprint",
    "attempt",
    "context_fingerprint",
    "context_version",
    "contract_request_fingerprint",
    "contract_sql_fingerprint",
    "cycle",
    "duration_ms",
    "error_code",
    "evidence_fingerprint",
    "evidence_not_recorded",
    "executed",
    "failure_category",
    "generated_sql_fingerprint",
    "intent",
    "plan",
    "preflight_request_fingerprint",
    "preflight_sql_fingerprint",
    "question_fingerprint",
    "reason",
    "repair_applied",
    "repairable",
    "repaired_sql_fingerprint",
    "repaired_sql_proposal_fingerprint",
    "requires_reapproval",
    "security_request_fingerprint",
    "security_sql_fingerprint",
    "sql_after_fingerprint",
    "sql_before_fingerprint",
    "status",
}


def visualize_shadow_run(record: ShadowRunRecord) -> ShadowRunVisualization:
    captured = validate_shadow_run_record(record)
    if captured["event_type"] == "generate":
        return _visualize_generate(captured)
    if captured["event_type"] == "execute_approved_shadow":
        return _visualize_execute_approved(captured)
    return _base_visualization(captured, has_unknown_evidence=True)


def correlate_agent_run(
    records: Sequence[ShadowRunRecord],
    agent_run_id: str | None = None,
) -> ShadowAgentRunCorrelation:
    captured = [validate_shadow_run_record(record) for record in records]
    if agent_run_id is not None:
        captured = [
            record for record in captured if record["agent_run_id"] == agent_run_id
        ]
        if not captured:
            return {"agent_run_id": agent_run_id, "records": []}
    agent_run_ids = {record["agent_run_id"] for record in captured}
    if len(agent_run_ids) != 1:
        raise ValueError("records must share one agent_run_id")
    ordered = sorted(
        captured,
        key=lambda item: (
            item.get("created_at", ""),
            item["event_type"],
            item["shadow_record_id"],
        ),
    )
    return {
        "agent_run_id": ordered[0]["agent_run_id"],
        "records": [
            {
                "shadow_record_id": record["shadow_record_id"],
                "run_id": record["run_id"],
                "event_type": record["event_type"],
                "final_status": record["status"],
            }
            for record in ordered
        ],
    }


def _visualize_generate(record: ShadowRunRecord) -> ShadowRunVisualization:
    visualization = _base_visualization(record)
    evidence = _evidence(record)
    fingerprints = _fingerprints(record)
    lineage = _mapping(record.get("lineage"))
    final_stage = _safe_text(lineage.get("failure_stage")) or _failure_stage(evidence)

    if record.get("question") or fingerprints.get("question"):
        _append_step(
            visualization,
            "receive_question",
            "receive_question",
            "node",
            "ok",
            {"question_fingerprint": fingerprints.get("question")},
        )
    if record.get("semantic_context") or lineage.get("context_version"):
        _append_step(
            visualization,
            "load_context",
            "load_context",
            "node",
            "ok",
            {
                "context_version": _safe_text(lineage.get("context_version")),
                "context_fingerprint": _safe_text(lineage.get("context_fingerprint")),
            },
        )
    if evidence.get("intent") or lineage.get("intent"):
        _append_step(
            visualization,
            "classify_intent",
            "classify_intent",
            "node",
            "ok",
            {"intent": _safe_text(evidence.get("intent")) or _safe_text(lineage.get("intent"))},
        )
    if isinstance(evidence.get("plan"), Mapping):
        _append_step(
            visualization,
            "build_plan",
            "build_plan",
            "node",
            "ok",
            {"plan": "recorded"},
        )
    generated_sql_fingerprint = _generated_sql_fingerprint(evidence)
    if (
        generated_sql_fingerprint
        or record.get("generated_sql")
        or fingerprints.get("langgraph_sql")
    ):
        _append_step(
            visualization,
            "generate_sql",
            "generate_sql",
            "node",
            _stage_status(record, "generate_sql"),
            _generated_sql_metadata(generated_sql_fingerprint),
        )

    repair_history = _repair_history(evidence)
    if repair_history:
        _append_repair_cycles(visualization, repair_history, evidence, record)
    else:
        _append_observed_gate_path(visualization, evidence, record, final_stage)

    _append_final(visualization, record)
    return _finalize_visualization(visualization)


def _visualize_execute_approved(record: ShadowRunRecord) -> ShadowRunVisualization:
    visualization = _base_visualization(record)
    evidence = _evidence(record)
    fingerprints = _fingerprints(record)
    if record.get("approved_sql_original") or fingerprints.get("approved_sql"):
        _append_step(
            visualization,
            "approved_sql_received",
            "approved_sql_received",
            "input",
            "ok",
            {"approved_sql_fingerprint": fingerprints.get("approved_sql")},
        )
    _append_observed_gate_path(
        visualization,
        evidence,
        record,
        _failure_stage(evidence),
    )
    if record.get("repaired_sql_proposal") or record.get("requires_reapproval"):
        _append_step(
            visualization,
            "repair_sql_proposal",
            "repair_sql_proposal",
            "repair",
            "warning",
            {
                "repaired_sql_proposal_fingerprint": fingerprints.get(
                    "repaired_sql_proposal"
                ),
            },
        )
        if record.get("requires_reapproval"):
            _append_step(
                visualization,
                "requires_reapproval",
                "requires_reapproval",
                "terminal",
                "warning",
                {"requires_reapproval": True},
            )
    _append_final(visualization, record)
    return _finalize_visualization(visualization)


def _append_observed_gate_path(
    visualization: ShadowRunVisualization,
    evidence: Mapping[str, Any],
    record: ShadowRunRecord,
    final_stage: str,
) -> None:
    security = _mapping(evidence.get("security_result"))
    contract = _mapping(evidence.get("contract_result"))
    preflight = _mapping(evidence.get("preflight_result"))
    if _is_recorded_result(security):
        _append_step(
            visualization,
            "security_gate",
            "security_gate",
            "gate",
            _result_status(security, final_stage == "security_gate"),
            _result_metadata(security, "security"),
        )
    if _result_approved(security) and _is_recorded_result(contract):
        _append_step(
            visualization,
            "contract_gate",
            "contract_gate",
            "gate",
            _result_status(contract, final_stage == "contract_gate"),
            _result_metadata(contract, "contract"),
        )
    if _result_approved(contract) and _is_recorded_result(preflight):
        _append_step(
            visualization,
            "engine_preflight",
            "engine_preflight",
            "preflight",
            _preflight_status(preflight, record),
            _result_metadata(preflight, "preflight"),
        )


def _append_gate_cycle_from_history(
    visualization: ShadowRunVisualization,
    history_entry: Mapping[str, Any],
    cycle: int,
) -> None:
    _append_step(
        visualization,
        f"security_gate_cycle_{cycle}",
        "security_gate",
        "gate",
        "ok",
        {"cycle": cycle},
    )
    _append_step(
        visualization,
        f"contract_gate_cycle_{cycle}",
        "contract_gate",
        "gate",
        "ok",
        {"cycle": cycle},
    )
    _append_step(
        visualization,
        f"engine_preflight_cycle_{cycle}",
        "engine_preflight",
        "preflight",
        "warning",
        {
            "cycle": cycle,
            "repairable": True,
            "failure_category": _safe_text(history_entry.get("failure_category")),
            "error_code": _safe_text(history_entry.get("error_code")),
        },
    )


def _append_repair_cycles(
    visualization: ShadowRunVisualization,
    repair_history: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, Any],
    record: ShadowRunRecord,
) -> None:
    for index, history_entry in enumerate(repair_history, start=1):
        _append_gate_cycle_from_history(visualization, history_entry, cycle=index)
        _append_step(
            visualization,
            f"repair_sql_attempt_{index}",
            "repair_sql",
            "repair",
            _repair_status(history_entry),
            _repair_metadata(history_entry, attempt=index),
        )
    _append_final_gate_cycle(
        visualization,
        evidence,
        record,
        cycle=len(repair_history) + 1,
    )


def _append_final_gate_cycle(
    visualization: ShadowRunVisualization,
    evidence: Mapping[str, Any],
    record: ShadowRunRecord,
    cycle: int = 2,
) -> None:
    del record
    security = _mapping(evidence.get("security_result"))
    contract = _mapping(evidence.get("contract_result"))
    preflight = _mapping(evidence.get("preflight_result"))
    if _is_recorded_result(security):
        _append_step(
            visualization,
            "security_gate_after_repair",
            "security_gate",
            "gate",
            _result_status(security, False),
            {**_result_metadata(security, "security"), "cycle": cycle},
        )
    if _is_recorded_result(contract):
        _append_step(
            visualization,
            "contract_gate_after_repair",
            "contract_gate",
            "gate",
            _result_status(contract, False),
            {**_result_metadata(contract, "contract"), "cycle": cycle},
        )
    if _is_recorded_result(preflight):
        _append_step(
            visualization,
            "engine_preflight_after_repair",
            "engine_preflight",
            "preflight",
            _result_status(preflight, False),
            {**_result_metadata(preflight, "preflight"), "cycle": cycle},
        )


def _append_final(
    visualization: ShadowRunVisualization,
    record: ShadowRunRecord,
) -> None:
    persistence_error = _persistence_error(_evidence(record))
    if persistence_error:
        _append_step(
            visualization,
            "persistence_failure",
            "persistence_failure",
            "persistence",
            "error",
            {"error_code": persistence_error},
        )
    if not visualization["steps"] or (
        record["status"] != "success"
        and len(visualization["steps"]) == 1
        and visualization["steps"][0]["label"] == "receive_question"
    ):
        _append_step(
            visualization,
            "evidence_not_recorded",
            "evidence_not_recorded",
            "terminal",
            "unknown",
            {"reason": "no_executed_step_evidence"},
        )
    _append_step(
        visualization,
        "final",
        "final",
        "terminal",
        "ok" if record["status"] == "success" else "error",
        {
            "status": record["status"],
            "evidence_fingerprint": record["evidence_fingerprint"],
        },
    )


def _append_step(
    visualization: ShadowRunVisualization,
    step_id: str,
    label: str,
    step_type: StepType,
    status: StepStatus,
    metadata: Mapping[str, str | int | bool | None] | None = None,
) -> None:
    sequence = len(visualization["steps"]) + 1
    candidate = _unique_step_id(visualization, step_id)
    if visualization["steps"]:
        previous = visualization["steps"][-1]["id"]
        visualization["edges"].append(
            {
                "source": previous,
                "target": candidate,
                "edge_type": _edge_type(previous, candidate, step_type),
            }
        )
    visualization["steps"].append(
        {
            "id": candidate,
            "label": label,
            "step_type": step_type,
            "status": status,
            "sequence": sequence,
            "metadata": _safe_metadata(metadata or {}),
        }
    )


def _finalize_visualization(
    visualization: ShadowRunVisualization,
) -> ShadowRunVisualization:
    steps = visualization["steps"]
    visualization["flags"] = {
        "requires_reapproval": visualization["flags"]["requires_reapproval"],
        "has_repair": any(step["step_type"] == "repair" for step in steps),
        "has_error": any(step["status"] == "error" for step in steps),
        "persistence_failure": any(
            _metadata_has_prefix(step["metadata"], "SHADOW_REPOSITORY")
            for step in steps
        ),
        "has_unknown_evidence": any(step["status"] == "unknown" for step in steps),
    }
    return visualization


def _base_visualization(
    record: ShadowRunRecord,
    *,
    has_unknown_evidence: bool = False,
) -> ShadowRunVisualization:
    return {
        "run": {
            "shadow_record_id": record["shadow_record_id"],
            "agent_run_id": record["agent_run_id"],
            "run_id": record["run_id"],
            "event_type": record["event_type"],
            "final_status": record["status"],
            "created_at": record["created_at"],
            "completed_at": record.get("completed_at"),
            "duration_ms": None,
        },
        "steps": [],
        "edges": [],
        "flags": {
            "requires_reapproval": bool(record.get("requires_reapproval")),
            "has_repair": False,
            "has_error": record["status"] != "success",
            "persistence_failure": False,
            "has_unknown_evidence": has_unknown_evidence,
        },
    }


def _edge_type(source: str, target: str, step_type: StepType) -> EdgeType:
    if target == "final":
        return "terminal"
    if step_type == "repair" or "repair" in source or "repair" in target:
        return "repair"
    if step_type in {"gate", "preflight", "terminal"}:
        return "conditional"
    return "normal"


def _result_status(result: Mapping[str, Any], failed: bool) -> StepStatus:
    status = _safe_text(result.get("status"))
    if status in {"approved", "success", "repaired"}:
        return "ok"
    if status == "rejected":
        return "error" if failed else "warning"
    if status == "not_run":
        return "unknown"
    if status:
        return "error"
    return "unknown"


def _preflight_status(
    result: Mapping[str, Any],
    record: ShadowRunRecord,
) -> StepStatus:
    status = _safe_text(result.get("status"))
    if status == "approved":
        return "ok"
    if bool(result.get("repairable")) or record.get("repaired_sql_proposal"):
        return "warning"
    return _result_status(result, record["status"] != "success")


def _stage_status(record: ShadowRunRecord, stage: str) -> StepStatus:
    if record["status"] == "infrastructure_error":
        errors = _errors(_evidence(record))
        if any(_safe_text(error.get("stage")) == stage for error in errors):
            return "error"
    return "ok"


def _repair_status(history_entry: Mapping[str, Any]) -> StepStatus:
    if history_entry.get("repair_applied") is True:
        return "ok"
    if history_entry.get("error_code"):
        return "error"
    return "warning"


def _result_metadata(
    result: Mapping[str, Any],
    prefix: str,
) -> dict[str, str | int | bool | None]:
    metadata: dict[str, str | int | bool | None] = {
        "status": _safe_text(result.get("status")),
        "duration_ms": _safe_int(result.get("duration_ms")),
        "repairable": _safe_bool(result.get("repairable")),
        "executed": _safe_bool(result.get("executed")),
    }
    for key in ("sql_fingerprint", "request_fingerprint"):
        value = _safe_text(result.get(key))
        if value:
            metadata[f"{prefix}_{key}"] = value
    code = _first_code(result)
    if code:
        metadata["error_code"] = code
    return metadata


def _generated_sql_fingerprint(evidence: Mapping[str, Any]) -> str:
    generated_sql = evidence.get("generated_sql")
    if not isinstance(generated_sql, str) or not generated_sql:
        return ""
    return stable_fingerprint(generated_sql)


def _generated_sql_metadata(
    fingerprint: str,
) -> dict[str, str | int | bool | None]:
    if fingerprint:
        return {"generated_sql_fingerprint": fingerprint}
    return {"evidence_not_recorded": True}


def _repair_metadata(
    history_entry: Mapping[str, Any],
    *,
    attempt: int,
) -> dict[str, str | int | bool | None]:
    recorded_attempt = _safe_int(history_entry.get("attempt")) or attempt
    return {
        "attempt": recorded_attempt,
        "repair_applied": _safe_bool(history_entry.get("repair_applied")),
        "failure_category": _safe_text(history_entry.get("failure_category")),
        "sql_before_fingerprint": _safe_text(
            history_entry.get("sql_before_fingerprint")
        ),
        "sql_after_fingerprint": _safe_text(
            history_entry.get("sql_after_fingerprint")
        ),
        "repaired_sql_fingerprint": _safe_text(
            history_entry.get("sql_after_fingerprint")
        ),
        "duration_ms": _safe_int(history_entry.get("duration_ms")),
    }


def _first_code(result: Mapping[str, Any]) -> str | None:
    for key in ("errors", "findings"):
        value = result.get(key)
        if isinstance(value, list) and value and isinstance(value[0], Mapping):
            return _safe_text(value[0].get("code"))
    return None


def _failure_stage(evidence: Mapping[str, Any]) -> str:
    response = _mapping(evidence.get("response"))
    metadata = _mapping(response.get("metadata"))
    return _safe_text(metadata.get("failure_stage"))


def _evidence(record: ShadowRunRecord) -> Mapping[str, Any]:
    return _mapping(record.get("langgraph_evidence"))


def _fingerprints(record: ShadowRunRecord) -> Mapping[str, str]:
    raw = _mapping(record.get("fingerprints"))
    output: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(key, str) and isinstance(value, str) and value:
            output[key] = value
    return output


def _repair_history(evidence: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = evidence.get("repair_history")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _errors(evidence: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = evidence.get("errors")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _persistence_error(evidence: Mapping[str, Any]) -> str:
    for error in _errors(evidence):
        code = _safe_text(error.get("code"))
        stage = _safe_text(error.get("stage"))
        if code.startswith("SHADOW_REPOSITORY") or stage == "persist_shadow":
            return code or "SHADOW_REPOSITORY_ERROR"
    return ""


def _is_recorded_result(result: Mapping[str, Any]) -> bool:
    status = result.get("status")
    return isinstance(status, str) and status != "not_run"


def _result_approved(result: Mapping[str, Any]) -> bool:
    return _safe_text(result.get("status")) in {"approved", "success"}


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _safe_metadata(
    metadata: Mapping[str, str | int | bool | None],
) -> dict[str, str | int | bool | None]:
    output: dict[str, str | int | bool | None] = {}
    for key, value in metadata.items():
        if value in {"", None}:
            continue
        safe_key = "".join(
            char if char.isalnum() or char == "_" else "_"
            for char in str(key)
        )[:64]
        if not safe_key or safe_key not in _ALLOWED_METADATA_KEYS:
            continue
        if isinstance(value, bool):
            output[safe_key] = value
        elif isinstance(value, int):
            output[safe_key] = value
        else:
            safe_value = _safe_text(value)
            if safe_value:
                output[safe_key] = safe_value
    return output


def _safe_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(
        char if char.isalnum() or char in "._:-" else "_"
        for char in value.strip()
    )[:96]


def _safe_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _safe_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _metadata_has_prefix(
    metadata: Mapping[str, str | int | bool | None],
    prefix: str,
) -> bool:
    return any(
        isinstance(value, str) and value.startswith(prefix)
        for value in metadata.values()
    )


def _unique_step_id(
    visualization: ShadowRunVisualization,
    step_id: str,
) -> str:
    existing = {step["id"] for step in visualization["steps"]}
    if step_id not in existing:
        return step_id
    index = 2
    while f"{step_id}_{index}" in existing:
        index += 1
    return f"{step_id}_{index}"


def clone_visualization(
    visualization: ShadowRunVisualization,
) -> ShadowRunVisualization:
    return cast(ShadowRunVisualization, deepcopy(visualization))

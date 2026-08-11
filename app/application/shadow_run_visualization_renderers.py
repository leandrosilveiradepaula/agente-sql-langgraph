from __future__ import annotations

from collections.abc import Mapping

from app.domain.shadow_run_visualization import (
    ShadowAgentRunCorrelation,
    ShadowRunStep,
    ShadowRunVisualization,
)


_ALLOWED_RENDER_METADATA_KEYS = {
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


def render_mermaid(visualization: ShadowRunVisualization) -> str:
    lines = ["flowchart TD"]
    for step in visualization["steps"]:
        label = _mermaid_label(step)
        lines.append(f"  {_node_id(step['id'])}[\"{label}\"]")
    for edge in visualization["edges"]:
        arrow = "-.->" if edge["edge_type"] in {"conditional", "repair"} else "-->"
        lines.append(f"  {_node_id(edge['source'])} {arrow} {_node_id(edge['target'])}")
    lines.extend(
        [
            "  classDef ok fill:#e9f7ef,stroke:#2e7d32,color:#1b1b1b",
            "  classDef warning fill:#fff8e1,stroke:#f9a825,color:#1b1b1b",
            "  classDef error fill:#ffebee,stroke:#c62828,color:#1b1b1b",
            "  classDef unknown fill:#eceff1,stroke:#607d8b,color:#1b1b1b",
        ]
    )
    for step in visualization["steps"]:
        lines.append(f"  class {_node_id(step['id'])} {step['status']}")
    return "\n".join(lines).strip() + "\n"


def render_timeline(visualization: ShadowRunVisualization) -> str:
    lines = [
        (
            f"run shadow_record_id={_safe_line_text(visualization['run']['shadow_record_id'])} "
            f"agent_run_id={_safe_line_text(visualization['run']['agent_run_id'])} "
            f"run_id={_safe_line_text(visualization['run']['run_id'])} "
            f"event_type={_safe_line_text(visualization['run']['event_type'])} "
            f"final_status={_safe_line_text(visualization['run']['final_status'])}"
        )
    ]
    for step in visualization["steps"]:
        metadata = _metadata_text(step["metadata"])
        suffix = f" {metadata}" if metadata else ""
        lines.append(
            f"{step['sequence']:02d} {_safe_line_text(step['status'])} "
            f"{_safe_line_text(step['label'])}{suffix}"
        )
    return "\n".join(lines).strip() + "\n"


def render_correlation(
    correlation: ShadowAgentRunCorrelation,
) -> str:
    lines = [f"agent_run_id={_safe_line_text(correlation['agent_run_id'])}"]
    for index, record in enumerate(correlation["records"], start=1):
        lines.append(
            f"{index:02d} event_type={_safe_line_text(record['event_type'])} "
            f"shadow_record_id={_safe_line_text(record['shadow_record_id'])} "
            f"run_id={_safe_line_text(record['run_id'])} "
            f"status={_safe_line_text(record['final_status'])}"
        )
    return "\n".join(lines).strip() + "\n"


def _metadata_text(metadata: Mapping[str, str | int | bool | None]) -> str:
    parts: list[str] = []
    for key in sorted(metadata):
        if key not in _ALLOWED_RENDER_METADATA_KEYS:
            continue
        value = metadata[key]
        if value is None:
            continue
        parts.append(f"{key}={_safe_line_text(str(value))}")
    return " ".join(parts)


def _mermaid_label(step: ShadowRunStep) -> str:
    metadata = _metadata_text(step["metadata"])
    text = (
        f"{step['sequence']:02d} {_safe_line_text(step['status'])} "
        f"{_safe_line_text(step['label'])}"
    )
    if metadata:
        text = f"{text} | {metadata}"
    return _escape_mermaid(text)


def _escape_mermaid(text: str) -> str:
    escaped = _safe_line_text(text)
    return (
        escaped.replace("&", "&amp;")
        .replace("\\", "&#92;")
        .replace('"', "&quot;")
        .replace("`", "&#96;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("[", "&#91;")
        .replace("]", "&#93;")
        .replace("{", "&#123;")
        .replace("}", "&#125;")
        .replace("(", "&#40;")
        .replace(")", "&#41;")
        .replace("|", "&#124;")
    )


def _safe_line_text(value: object) -> str:
    return " ".join(str(value).replace("\r", " ").replace("\n", " ").split())


def _node_id(value: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in value)
    if safe and safe[0].isdigit():
        return f"n_{safe}"
    return safe or "node"

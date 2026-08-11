from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import scripts.check_no_network as check_no_network
from app.adapters.testing.shadow_run_visualization_fixtures import (
    SYNTHETIC_QUESTION,
    SYNTHETIC_REPAIR_SQL,
    SYNTHETIC_SQL,
    all_records,
    examples,
    generate_for_agent,
)
from app.application.shadow_run_visualization_renderers import (
    render_correlation,
    render_mermaid,
    render_timeline,
)
from app.domain.result_normalization import stable_fingerprint
from app.domain.shadow_evidence_types import ShadowRunRecord
from app.domain.shadow_run_visualization import (
    ShadowRunVisualization,
    correlate_agent_run,
    visualize_shadow_run,
)
from scripts import render_shadow_run


ROOT = Path(__file__).resolve().parent


def main() -> None:
    records = all_records()
    _test_generate_simple_order(records["generate_without_repair"])
    _test_repair_path(records["generate_with_repair"])
    _test_two_repair_path(records["generate_with_two_repairs"])
    _test_security_rejection(records["generate_rejected_security"])
    _test_contract_rejection(records["generate_rejected_contract"])
    _test_execute_approved_valid(records["execute_approved_valid"])
    _test_execute_repair_reapproval(records["execute_approved_repair_reapproval"])
    _test_generated_vs_repaired_fingerprints(records["generate_with_repair"])
    _test_redaction(
        records["generate_with_repair"],
        records["execute_approved_repair_reapproval"],
    )
    _test_metadata_allowlist(records["generate_with_secret_metadata"])
    _test_mermaid_escaping()
    _test_safe_error(records["persistence_failure"])
    _test_deterministic(records["generate_with_repair"])
    _test_negative_timing(records["generate_negative_timing"])
    _test_identifiers(records["generate_without_repair"])
    _test_unknown_evidence(records["internal_error_sanitized"])
    _test_correlation(records)
    _test_mixed_agent_run_correlation(records)
    _test_script_and_drift_check()
    _test_real_contract_fields(records["generate_without_repair"])
    print("testar_shadow_run_visualization.py: 29/29 OK")


def _labels(record: ShadowRunRecord) -> list[str]:
    return [step["label"] for step in visualize_shadow_run(record)["steps"]]


def _test_generate_simple_order(record: ShadowRunRecord) -> None:
    labels = _labels(record)
    assert labels[:8] == [
        "receive_question",
        "load_context",
        "classify_intent",
        "build_plan",
        "generate_sql",
        "security_gate",
        "contract_gate",
        "engine_preflight",
    ]
    assert "repair_sql" not in labels


def _test_repair_path(record: ShadowRunRecord) -> None:
    labels = _labels(record)
    assert labels.count("repair_sql") == 1
    first_preflight = labels.index("engine_preflight")
    repair = labels.index("repair_sql")
    second_security = labels.index("security_gate", repair + 1)
    second_contract = labels.index("contract_gate", second_security + 1)
    second_preflight = labels.index("engine_preflight", second_contract + 1)
    assert first_preflight < repair < second_security < second_contract < second_preflight


def _test_two_repair_path(record: ShadowRunRecord) -> None:
    visualization = visualize_shadow_run(record)
    steps = visualization["steps"]
    labels = [step["label"] for step in steps]
    assert labels.count("repair_sql") == 2
    first_repair = labels.index("repair_sql")
    second_repair = labels.index("repair_sql", first_repair + 1)
    assert labels[-1] == "final"
    assert first_repair < second_repair < labels.index("final")
    cycles = [
        (step["label"], step["metadata"].get("cycle"))
        for step in steps
        if step["label"] in {"security_gate", "contract_gate", "engine_preflight"}
    ]
    assert cycles == [
        ("security_gate", 1),
        ("contract_gate", 1),
        ("engine_preflight", 1),
        ("security_gate", 2),
        ("contract_gate", 2),
        ("engine_preflight", 2),
        ("security_gate", 3),
        ("contract_gate", 3),
        ("engine_preflight", 3),
    ]
    repair_attempts = [
        step["metadata"].get("attempt")
        for step in steps
        if step["label"] == "repair_sql"
    ]
    assert repair_attempts == [1, 2]


def _test_security_rejection(record: ShadowRunRecord) -> None:
    labels = _labels(record)
    assert "security_gate" in labels
    assert "contract_gate" not in labels
    assert labels[-1] == "final"


def _test_contract_rejection(record: ShadowRunRecord) -> None:
    labels = _labels(record)
    assert "security_gate" in labels
    assert "contract_gate" in labels
    assert "engine_preflight" not in labels
    assert labels[-1] == "final"


def _test_execute_approved_valid(record: ShadowRunRecord) -> None:
    labels = _labels(record)
    assert labels[:4] == [
        "approved_sql_received",
        "security_gate",
        "contract_gate",
        "engine_preflight",
    ]
    assert "generate_sql" not in labels
    assert "classify_intent" not in labels
    assert "build_plan" not in labels


def _test_execute_repair_reapproval(record: ShadowRunRecord) -> None:
    visualization = visualize_shadow_run(record)
    labels = [step["label"] for step in visualization["steps"]]
    assert "repair_sql_proposal" in labels
    assert "requires_reapproval" in labels
    assert visualization["flags"]["requires_reapproval"] is True


def _test_generated_vs_repaired_fingerprints(record: ShadowRunRecord) -> None:
    visualization = visualize_shadow_run(record)
    generated = next(
        step for step in visualization["steps"] if step["label"] == "generate_sql"
    )
    repair = next(step for step in visualization["steps"] if step["label"] == "repair_sql")
    generated_fp = stable_fingerprint(SYNTHETIC_SQL)
    repaired_fp = stable_fingerprint(SYNTHETIC_REPAIR_SQL)
    assert generated["metadata"]["generated_sql_fingerprint"] == generated_fp
    assert generated["metadata"].get("generated_sql_fingerprint") != repaired_fp
    assert repair["metadata"]["repaired_sql_fingerprint"] == repaired_fp
    assert "langgraph_sql_fingerprint" not in generated["metadata"]


def _test_redaction(
    generate_record: ShadowRunRecord,
    execute_record: ShadowRunRecord,
) -> None:
    generate_visualization = visualize_shadow_run(generate_record)
    execute_visualization = visualize_shadow_run(execute_record)
    mermaid = render_mermaid(generate_visualization) + render_mermaid(
        execute_visualization
    )
    timeline = render_timeline(generate_visualization) + render_timeline(
        execute_visualization
    )
    combined = mermaid + timeline
    assert SYNTHETIC_SQL not in combined
    assert SYNTHETIC_REPAIR_SQL not in combined
    assert SYNTHETIC_QUESTION not in combined
    assert "SELECT" not in combined
    assert "question_fingerprint=" in combined
    assert "approved_sql_fingerprint=" in combined
    assert "repaired_sql_proposal_fingerprint=" in combined
    assert "duration_ms=3" in combined


def _test_metadata_allowlist(record: ShadowRunRecord) -> None:
    visualization = visualize_shadow_run(record)
    output = render_mermaid(visualization) + render_timeline(visualization)
    blocked_values = [
        "sensitive-password-value",
        "sensitive-token-value",
        "sensitive-authorization-value",
        "sensitive-cookie-value",
        "sensitive-dsn-value",
        "sensitive-approved-sql-value",
        "sensitive-repaired-sql-value",
        "sensitive-question-value",
        "sensitive-raw-response-value",
    ]
    assert not any(value in str(visualization) for value in blocked_values)
    assert not any(value in output for value in blocked_values)

    unsafe: ShadowRunVisualization = {
        "run": {
            "shadow_record_id": "shadow-manual",
            "agent_run_id": "agent-manual",
            "run_id": "run-manual",
            "event_type": "generate",
            "final_status": "success",
            "created_at": "2026-08-10T00:00:00+00:00",
            "completed_at": None,
            "duration_ms": None,
        },
        "steps": [
            {
                "id": "manual",
                "label": "manual",
                "step_type": "node",
                "status": "ok",
                "sequence": 1,
                "metadata": {
                    "status": "ok",
                    "password": "manual-password-leak",
                    "token": "manual-token-leak",
                    "authorization": "manual-authorization-leak",
                    "cookie": "manual-cookie-leak",
                    "dsn": "manual-dsn-leak",
                    "approved_sql": "manual-approved-sql-leak",
                    "repaired_sql": "manual-repaired-sql-leak",
                    "question": "manual-question-leak",
                    "raw_response": "manual-raw-response-leak",
                },
            }
        ],
        "edges": [],
        "flags": {
            "requires_reapproval": False,
            "has_repair": False,
            "has_error": False,
            "persistence_failure": False,
            "has_unknown_evidence": False,
        },
    }
    rendered = render_mermaid(unsafe) + render_timeline(unsafe)
    assert "status=ok" in rendered
    assert "manual-password-leak" not in rendered
    assert "manual-token-leak" not in rendered
    assert "manual-authorization-leak" not in rendered
    assert "manual-cookie-leak" not in rendered
    assert "manual-dsn-leak" not in rendered
    assert "manual-approved-sql-leak" not in rendered
    assert "manual-repaired-sql-leak" not in rendered
    assert "manual-question-leak" not in rendered
    assert "manual-raw-response-leak" not in rendered


def _test_mermaid_escaping() -> None:
    malicious = "\" \\ \n \r []{}() --> ` <> & |"
    visualization: ShadowRunVisualization = {
        "run": {
            "shadow_record_id": "shadow-escape",
            "agent_run_id": "agent-escape",
            "run_id": "run-escape",
            "event_type": "generate",
            "final_status": "success",
            "created_at": "2026-08-10T00:00:00+00:00",
            "completed_at": None,
            "duration_ms": None,
        },
        "steps": [
            {
                "id": "node]one",
                "label": f"safe{malicious}",
                "step_type": "node",
                "status": "ok",
                "sequence": 1,
                "metadata": {"error_code": f"code{malicious}"},
            },
            {
                "id": "node two",
                "label": "next",
                "step_type": "terminal",
                "status": "ok",
                "sequence": 2,
                "metadata": {},
            },
        ],
        "edges": [{"source": "node]one", "target": "node two", "edge_type": "normal"}],
        "flags": {
            "requires_reapproval": False,
            "has_repair": False,
            "has_error": False,
            "persistence_failure": False,
            "has_unknown_evidence": False,
        },
    }
    mermaid = render_mermaid(visualization)
    assert mermaid.startswith("flowchart TD\n")
    assert mermaid.count(" --> ") == 1
    assert "\n  safe" not in mermaid
    for expected in (
        "&quot;",
        "&#92;",
        "&#91;",
        "&#93;",
        "&#123;",
        "&#125;",
        "&#40;",
        "&#41;",
        "--&gt;",
        "&#96;",
        "&lt;",
        "&gt;",
        "&amp;",
        "&#124;",
    ):
        assert expected in mermaid


def _test_safe_error(record: ShadowRunRecord) -> None:
    visualization = visualize_shadow_run(record)
    text = render_timeline(visualization)
    assert "SHADOW_REPOSITORY_UNAVAILABLE" in text
    assert visualization["flags"]["persistence_failure"] is True


def _test_deterministic(record: ShadowRunRecord) -> None:
    first = visualize_shadow_run(record)
    second = visualize_shadow_run(record)
    assert render_mermaid(first) == render_mermaid(second)
    assert render_timeline(first) == render_timeline(second)


def _test_negative_timing(record: ShadowRunRecord) -> None:
    visualization = visualize_shadow_run(record)
    text = render_timeline(visualization)
    assert "duration_ms=-42" not in text
    preflight = next(
        step for step in visualization["steps"] if step["label"] == "engine_preflight"
    )
    assert preflight["metadata"].get("duration_ms") is None


def _test_identifiers(record: ShadowRunRecord) -> None:
    text = render_timeline(visualize_shadow_run(record))
    assert "shadow_record_id=shadow-lg-run-generate-ok" in text
    assert "agent_run_id=agent-run-visualization" in text
    assert "run_id=lg-run-generate-ok" in text
    assert "event_type=generate" in text


def _test_unknown_evidence(record: ShadowRunRecord) -> None:
    labels = _labels(record)
    assert "generate_sql" not in labels
    assert "security_gate" not in labels
    assert "evidence_not_recorded" in labels


def _test_correlation(records: dict[str, ShadowRunRecord]) -> None:
    correlation = correlate_agent_run(
        [
            records["generate_without_repair"],
            records["execute_approved_valid"],
        ]
    )
    text = render_correlation(correlation)
    assert "agent_run_id=agent-run-visualization" in text
    assert "event_type=generate" in text
    assert "event_type=execute_approved_shadow" in text
    assert "shadow-lg-run-generate-ok" in text
    assert "shadow-lg-run-execute-ok" in text


def _test_mixed_agent_run_correlation(records: dict[str, ShadowRunRecord]) -> None:
    other = generate_for_agent("agent-run-other", "lg-run-other-agent")
    correlation = correlate_agent_run(
        [
            records["execute_approved_valid"],
            other,
            records["generate_without_repair"],
        ],
        agent_run_id="agent-run-visualization",
    )
    text = render_correlation(correlation)
    assert [item["event_type"] for item in correlation["records"]] == [
        "generate",
        "execute_approved_shadow",
    ]
    assert "agent_run_id=agent-run-visualization" in text
    assert "agent-run-other" not in text
    assert "lg-run-other-agent" not in text


def _test_script_and_drift_check() -> None:
    assert render_shadow_run.check_examples()
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "run.mmd"
        assert render_shadow_run.main(
            ["--example", "generate", "--output", str(output)]
        ) == 0
        assert output.read_text(encoding="utf-8") == render_mermaid(
            visualize_shadow_run(examples()["generate"])
        )
    guarded = check_no_network.run_guarded(
        [sys.executable, "scripts/render_shadow_run.py", "--check-examples"],
        capture=True,
    )
    assert guarded.returncode == 0, guarded.stderr + guarded.stdout


def _test_real_contract_fields(record: ShadowRunRecord) -> None:
    required = {
        "shadow_record_id",
        "agent_run_id",
        "run_id",
        "event_type",
        "status",
        "created_at",
        "completed_at",
        "requires_reapproval",
        "langgraph_evidence",
        "fingerprints",
        "lineage",
        "evidence_fingerprint",
    }
    assert required <= set(record)


if __name__ == "__main__":
    main()

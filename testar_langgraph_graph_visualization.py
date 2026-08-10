from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import scripts.check_no_network as check_no_network
import scripts.render_langgraph_graph as renderer


ROOT = Path(__file__).resolve().parent


REQUIRED_NODES = {
    "receive_question",
    "load_context",
    "classify_intent",
    "build_plan",
    "generate_sql",
    "security_gate",
    "contract_gate",
    "engine_preflight",
    "repair_sql",
    "execute_sql",
    "normalize_result",
    "serialize_result",
    "build_run_record",
    "persist_run",
    "record_audit",
    "emit_observability",
    "build_application_response",
    "finalize_invalid_request",
    "finalize_infrastructure_error",
}


def main() -> None:
    first = renderer.render_mermaid()
    second = renderer.render_mermaid()
    assert first == second

    versioned = renderer.OUTPUT.read_text(encoding="utf-8")
    assert first == renderer._normalize_mermaid(versioned)

    for node in REQUIRED_NODES:
        assert node in first

    assert "repair_sql" in first
    assert "engine_preflight" in first
    assert "engine_preflight -.-> repair_sql;" in first
    assert "repair_sql -.-> security_gate;" in first
    assert "security_gate -.-> contract_gate;" in first
    assert "contract_gate -.-> engine_preflight;" in first
    assert "-." in first

    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "graph.mmd"
        assert renderer.main(["--output", str(output)]) == 0
        assert output.read_text(encoding="utf-8") == first

    guarded = check_no_network.run_guarded(
        [sys.executable, "scripts/render_langgraph_graph.py", "--check"],
        capture=True,
    )
    assert guarded.returncode == 0, guarded.stderr + guarded.stdout

    print("testar_langgraph_graph_visualization.py: 12/12 OK")


if __name__ == "__main__":
    main()

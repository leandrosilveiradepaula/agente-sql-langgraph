from __future__ import annotations

"""Offline, synthetic contract tests for a secret-safe n8n export auditor."""

import io
import json
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.audit_n8n_workflow_export_readonly import (
    WorkflowAuditError,
    compare_exports,
    load_workflow,
    main,
    summarize_workflow,
)


_PRIVATE = "TOP_SECRET_PRIVATE_TOKEN_MUST_NOT_LEAK"


def _fake_export() -> dict:
    return {
        "id": "test-flow-001",
        "name": "Synthetic Workflow",
        "active": True,
        "pinData": {"password": _PRIVATE, "raw_result": [_PRIVATE]},
        "connections": {},
        "nodes": [
            {
                "id": "node1",
                "name": "Classifier synthetic",
                "type": "n8n-nodes-base.code",
                "parameters": {
                    "jsCode": "const a = 'alpha';\n"
                    "const b = \"beta\";\n"
                    "const secret = '" + _PRIVATE + "';\n"
                    "return [{json: {value:a, other:b}}];",
                    "credentials": {"value": _PRIVATE},
                },
            },
            {
                "id": "node2",
                "name": "Send request",
                "type": "n8n-nodes-base.httpRequest",
                "parameters": {
                    "url": "https://example.invalid/private/" + _PRIVATE,
                    "headers": {"Authorization": "Bearer " + _PRIVATE},
                },
            },
            {
                "id": "node3",
                "name": "Bearer " + _PRIVATE,
                "type": "n8n-nodes-base.postgres",
                "parameters": {
                    "query": "SELECT x FROM fixture WHERE secret='" + _PRIVATE + "'",
                },
            },
        ],
    }


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_secret_safe_inventory_and_metadata_only() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "workflow.json"
        _write(path, _fake_export())
        workflow, digest = load_workflow(path)
        summary = summarize_workflow(workflow, digest)
        assert summary["node_count"] == 3
        assert summary["live_instance_verified"] is False
        assert summary["export_active_flag"] is True
        assert summary["nodes"][2]["name"] == "node-003"
        assert summary["nodes"][0]["code_characters"] > 20
        assert "INLINE_CODE_REVIEW" in summary["nodes"][0]["review_flags"]
        assert "EXTERNAL_REQUEST_REVIEW" in summary["nodes"][1]["review_flags"]
        assert "INLINE_QUERY_REVIEW" in summary["nodes"][2]["review_flags"]
        assert _PRIVATE not in json.dumps(summary)
        assert "example.invalid" not in json.dumps(summary)
        assert "SELECT x FROM" not in json.dumps(summary)
        assert "Authorization" not in json.dumps(summary)
        output = io.StringIO()
        with redirect_stdout(output):
            rc = main(["--workflow", str(path)])
        assert rc == 0
        assert _PRIVATE not in output.getvalue()
        assert json.loads(output.getvalue())["node_count"] == 3


def test_drift_detects_changed_added_and_removed_nodes() -> None:
    old = _fake_export()
    current = deepcopy(old)
    current["nodes"][0]["parameters"]["jsCode"] += "\nreturn [];"
    current["nodes"].pop(1)
    current["nodes"].append({
        "id": "new-node",
        "name": "New workflow step",
        "type": "n8n-nodes-base.if",
        "parameters": {},
    })
    baseline = summarize_workflow(old, "a" * 64)
    updated = summarize_workflow(current, "b" * 64)
    diff = compare_exports(baseline, updated)
    assert diff["changed"] == 1
    assert diff["added"] == 1
    assert diff["removed"] == 1
    assert diff["unchanged"] == 1
    assert diff["baseline_export_sha256"] == "a" * 64
    assert diff["candidate_export_sha256"] == "b" * 64

    with TemporaryDirectory() as directory:
        base_path = Path(directory) / "reference.json"
        current_path = Path(directory) / "current.json"
        _write(base_path, old)
        _write(current_path, current)
        output = io.StringIO()
        with redirect_stdout(output):
            assert main([
                "--workflow", str(current_path),
                "--compare-to", str(base_path),
            ]) == 0
        emitted = json.loads(output.getvalue())
        assert emitted["comparison"]["changed"] == 1
        assert emitted["comparison"]["removed"] == 1
        assert _PRIVATE not in output.getvalue()


def test_malformed_and_duplicate_exports_fail_closed() -> None:
    samples = [
        {},
        {"nodes": []},
        {"nodes": [{"name": "bad", "type": "code", "parameters": []}]},
        {"nodes": [{"name": "bad", "type": "code", "parameters": {"jsCode": []}}]},
        {"nodes": [{"name": "missing type", "parameters": {}}]},
        {"nodes": [{"name": "bad", "type": "code"}], "connections": []},
    ]
    for data in samples:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            _write(path, data)
            output = io.StringIO()
            with redirect_stdout(output):
                result = main(["--workflow", str(path)])
            assert result == 2
            assert "rejected" in output.getvalue()
            assert _PRIVATE not in output.getvalue()

    duplicate = _fake_export()
    duplicate["nodes"].append(deepcopy(duplicate["nodes"][0]))
    try:
        summarize_workflow(duplicate, "c" * 64)
    except WorkflowAuditError as exc:
        assert str(exc) == "WORKFLOW_NODE_IDENTIFIER_DUPLICATE"
    else:
        raise AssertionError("duplicate node identity accepted")


def test_error_outputs_do_not_leak_private_paths_or_bad_payloads() -> None:
    with TemporaryDirectory() as directory:
        filename = Path(directory) / ("SECRET_" + _PRIVATE + ".json")
        filename.write_text("{not valid JSON:" + _PRIVATE)
        output = io.StringIO()
        with redirect_stdout(output):
            assert main(["--workflow", str(filename)]) == 2
        safe = output.getvalue()
        assert _PRIVATE not in safe
        assert "SECRET_" not in safe
        assert "WORKFLOW_READ_OR_JSON_INVALID" in safe


if __name__ == "__main__":
    test_secret_safe_inventory_and_metadata_only()
    test_drift_detects_changed_added_and_removed_nodes()
    test_malformed_and_duplicate_exports_fail_closed()
    test_error_outputs_do_not_leak_private_paths_or_bad_payloads()
    print("N8N_EXPORT_HARDCODE_AUDIT_READONLY=PASS")

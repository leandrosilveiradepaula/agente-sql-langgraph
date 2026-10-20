from __future__ import annotations

"""Offline, synthetic contract tests for a secret-safe n8n export auditor."""

import io
import json
import shutil
import subprocess
import sys
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
        assert summary["nodes"][0]["name"] == "node-001"
        assert summary["nodes"][1]["name"] == "node-002"
        assert summary["nodes"][2]["name"] == "node-003"
        assert summary["nodes"][0]["type"] == "code"
        assert summary["nodes"][1]["type"] == "httpRequest"
        assert summary["nodes"][2]["type"] == "postgres"
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


def test_topology_runtime_configuration_and_workflow_identity_drift() -> None:
    original = _fake_export()
    before = summarize_workflow(original, "a" * 64)
    assert len(before["nodes"][0]["runtime_configuration_sha256"]) == 64

    rewired = deepcopy(original)
    rewired["connections"] = {
        "Classifier synthetic": {
            "main": [[{"node": "Send request", "type": "main", "index": 0}]]
        }
    }
    comparison = compare_exports(
        before, summarize_workflow(rewired, "b" * 64),
    )
    assert comparison["changed"] == 0
    assert comparison["topology_changed"] is True
    assert comparison["workflow_id_matches_baseline"] is True

    # These fields affect execution even with identical parameters and edges.
    for key, value in (
        ("typeVersion", 2.5),
        ("credentials", {"private": {"id": _PRIVATE}}),
    ):
        modified = deepcopy(original)
        modified["nodes"][0][key] = value
        current = summarize_workflow(modified, "b" * 64)
        delta = compare_exports(before, current)
        assert delta["changed"] == 1, key
        assert delta["topology_changed"] is False
        assert _PRIVATE not in json.dumps(current)
        assert _PRIVATE not in json.dumps(delta)

    visual_only = deepcopy(original)
    visual_only["nodes"][0]["position"] = [100, 200]
    delta = compare_exports(
        before, summarize_workflow(visual_only, "b" * 64),
    )
    assert delta["changed"] == 0
    assert delta["topology_changed"] is False

    other_flow = deepcopy(original)
    other_flow["id"] = "different-flow-id"
    delta = compare_exports(
        before, summarize_workflow(other_flow, "b" * 64),
    )
    assert delta["workflow_id_matches_baseline"] is False


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


def test_no_arbitrary_node_names_can_reach_report() -> None:
    fixture = _fake_export()
    fixture["nodes"][0]["name"] = "nonobvious-" + _PRIVATE
    fixture["nodes"][1]["name"] = "customer db host-and-user"
    report = summarize_workflow(fixture, "d" * 64)
    data = json.dumps(report, ensure_ascii=False)
    assert "nonobvious-" not in data
    assert "customer db host" not in data
    assert _PRIVATE not in data
    assert all(
        node["name"] == f"node-{index + 1:03d}"
        for index, node in enumerate(report["nodes"])
    )
    assert all(
        len(node["node_identity_sha256"]) == 64 for node in report["nodes"]
    )

    fixture["nodes"][0]["type"] = "n8n-nodes-base." + _PRIVATE
    hidden = summarize_workflow(fixture, "e" * 64)
    assert hidden["nodes"][0]["type"] == "other_builtin"
    assert _PRIVATE not in json.dumps(hidden)
    assert len(hidden["nodes"][0]["type_fingerprint"]) == 64

    fixture["nodes"][0]["type"] = "n8n-nodes-base.invalid:" + _PRIVATE
    try:
        summarize_workflow(fixture, "e" * 64)
    except WorkflowAuditError as exc:
        assert str(exc) == "WORKFLOW_NODE_TYPE_INVALID"
    else:
        raise AssertionError("untrusted type string accepted")


def test_singleton_cli_export_envelope_and_multibundle_rejection() -> None:
    with TemporaryDirectory() as directory:
        path = Path(directory) / "published-export.json"
        source = _fake_export()
        path.write_text(json.dumps([source]), encoding="utf-8")
        workflow, hash_value = load_workflow(path)
        assert workflow == source
        assert len(hash_value) == 64
        assert summarize_workflow(workflow, hash_value)["node_count"] == 3

        path.write_text(json.dumps([source, deepcopy(source)]), encoding="utf-8")
        try:
            load_workflow(path)
        except WorkflowAuditError as exc:
            assert str(exc) == "WORKFLOW_SINGLE_RECORD_REQUIRED"
        else:
            raise AssertionError("multi-workflow export accepted")


def test_published_cli_runner_is_manual_and_fails_closed() -> None:
    path = Path(__file__).resolve().parent / "scripts" / "audit_n8n_published_workflow_readonly.sh"
    script = path.read_text(encoding="utf-8")
    assert "set -Eeuo pipefail" in script
    assert "umask 077" in script
    assert "export:workflow" in script
    assert "--published" in script
    assert 'docker exec -u node "$CONTAINER"' in script
    assert "CONTAINER_EXPORT_CLEANUP_UNCONFIRMED" in script
    assert "official_webhook_route_verified" in script
    assert "--id=$WORKFLOW_ID" in script
    assert "--all" not in script
    assert "import:workflow" not in script
    assert "export:credentials" not in script
    assert "n8n execute" not in script

    # On POSIX, exercise parsing and early rejection without Docker calls.
    executable = shutil.which("bash")
    if executable and sys.platform != "win32":
        syntax = subprocess.run(
            [executable, "-n", str(path)],
            capture_output=True, text=True, timeout=10, check=False,
        )
        assert syntax.returncode == 0
        help_result = subprocess.run(
            [executable, str(path), "--help"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        assert help_result.returncode == 0
        denied = subprocess.run(
            [executable, str(path), "--workflow-id", "invalid/id"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        assert denied.returncode == 2
        assert "WORKFLOW_ID_INVALID" in denied.stderr


if __name__ == "__main__":
    test_secret_safe_inventory_and_metadata_only()
    test_no_arbitrary_node_names_can_reach_report()
    test_singleton_cli_export_envelope_and_multibundle_rejection()
    test_published_cli_runner_is_manual_and_fails_closed()
    test_drift_detects_changed_added_and_removed_nodes()
    test_topology_runtime_configuration_and_workflow_identity_drift()
    test_malformed_and_duplicate_exports_fail_closed()
    test_error_outputs_do_not_leak_private_paths_or_bad_payloads()
    print("N8N_EXPORT_HARDCODE_AUDIT_READONLY=PASS")

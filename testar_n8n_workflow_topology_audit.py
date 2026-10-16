from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from testar_n8n_shadow_network_probe import _bash_binary


ROOT = Path(__file__).resolve().parent
INSPECTOR = ROOT / "scripts/n8n/audit_official_workflow_topology.js"
RUNNER = ROOT / "scripts/n8n/run_official_workflow_topology_audit.sh"


def _node_binary() -> str:
    node = shutil.which("node")
    assert node is not None, "Node.js is required for offline n8n topology audit validation"
    return node


def test_syntax():
    for command in (
        [_node_binary(), "--check", str(INSPECTOR)],
        [_bash_binary(), "-n"],
    ):
        is_shell = command[-1] == "-n"
        check = subprocess.run(
            command,
            input=RUNNER.read_text(encoding="utf-8") if is_shell else None,
            text=True, capture_output=True, check=False,
        )
        assert check.returncode == 0, check.stderr


def test_sanitized_index_and_detail():
    sensitive_marker = "PRIVATE_FIXTURE_VALUE_DO_NOT_PRINT_abc123"
    fixtures = [{
        "id": "main_valid",
        "name": sensitive_marker,
        "active": True,
        "nodes": [
            {
                "name": "incoming_" + sensitive_marker,
                "type": "n8n-nodes-base.webhook",
                "parameters": {
                    "path": sensitive_marker,
                    "headers": {"Authorization": sensitive_marker},
                },
            },
            {
                "name": "query",
                "type": "n8n-nodes-base.postgres",
                "parameters": {"query": "SELECT '" + sensitive_marker + "'"},
                "credentials": {"postgres": {"name": sensitive_marker}},
            },
            {
                "name": "outgoing",
                "type": "n8n-nodes-base.respondToWebhook",
                "parameters": {"responseBody": sensitive_marker},
            },
        ],
        "connections": {
            "incoming_" + sensitive_marker: {
                "main": [[{"node": "query", "type": "main", "index": 0}]]
            },
            "query": {
                "main": [[{"node": "outgoing", "type": "main", "index": 0}]]
            },
        },
    }, {
        "id": "isolated_test",
        "name": "Temporary manual test",
        "active": False,
        "nodes": [{
            "name": "start",
            "type": "n8n-nodes-base.manualTrigger",
            "parameters": {},
        }],
        "connections": {},
    }]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "export.json"
        path.write_text(json.dumps(fixtures), encoding="utf-8")
        for requested, expected in (
            ("", ["N8N_AUDIT_MODE=INDEX", "WORKFLOW_COUNT=2",
                  "WORKFLOW id=main_valid active=true", "WORKFLOW id=isolated_test active=false"]),
            ("main_valid", ["N8N_AUDIT_MODE=DETAIL", "WORKFLOW_ID=main_valid",
                            "NODE index=0 kind=trigger", "NODE index=1 kind=database",
                            "NODE index=2 kind=response", "to=1", "to=2",
                            "N8N_TOPOLOGY_AUDIT=PASS"]),
        ):
            cmd = [_node_binary(), str(INSPECTOR), str(path)]
            if requested:
                cmd.append(requested)
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            assert result.returncode == 0, result.stdout + result.stderr
            assert all(marker in result.stdout for marker in expected), result.stdout
            assert sensitive_marker not in result.stdout
            assert "SELECT" not in result.stdout
            assert "Authorization" not in result.stdout
            assert result.stderr == ""

        invalid_id = subprocess.run(
            [_node_binary(), str(INSPECTOR), str(path), "invalid/id"],
            capture_output=True, text=True, check=False,
        )
        assert invalid_id.returncode != 0
        assert "INVALID_ARGUMENTS" in invalid_id.stdout
        assert sensitive_marker not in invalid_id.stdout

        path.write_text(sensitive_marker, encoding="utf-8")
        invalid_json = subprocess.run(
            [_node_binary(), str(INSPECTOR), str(path)],
            capture_output=True, text=True, check=False,
        )
        assert invalid_json.returncode != 0
        assert "EXPORT_READ_FAILED" in invalid_json.stdout
        assert sensitive_marker not in invalid_json.stdout


def test_runner_safety():
    source = RUNNER.read_text(encoding="utf-8")
    assert "n8n export:workflow" in source
    assert "mkdir -m 700" in source
    assert "trap cleanup EXIT" in source
    assert "docker exec -u node" in source
    assert "N8N_AUDIT_WORKFLOW_ID" in source
    for forbidden in (
        "n8n import:workflow",
        "export:credentials",
        "--decrypted",
        "docker network connect",
        "docker compose up",
    ):
        assert forbidden not in source


if __name__ == "__main__":
    test_syntax()
    test_sanitized_index_and_detail()
    test_runner_safety()
    print("N8N_WORKFLOW_TOPOLOGY_AUDIT_OFFLINE=PASS")

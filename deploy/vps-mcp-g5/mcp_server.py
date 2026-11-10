"""Private, least-privilege MCP gateway for Agente Financeiro.

Runs as agente-mcp under the existing Secure MCP Tunnel.  The root broker
accepts only a fixed set of named operations through a local Unix socket.
There is no shell, SQL, network target, or command parameter exposed to MCP.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
from pathlib import Path

from mcp.server import MCPServer

mcp = MCPServer("Agente Financeiro VPS")
SOCKET = "/run/agente-financeiro-mcp/operations.sock"


def _read(operation: str, expected_sha: str | None = None) -> dict[str, object]:
    """Only fixed operations can be sent; no dynamic commands or arguments."""
    if operation not in {"runtime_status", "revision", "n8n_inventory", "import_evidence", "audit_evidence",
                         "repo_sync", "benchmark_plan", "benchmark_recover", "benchmark_status"}:
        return {"status": "rejected", "reason": "operation_not_allowed"}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3700 if operation == "benchmark_recover" else
                              150 if operation in ("repo_sync", "import_evidence") else 90)
            client.connect(SOCKET)
            payload = {"op": operation}
            if operation == "repo_sync":
                payload["expected_sha"] = expected_sha
            client.sendall((json.dumps(payload) + "\n").encode("ascii"))
            data = bytearray()
            while b"\n" not in data:
                block = client.recv(4096)
                if not block:
                    break
                data.extend(block)
                if len(data) > 16384:
                    raise ValueError("response_limit")
            response = json.loads(bytes(data).split(b"\n", 1)[0])
            return response if isinstance(response, dict) else {"status": "unavailable"}
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        return {"status": "unavailable", "reason": "broker_unreachable"}


def _fixed_command(*argv: str) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            list(argv), capture_output=True, text=True, timeout=5, check=False,
            shell=False, env={"PATH": "/usr/bin:/bin", "LANG": "C"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return False, "unavailable"
    return result.returncode == 0, result.stdout.strip()[:160]


@mcp.tool()
def mcp_health() -> dict[str, object]:
    """Check that the private tunnel and MCP gateway are reachable."""
    return {"status": "ok", "mode": "controlled_operations", "real_sql_execution": False}


@mcp.tool()
def host_status() -> dict[str, object]:
    """Read load, uptime and disk space, without addresses, passwords or logs."""
    try:
        uptime = int(float(Path("/proc/uptime").read_text().split()[0]))
    except (OSError, ValueError, IndexError):
        uptime = None
    try:
        stat = os.statvfs("/")
        total_gb = round(stat.f_frsize * stat.f_blocks / 1024**3, 1)
        free_gb = round(stat.f_frsize * stat.f_bavail / 1024**3, 1)
        load_1m = round(os.getloadavg()[0], 2)
    except OSError:
        total_gb = free_gb = load_1m = None
    ok, docker = _fixed_command("/usr/bin/systemctl", "is-active", "docker")
    return {"uptime_seconds": uptime, "disk_total_gb": total_gb,
            "disk_free_gb": free_gb, "load_1m": load_1m,
            "docker_service_active": ok and docker == "active"}


@mcp.tool()
def langgraph_repo_revision() -> dict[str, object]:
    """Retrieve the actual VPS LangGraph repository SHA via scoped local broker."""
    return _read("revision")


@mcp.tool()
def docker_runtime_status() -> dict[str, object]:
    """Read only the official n8n and Shadow TEST container health and SQL safety flag."""
    return _read("runtime_status")


@mcp.tool()
def n8n_shadow_workflow_inventory() -> dict[str, object]:
    """Read only workflow IDs, active flags and bindings of known Shadow webhooks."""
    return _read("n8n_inventory")


@mcp.tool()
def import_shadow_evidence_read_draft() -> dict[str, object]:
    """One narrowly scoped change: import the preapproved evidence-read relay INACTIVE.

    Never publishes/activates a workflow, changes existing workflows, binds
    credentials, calls LLM, runs financial SQL, performs cutover or writes DB.
    Only operates on the exact reviewed source SHA after preflight.
    """
    return _read("import_evidence")


@mcp.tool()
def audit_shadow_evidence_draft_bindings() -> dict[str, object]:
    """Audit existing INACTIVE evidence relay credentials and read-only topology.

    No workflow update, network inference or SQL/LLM activity. Never prints
    credential values, URLs, webhook tokens or raw n8n exports.
    """
    return _read("audit_evidence")


@mcp.tool()
def sync_approved_langgraph_main(expected_sha: str) -> dict[str, object]:
    """Fast-forward the VPS checkout to an exact GitHub main SHA (no other branch)."""
    return _read("repo_sync", expected_sha)


@mcp.tool()
def g5_benchmark_preflight() -> dict[str, object]:
    """Verify G5 archive integrity and cached PostgreSQL image, no decryption."""
    return _read("benchmark_plan")


@mcp.tool()
def g5_benchmark_recover_once() -> dict[str, object]:
    """Recover 63 historic n8n cases offline using operator-provisioned one-shot local G5 passphrase. Never return secrets/SQL."""
    return _read("benchmark_recover")


@mcp.tool()
def g5_benchmark_recovery_status() -> dict[str, object]:
    """Verify the root-only private 63-case snapshot; returns counts only."""
    return _read("benchmark_status")


if __name__ == "__main__":
    mcp.run(transport="stdio")
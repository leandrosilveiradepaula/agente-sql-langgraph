#!/usr/bin/python3
"""Root-owned, local-only capability broker for the private MCP service.

Linux SO_PEERCRED restricts requests to the non-root agente-mcp identity.
Legacy fixed diagnostics remain available. The administrator-approved
execution operations are authenticated via SO_PEERCRED, bounded, and audited.
"""
from __future__ import annotations

import fcntl
import json
import os
import pwd
import re
import socket
import socketserver
import struct
import subprocess
import sys
from pathlib import Path
from benchmark_ops import repo_sync, benchmark_plan, benchmark_recover, benchmark_status
import vps_admin
from crypto_j1_readonly import timer_status as cia_timer_status, journal_summary as cia_journal_summary, sqlite_audit_via_owner as cia_sqlite_audit

SOCKET = Path("/run/agente-financeiro-mcp/operations.sock")
ROOT = Path("/docker/agente-sql-langgraph-repo")
PACKAGE = Path("/opt/agente-financeiro-mcp")
N8N = "n8n-n8n-1"
SHADOW = "agente-sql-langgraph-shadow-test-langgraph-shadow-test-1"
KNOWN_WEBHOOKS = ("langgraph-shadow-parallel-v1", "langgraph-shadow-evidence-v1")
ALLOWLIST = {"revision", "runtime_status", "n8n_inventory", "import_evidence", "audit_evidence",
             "repo_sync", "benchmark_plan", "benchmark_recover", "benchmark_status",
             "cia_timer", "cia_journal", "cia_sqlite",
             "admin_exec", "admin_start", "admin_status", "admin_cancel"}
ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class Blocked(Exception):
    pass


def _run(argv: list[str], timeout: int = 20, stdin: str | None = None) -> str:
    """Fixed argv executor used by the legacy diagnostic operations only."""
    try:
        result = subprocess.run(
            argv, input=stdin, capture_output=True, text=True, timeout=timeout,
            check=False, shell=False, cwd="/", env={"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Blocked("command_unavailable") from exc
    if result.returncode != 0:
        raise Blocked("command_failed")
    if len(result.stdout) > 16000:
        raise Blocked("output_limit")
    return result.stdout.strip()


def _revision() -> dict[str, object]:
    if not ROOT.is_dir():
        return {"available": False, "reason": "repo_missing"}
    try:
        sha = _run(["/usr/bin/git", "-C", str(ROOT), "rev-parse", "HEAD"], 8)
    except Blocked:
        return {"available": False, "reason": "repo_unreadable"}
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        return {"available": False, "reason": "repo_unreadable"}
    return {"available": True, "sha": sha}


def _container(name: str) -> dict[str, object]:
    try:
        value = _run([
            "/usr/bin/docker", "inspect", "--format",
            '{{.State.Running}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}', name,
        ], 12)
    except Blocked:
        return {"available": False}
    m = re.fullmatch(r"(true|false)\|(healthy|unhealthy|starting|none)", value)
    if not m:
        return {"available": False}
    return {"available": True, "running": m.group(1) == "true", "health": m.group(2)}


def _runtime_status() -> dict[str, object]:
    n8n = _container(N8N)
    shadow = _container(SHADOW)
    sql_disabled = None
    if shadow.get("available"):
        try:
            raw = _run([
                "/usr/bin/docker", "inspect", "--format",
                '{{range .Config.Env}}{{if eq . "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false"}}yes{{end}}{{end}}',
                SHADOW,
            ], 12)
            sql_disabled = raw == "yes"
        except Blocked:
            pass
    return {"n8n": n8n, "langgraph_shadow_test": shadow,
            "shadow_real_sql_execution_disabled": sql_disabled}


# Executed inside the existing n8n container. Only an allowlisted projection
# leaves the container; raw workflow configs and credential refs are never sent.
INVENTORY_JS = r'''
const fs=require('node:fs');
const x=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));
if(!Array.isArray(x)) process.exit(2);
const paths=['langgraph-shadow-parallel-v1','langgraph-shadow-evidence-v1'];
const out={};
for(const path of paths){
 const entries=[];
 for(const w of x){
  const nodes=Array.isArray(w.nodes)?w.nodes:[];
  const hook=nodes.find(n=>n.type==='n8n-nodes-base.webhook' && n.parameters?.path===path);
  if(!hook)continue;
  if(!/^[A-Za-z0-9_-]{1,128}$/.test(w.id||''))process.exit(2);
  const read=nodes.find(n=>n.name==='Read LangGraph Evidence');
  entries.push({id:w.id,active:w.active===true,node_count:nodes.length,
    webhook_header_auth_bound:Boolean(hook.credentials?.httpHeaderAuth?.id),
    evidence_reader_header_auth_bound:Boolean(read?.credentials?.httpHeaderAuth?.id)});
 }
 out[path]=entries;
}
console.log(JSON.stringify(out));
'''


def _inventory() -> dict[str, object]:
    # The n8n CLI exports only into the n8n container, not to MCP or the host.
    path = ""
    try:
        path = _run(["/usr/bin/docker", "exec", "-u", "node", N8N,
                     "sh", "-c", "umask 077; mktemp /tmp/agente-mcp-workflows.XXXXXXXX"], 10)
        if not re.fullmatch(r"/tmp/agente-mcp-workflows\.[A-Za-z0-9]{8}", path):
            raise Blocked("invalid_private_path")
        _run(["/usr/bin/docker", "exec", "-u", "node", N8N,
              "n8n", "export:workflow", "--all", "--output=" + path], 30)
        raw = _run(["/usr/bin/docker", "exec", "-u", "node", N8N,
                    "node", "-e", INVENTORY_JS, path], 15)
        data = json.loads(raw)
        if not isinstance(data, dict) or set(data) != set(KNOWN_WEBHOOKS):
            raise Blocked("invalid_inventory")
        return {"status": "ok", "workflows": data}
    except (Blocked, ValueError, json.JSONDecodeError):
        return {"status": "unavailable", "reason": "n8n_inventory_failed"}
    finally:
        if re.fullmatch(r"/tmp/agente-mcp-workflows\.[A-Za-z0-9]{8}", path):
            try:
                _run(["/usr/bin/docker", "exec", "-u", "node", N8N,
                      "rm", "-f", "--", path], 10)
            except Blocked:
                print("audit=inventory_private_temp_cleanup_unconfirmed", file=sys.stderr)


def _import_evidence() -> dict[str, object]:
    # Serialize imports to avoid overlapping MCP calls creating duplicate drafts.
    with open("/run/agente-financeiro-mcp/evidence-import.lock", "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        script = PACKAGE / "import_evidence_draft.sh"
        if not script.is_file() or script.is_symlink():
            return {"status": "blocked", "reason": "reviewed_importer_missing"}
        try:
            # Script itself strictly pins source SHA, SQL flag, n8n health,
            # private address, inactive JSON and pre/post-workflow comparison.
            stdout = _run(["/usr/bin/bash", str(script)], timeout=120)
        except Blocked:
            return {"status": "blocked", "reason": "import_preflight_or_execution_failed"}
        lines = stdout.splitlines()
        if "EVIDENCE_READ_DRAFT=CREATED" not in lines or \
            "EXISTING_WORKFLOW_NODES_AND_STATUS_UNCHANGED=true" not in lines:
            return {"status": "blocked", "reason": "import_verification_failed"}
        ids = [s.split("=", 1)[1] for s in lines if s.startswith("WORKFLOW_ID=")]
        if len(ids) != 1 or not ID.fullmatch(ids[0]):
            return {"status": "blocked", "reason": "import_id_invalid"}
        return {"status": "created", "workflow_id": ids[0], "active": False,
                "credentials_bound": False, "existing_workflows_untouched": True,
                "financial_sql_executed": False}


def _audit_evidence() -> dict[str, object]:
    """Run only the reviewed, immutable-SHA, read-only n8n binding verifier."""
    rev = _revision()
    if rev.get("sha") != "3e2192e7c33bcff2ab641f2373ce36c664b3cf39":
        return {"status": "blocked", "reason": "reviewed_repo_sha_mismatch"}
    inventory = _inventory()
    if inventory.get("status") != "ok":
        return {"status": "blocked", "reason": "inventory_unavailable"}
    entries = inventory.get("workflows", {}).get("langgraph-shadow-evidence-v1", [])
    if len(entries) != 1 or entries[0].get("active") is not False:
        return {"status": "blocked", "reason": "no_unique_inactive_evidence_workflow"}
    workflow_id = entries[0]["id"]
    if not ID.fullmatch(workflow_id):
        return {"status": "blocked", "reason": "workflow_id_invalid"}
    script = ROOT / "scripts/n8n/audit_shadow_evidence_read_bindings_readonly.sh"
    try:
        report = _run(["/usr/bin/bash", str(script), "--workflow-id", workflow_id,
                       "--container", N8N], timeout=60)
    except Blocked:
        return {"status": "blocked", "reason": "binding_audit_rejected"}
    if "EVIDENCE_READ_BINDINGS=PASS" not in report.splitlines():
        return {"status": "blocked", "reason": "binding_audit_did_not_pass"}
    return {"status": "pass", "workflow_id": workflow_id, "active": False,
            "private_read_verified": False, "tenant_scope_verified": False,
            "financial_sql_executed": False}


def dispatch(op: str, expected_sha: str | None = None,
             params: dict[str, object] | None = None) -> dict[str, object]:
    if op not in ALLOWLIST:
        return {"status": "rejected", "reason": "operation_not_allowed"}
    if op in {"admin_exec", "admin_start", "admin_status", "admin_cancel"}:
        payload = params if isinstance(params, dict) else {}
        expected = {
            "admin_exec": {"argv", "cwd", "timeout_seconds", "show_output"},
            "admin_start": {"argv", "cwd", "timeout_seconds"},
            "admin_status": {"job_id", "show_output"},
            "admin_cancel": {"job_id"},
        }[op]
        if set(payload) != expected:
            return {"status": "blocked", "reason": "admin_arguments_invalid"}
        if op == "admin_exec":
            return vps_admin.execute(**payload)
        if op == "admin_start":
            return vps_admin.start(**payload)
        if op == "admin_status":
            return vps_admin.status(**payload)
        return vps_admin.cancel(**payload)
    if op == "cia_timer":
        return cia_timer_status()
    if op == "cia_journal":
        return cia_journal_summary()
    if op == "cia_sqlite":
        return cia_sqlite_audit()
    if op == "repo_sync":
        return repo_sync(expected_sha)
    if op == "benchmark_plan":
        if _runtime_status().get("shadow_real_sql_execution_disabled") is not True:
            return {"status": "blocked", "reason": "shadow_sql_safety_unverified"}
        return benchmark_plan()
    if op == "benchmark_recover":
        if _runtime_status().get("shadow_real_sql_execution_disabled") is not True:
            return {"status": "blocked", "reason": "shadow_sql_safety_unverified"}
        return benchmark_recover()
    if op == "benchmark_status":
        return benchmark_status()
    if op == "revision":
        return _revision()
    if op == "runtime_status":
        return _runtime_status()
    if op == "n8n_inventory":
        return _inventory()
    if op == "import_evidence":
        return _import_evidence()
    if op == "audit_evidence":
        return _audit_evidence()
    return {"status": "rejected", "reason": "operation_not_allowed"}


class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            peer = struct.unpack("3i", self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if peer[1] != pwd.getpwnam("agente-mcp").pw_uid:
                return
            self.request.settimeout(3750)
            raw = self.rfile.readline(16385)
            if len(raw) > 16384 or not raw.endswith(b"\n"):
                return
            req = json.loads(raw)
            if not isinstance(req, dict) or not isinstance(req.get("op"), str):
                return
            op = req["op"]
            expected_fields = ({"op", "expected_sha"} if op == "repo_sync" else
                               {"op", "argv", "cwd", "timeout_seconds", "show_output"} if op == "admin_exec" else
                               {"op", "argv", "cwd", "timeout_seconds"} if op == "admin_start" else
                               {"op", "job_id", "show_output"} if op == "admin_status" else
                               {"op", "job_id"} if op == "admin_cancel" else {"op"})
            if set(req) != expected_fields:
                return
            params = {k: v for k, v in req.items() if k not in ("op", "expected_sha")}
            result = dispatch(op, req.get("expected_sha"), params)
            print("mcp_op=" + (op if op in ALLOWLIST else "rejected") +
                  " status=" + str(result.get("status", "ok")), flush=True)
            data = json.dumps(result, ensure_ascii=True, separators=(",", ":")).encode("ascii") + b"\n"
            self.wfile.write(data[:16384])
        except (OSError, ValueError, json.JSONDecodeError):
            pass


class UnixServer(socketserver.ThreadingUnixStreamServer):
    allow_reuse_address = False
    daemon_threads = True


def main() -> None:
    SOCKET.parent.mkdir(parents=True, exist_ok=True)
    # Never unlink a socket created by an unexpected process.
    if SOCKET.exists():
        if not SOCKET.is_socket():
            raise RuntimeError("unexpected_socket_path")
        SOCKET.unlink()
    with UnixServer(str(SOCKET), Handler) as server:
        os.chmod(SOCKET, 0o660)
        server.serve_forever()


if __name__ == "__main__":
    main()
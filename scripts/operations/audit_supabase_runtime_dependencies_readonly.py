#!/usr/bin/env python3
"""Read-only VPS audit of actual Shadow DSNs and n8n financial credentials.

No writes, no SQL queries, no n8n API key. Docker inspect and n8n CLI exports
are captured strictly in process memory; secret contents NEVER enter output.
The n8n --decrypted path is explicit, opt-in, one credential ID at a time, and
requires local terminal confirmation. No files are created by the scanner.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from urllib.parse import unquote, urlsplit

PROJECT_REF = re.compile(r"^[a-z]{20}$")
CONTAINER_ID = re.compile(r"^[A-Za-z0-9_.-]{1,180}$")
WORKFLOW_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
CREDENTIAL_ID = WORKFLOW_ID
DIRECT_HOST = re.compile(r"^db\.([a-z]{20})\.supabase\.co$")
POOLER_HOST = re.compile(r"^[a-z0-9.-]+\.pooler\.supabase\.com$")
POOLER_USER = re.compile(r"^[A-Za-z0-9_-]+\.([a-z]{20})$")
MAX_CLI_OUTPUT = 3_000_000
ALLOWED_RESULTS = frozenset((
    "SOURCE", "DEMO", "OTHER_SUPABASE_UNVERIFIED", "UNKNOWN",
))


class AuditBlocked(Exception):
    pass


def project_for_host_user(host: str | None, username: str | None) -> str | None:
    """Trust a Supabase-specific hostname and the pooler project identity."""
    if not isinstance(host, str):
        return None
    host = host.lower().rstrip(".")
    direct = DIRECT_HOST.fullmatch(host)
    if direct:
        # A conflicting project in a non-standard username is ambiguous.
        if username and (m := POOLER_USER.fullmatch(username)) and m[1] != direct[1]:
            return None
        return direct[1]
    if POOLER_HOST.fullmatch(host) and isinstance(username, str):
        pooler = POOLER_USER.fullmatch(username)
        return pooler[1] if pooler else None
    return None


def classify_reference(ref: str | None, *, source: str, demo: str) -> str:
    if ref == source:
        return "SOURCE"
    if ref == demo:
        return "DEMO"
    return "OTHER_SUPABASE_UNVERIFIED" if ref else "UNKNOWN"


def classify_dsn(raw: str | None, *, source: str, demo: str) -> str:
    if not isinstance(raw, str) or len(raw) > 16000:
        return "UNKNOWN"
    try:
        parsed = urlsplit(raw.strip())
        if parsed.scheme not in ("postgres", "postgresql"):
            return "UNKNOWN"
        username = unquote(parsed.username) if parsed.username else None
        return classify_reference(
            project_for_host_user(parsed.hostname, username),
            source=source, demo=demo,
        )
    except (ValueError, TypeError, UnicodeError):
        return "UNKNOWN"


def classify_pg_credential(data: object, *, source: str, demo: str) -> str:
    if not isinstance(data, dict):
        return "UNKNOWN"
    host = data.get("host")
    user = data.get("user")
    if isinstance(host, str) and isinstance(user, str):
        ref = project_for_host_user(host, user)
        if ref:
            return classify_reference(ref, source=source, demo=demo)
    for key in ("connectionString", "connectionStringUrl"):
        value = data.get(key)
        if isinstance(value, str):
            result = classify_dsn(value, source=source, demo=demo)
            if result != "UNKNOWN":
                return result
    return "UNKNOWN"


def run_private_cli(command: list[str], *, timeout: int = 80) -> str:
    """Never echo command output, stderr, subprocess exception or environment."""
    try:
        process = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        raise AuditBlocked("PRIVATE_CLI_UNAVAILABLE") from None
    if process.returncode != 0 or len(process.stdout) > MAX_CLI_OUTPUT:
        raise AuditBlocked("PRIVATE_CLI_INVALID_RESULT")
    return process.stdout


def running_docker_environment(container: str) -> dict[str, str]:
    if not CONTAINER_ID.fullmatch(container):
        raise AuditBlocked("INVALID_CONTAINER")
    status = run_private_cli(
        ["docker", "inspect", "--format", "{{.State.Running}}", container],
        timeout=20,
    ).strip()
    if status != "true":
        raise AuditBlocked("CONTAINER_NOT_RUNNING")
    raw = run_private_cli(
        ["docker", "inspect", "--format", "{{json .Config.Env}}", container],
        timeout=20,
    )
    try:
        pairs = json.loads(raw)
    except ValueError:
        raise AuditBlocked("CONTAINER_ENV_UNVERIFIED") from None
    if not isinstance(pairs, list) or len(pairs) > 500:
        raise AuditBlocked("CONTAINER_ENV_UNVERIFIED")
    out: dict[str, str] = {}
    for item in pairs:
        if not isinstance(item, str) or "=" not in item:
            raise AuditBlocked("CONTAINER_ENV_UNVERIFIED")
        key, _, value = item.partition("=")
        if key in out:
            raise AuditBlocked("DUPLICATE_CONTAINER_ENV")
        out[key] = value
    return out


def parse_n8n_one(stdout: str, expected_id: str, *, decrypted: bool) -> dict:
    """Parse exactly one matching n8n JSON array from noisy stdout."""
    if not stdout or len(stdout) > MAX_CLI_OUTPUT:
        raise AuditBlocked("N8N_OUTPUT_UNVERIFIED")
    decoder = json.JSONDecoder()
    matched = []
    for match in re.finditer(r"\[\s*\{", stdout):
        try:
            candidate, _ = decoder.raw_decode(stdout[match.start():])
        except (TypeError, ValueError):
            continue
        if not isinstance(candidate, list) or len(candidate) != 1:
            continue
        item = candidate[0]
        if not isinstance(item, dict) or item.get("id") != expected_id:
            continue
        if decrypted:
            if item.get("type") != "postgres" or not isinstance(item.get("data"), dict):
                continue
        elif not isinstance(item.get("nodes"), list):
            continue
        matched.append(item)
    if len(matched) != 1:
        raise AuditBlocked("N8N_OUTPUT_UNVERIFIED")
    return matched[0]


def find_pg_credentials(workflow: dict) -> tuple[int, list[str]]:
    """Conservatively include references from disabled/unreachable nodes."""
    nodes = workflow["nodes"]
    if len(nodes) > 800:
        raise AuditBlocked("N8N_NODE_COUNT_UNEXPECTED")
    ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict):
            raise AuditBlocked("N8N_NODE_INVALID")
        all_credentials = node.get("credentials") or {}
        if not isinstance(all_credentials, dict):
            raise AuditBlocked("N8N_CREDENTIAL_REFERENCE_INVALID")
        cred = all_credentials.get("postgres")
        if cred is None:
            continue
        if not isinstance(cred, dict):
            raise AuditBlocked("N8N_CREDENTIAL_REFERENCE_INVALID")
        cid = cred.get("id")
        if not isinstance(cid, str) or not CREDENTIAL_ID.fullmatch(cid):
            raise AuditBlocked("N8N_CREDENTIAL_REFERENCE_INVALID")
        ids.add(cid)
    if len(ids) > 30:
        raise AuditBlocked("N8N_CREDENTIAL_COUNT_UNEXPECTED")
    return len(nodes), sorted(ids)


def n8n_credentials_targets(
    container: str, workflow_id: str, *, source: str, demo: str,
) -> tuple[int, int, str]:
    if not CONTAINER_ID.fullmatch(container) or not WORKFLOW_ID.fullmatch(workflow_id):
        raise AuditBlocked("N8N_IDENTIFIER_INVALID")
    # n8n v2.4.8 CLI was source-verified for this procedure. Fail on drift.
    version = run_private_cli(
        ["docker", "exec", "-u", "node", container, "n8n", "--version"],
        timeout=40,
    ).strip()
    if version != "2.4.8":
        raise AuditBlocked("N8N_VERSION_UNSUPPORTED")
    exported = run_private_cli(
        ["docker", "exec", "-u", "node", container, "n8n",
         "export:workflow", "--id=" + workflow_id],
    )
    workflow = parse_n8n_one(exported, workflow_id, decrypted=False)
    n_nodes, ids = find_pg_credentials(workflow)
    if not ids:
        # Zero DB credential IDs cannot certify a database-independent workflow.
        return n_nodes, 0, "UNKNOWN"
    targets: list[str] = []
    for credential_id in ids:
        # Locally decrypted only in an ephemeral process pipe, never in
        # stdout/stderr from this script or in an on-disk export file.
        raw = run_private_cli(
            ["docker", "exec", "-u", "node", container, "n8n",
             "export:credentials", "--id=" + credential_id, "--decrypted"],
        )
        credential = parse_n8n_one(raw, credential_id, decrypted=True)
        targets.append(classify_pg_credential(credential["data"], source=source, demo=demo))
    if "SOURCE" in targets:
        combined = "SOURCE"
    elif "UNKNOWN" in targets or len(set(targets)) > 1:
        combined = "UNKNOWN"
    else:
        combined = targets[0]
    if combined not in ALLOWED_RESULTS:
        raise AuditBlocked("N8N_CLASSIFICATION_INVALID")
    return n_nodes, len(ids), combined


def audit(*, source: str, demo: str, shadow_container: str,
          n8n_container: str | None, workflow_id: str | None,
          inspect_n8n: bool) -> dict[str, str]:
    if not PROJECT_REF.fullmatch(source) or not PROJECT_REF.fullmatch(demo) or source == demo:
        raise AuditBlocked("PROJECT_REFS_INVALID")
    runtime_env = running_docker_environment(shadow_container)
    result = {
        "SHADOW_EVIDENCE_TARGET": classify_dsn(
            runtime_env.get("LANGGRAPH_SHADOW_DATABASE_DSN"), source=source, demo=demo
        ),
        "SHADOW_CONTEXT_TARGET": classify_dsn(
            runtime_env.get("CONTEXT_POSTGRES_DSN"), source=source, demo=demo
        ),
        "SHADOW_REAL_SQL_EXECUTION_DISABLED": (
            "PASS" if runtime_env.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") == "false"
            else "BLOCKED"
        ),
        "N8N_OFFICIAL_CREDENTIAL_TARGET": "NOT_AUDITED",
        "N8N_PUBLISHED_VERSION": "NOT_ATTESTED",
    }
    if inspect_n8n:
        if not n8n_container or not workflow_id:
            raise AuditBlocked("N8N_AUDIT_IDENTIFIERS_REQUIRED")
        if not sys.stdin.isatty():
            raise AuditBlocked("LOCAL_TTY_CONFIRMATION_REQUIRED")
        answer = input("Auditar localmente credenciais n8n em memoria? Digite AUDIT-N8N-LOCAL: ")
        if answer != "AUDIT-N8N-LOCAL":
            raise AuditBlocked("N8N_LOCAL_CONSENT_REQUIRED")
        nodes, credentials, target = n8n_credentials_targets(
            n8n_container, workflow_id, source=source, demo=demo
        )
        result["N8N_OFFICIAL_NODE_COUNT"] = str(nodes)
        result["N8N_POSTGRES_CREDENTIAL_COUNT"] = str(credentials)
        result["N8N_OFFICIAL_CREDENTIAL_TARGET"] = target
        # A stored workflow export is NOT proof of the version currently
        # published to webhooks in n8n 2.4.8. Independently reconcile G1.
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-project-ref", required=True)
    p.add_argument("--demo-project-ref", required=True)
    p.add_argument("--shadow-container", required=True)
    p.add_argument("--n8n-container", default=None)
    p.add_argument("--official-workflow-id", default=None)
    p.add_argument("--inspect-n8n-credentials", action="store_true")
    args = p.parse_args()
    print("SUPABASE_DEPENDENCY_AUDIT=READ_ONLY")
    try:
        result = audit(
            source=args.source_project_ref,
            demo=args.demo_project_ref,
            shadow_container=args.shadow_container,
            n8n_container=args.n8n_container,
            workflow_id=args.official_workflow_id,
            inspect_n8n=args.inspect_n8n_credentials,
        )
        for key, value in result.items():
            # Only vetted enum and counts emitted; no raw DSNs or metadata.
            if not isinstance(value, str) or len(value) > 30:
                raise AuditBlocked("UNSAFE_STATUS_VALUE")
            print("SUPABASE_" + key + "=" + value)
        print("SUPABASE_SOURCE_RETIREMENT=BLOCKED_PENDING_ARCHIVE_AND_CUTOVER")
        return 0
    except (AuditBlocked, ValueError) as exc:
        print("SUPABASE_DEPENDENCY_AUDIT=BLOCKED")
        print("SUPABASE_DEPENDENCY_ERROR=" + (str(exc) if isinstance(exc, AuditBlocked) else "INVALID_INPUT"))
        return 2
    except Exception:
        # Exceptions from third party/Docker may embed secrets; suppress them.
        print("SUPABASE_DEPENDENCY_AUDIT=BLOCKED")
        print("SUPABASE_DEPENDENCY_ERROR=UNEXPECTED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

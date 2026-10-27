#!/usr/bin/env python3
"""Read-only inventory after a partially failed G1 credential POST.

No DB writes, no n8n POST/PUT, no decrypted credential exports, no SQL.
Credential exports are processed in memory: never print, save or log them.
"""
from __future__ import annotations

import argparse
import getpass
import json
import re
import subprocess
import sys
from pathlib import Path

from g1_readonly_rollout import (
    N8nApi,
    RolloutError,
    assert_binding_id,
    load_config,
    read_n8n_runtime_version,
    validate_workflow,
    workflow_fingerprint,
)


def find_n8n_container(explicit: str) -> str:
    if explicit:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,180}", explicit):
            raise RolloutError("nome de container invalido")
        return explicit
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}} {{.Image}}"],
            capture_output=True, text=True, check=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RolloutError("nao foi possivel localizar n8n") from exc
    containers = [line.split()[0] for line in result.stdout.splitlines()
                  if len(line.split()) >= 2 and
                  re.search(r"(^|/)n8n([:@]|$)", " ".join(line.split()[1:]).lower())]
    if len(containers) != 1:
        raise RolloutError("container n8n ausente ou ambiguo")
    return containers[0]


def parse_encrypted_export(stdout: str, role: str, credential_type: str) -> int:
    """Count matching metadata, discarding all encrypted credential data.

    n8n 2.4.8 prints JSON via its logger, which may add informational lines.
    Recognize only a JSON array whose members have credential metadata.
    Never echo any part of stdout, including in exceptions.
    """
    if not stdout or len(stdout) > 16_000_000:
        raise RolloutError("inventario de credenciais invalido ou grande")
    matches = []
    decoder = json.JSONDecoder()
    for candidate in re.finditer(r"\[\s*\{", stdout):
        try:
            value, _ = decoder.raw_decode(stdout[candidate.start():])
        except (ValueError, TypeError):
            continue
        if not isinstance(value, list) or not value:
            continue
        if not all(isinstance(item, dict) and
                   isinstance(item.get("id"), str) and
                   isinstance(item.get("name"), str) and
                   isinstance(item.get("type"), str)
                   for item in value):
            continue
        matches.append(value)
    if len(matches) != 1:
        raise RolloutError("JSON de credenciais nao verificavel")
    credentials = matches[0]
    names = [item["name"] for item in credentials if
             item["type"] == credential_type and
             re.fullmatch(re.escape(role) + r"-[0-9]{14}", item["name"])]
    return len(names)


def inventory_credentials(container: str, role: str, credential_type: str) -> int:
    """Invoke encrypted-only n8n CLI, keeping stdout/stderr in process memory."""
    try:
        result = subprocess.run(
            ["docker", "exec", "-u", "node", container,
             "n8n", "export:credentials", "--all"],
            capture_output=True, text=True, timeout=60, check=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RolloutError("exportacao criptografada read-only falhou") from exc
    return parse_encrypted_export(result.stdout, role, credential_type)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("g1_readonly_rollout.json"))
    parser.add_argument("--n8n-url", required=True)
    parser.add_argument("--n8n-container", default="")
    parser.add_argument("--snapshot", type=Path, default=Path.home() /
                        ".local/state/agente-sql-langgraph/g1-readonly-snapshot.json")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    print("G1_RECONCILE_MODE=READ_ONLY")
    if args.snapshot.exists() or args.snapshot.is_symlink():
        raise RolloutError("snapshot G1 existe; requer analise separada")
    container = find_n8n_container(args.n8n_container)
    read_n8n_runtime_version(config, container)
    count = inventory_credentials(container, config.raw["role_name"],
                                  config.n8n["credential_type"])
    print("G1_CREDENTIAL_MATCHES=" + str(count))
    api_key = getpass.getpass("n8n API key (sem eco): ")
    try:
        api = N8nApi(args.n8n_url, api_key)
    finally:
        api_key = ""
    workflow = api.request("GET", "/api/v1/workflows/" + config.n8n["workflow_id"])
    validate_workflow(workflow, config, require_old_bindings=True)
    assert_binding_id(workflow, config, config.n8n["old_credential_id"])
    print("G1_N8N_BINDINGS=OLD_BINDINGS_CONFIRMED")
    print("G1_WORKFLOW_FINGERPRINT=" + workflow_fingerprint(workflow)[:12])
    print("G1_SNAPSHOT=ABSENT")
    if count == 0:
        print("G1_RECOVERY=NO_CREDENTIAL_FOUND_DO_NOT_RETRY_APPLY")
    else:
        print("G1_RECOVERY=POTENTIAL_ORPHAN_CREDENTIAL_REVIEW_REQUIRED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RolloutError as exc:
        print("G1_RECOVERY=BLOCKED_REVIEW_REQUIRED")
        print("ERROR=" + str(exc), file=sys.stderr)
        raise SystemExit(2)
    except Exception:
        print("G1_RECOVERY=BLOCKED_REVIEW_REQUIRED")
        print("ERROR=OPERACAO_INESPERADA", file=sys.stderr)
        raise SystemExit(2)

#!/usr/bin/env python3
"""Operator-gated migration of ONLY the official n8n LLM provider HTTP transports.

Dry-run is the default; no n8n API key, n8n writes, provider calls or SQL.
Apply/rollback require a local typed confirmation and an n8n API key entered
via getpass, never command-line, environment output or a repository file.
Never implicitly activate LangGraph or alter finance execution permissions.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.n8n.official_sql_infodive_provider_candidate import (
    Blocked, _read_export, check, fingerprint, prepare_candidate,
)
from scripts.operations.g1_readonly_rollout import (
    N8nApi, RolloutError, workflow_projection,
)

EXPECTED_NODES_MIN = 1
EXPECTED_NODES_MAX = 2500
WORKFLOW_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")


def _validate_private_directory(path: Path) -> None:
    check(path.is_absolute() and path.is_dir() and not path.is_symlink(),
          "BACKUP_DIRECTORY_INVALID")
    check((stat.S_IMODE(path.stat().st_mode) & 0o077) == 0,
          "BACKUP_DIRECTORY_PERMISSIONS_UNSAFE")


def _private_create(path: Path, content: object) -> None:
    payload = json.dumps(content, sort_keys=True, ensure_ascii=True) + "\n"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(str(path), flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
    except (OSError, ValueError):
        raise Blocked("BACKUP_WRITE_FAILED") from None


def _load_config(path: Path) -> dict:
    check(path.is_file() and not path.is_symlink() and path.stat().st_size < 65536,
          "PROVIDER_CONFIG_MISSING")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        raise Blocked("PROVIDER_CONFIG_INVALID") from None
    check(isinstance(result, dict), "PROVIDER_CONFIG_INVALID")
    return result


def _published_and_active(workflow: Mapping[str, Any], workflow_id: str) -> bool:
    return (
        workflow.get("id") == workflow_id
        and workflow.get("active") is True
        and isinstance(workflow.get("activeVersionId"), str)
        and bool(workflow.get("activeVersionId"))
        and workflow.get("activeVersionId") == workflow.get("versionId")
    )


def _projection(workflow: Mapping[str, Any]) -> dict:
    try:
        return workflow_projection(workflow)
    except (RolloutError, KeyError, TypeError, ValueError):
        raise Blocked("N8N_PUBLIC_PUT_SCHEMA_UNSUPPORTED") from None


def _assert_baseline(
    cli: Mapping[str, Any],
    api_workflow: Mapping[str, Any],
    workflow_id: str,
) -> None:
    check(_published_and_active(cli, workflow_id)
          and _published_and_active(api_workflow, workflow_id),
          "PUBLISHED_REVISION_NOT_ALIGNED")
    check(cli.get("versionId") == api_workflow.get("versionId")
          and cli.get("activeVersionId") == api_workflow.get("activeVersionId"),
          "CLI_API_PUBLISHED_REVISION_MISMATCH")
    check(_projection(cli) == _projection(api_workflow),
          "CLI_API_CONTENT_DRIFT")


def _assert_only_four_changes(before: Mapping[str, Any],
                              after: Mapping[str, Any],
                              expected: Mapping[str, Any]) -> None:
    a, b, wanted = _projection(before), _projection(after), _projection(expected)
    check(len(a["nodes"]) == len(b["nodes"]) == len(wanted["nodes"]),
          "POST_APPLY_NODE_COUNT_DRIFT")
    check(a["connections"] == b["connections"] == wanted["connections"],
          "POST_APPLY_CONNECTION_DRIFT")
    check(a["name"] == b["name"] == wanted["name"],
          "POST_APPLY_NAME_DRIFT")
    # n8n 2.4.8 can prune literal defaults from settings on PUT, but that
    # change MUST be reviewed, not automatically declared equivalent.
    check(a["settings"] == b["settings"] == wanted["settings"],
          "POST_APPLY_SETTINGS_DRIFT")
    check(b["nodes"] == wanted["nodes"],
          "POST_APPLY_NODE_CONTENT_DRIFT")


def _check_credential(api: N8nApi, configuration: dict) -> None:
    # Public list supplies metadata only, never decrypted secrets.
    target = configuration["credential_id"]
    cred_type = configuration["credential_type"]
    try:
        listing = api.request("GET", "/api/v1/credentials")
    except RolloutError:
        raise Blocked("N8N_CREDENTIAL_LIST_UNAVAILABLE") from None
    items = listing.get("data") if isinstance(listing, dict) else None
    check(isinstance(items, list), "N8N_CREDENTIAL_LIST_INVALID")
    matches = [item for item in items
               if isinstance(item, dict) and item.get("id") == target]
    check(len(matches) == 1, "N8N_PROVIDER_CREDENTIAL_NOT_FOUND")
    check(matches[0].get("type") == cred_type and
          matches[0].get("name") == configuration["credential_name"],
          "N8N_PROVIDER_CREDENTIAL_TYPE_MISMATCH")


def _require_confirmation(value: str) -> None:
    if input("Digite " + value + " para confirmar a mudanca n8n: ").strip() != value:
        raise Blocked("LOCAL_APPROVAL_MISSING")


def _make_api(base: str) -> N8nApi:
    key = getpass.getpass("n8n API key (sem eco): ")
    try:
        return N8nApi(base, key)
    except RolloutError:
        raise Blocked("N8N_API_AUTH_INVALID") from None
    finally:
        key = ""


def dry_run(*, container: str, workflow_id: str, config: dict,
            expected_sha: str) -> dict[str, object]:
    before = _read_export(container, workflow_id)
    check(_published_and_active(before, workflow_id), "STORED_NOT_PUBLISHED")
    check(fingerprint(before) == expected_sha, "WORKFLOW_SHA_DRIFT")
    candidate, change = prepare_candidate(before, workflow_id, config)
    _projection(candidate)  # catch unsupported public PUT fields before writes
    return {
        "mode": "DRY_RUN",
        "status": "READY",
        "baseline_sha256": expected_sha,
        "candidate_sha256": change["candidate_sha256"],
        "changed_nodes": change["changed_nodes"],
        "n8n_nodes": len(before["nodes"]),
        "provider_calls": 0,
        "sql_executed": False,
        "n8n_modified": False,
    }


def apply(*, api: N8nApi, container: str, workflow_id: str, config: dict,
          expected_sha: str, backup_dir: Path) -> dict[str, object]:
    # All safety gates must complete before any write.
    _validate_private_directory(backup_dir)
    cli = _read_export(container, workflow_id)
    check(fingerprint(cli) == expected_sha, "WORKFLOW_SHA_DRIFT")
    before = api.request("GET", f"/api/v1/workflows/{workflow_id}")
    check(isinstance(before, dict), "N8N_API_WORKFLOW_INVALID")
    _assert_baseline(cli, before, workflow_id)
    _check_credential(api, config)
    candidate, report = prepare_candidate(before, workflow_id, config)
    payload = _projection(candidate)
    backup_path = backup_dir / ("official-llm-before-" + expected_sha[:16] + ".json")
    _private_create(backup_path, {
        "workflow_id": workflow_id, "before": before,
        "baseline_sha256": expected_sha,
    })
    # Recheck immediately before n8n PUT. Never overwrite concurrent changes.
    fresh = api.request("GET", f"/api/v1/workflows/{workflow_id}")
    check(fingerprint(fresh) == fingerprint(before), "WORKFLOW_CHANGED_BEFORE_PUT")
    api.request("PUT", f"/api/v1/workflows/{workflow_id}", payload)
    after = api.request("GET", f"/api/v1/workflows/{workflow_id}")
    check(isinstance(after, dict), "POST_APPLY_READ_FAILED_BACKUP_REQUIRED")
    check(_published_and_active(after, workflow_id),
          "POST_APPLY_NOT_PUBLISHED_BACKUP_REQUIRED")
    _assert_only_four_changes(before, after, candidate)
    receipt_path = backup_dir / ("official-llm-receipt-" + expected_sha[:16] + ".json")
    _private_create(receipt_path, {
        "workflow_id": workflow_id, "baseline_sha256": expected_sha,
        "applied_sha256": fingerprint(after),
        "candidate_sha256": report["candidate_sha256"],
    })
    return {
        "mode": "APPLY",
        "status": "APPLIED_AND_VERIFIED",
        "changed_nodes": 4,
        "published_version_aligned": True,
        "backup_created": True,
        "receipt_created": True,
        "sql_executed_by_script": False,
        "provider_calls_by_script": 0,
    }


def rollback(*, api: N8nApi, container: str, workflow_id: str,
             backup_dir: Path, baseline_sha: str) -> dict[str, object]:
    _validate_private_directory(backup_dir)
    backup_path = backup_dir / ("official-llm-before-" + baseline_sha[:16] + ".json")
    receipt_path = backup_dir / ("official-llm-receipt-" + baseline_sha[:16] + ".json")
    check(backup_path.is_file() and not backup_path.is_symlink()
          and receipt_path.is_file() and not receipt_path.is_symlink(),
          "ROLLBACK_PRIVATE_EVIDENCE_MISSING")
    check(stat.S_IMODE(backup_path.stat().st_mode) & 0o077 == 0
          and stat.S_IMODE(receipt_path.stat().st_mode) & 0o077 == 0,
          "ROLLBACK_PRIVATE_PERMISSIONS_UNSAFE")
    try:
        saved = json.loads(backup_path.read_text(encoding="utf-8"))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise Blocked("ROLLBACK_EVIDENCE_INVALID") from None
    check(saved.get("workflow_id") == workflow_id
          and receipt.get("workflow_id") == workflow_id
          and saved.get("baseline_sha256") == baseline_sha
          and receipt.get("baseline_sha256") == baseline_sha,
          "ROLLBACK_EVIDENCE_IDENTITY_MISMATCH")
    before = saved.get("before")
    check(isinstance(before, dict), "ROLLBACK_WORKFLOW_INVALID")
    current = api.request("GET", f"/api/v1/workflows/{workflow_id}")
    check(isinstance(current, dict) and
          fingerprint(current) == receipt.get("applied_sha256"),
          "ROLLBACK_CURRENT_REVISION_CHANGED")
    check(_published_and_active(current, workflow_id), "ROLLBACK_NOT_PUBLISHED")
    api.request("PUT", f"/api/v1/workflows/{workflow_id}", _projection(before))
    restored = api.request("GET", f"/api/v1/workflows/{workflow_id}")
    check(isinstance(restored, dict) and _published_and_active(restored, workflow_id),
          "ROLLBACK_POST_VERIFY_FAILED")
    check(_projection(restored) == _projection(before),
          "ROLLBACK_POST_VERIFY_FAILED")
    return {
        "mode": "ROLLBACK",
        "status": "RESTORED_AND_VERIFIED",
        "sql_executed_by_script": False,
        "provider_calls_by_script": 0,
    }


def main() -> int:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n8n-container", required=True)
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--expected-stored-sha", required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--n8n-url")
    parser.add_argument("--private-backup-dir", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--rollback", action="store_true")
    args = parser.parse_args()
    print("INFODIVE_OFFICIAL_OPERATION=" +
          ("ROLLBACK" if args.rollback else "APPLY" if args.apply else "DRY_RUN"))
    try:
        check(bool(WORKFLOW_ID.fullmatch(args.workflow_id)) and
              bool(HASH.fullmatch(args.expected_stored_sha)),
              "IDENTITY_INVALID")
        if not args.rollback:
            check(args.config is not None, "PROVIDER_CONFIG_MISSING")
            config = _load_config(args.config)
        if args.apply or args.rollback:
            check(args.private_backup_dir is not None and args.n8n_url,
                  "N8N_API_OR_BACKUP_REQUIRED")
            _require_confirmation(
                "ROLLBACK-INFODIVE" if args.rollback else "APPLY-INFODIVE"
            )
            api = _make_api(args.n8n_url)
            result = (rollback(
                api=api, container=args.n8n_container, workflow_id=args.workflow_id,
                baseline_sha=args.expected_stored_sha,
                backup_dir=args.private_backup_dir,
            ) if args.rollback else apply(
                api=api, container=args.n8n_container, workflow_id=args.workflow_id,
                config=config, expected_sha=args.expected_stored_sha,
                backup_dir=args.private_backup_dir,
            ))
        else:
            result = dry_run(
                container=args.n8n_container, workflow_id=args.workflow_id,
                config=config, expected_sha=args.expected_stored_sha,
            )
        for name, value in result.items():
            print("INFODIVE_OFFICIAL_" + name.upper() + "=" + str(value))
        return 0
    except (Blocked, RolloutError) as error:
        print("INFODIVE_OFFICIAL_STATUS=BLOCKED")
        print("INFODIVE_OFFICIAL_REASON=" +
              (str(error) if isinstance(error, Blocked) else "N8N_API_REJECTED"))
        return 2
    except Exception:
        # No raw exception, headers, DSN, SQL, credential, URL or workflow.
        print("INFODIVE_OFFICIAL_STATUS=BLOCKED")
        print("INFODIVE_OFFICIAL_REASON=UNEXPECTED_FAILURE")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Reconcile only an authorized seven-node n8n Shadow candidate.

Default: READ-ONLY review of a live workflow using the n8n 2.4.8 public API.
Apply requires an exact fresh snapshot hash, explicit opt-in and a private
pre-change backup. Never uses n8n import:workflow (which deactivates active
workflows), never edits the official finance workflow and never calls an LLM
or a financial SQL endpoint.

No request/response body, JS code, internal URL or credential data is logged.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import pathlib
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.n8n.render_parallel_shadow_workflow import (
    render_private_candidate, validate_internal_base_url,
)
from scripts.n8n.verify_parallel_shadow_bindings_export import (
    CALL_EXPRESSION, BindingAuditError, validate_export,
)

# Only known versions of this *structural n8n workflow*, not a business
# benchmark or an old customer prompt. A modified or unfamiliar Code node
# must be investigated rather than silently "repaired".
HISTORICAL_CANDIDATE_COMMITS = (
    "c329002cb48e4a4f4a27b8020e563440fb98e480",
    "ddc6e90174f74be43b0c1d31bd29846ef9bb2bdf",
    "7b9fd2f4c5e71943470b5e3ff06b229b0f41f5a6",
    "cdbe001d6c6b05f9e8b7693bc5ca2466ec7992d7",
)
TEMPLATE_PATH = "scripts/n8n/parallel_langgraph_shadow_v1.workflow.json"
CODE_NAMES = (
    "Validate Shadow Envelope",
    "Validate LangGraph Response",
    "Assert Shadow Evidence",
)
CALL_NAME = "Call LangGraph Shadow"
READ_NAME = "Read Correlated Evidence"
WORKFLOW_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
MAX_BYTES = 2 * 1024 * 1024
# n8n@2.4.8 public API node.yml explicitly marks timestamps as readOnly.
# These may appear in an exported node but must never be PUT back.
# All edit-authorized fields below come from the published node.yml.
API_NODE_READ_ONLY_FIELDS = frozenset(("createdAt", "updatedAt"))
API_NODE_FIELDS = frozenset((
    "id", "name", "type", "typeVersion", "position", "parameters",
    "credentials", "webhookId", "disabled", "notes", "notesInFlow",
    "executeOnce", "alwaysOutputData", "retryOnFail", "maxTries",
    "waitBetweenTries", "continueOnFail", "onError",
))
API_SETTINGS_FIELDS = frozenset((
    "executionOrder", "saveDataSuccessExecution", "saveDataErrorExecution",
    "saveManualExecutions", "saveExecutionProgress", "executionTimeout",
    "errorWorkflow", "timezone", "callerPolicy", "callerIds",
    "timeSavedPerExecution", "availableInMCP",
))
# n8n@2.4.8 supports timeSavedMode ('fixed' | 'dynamic') internally, but
# public workflowSettings.yml sets additionalProperties=false and omits it.
# WorkflowService.update merges PUT settings over the persisted settings;
# keep this one validated server-retained field outside the public PUT, then
# attest that ALL settings stayed unchanged after the authorized update.
# Never treat arbitrary unknown settings as safe to omit.
API_SETTINGS_SERVER_RETAINED_FIELDS = frozenset(("timeSavedMode",))


class ReconcileError(ValueError):
    """Fixed safe-to-display failure label."""


def _fail(code: str):
    raise ReconcileError(code)


def _sha(raw: Mapping) -> str:
    return hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def _historical_code() -> dict[str, dict[str, str]]:
    options = {name: {} for name in CODE_NAMES}
    for commit in HISTORICAL_CANDIDATE_COMMITS:
        try:
            data = subprocess.check_output(
                ["git", "show", f"{commit}:{TEMPLATE_PATH}"],
                cwd=ROOT, stderr=subprocess.DEVNULL, timeout=8,
            )
            workflow = json.loads(data)
        except (OSError, subprocess.SubprocessError, ValueError):
            _fail("HISTORICAL_SOURCE_UNAVAILABLE")
        nodes = {node["name"]: node for node in workflow["nodes"]}
        for name in CODE_NAMES:
            options[name][nodes[name]["parameters"]["jsCode"]] = commit[:7]
    return options


def _old_read_url(latest: str) -> str:
    # Exact known former route: no run_id filter. Never construct
    # a dynamic URL from arbitrary strings in a live workflow.
    old_suffix = (
        "+ '/shadow-runs?run_id=' + encodeURIComponent($json.run_id)"
        " + '&limit=10'"
    )
    if latest.count(old_suffix) != 1:
        _fail("REVIEWED_READ_CONTRACT_CHANGED")
    return latest.replace(old_suffix, "+ '/shadow-runs?limit=10'")


def build_reconciliation(raw: Mapping, workflow_id: str,
                         known: Mapping[str, Mapping[str, str]]
                         ) -> tuple[dict, list[dict]]:
    """Pure fail-closed classification and in-memory candidate construction."""
    if not WORKFLOW_ID_RE.fullmatch(workflow_id):
        _fail("WORKFLOW_ID_INVALID")
    if not isinstance(raw, Mapping) or raw.get("id") != workflow_id:
        _fail("WORKFLOW_ID_MISMATCH")
    nodes = raw.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != 7:
        _fail("NODE_SET_MISMATCH")
    if any(not isinstance(n, Mapping) for n in nodes):
        _fail("NODE_SET_MISMATCH")
    by_name = {n.get("name"): n for n in nodes}
    if len(by_name) != 7 or CALL_NAME not in by_name:
        _fail("NODE_SET_MISMATCH")
    try:
        call_url = by_name[CALL_NAME]["parameters"]["url"]
        match = CALL_EXPRESSION.fullmatch(call_url)
        if match is None:
            _fail("PRIVATE_CALL_URL_UNRECOGNIZED")
        base = json.loads(match.group(1))
        if validate_internal_base_url(base) != base:
            _fail("PRIVATE_CALL_URL_UNRECOGNIZED")
        expected = render_private_candidate(base)
    except (ValueError, TypeError, KeyError, AttributeError, BindingAuditError):
        _fail("PRIVATE_CALL_URL_UNRECOGNIZED")
    updated = copy.deepcopy(raw)
    changed = []
    want_nodes = {n["name"]: n for n in expected["nodes"]}
    got_nodes = {n["name"]: n for n in updated["nodes"]}
    if set(got_nodes) != set(want_nodes):
        _fail("NODE_SET_MISMATCH")
    for name in CODE_NAMES:
        have = got_nodes[name]["parameters"].get("jsCode")
        target = want_nodes[name]["parameters"]["jsCode"]
        if have == target:
            continue
        if not isinstance(have, str) or have not in known[name]:
            _fail("UNKNOWN_CODE_REVISION")
        got_nodes[name]["parameters"]["jsCode"] = target
        changed.append({"node": name, "source_revision": known[name][have]})
    read = got_nodes[READ_NAME]
    actual_read_url = read["parameters"].get("url")
    latest_read_url = want_nodes[READ_NAME]["parameters"]["url"]
    if actual_read_url != latest_read_url:
        if actual_read_url != _old_read_url(latest_read_url):
            _fail("UNKNOWN_READ_URL_REVISION")
        read["parameters"]["url"] = latest_read_url
        changed.append({"node": READ_NAME, "source_revision": "pre-run-id"})
    # Keep default-GET serialization exactly as stored (n8n 2.x omits GET).
    try:
        validate_export(
            updated, workflow_id, expect_active=True,
            require_active_version_match=True,
        )
    except BindingAuditError as exc:
        # Do not print credential IDs, URLs or n8n fields even if a
        # validation exception is enriched in the future.
        _fail("OTHER_BINDING_GUARD_FAILED")
    return updated, changed


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class N8nApi:
    def __init__(self, base_url: str, api_key: str):
        parsed = urllib.parse.urlsplit(base_url)
        if (
            parsed.scheme != "https" or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment
            or not isinstance(api_key, str) or len(api_key.strip()) < 16
        ):
            _fail("N8N_API_CONFIGURATION_INVALID")
        self.base = base_url.rstrip("/")
        self.key = api_key
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ssl.create_default_context()),
            _NoRedirect(),
        )

    def exchange(self, workflow_id: str, method: str,
                 payload: dict | None = None) -> dict:
        if not WORKFLOW_ID_RE.fullmatch(workflow_id):
            _fail("WORKFLOW_ID_INVALID")
        url = self.base + "/api/v1/workflows/" + urllib.parse.quote(
            workflow_id, safe="",
        )
        content = None if payload is None else json.dumps(
            payload, separators=(",", ":"), ensure_ascii=True,
        ).encode("utf-8")
        request = urllib.request.Request(
            url, method=method, data=content,
            headers={
                "X-N8N-API-KEY": self.key,
                "Accept": "application/json",
                **({"Content-Type": "application/json"} if content else {}),
            },
        )
        try:
            with self.opener.open(request, timeout=20) as response:
                data = response.read(MAX_BYTES + 1)
                if len(data) > MAX_BYTES:
                    _fail("N8N_RESPONSE_TOO_LARGE")
                output = json.loads(data)
        except urllib.error.HTTPError as exc:
            # Server response bodies can contain private workflow info;
            # print only a fixed code, never exception strings or headers.
            _fail("N8N_HTTP_REJECTED_" + str(exc.code))
        except (urllib.error.URLError, OSError, ValueError):
            _fail("N8N_TRANSPORT_OR_RESPONSE_FAILED")
        if not isinstance(output, dict) or output.get("id") != workflow_id:
            _fail("N8N_RESPONSE_IDENTITY_MISMATCH")
        return output


def _public_update_payload(workflow: dict) -> dict:
    """Strict n8n@2.4.8 public PUT schema, no arbitrary entity metadata."""
    if not isinstance(workflow.get("name"), str) or not workflow["name"]:
        _fail("N8N_UPDATE_SCHEMA_UNSUPPORTED")
    if not isinstance(workflow.get("connections"), dict):
        _fail("N8N_UPDATE_SCHEMA_UNSUPPORTED")
    settings = workflow.get("settings")
    if not isinstance(settings, dict):
        _fail("N8N_UPDATE_SCHEMA_UNSUPPORTED_SETTINGS")
    if set(settings) - API_SETTINGS_FIELDS - API_SETTINGS_SERVER_RETAINED_FIELDS:
        # Unknown settings can alter workflow execution or exposure; never
        # drop or forward them merely to satisfy an API schema check.
        _fail("N8N_UPDATE_SCHEMA_UNSUPPORTED_SETTINGS_FIELDS")
    if "timeSavedMode" in settings and settings["timeSavedMode"] not in (
        "fixed", "dynamic",
    ):
        _fail("N8N_UPDATE_SCHEMA_UNSUPPORTED_SETTINGS_TIME_SAVED_MODE")
    # A n8n 2.4.8 public PUT cannot accept timeSavedMode, but n8n's
    # WorkflowService.update preserves it by merging the submitted settings.
    # The dry-run checks compatibility without changing the original export.
    public_settings = {
        key: copy.deepcopy(value) for key, value in settings.items()
        if key in API_SETTINGS_FIELDS
    }
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != 7:
        _fail("N8N_UPDATE_SCHEMA_UNSUPPORTED_NODES")
    public_nodes = []
    for node in nodes:
        if not isinstance(node, dict):
            _fail("N8N_UPDATE_SCHEMA_UNSUPPORTED_NODES")
        unknown_fields = set(node) - API_NODE_FIELDS - API_NODE_READ_ONLY_FIELDS
        if unknown_fields:
            # Deliberately report only the category, not untrusted key names
            # or values supplied by a potentially modified workflow.
            _fail("N8N_UPDATE_SCHEMA_UNSUPPORTED_NODE_FIELDS")
        # Project to *only* editable schema fields. The only discarded
        # fields are documented n8n-managed timestamps; credentials,
        # workflow topology, parameters and node IDs remain unchanged.
        public_nodes.append({
            key: copy.deepcopy(value) for key, value in node.items()
            if key in API_NODE_FIELDS
        })
    payload = {
        "name": workflow["name"],
        "nodes": public_nodes,
        "connections": copy.deepcopy(workflow["connections"]),
        "settings": public_settings,
    }
    if "staticData" in workflow:
        if workflow["staticData"] is not None and not isinstance(
            workflow["staticData"], (dict, str),
        ):
            _fail("N8N_UPDATE_SCHEMA_UNSUPPORTED")
        payload["staticData"] = workflow["staticData"]
    return payload


def reconcile(api, workflow_id: str, *, apply: bool = False,
              expected_hash: str = "", backup_dir: pathlib.Path | None = None,
              approved: bool = False,
              known: Mapping[str, Mapping[str, str]] | None = None) -> dict:
    before = api.exchange(workflow_id, "GET")
    hash_before = _sha(before)
    updated, changes = build_reconciliation(
        before, workflow_id, known if known is not None else _historical_code(),
    )
    payload = _public_update_payload(updated)  # fail in dry-run too.
    report = {
        "mode": "apply" if apply else "dry_run",
        "status": "ready" if changes else "already_current",
        "snapshot_sha256": hash_before,
        "changed_nodes": changes,
        "published_identity_verified": True,
        "financial_sql_executed": False,
        "llm_calls": 0,
    }
    if not apply:
        return report
    if not changes:
        _fail("NO_CHANGE_TO_APPLY")
    if not approved:
        _fail("EXPLICIT_OPERATIONAL_APPROVAL_REQUIRED")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        _fail("EXPECTED_SNAPSHOT_HASH_REQUIRED")
    if expected_hash != hash_before:
        _fail("WORKFLOW_SNAPSHOT_CHANGED")
    if os.name != "posix":
        # Windows does not enforce POSIX mode bits for 0700 directories.
        # This privileged apply operation is supported only on the Linux VPS.
        _fail("APPLY_REQUIRES_POSIX_HOST")
    if backup_dir is None or not backup_dir.is_absolute():
        _fail("PRIVATE_BACKUP_DIR_REQUIRED")
    # Avoid writing into directories controlled by a different user.
    if not backup_dir.is_dir() or backup_dir.is_symlink():
        _fail("PRIVATE_BACKUP_DIR_INVALID")
    if backup_dir.stat().st_mode & 0o077:
        _fail("PRIVATE_BACKUP_PERMISSIONS_UNSAFE")
    # Re-read immediately before PUT; public API has no atomic If-Match.
    if _sha(api.exchange(workflow_id, "GET")) != hash_before:
        _fail("WORKFLOW_CHANGED_BEFORE_APPLY")
    backup_file = backup_dir / ("g1-candidate-" + hash_before[:12] + ".json")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(backup_file, flags, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(before, handle, ensure_ascii=True, sort_keys=True)
            handle.write("\n")
    except FileExistsError:
        _fail("BACKUP_ALREADY_EXISTS")
    except OSError:
        _fail("BACKUP_WRITE_FAILED")
    # n8n 2.4.8 public PUT republishes when already published. Never use
    # import:workflow (which *deactivates* an active workflow).
    api.exchange(workflow_id, "PUT", payload)
    after = api.exchange(workflow_id, "GET")
    try:
        # The PUT is ONLY a four-parameter transport upgrade, not a settings
        # migration. In particular, timeSavedMode must remain unchanged even
        # though the public API rejects it in the update request.
        if after.get("settings") != before.get("settings"):
            _fail("POST_APPLY_SETTINGS_DRIFT")
        # Only accept the exact patched parameters; n8n may rewrite the
        # version IDs, but must preserve all audited structural invariants.
        if not after.get("active") or (
            after.get("versionId") != after.get("activeVersionId")
        ):
            _fail("POST_APPLY_PUBLICATION_NOT_ATTESTED")
        candidate, changes_left = build_reconciliation(
            after, workflow_id, known if known is not None else _historical_code(),
        )
        if changes_left:
            _fail("POST_APPLY_CONTRACT_DRIFT")
    except ReconcileError:
        # Never overwrite a concurrent third-party edit in an automatic
        # rollback. Keep the private backup and require operator review.
        _fail("POST_APPLY_VERIFY_FAILED_BACKUP_REQUIRED")
    return {
        **report,
        "status": "applied",
        "backup_created": True,
        "post_apply_published": True,
    }


class _OfflineExportApi:
    """In-memory GET-only adapter; no HTTP, API key or workflow mutation."""

    def __init__(self, exported: dict):
        self.exported = exported

    def exchange(self, workflow_id: str, method: str,
                 payload: dict | None = None) -> dict:
        if method != "GET" or self.exported.get("id") != workflow_id:
            _fail("OFFLINE_EXPORT_ACCESS_REJECTED")
        return copy.deepcopy(self.exported)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n8n-base-url")
    parser.add_argument("--workflow-file", type=pathlib.Path)
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--expected-sha256", default="")
    parser.add_argument("--backup-dir", type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        if not WORKFLOW_ID_RE.fullmatch(args.workflow_id):
            _fail("WORKFLOW_ID_INVALID")
        if bool(args.workflow_file) == bool(args.n8n_base_url):
            _fail("SELECT_ONE_INPUT_SOURCE")
        if args.workflow_file is not None:
            # Allow a local export ONLY for read-only dry-run. API key not
            # required, and even an operator opt-in cannot mutate this mode.
            if args.apply:
                _fail("OFFLINE_EXPORT_CANNOT_APPLY")
            path = args.workflow_file
            if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
                _fail("PRIVATE_EXPORT_INVALID")
            try:
                exported = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError):
                _fail("PRIVATE_EXPORT_INVALID")
            if isinstance(exported, list):
                if len(exported) != 1:
                    _fail("PRIVATE_EXPORT_NOT_SINGLE")
                exported = exported[0]
            if not isinstance(exported, dict):
                _fail("PRIVATE_EXPORT_INVALID")
            api = _OfflineExportApi(exported)
        else:
            api = N8nApi(
                args.n8n_base_url, os.environ.get("N8N_API_KEY", ""),
            )
        report = reconcile(
            api, args.workflow_id, apply=args.apply,
            expected_hash=args.expected_sha256,
            backup_dir=args.backup_dir,
            approved=os.environ.get("N8N_CANDIDATE_UPDATE_APPROVED") == "true",
        )
        print(json.dumps(report, ensure_ascii=True, sort_keys=True))
        return 0
    except ReconcileError as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)}))
        return 2
    except Exception:
        # Not even Python exception text: urllib/repo errors may embed URLs.
        print('{"status":"rejected","reason":"UNEXPECTED_SANITIZED_FAILURE"}')
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

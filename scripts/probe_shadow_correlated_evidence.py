from __future__ import annotations

"""Exercise Shadow HTTP correlation and evidence without invoking any LLM.

The POST is deliberately rejected by request validation (empty question).
Exactly one synthetic rejected evidence record is expected to be persisted.
No financial SQL is generated, executed, repaired, or approved.
"""

import json
import os
import urllib.error
import urllib.request
from uuid import uuid4


def request(method: str, path: str, token: str, payload: dict | None = None):
    port = int(os.environ.get("LANGGRAPH_HTTP_PORT", "8000"))
    encoded = (
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if payload is not None else None
    )
    headers = {"Authorization": "Bearer " + token}
    if payload is not None:
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=encoded,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return resp.status, json.loads(resp.read(65536))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read(65536))
        finally:
            exc.close()


def validate_rejection(
    *,
    agent_run_id: str,
    status: int,
    response: dict,
) -> str:
    if status != 422 or response.get("status") != "rejected":
        raise ValueError("unexpected_rejection_status")
    if response.get("agent_run_id") != agent_run_id:
        raise ValueError("agent_run_id_mismatch")
    if response.get("sql") is not None:
        raise ValueError("unexpected_sql")
    errors = response.get("errors")
    if not isinstance(errors, list) or not any(
        isinstance(e, dict)
        and e.get("code") == "INTERNAL_GENERATE_QUESTION_REQUIRED"
        for e in errors
    ):
        raise ValueError("missing_question_gate")
    run_id = response.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ValueError("missing_run_id")
    return run_id


def validate_evidence(
    *,
    agent_run_id: str,
    run_id: str,
    status: int,
    response: dict,
) -> None:
    if status != 200 or response.get("agent_run_id") != agent_run_id:
        raise ValueError("evidence_read_failed")
    items = response.get("items")
    if not isinstance(items, list):
        raise ValueError("evidence_items_missing")
    records = [
        item for item in items
        if isinstance(item, dict)
        and item.get("agent_run_id") == agent_run_id
        and item.get("run_id") == run_id
        and item.get("event_type") == "generate"
        and item.get("status") == "rejected"
        and isinstance(item.get("shadow_record_id"), str)
        and bool(item["shadow_record_id"])
    ]
    if len(records) != 1:
        raise ValueError("evidence_not_correlated")


def main() -> int:
    if os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") != "false":
        print("ABORTED: real SQL execution must be disabled")
        return 2
    token = os.environ.get("LANGGRAPH_S2S_TOKEN")
    if not token:
        print("ABORTED: authenticated Shadow unavailable")
        return 3
    agent_run_id = "shadow-probe-" + uuid4().hex
    payload = {
        "contract_version": "1",
        "agent_run_id": agent_run_id,
        "principal": {"id": "shadow-probe", "profile": "runtime_validation"},
        "question": "",
        "correlation_metadata": {
            "source": "shadow_http_probe",
            "official_flow_modified": False,
        },
    }
    try:
        status, rejected = request(
            "POST", "/v1/internal/sql-agent/generate", token, payload
        )
        run_id = validate_rejection(
            agent_run_id=agent_run_id, status=status, response=rejected
        )
        print("VALIDATION_GATE=PASS")
        status, evidence = request(
            "GET",
            f"/v1/internal/agent-runs/{agent_run_id}/shadow-runs?limit=5",
            token,
        )
        validate_evidence(
            agent_run_id=agent_run_id, run_id=run_id,
            status=status, response=evidence,
        )
        print("EVIDENCE_CORRELATION=PASS")
        print("AGENT_RUN_ID=" + agent_run_id)
        print("LLM_CALLS=0")
        print("REAL_SQL_EXECUTION=false")
        print("OFFICIAL_N8N_FLOW_MODIFIED=false")
        print("SHADOW_HTTP_EVIDENCE_PROBE=PASS")
        return 0
    except (ValueError, urllib.error.URLError, OSError) as exc:
        # No request bodies, responses, tokens or connection data in logs.
        print("SHADOW_HTTP_EVIDENCE_PROBE=FAIL")
        print("FAILURE_TYPE=" + type(exc).__name__)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())

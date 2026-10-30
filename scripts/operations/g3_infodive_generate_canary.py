#!/usr/bin/env python3
"""Opt-in SQL-InfoDive generation canary; no SQL execution or Gemini requests.

Run INSIDE the configured Shadow TEST container. Prints only sanitized metadata.
Requires explicit --invoke-private-provider. Generate may persist Shadow evidence.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import uuid

from app.infrastructure.http.http_contracts import http_transport_failure
from app.infrastructure.http.stdlib_http_transport import StdlibHttpTransport
from app.integrations.openai_compatible.configuration import (
    load_openai_compatible_configuration,
)
from app.test_runtime.composition import create_shadow_test_runtime


class PrivateOnlyTransport:
    def __init__(self) -> None:
        self.inner = StdlibHttpTransport()
        self.calls: list[tuple[str, int | None]] = []
        self.other_provider_attempted = False

    def send(self, request):
        if request.operation_name != "openai_compatible_chat_completions":
            self.other_provider_attempted = True
            return http_transport_failure("connection_failure")
        result = self.inner.send(request)
        self.calls.append((
            result.status,
            result.response.status_code if result.response is not None else None,
        ))
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--invoke-private-provider", action="store_true")
    parser.add_argument("--question", required=True)
    args = parser.parse_args()
    print("INFODIVE_CANARY_MODE=SHADOW_GENERATE_ONLY")
    if os.environ.get("LANGGRAPH_RUNTIME_MODE") != "shadow_test":
        print("INFODIVE_CANARY_STATUS=BLOCKED_RUNTIME")
        return 2
    if os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") != "false":
        print("INFODIVE_CANARY_STATUS=BLOCKED_REAL_SQL")
        return 2
    if os.environ.get("LANGGRAPH_EXPECTED_ORGANIZATION_ID"):
        # Tenant-bound systems must use the normal Product S2S request path.
        print("INFODIVE_CANARY_STATUS=BLOCKED_TENANT_BOUND")
        return 2
    if not args.question.strip() or len(args.question) > 1500:
        print("INFODIVE_CANARY_STATUS=BLOCKED_QUESTION")
        return 2
    try:
        cfg = load_openai_compatible_configuration()
    except Exception:
        print("INFODIVE_CANARY_STATUS=BLOCKED_PROVIDER_CONFIG")
        return 2
    if cfg is None or cfg.provider_key != "infodive_ibm_cloud":
        print("INFODIVE_CANARY_STATUS=BLOCKED_PROVIDER_SELECTION")
        return 2
    if not os.getenv(cfg.api_key_secret_name) or not os.getenv("LANGGRAPH_S2S_TOKEN"):
        print("INFODIVE_CANARY_STATUS=BLOCKED_CREDENTIALS")
        return 2
    print("INFODIVE_PROVIDER=" + cfg.provider_key)
    print("INFODIVE_MODEL=" + cfg.model_id)
    print("INFODIVE_CONFIG_VERSION=" + cfg.config_version)
    print("INFODIVE_CANARY_REAL_SQL_EXECUTED=false")
    if not args.invoke_private_provider:
        print("INFODIVE_CANARY_STATUS=PREFLIGHT_PASS_NO_LLM")
        return 0
    trace = PrivateOnlyTransport()
    runtime = create_shadow_test_runtime(http_transport_override=trace)
    body = json.dumps({
        "contract_version": "1",
        "agent_run_id": "infodive-canary-" + uuid.uuid4().hex,
        "question": args.question,
        "principal": {"id": "infodive-private-canary"},
        "llm_selection": {
            "provider_key": cfg.provider_key,
            "model_key": cfg.model_id,
            "config_version": cfg.config_version,
        },
    }, ensure_ascii=False).encode("utf-8")
    events: list[dict] = []
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        events.append(message)

    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "scheme": "http",
        "path": "/v1/internal/sql-agent/generate", "query_string": b"",
        "headers": [
            (b"content-type", b"application/json"),
            (b"authorization", ("Bearer " + os.environ["LANGGRAPH_S2S_TOKEN"]).encode()),
        ],
    }
    asyncio.run(runtime.app(scope, receive, send))
    status = next(
        (event.get("status") for event in events if event.get("type") == "http.response.start"),
        None,
    )
    raw = b"".join(
        event.get("body", b"") for event in events
        if event.get("type") == "http.response.body"
    )
    try:
        response = json.loads(raw)
    except Exception:
        response = {}
    sql = response.get("sql")
    preflight = response.get("preflight") or {}
    print("INFODIVE_CANARY_HTTP=" + str(status))
    print("INFODIVE_CANARY_STATUS_RESPONSE=" + str(response.get("status")))
    print("INFODIVE_CANARY_INTENT=" + str(response.get("intent")))
    print("INFODIVE_CANARY_PROVIDER_CALLS=" + str(len(trace.calls)))
    print("INFODIVE_CANARY_LAST_PROVIDER_HTTP=" +
          str(trace.calls[-1][1] if trace.calls else None))
    print("INFODIVE_CANARY_OTHER_PROVIDER_ATTEMPTED=" +
          str(trace.other_provider_attempted))
    print("INFODIVE_CANARY_SQL_PRESENT=" + str(bool(sql)))
    if isinstance(sql, str) and sql:
        print("INFODIVE_CANARY_SQL_SHA256=" +
              hashlib.sha256(sql.encode()).hexdigest())
    print("INFODIVE_CANARY_PREFLIGHT_STATUS=" + str(preflight.get("status")))
    print("INFODIVE_CANARY_PREFLIGHT_EXECUTED=" + str(preflight.get("executed")))
    print("INFODIVE_CANARY_ERRORS=" + ",".join(
        str(e.get("code", "")) for e in response.get("errors", [])
        if isinstance(e, dict)
    ))
    print("INFODIVE_CANARY_SQL_EXECUTED=false")
    success = (
        status == 200 and response.get("status") == "success"
        and isinstance(sql, str) and bool(sql)
        and preflight.get("executed") is False
        and bool(trace.calls) and not trace.other_provider_attempted
    )
    print("INFODIVE_CANARY_RESULT=" +
          ("SQL_GENERATED_FOR_REVIEW" if success else "DIAGNOSIS_REQUIRED"))
    return 0 if success else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        # Never leak SQL, a key, DSN, credentials, provider raw response or prompt.
        print("INFODIVE_CANARY_STATUS=UNEXPECTED_FAILURE")
        raise SystemExit(2)

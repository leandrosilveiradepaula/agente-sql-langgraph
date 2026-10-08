from __future__ import annotations

import argparse
import asyncio
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.integrations.openai_compatible.configuration import (
    load_openai_compatible_configuration,
)
from app.test_runtime.composition import create_shadow_test_runtime


class Receive:
    def __init__(self, body: bytes) -> None:
        self._messages = [
            {"type": "http.request", "body": body, "more_body": False}
        ]

    async def __call__(self) -> dict[str, Any]:
        return deepcopy(self._messages.pop(0))


class Send:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def __call__(self, event: dict[str, Any]) -> None:
        self.events.append(deepcopy(event))


def _run_request(
    app: Any,
    *,
    token: str,
    payload: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    body = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/v1/internal/sql-agent/generate",
        "query_string": b"",
        "headers": [
            (b"content-type", b"application/json"),
            (b"accept", b"application/json"),
            (b"authorization", ("Bearer " + token).encode("ascii")),
        ],
    }
    send = Send()
    asyncio.run(app(scope, Receive(body), send))
    status = int(send.events[0]["status"])
    response = json.loads(send.events[1]["body"].decode("utf-8"))
    return status, response


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", required=True)
    args = parser.parse_args()

    runtime = create_shadow_test_runtime()
    if runtime.config.allow_real_sql_execution:
        raise RuntimeError("Real SQL execution must remain disabled.")

    local = load_openai_compatible_configuration()
    if local is None:
        raise RuntimeError("OpenAI-compatible local provider is not configured.")

    cases = json.loads(
        Path(args.cases).read_text(encoding="utf-8")
    )["cases"]
    failures = 0

    for index, case in enumerate(cases, start=1):
        question = case["question"]
        expected_intent = case["expected_intent"]
        payload = {
            "contract_version": "1",
            "agent_run_id": f"shadow-full-flow-{index}",
            "question": question,
            "principal": {"id": "shadow-validation"},
            "llm_selection": {
                "provider_key": local.provider_key,
                "model_key": local.model_id,
                "config_version": local.config_version,
            },
            "correlation_metadata": {
                "validation_suite":
                    "demo-finance-generalization-full-flow-v1",
                "case_index": index,
            },
        }
        http_status, response = _run_request(
            runtime.app,
            token=runtime.config.s2s_token,
            payload=payload,
        )
        errors = (
            response.get("errors")
            if isinstance(response.get("errors"), list)
            else []
        )
        error_codes = [
            item.get("code")
            for item in errors
            if isinstance(item, dict)
        ]
        intent = response.get("intent")
        status = response.get("status")
        passed = (
            http_status in {200, 422}
            and intent == expected_intent
            and status in {"success", "rejected"}
        )
        if not passed:
            failures += 1

        print("=" * 80)
        print("CASE:", index)
        print("QUESTION:", question)
        print("EXPECTED_INTENT:", expected_intent)
        print("HTTP_STATUS:", http_status)
        print("STATUS:", status)
        print("INTENT:", intent)
        print("PLAN_STATUS:", response.get("plan_status"))
        print(
            "SQL_PRESENT:",
            isinstance(response.get("sql"), str)
            and bool(response.get("sql")),
        )
        print("ERROR_CODES:", error_codes)
        print("RESULT:", "PASS" if passed else "FAIL")

    print()
    print("SUMMARY:", f"{len(cases) - failures}/{len(cases)} PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

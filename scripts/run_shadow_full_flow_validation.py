from __future__ import annotations

import argparse
import asyncio
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

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


    print("PROVIDER: default runtime generator")
    cases = json.loads(
        Path(args.cases).read_text(encoding="utf-8")
    )["cases"]
    semantic_failures = 0
    full_flow_failures = 0

    for index, case in enumerate(cases, start=1):
        question = case["question"]
        expected_intent = case["expected_intent"]
        payload = {
            "contract_version": "1",
            "agent_run_id": f"shadow-full-flow-{index}",
            "question": question,
            "principal": {"id": "shadow-validation"},
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
        semantic_passed = intent == expected_intent
        full_flow_passed = (
            semantic_passed
            and http_status == 200
            and status == "success"
            and response.get("plan_status") == "planned"
            and isinstance(response.get("sql"), str)
            and bool(response.get("sql"))
        )
        if not semantic_passed:
            semantic_failures += 1
        if not full_flow_passed:
            full_flow_failures += 1

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
        metadata = response.get("metadata")
        gate_diagnostics = (
            metadata.get("gate_diagnostics")
            if isinstance(metadata, dict)
            else None
        )
        if gate_diagnostics:
            print(
                "GATE_DIAGNOSTICS:",
                json.dumps(
                    gate_diagnostics,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
            )
        print(
            "SEMANTIC_RESULT:",
            "PASS" if semantic_passed else "FAIL",
        )
        print(
            "FULL_FLOW_RESULT:",
            "PASS" if full_flow_passed else "FAIL",
        )

    print()
    print(
        "SEMANTIC_SUMMARY:",
        f"{len(cases) - semantic_failures}/{len(cases)} PASS",
    )
    print(
        "FULL_FLOW_SUMMARY:",
        f"{len(cases) - full_flow_failures}/{len(cases)} PASS",
    )
    return 1 if full_flow_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

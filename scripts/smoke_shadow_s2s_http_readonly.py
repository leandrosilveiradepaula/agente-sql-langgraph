from __future__ import annotations

"""Local-only HTTP smoke: health, S2S denial, authenticated route validation.

No POST, LLM, SQL execution, evidence writes, database reads or secrets printed.
"""
import json
import os
import urllib.error
import urllib.request


def call(path: str, *, token: str | None = None) -> tuple[int, dict]:
    port = int(os.environ.get("LANGGRAPH_HTTP_PORT", "8000"))
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        method="GET",
        headers=({"Authorization": "Bearer " + token} if token else {}),
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            return response.status, json.loads(response.read(8192))
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read(8192))
        finally:
            exc.close()


def main() -> int:
    if os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") != "false":
        print("ABORTED: real SQL execution must be disabled")
        return 2
    token = os.environ.get("LANGGRAPH_S2S_TOKEN")
    if not token:
        print("ABORTED: S2S token not configured")
        return 3

    health_code, health = call("/health")
    if health_code != 200 or health.get("status") != "ok" or health.get("real_sql_execution") is not False:
        print("HEALTH=FAIL")
        return 4
    print("HEALTH=PASS")
    if call("/v1/internal/shadow-runs/invalid!")[0] != 401:
        print("S2S_MISSING=FAIL")
        return 5
    print("S2S_MISSING=DENIED")
    if call("/v1/internal/shadow-runs/invalid!", token="test-wrong-credential")[0] != 401:
        print("S2S_INVALID=FAIL")
        return 6
    print("S2S_INVALID=DENIED")
    # Invalid route parameter is rejected before any evidence repository read.
    status, body = call("/v1/internal/shadow-runs/invalid!", token=token)
    if status != 400 or not isinstance(body.get("error"), dict):
        print("S2S_VALID_ROUTING=FAIL")
        return 7
    print("S2S_VALID_ROUTING=PASS")
    print("LLM_CALLS=0")
    print("SQL_EXECUTION=false")
    print("HTTP_SHADOW_SMOKE=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

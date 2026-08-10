from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from app.adapters.testing.fake_context_repository import FakeContextRepository
from app.adapters.testing.fake_engine_preflight import FakeEnginePreflight
from app.adapters.testing.fake_shadow_evidence_repository import (
    FakeShadowEvidenceRepository,
)
from app.adapters.testing.fake_sql_generator import FakeSqlGenerator
from app.adapters.testing.fake_sql_repairer import FakeSqlRepairer
from app.application.internal_sql_agent_v1 import (
    ExecuteApprovedSqlShadowUseCase,
    GenerateSqlUseCase,
)
from app.http.http_request import default_http_request_limits
from app.http.http_response import default_http_response_limits
from app.http.internal_sql_agent_v1_handler import (
    create_internal_sql_agent_v1_http_handler,
)

_FORWARDED_HEADER_NAMES = {
    "accept",
    "content-length",
    "content-type",
    "x-correlation-id",
    "x-request-id",
}
_LOCAL_TEST_ONLY_ENV = "LANGGRAPH_LOCAL_TEST_ONLY"
_LOCAL_TEST_ONLY_VALUE = "1"


class LocalShadowIds:
    def __init__(self) -> None:
        self.index = 0

    def __call__(self) -> str:
        self.index += 1
        return f"lg-local-run-{self.index}"


class LocalShadowRuntime:
    def __init__(
        self,
        *,
        sql: str = "SELECT id FROM schema_test.table_test",
        repair_sql: str = "SELECT id FROM schema_test.table_test",
        preflight_mode: str = "approved",
    ) -> None:
        self.repository = FakeShadowEvidenceRepository()
        self.sql_generator = FakeSqlGenerator(sql)
        self.sql_repairer = FakeSqlRepairer(responses=[repair_sql, repair_sql])
        self.engine_preflight = _preflight_for_mode(preflight_mode)
        self.id_generator = LocalShadowIds()
        self.received_requests: list[dict[str, Any]] = []
        self.handler = create_internal_sql_agent_v1_http_handler(
            generate_use_case=GenerateSqlUseCase(
                context_repository=FakeContextRepository(),
                sql_generator=self.sql_generator,
                engine_preflight=self.engine_preflight,
                sql_repairer=self.sql_repairer,
                id_generator=self.id_generator,
                shadow_repository=self.repository,
                langgraph_version="local-shadow-e2e",
                langgraph_commit="local-test-only",
            ),
            execute_approved_shadow_use_case=ExecuteApprovedSqlShadowUseCase(
                engine_preflight=self.engine_preflight,
                sql_repairer=self.sql_repairer,
                id_generator=self.id_generator,
                shadow_repository=self.repository,
                langgraph_version="local-shadow-e2e",
                langgraph_commit="local-test-only",
            ),
            request_limits=default_http_request_limits(),
            response_limits=default_http_response_limits(),
        )

    def capture_request(
        self,
        *,
        path: str,
        headers: Mapping[str, str],
        payload: object,
    ) -> None:
        body = payload if isinstance(payload, Mapping) else {}
        self.received_requests.append(
            {
                "path": path,
                "header_names": sorted(key.casefold() for key in headers),
                "body_keys": sorted(str(key) for key in body),
                "principal_keys": sorted(
                    str(key)
                    for key in (
                        body.get("principal", {})
                        if isinstance(body.get("principal"), Mapping)
                        else {}
                    )
                ),
                "correlation_metadata_keys": sorted(
                    str(key)
                    for key in (
                        body.get("correlation_metadata", {})
                        if isinstance(body.get("correlation_metadata"), Mapping)
                        else {}
                    )
                ),
                "contract_version": body.get("contract_version"),
                "agent_run_id": body.get("agent_run_id"),
                "question": body.get("question"),
                "approved_sql": body.get("approved_sql"),
                "principal": deepcopy(body.get("principal", {})),
                "correlation_metadata": deepcopy(
                    body.get("correlation_metadata", {})
                ),
            }
        )

    def records_summary(self, agent_run_id: str | None = None) -> list[dict[str, Any]]:
        records = list(self.repository.records.values())
        if agent_run_id:
            records = [
                record
                for record in records
                if record["agent_run_id"] == agent_run_id
            ]
        return [
            {
                "shadow_record_id": record["shadow_record_id"],
                "agent_run_id": record["agent_run_id"],
                "run_id": record["run_id"],
                "event_type": record["event_type"],
                "status": record["status"],
                "question": record.get("question"),
                "generated_sql": record.get("generated_sql"),
                "approved_sql_original": record.get("approved_sql_original"),
                "repaired_sql_proposal": record.get("repaired_sql_proposal"),
                "requires_reapproval": record.get("requires_reapproval"),
                "principal": deepcopy(record.get("principal", {})),
                "correlation_metadata": deepcopy(
                    record.get("correlation_metadata", {})
                ),
                "preflight_executed": _preflight_executed(record),
            }
            for record in sorted(records, key=lambda item: item["run_id"])
        ]


class LocalInternalSqlAgentV1HttpServer(ThreadingHTTPServer):
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        runtime: LocalShadowRuntime,
    ) -> None:
        super().__init__(server_address, _LocalShadowRequestHandler)
        self.runtime = runtime


class _LocalShadowRequestHandler(BaseHTTPRequestHandler):
    server_version = "LangGraphLocalShadow/1"

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/__local-test/records":
            query = parse_qs(parsed.query)
            agent_run_id = query.get("agent_run_id", [None])[0]
            self._send_json(
                200,
                {
                    "records": self.server.runtime.records_summary(agent_run_id),  # type: ignore[attr-defined]
                },
            )
            return
        if parsed.path == "/__local-test/received-requests":
            self._send_json(
                200,
                {"requests": self.server.runtime.received_requests},  # type: ignore[attr-defined]
            )
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        length = _safe_content_length(self.headers.get("content-length"))
        body = self.rfile.read(length)
        headers = _internal_headers({key: value for key, value in self.headers.items()})
        path = urlsplit(self.path).path
        payload = _decode_json(body)
        self.server.runtime.capture_request(  # type: ignore[attr-defined]
            path=path,
            headers=headers,
            payload=payload,
        )
        response = self.server.runtime.handler.handle(  # type: ignore[attr-defined]
            {
                "method": "POST",
                "path": path,
                "headers": headers,
                "body": body,
            }
        )
        self.send_response(response["status_code"])
        for key, value in response["headers"].items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(response["body"])

    def log_message(self, *_args: Any) -> None:
        return

    def _send_json(self, status_code: int, payload: Mapping[str, Any]) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_local_shadow_test_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    runtime: LocalShadowRuntime | None = None,
) -> LocalInternalSqlAgentV1HttpServer:
    _ensure_local_test_only_enabled()
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("Local shadow test server only binds to localhost.")
    return LocalInternalSqlAgentV1HttpServer(
        (host, port),
        runtime or LocalShadowRuntime(),
    )


def _ensure_local_test_only_enabled() -> None:
    value = os.environ.get(_LOCAL_TEST_ONLY_ENV)
    if value != _LOCAL_TEST_ONLY_VALUE:
        raise RuntimeError(
            "Refusing to start local shadow test server. "
            f"Set {_LOCAL_TEST_ONLY_ENV}={_LOCAL_TEST_ONLY_VALUE} explicitly."
        )


def _preflight_for_mode(mode: str) -> FakeEnginePreflight:
    if mode == "repairable_once":
        return FakeEnginePreflight(
            responses=[
                {
                    "status": "rejected",
                    "provider_name": "fake_engine_preflight",
                    "failure_category": "column_not_found",
                    "message": "column not found",
                    "repairable": True,
                    "executed": False,
                    "rows_returned": 0,
                },
                {
                    "status": "approved",
                    "provider_name": "fake_engine_preflight",
                    "duration_ms": 1,
                    "statement_planned": True,
                    "executed": False,
                    "rows_returned": 0,
                },
            ]
        )
    return FakeEnginePreflight()


def _preflight_executed(record: Mapping[str, Any]) -> bool | None:
    evidence = record.get("langgraph_evidence")
    if not isinstance(evidence, Mapping):
        return None
    preflight = evidence.get("preflight_result") or evidence.get("validation", {}).get(
        "preflight"
    )
    if not isinstance(preflight, Mapping):
        return None
    value = preflight.get("executed")
    return value if isinstance(value, bool) else None


def _decode_json(body: bytes) -> object:
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return {}


def _safe_content_length(value: str | None) -> int:
    try:
        parsed = int(value or "0")
    except ValueError:
        return 0
    return max(0, min(parsed, 1024 * 1024))


def _internal_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.casefold() in _FORWARDED_HEADER_NAMES
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a local/test-only internal SQL agent v1 server.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("LANGGRAPH_LOCAL_TEST_HOST", "127.0.0.1"),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("LANGGRAPH_LOCAL_TEST_PORT", "8765")),
    )
    args = parser.parse_args(argv)
    server = create_local_shadow_test_server(host=args.host, port=args.port)
    host, port = server.server_address[:2]
    print(
        json.dumps(
            {
                "event": "langgraph_local_shadow_ready",
                "host": host,
                "port": port,
            },
            separators=(",", ":"),
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

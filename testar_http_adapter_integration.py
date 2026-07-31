from __future__ import annotations

import json

from app.adapters.testing.fake_graph_runtime import FakeGraphRuntime
from app.application.sql_agent_service import SqlAgentApplicationService
from app.domain.application_response_types import (
    APPLICATION_RESPONSE_CONTRACT_VERSION,
)
from app.domain.result_normalization import stable_fingerprint
from app.http.http_request import default_http_request_limits
from app.http.http_response import default_http_response_limits
from app.http.sql_agent_http_handler import SqlAgentHttpHandler


class Ids:
    def __init__(self) -> None:
        self.values = ["req-generated", "run-generated"]

    def __call__(self) -> str:
        return self.values.pop(0)


def _response(status="success", *, request_id="req-1", run_id="run-1"):
    response = {
        "contract_version": APPLICATION_RESPONSE_CONTRACT_VERSION,
        "response_id": "response-1",
        "request_id": request_id,
        "run_id": run_id,
        "status": status,
        "original_outcome": status,
        "message": "Public",
        "data": {
            "result": {
                "contract_version": "v1",
                "columns": [],
                "rows": [],
                "result_fingerprint": "result-1",
            },
            "pagination": {
                "mode": "none",
                "has_more": False,
                "next_cursor": None,
                "total_rows": 0,
                "returned_rows": 0,
            },
        }
        if status == "success"
        else None,
        "errors": [],
        "warnings": [],
        "metadata": {"lineage": {}},
        "finalization": {
            "status": "completed" if status == "success" else "incomplete",
            "run_record_built": status == "success",
            "persisted": status == "success",
            "audited": status == "success",
        },
        "response_fingerprint": "",
    }
    payload = dict(response)
    payload.pop("response_fingerprint", None)
    response["response_fingerprint"] = stable_fingerprint(payload)
    return response


def _handler(final_state):
    runtime = FakeGraphRuntime(final_state=final_state)
    service = SqlAgentApplicationService(runtime=runtime, id_generator=Ids())
    handler = SqlAgentHttpHandler(
        application_service=service,
        request_limits=default_http_request_limits(),
        response_limits=default_http_response_limits(),
    )
    return handler, runtime


def _request(body=b'{"question":"ok","request_id":"req-1","run_id":"run-1"}'):
    return {
        "method": "POST",
        "path": "/v1/sql-agent/query",
        "headers": {"Content-Type": "application/json"},
        "body": body,
    }


def _body(http):
    return json.loads(http["body"].decode("utf-8"))


def test_post_valido_success_rejected_e_capability_unavailable() -> None:
    for status, expected in [
        ("success", 200),
        ("rejected", 422),
        ("infrastructure_error", 503),
    ]:
        handler, runtime = _handler({"application_response": _response(status)})
        http = handler.handle(_request())
        assert http["status_code"] == expected
        assert runtime.calls == 1
        assert _body(http)["status"] == status
        assert "final_status" not in _body(http)


def test_request_invalida_nao_chama_service_runtime() -> None:
    handler, runtime = _handler({"application_response": _response()})
    http = handler.handle(_request(body=b"{"))
    assert http["status_code"] == 400
    assert runtime.calls == 0
    assert _body(http)["status"] == "rejected"


def test_ids_gerados_service_e_runtime_uma_vez() -> None:
    handler, runtime = _handler(
        {
            "application_response": _response(
                request_id="req-generated",
                run_id="run-generated",
            )
        }
    )
    http = handler.handle(_request(body=b'{"question":"ok"}'))
    assert http["status_code"] == 200
    assert runtime.calls == 1
    assert runtime.last_initial_state["request_id"] == "req-generated"
    assert http["headers"]["X-Request-ID"] == "req-generated"
    assert http["headers"]["X-Run-ID"] == "run-generated"


def test_repair_path_representado_sem_provider_live() -> None:
    handler, runtime = _handler({"application_response": _response()})
    http = handler.handle(_request())
    assert http["status_code"] == 200
    assert runtime.calls == 1
    serialized = repr(_body(http)).casefold()
    assert "graphstate" not in serialized
    assert "provider live" not in serialized


def main() -> None:
    tests = [
        test_post_valido_success_rejected_e_capability_unavailable,
        test_request_invalida_nao_chama_service_runtime,
        test_ids_gerados_service_e_runtime_uma_vez,
        test_repair_path_representado_sem_provider_live,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()

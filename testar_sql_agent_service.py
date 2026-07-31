from __future__ import annotations

from copy import deepcopy

from app.adapters.testing.fake_graph_runtime import FakeGraphRuntime
from app.application.sql_agent_service import SqlAgentApplicationService
from app.domain.application_response_types import (
    APPLICATION_RESPONSE_CONTRACT_VERSION,
)
from app.domain.result_normalization import stable_fingerprint


_DEFAULT_DATA = object()


class SequentialIds:
    def __init__(self) -> None:
        self.values = ["request-generated", "run-generated"]
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        return self.values.pop(0)


def _response(
    *,
    request_id: str = "request-1",
    run_id: str = "run-1",
    status: str = "success",
    data=_DEFAULT_DATA,
):
    if data is _DEFAULT_DATA:
        data = {
            "result": {
                "contract_version": (
                    "v1.0.0-deterministic-result-serialization"
                ),
                "columns": [],
                "rows": [],
                "result_fingerprint": "result-fingerprint",
            },
            "pagination": {
                "mode": "none",
                "has_more": False,
                "next_cursor": None,
                "total_rows": 0,
                "returned_rows": 0,
            },
        }
    response = {
        "contract_version": APPLICATION_RESPONSE_CONTRACT_VERSION,
        "response_id": stable_fingerprint(
            {
                "contract_version": APPLICATION_RESPONSE_CONTRACT_VERSION,
                "request_id": request_id,
                "run_id": run_id,
            }
        ),
        "request_id": request_id,
        "run_id": run_id,
        "status": status,
        "original_outcome": status,
        "message": "Mensagem publica.",
        "data": data if status == "success" else None,
        "errors": [],
        "warnings": [],
        "metadata": {
            "original_outcome": status,
            "finalization_status": "completed"
            if status == "success"
            else "incomplete",
            "lineage": {},
        },
        "finalization": {
            "status": "completed"
            if status == "success"
            else "incomplete",
            "run_record_built": status == "success",
            "persisted": status == "success",
            "persistence_record_id": "record-1"
            if status == "success"
            else None,
            "audited": status == "success",
            "audit_event_id": "audit-1"
            if status == "success"
            else None,
            "observability_emitted": status == "success",
            "observability_degraded": False,
            "error_codes": [],
        },
        "response_fingerprint": "",
    }
    payload = deepcopy(response)
    payload.pop("response_fingerprint", None)
    response["response_fingerprint"] = stable_fingerprint(payload)
    return response


def _refingerprint(response):
    payload = deepcopy(response)
    payload.pop("response_fingerprint", None)
    response["response_fingerprint"] = stable_fingerprint(payload)
    return response


_DEFAULT = object()


def _service(final_state=_DEFAULT, exception=None, ids=None):
    runtime = FakeGraphRuntime(
        final_state=final_state
        if final_state is not _DEFAULT
        else {"application_response": _response()},
        exception=exception,
    )
    id_generator = ids if ids is not None else SequentialIds()
    service = SqlAgentApplicationService(
        runtime=runtime,
        id_generator=id_generator,
    )
    return service, runtime, id_generator


def _request(**overrides):
    request = {
        "question": "  Pergunta original preservada?  ",
        "request_id": "request-1",
        "run_id": "run-1",
        "user": {
            "id": "user-1",
            "email": "user@example.invalid",
            "profile": "admin",
        },
        "options": {
            "use_cache": False,
            "max_repair_attempts": 2,
            "shadow_mode": False,
        },
    }
    request.update(overrides)
    return request


def test_success_rejected_e_infrastructure_error_do_grafo() -> None:
    data = {"result": {"columns": [], "rows": [], "result_fingerprint": "f"}}
    for status in ["success", "rejected", "infrastructure_error"]:
        service, runtime, _ = _service(
            {"application_response": _response(status=status, data=data)}
        )
        response = service.execute(_request())
        assert response["status"] == status
        assert runtime.calls == 1
        if status != "success":
            assert response["data"] is None


def test_request_invalida_nao_chama_runtime() -> None:
    service, runtime, _ = _service()
    response = service.execute({"question": ""})
    assert response["status"] == "rejected"
    assert response["data"] is None
    assert response["errors"][0]["code"] == (
        "APPLICATION_REQUEST_QUESTION_REQUIRED"
    )
    assert runtime.calls == 0


def test_runtime_chamado_uma_vez_estado_inicial_minimo() -> None:
    service, runtime, _ = _service()
    response = service.execute(_request())
    assert response["status"] == "success"
    assert runtime.calls == 1
    state = runtime.last_initial_state
    assert set(state) == {
        "question",
        "request_id",
        "run_id",
        "user",
        "options",
    }
    blocked = {
        "context",
        "query_plan",
        "generated_sql",
        "current_sql",
        "application_response",
        "run_record",
        "serialized_result",
    }
    assert not blocked.intersection(state)
    assert state["question"] == "  Pergunta original preservada?  "


def test_timeout_nao_atravessa_para_options_do_grafo() -> None:
    service, runtime, _ = _service()
    response = service.execute(
        _request(options={"timeout_seconds": 1, "max_repair_attempts": 0})
    )
    assert response["status"] == "success"
    assert "timeout_seconds" not in runtime.last_initial_state["options"]


def test_options_e_ids_preservados_e_ids_gerados() -> None:
    service, runtime, ids = _service()
    response = service.execute(_request())
    assert response["request_id"] == "request-1"
    assert response["run_id"] == "run-1"
    assert ids.calls == 0
    assert runtime.last_initial_state["options"]["max_repair_attempts"] == 2

    generated_response = _response(
        request_id="request-generated",
        run_id="run-generated",
    )
    service, runtime, ids = _service(
        {"application_response": generated_response},
        ids=SequentialIds(),
    )
    response = service.execute({"question": "Pergunta sem ids"})
    assert response["request_id"] == "request-generated"
    assert response["run_id"] == "run-generated"
    assert ids.calls == 2

    service, runtime, ids = _service(
        {"application_response": _response(request_id="request-generated", run_id="run-1")},
        ids=SequentialIds(),
    )
    response = service.execute(_request(request_id=None))
    assert response["request_id"] == "request-generated"
    assert response["run_id"] == "run-1"
    assert ids.calls == 1

    service, runtime, ids = _service(
        {"application_response": _response(request_id="request-1", run_id="request-generated")},
        ids=SequentialIds(),
    )
    response = service.execute(_request(run_id=None))
    assert response["request_id"] == "request-1"
    assert response["run_id"] == "request-generated"
    assert ids.calls == 1


def test_runtime_exception_sem_retry_e_sem_dados_brutos() -> None:
    service, runtime, _ = _service(exception=RuntimeError("token SELECT secret"))
    response = service.execute(_request())
    assert runtime.calls == 1
    assert response["status"] == "infrastructure_error"
    assert response["data"] is None
    serialized = repr(response).casefold()
    assert "token select secret" not in serialized
    assert "graphstate" not in serialized
    assert "  pergunta original preservada?  " not in serialized
    assert response["errors"][0]["code"] == "APPLICATION_SERVICE_RUNTIME_FAILED"

    service, runtime, _ = _service()
    response = service.execute(["nao", "mapping"])
    assert response["status"] == "rejected"
    assert runtime.calls == 0


def test_resultados_invalidos_do_runtime() -> None:
    cases = [
        None,
        "invalid",
        {},
        {"final_status": "approved"},
        {"application_response": "invalid"},
        {
            "application_response": {
                **_response(),
                "status": "unknown",
            }
        },
        {
            "application_response": {
                **_response(),
                "request_id": "other",
            }
        },
        {
            "application_response": {
                **_response(),
                "run_id": "other",
            }
        },
        {
            "application_response": {
                **_response(),
                "response_fingerprint": "",
            }
        },
        {
            "application_response": _response(
                status="success",
                data=None,
            )
        },
        {
            "application_response": _refingerprint({
                **_response(),
                "original_outcome": "unknown",
            })
        },
        {
            "application_response": _refingerprint({
                **_response(),
                "finalization": {"status": "unknown"},
            })
        },
        {
            "application_response": _refingerprint({
                **_response(),
                "finalization": {
                    **_response()["finalization"],
                    "persisted": False,
                },
            })
        },
    ]
    for final_state in cases:
        service, runtime, _ = _service(final_state)
        response = service.execute(_request())
        assert runtime.calls == 1
        assert response["status"] == "infrastructure_error"
        assert response["errors"][0]["code"] == (
            "APPLICATION_SERVICE_INVALID_GRAPH_RESULT"
        )


def test_request_e_estado_final_nao_mutados_resposta_independente() -> None:
    final_state = {"application_response": _response()}
    original_final_state = deepcopy(final_state)
    service, runtime, _ = _service(final_state)
    request = _request()
    original_request = deepcopy(request)
    response = service.execute(request)
    assert request == original_request
    assert final_state == original_final_state
    final_state["application_response"]["status"] = "rejected"
    assert response["status"] == "success"
    response["status"] = "rejected"
    assert runtime.final_state["application_response"]["status"] == "success"


def test_service_nao_chama_adapters_sinks_timeout_e_unexpected() -> None:
    class Spy:
        calls = 0

        def __getattr__(self, name):
            del name
            self.calls += 1
            raise AssertionError("Servico nao deve acessar adapter.")

    spy = Spy()
    service, runtime, _ = _service()
    service.unused_spy = spy
    response = service.execute(
        _request(options={"timeout_seconds": 1, "max_repair_attempts": 0})
    )
    assert response["status"] == "success"
    assert runtime.calls == 1
    assert spy.calls == 0

    service, _, _ = _service(ids=lambda: "id com espaco")
    response = service.execute({"question": "Pergunta"})
    assert response["status"] == "infrastructure_error"
    assert response["errors"][0]["code"] == "APPLICATION_SERVICE_RUNTIME_FAILED"

    service, runtime, _ = _service(ids=lambda: "same-id")
    response = service.execute({"question": "Pergunta"})
    assert response["status"] == "rejected"
    assert response["errors"][0]["code"] == "APPLICATION_REQUEST_ID_INVALID"
    assert runtime.calls == 0


def main() -> None:
    tests = [
        test_success_rejected_e_infrastructure_error_do_grafo,
        test_request_invalida_nao_chama_runtime,
        test_runtime_chamado_uma_vez_estado_inicial_minimo,
        test_timeout_nao_atravessa_para_options_do_grafo,
        test_options_e_ids_preservados_e_ids_gerados,
        test_runtime_exception_sem_retry_e_sem_dados_brutos,
        test_resultados_invalidos_do_runtime,
        test_request_e_estado_final_nao_mutados_resposta_independente,
        test_service_nao_chama_adapters_sinks_timeout_e_unexpected,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()

from __future__ import annotations

from copy import deepcopy

from app.adapters.testing.fake_run_repository import FakeRunRepository
from app.domain.run_record import build_run_record, default_finalization_limits
from app.graph.nodes.persist_run import create_persist_run_node


def _record() -> dict:
    return build_run_record(
        {
            "request_id": "request-test",
            "run_id": "run-test",
            "final_status": "approved",
            "current_stage": "serialize_result",
            "failure_stage": "",
            "context": {"fingerprint": "a" * 64},
            "context_version": "context-test",
            "query_plan": {"intent_name": "generic"},
            "generated_sql": "SELECT id FROM schema.table",
            "current_sql": "SELECT id FROM schema.table",
            "security_result": {"status": "approved"},
            "contract_result": {"status": "approved"},
            "engine_preflight_result": {"status": "approved"},
            "sql_execution_result": {"status": "success", "row_count": 0},
            "serialized_result": None,
            "repair_attempts": 0,
            "repair_history": [],
            "errors": [],
            "warnings": [],
        },
        limits=default_finalization_limits(),
    )


def _state(**overrides) -> dict:
    state = {
        "run_record": _record(),
        "errors": [],
        "warnings": [],
        "current_stage": "build_run_record",
        "final_status": "approved",
        "failure_stage": "",
    }
    state.update(overrides)
    return state


def test_save_valido_repository_chamado_uma_vez() -> None:
    repository = FakeRunRepository()
    node = create_persist_run_node(repository)
    state = _state()
    original = deepcopy(state)
    result = node(state)
    assert state == original
    assert repository.calls == 1
    assert result["persistence_result"]["status"] == "persisted"
    assert result["finalization_status"] == "persisted"
    assert result["current_stage"] == "persist_run"


def test_run_record_ausente() -> None:
    result = create_persist_run_node(FakeRunRepository())(
        _state(run_record=None)
    )
    assert result["final_status"] == "infrastructure_error"
    assert result["persistence_result"]["failure_category"] == (
        "request_invalid"
    )


def test_fingerprint_divergente() -> None:
    record = _record()
    repository = FakeRunRepository(
        responses=[
            {
                "status": "persisted",
                "record_id": "record-test",
                "persisted_fingerprint": "different",
                "idempotency_key": "key",
                "failure_category": "none",
                "diagnostic": None,
                "duration_ms": 1,
            }
        ]
    )
    result = create_persist_run_node(repository)(_state(run_record=record))
    assert result["persistence_result"]["failure_category"] == (
        "fingerprint_mismatch"
    )
    assert result["errors"][-1]["code"] == (
        "PERSIST_RUN_FINGERPRINT_MISMATCH"
    )


def test_resultado_anterior_inconsistente_nao_chama_repository() -> None:
    repository = FakeRunRepository()
    result = create_persist_run_node(repository)(
        _state(
            persistence_result={
                "status": "error",
                "record_id": None,
                "persisted_fingerprint": None,
                "idempotency_key": "old",
                "failure_category": "unavailable",
                "diagnostic": {
                    "code": "PERSIST_RUN_UNAVAILABLE",
                    "message": "Persistencia indisponivel.",
                    "failure_category": "unavailable",
                    "safe_details": {},
                },
                "duration_ms": 1,
            }
        )
    )
    assert repository.calls == 0
    assert result["final_status"] == "infrastructure_error"
    assert result["finalization_status"] == "persistence_failed"


def test_success_com_failure_category_ou_failure_com_record_id_rejeita() -> None:
    inconsistent_success = create_persist_run_node(
        FakeRunRepository(
            responses=[
                {
                    "status": "persisted",
                    "record_id": "record-test",
                    "persisted_fingerprint": _record()["fingerprint"],
                    "idempotency_key": "key",
                    "failure_category": "conflict",
                    "diagnostic": None,
                    "duration_ms": 1,
                }
            ]
        )
    )(_state())
    assert inconsistent_success["errors"][-1]["code"] == (
        "PERSIST_RUN_REQUEST_INVALID"
    )

    inconsistent_failure = create_persist_run_node(
        FakeRunRepository(
            responses=[
                {
                    "status": "error",
                    "record_id": "record-test",
                    "persisted_fingerprint": None,
                    "idempotency_key": "key",
                    "failure_category": "unavailable",
                    "diagnostic": {
                        "code": "PERSIST_RUN_UNAVAILABLE",
                        "message": "Persistencia indisponivel.",
                        "failure_category": "unavailable",
                        "safe_details": {},
                    },
                    "duration_ms": 1,
                }
            ]
        )
    )(_state())
    assert inconsistent_failure["errors"][-1]["code"] == (
        "PERSIST_RUN_REQUEST_INVALID"
    )


def test_idempotencia_e_conflito() -> None:
    repository = FakeRunRepository()
    node = create_persist_run_node(repository)
    state = _state()
    first = node(state)
    second = node(
        {
            **state,
            "persistence_result": first["persistence_result"],
        }
    )
    assert repository.calls == 1
    assert second["finalization_status"] == "persisted"

    request = repository.requests[0]
    conflict = repository.save(
        {
            **request,
            "run_record_fingerprint": "different",
        }
    )
    assert conflict["status"] == "rejected"
    assert conflict["failure_category"] == "conflict"


def test_timeout_autenticacao_indisponibilidade_excecao() -> None:
    cases = [
        (TimeoutError(), "PERSIST_RUN_TIMEOUT", "timeout"),
        (PermissionError(), "PERSIST_RUN_AUTHENTICATION_FAILED", "authentication_failed"),
        (
            RuntimeError("unavailable"),
            "PERSIST_RUN_UNEXPECTED_ERROR",
            "unexpected_error",
        ),
    ]
    for exception, code, category in cases:
        result = create_persist_run_node(
            FakeRunRepository(exceptions=[exception])
        )(_state())
        assert result["final_status"] == "infrastructure_error"
        assert result["errors"][-1]["code"] == code
        assert result["persistence_result"]["failure_category"] == category

    unavailable = create_persist_run_node(
        FakeRunRepository(
            responses=[
                {
                    "status": "error",
                    "record_id": None,
                    "persisted_fingerprint": None,
                    "idempotency_key": "key",
                    "failure_category": "unavailable",
                    "diagnostic": {
                        "code": "PERSIST_RUN_UNAVAILABLE",
                        "message": "Persistencia indisponivel.",
                        "failure_category": "unavailable",
                        "safe_details": {},
                    },
                    "duration_ms": 1,
                }
            ]
        )
    )(_state())
    assert unavailable["persistence_result"]["failure_category"] == (
        "unavailable"
    )


def test_erro_nao_contem_payload_nem_sql() -> None:
    result = create_persist_run_node(
        FakeRunRepository(exceptions=[RuntimeError("SELECT hidden")])
    )(_state())
    serialized = repr(result["errors"]).casefold()
    assert "select hidden" not in serialized
    assert "serialized_result" not in serialized
    assert "current_sql" not in serialized


def main() -> None:
    tests = [
        test_save_valido_repository_chamado_uma_vez,
        test_run_record_ausente,
        test_fingerprint_divergente,
        test_resultado_anterior_inconsistente_nao_chama_repository,
        test_success_com_failure_category_ou_failure_com_record_id_rejeita,
        test_idempotencia_e_conflito,
        test_timeout_autenticacao_indisponibilidade_excecao,
        test_erro_nao_contem_payload_nem_sql,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()

from __future__ import annotations

from copy import deepcopy

from app.domain.application_response import default_application_response_limits
from app.domain.result_normalization import stable_fingerprint
from app.graph.nodes.build_application_response import (
    create_build_application_response_node,
)


def _serialized() -> dict:
    fingerprint = stable_fingerprint({"rows": [1]})
    return {
        "status": "success",
        "contract_version": "serialization-test",
        "columns": [{"ordinal": 0, "original_name": "id"}],
        "rows": [{"ordinal": 0, "cells": [{"type": "integer", "value": 1}]}],
        "lineage": {
            "execution_provider_name": "fake_sql_executor",
            "serialized_result_fingerprint": fingerprint,
        },
        "diagnostics": [],
        "warnings": [],
        "error_code": None,
        "result_fingerprint": fingerprint,
        "canonical_json": None,
    }


def _state(**overrides) -> dict:
    state = {
        "request_id": "request-test",
        "run_id": "run-test",
        "original_outcome": "success",
        "finalization_status": "observed",
        "final_status": "approved",
        "current_stage": "emit_observability",
        "serialized_result": _serialized(),
        "normalized_result": {"status": "success"},
        "sql_execution_result": {"status": "success", "executed": True},
        "run_record": {
            "status": "built",
            "fingerprint": "a" * 64,
            "lineage": {
                "context_version": "context-test",
                "intent_name": "generic_test_intent",
                "current_sql_fingerprint": "b" * 64,
            },
            "metrics": {
                "row_count": 1,
                "column_count": 1,
                "bytes": 100,
                "duration_ms": 3,
                "truncated": False,
                "repair_attempts": 0,
            },
        },
        "persistence_result": {
            "status": "persisted",
            "record_id": "record-test",
            "persisted_fingerprint": "a" * 64,
            "idempotency_key": "persist-key",
            "failure_category": "none",
            "diagnostic": None,
            "duration_ms": 1,
        },
        "audit_result": {
            "status": "written",
            "event_id": "event-test",
            "event_fingerprint": "c" * 64,
            "idempotency_key": "audit-key",
            "failure_category": "none",
            "diagnostic": None,
            "duration_ms": 1,
        },
        "observability_result": {
            "status": "emitted",
            "event_fingerprint": "d" * 64,
            "diagnostic": None,
            "duration_ms": 1,
        },
        "errors": [],
        "warnings": [],
        "options": {
            "application_response_limits": default_application_response_limits()
        },
    }
    state.update(overrides)
    return state


def test_construcao_success_rejected_infra() -> None:
    node = create_build_application_response_node()
    success = node(_state())
    rejected = node(
        _state(
            original_outcome="rejected",
            final_status="rejected",
            serialized_result=None,
            errors=[{"code": "INTENT_NOT_RESOLVED", "stage": "classify"}],
        )
    )
    infra = node(
        _state(
            original_outcome="infrastructure_error",
            final_status="infrastructure_error",
            serialized_result=None,
            errors=[{"code": "CONTEXT_LOAD_FAILED", "stage": "load_context"}],
        )
    )
    assert success["application_response"]["status"] == "success"
    assert rejected["application_response"]["status"] == "rejected"
    assert rejected["application_response"]["data"] is None
    assert infra["application_response"]["status"] == "infrastructure_error"
    assert infra["application_response"]["data"] is None


def test_persistence_audit_observability() -> None:
    node = create_build_application_response_node()
    persistence = node(
        _state(
            finalization_status="persistence_failed",
            persistence_result={
                "status": "error",
                "record_id": None,
                "persisted_fingerprint": None,
                "idempotency_key": "",
                "failure_category": "unexpected_error",
                "diagnostic": {"code": "PERSIST_RUN_UNEXPECTED_ERROR"},
                "duration_ms": None,
            },
        )
    )
    audit = node(
        _state(
            finalization_status="audit_failed",
            audit_result={
                "status": "error",
                "event_id": None,
                "event_fingerprint": None,
                "idempotency_key": "",
                "failure_category": "unexpected_error",
                "diagnostic": {"code": "AUDIT_UNEXPECTED_ERROR"},
                "duration_ms": None,
            },
        )
    )
    observability = node(
        _state(
            finalization_status="observability_degraded",
            observability_result={
                "status": "degraded",
                "event_fingerprint": None,
                "diagnostic": {"code": "OBSERVABILITY_UNEXPECTED_ERROR"},
                "duration_ms": None,
            },
            warnings=["OBSERVABILITY_UNEXPECTED_ERROR: degraded"],
        )
    )
    assert persistence["application_response"]["status"] == (
        "infrastructure_error"
    )
    assert audit["application_response"]["status"] == "infrastructure_error"
    assert observability["application_response"]["status"] == "success"
    assert observability["application_response"]["warnings"]


def test_application_response_anterior_bloqueia_reconstrucao() -> None:
    node = create_build_application_response_node()
    result = node(
        _state(
            application_response={
                "status": "success",
                "response_fingerprint": "old",
            }
        )
    )
    response = result["application_response"]
    assert response["status"] == "infrastructure_error"
    assert response["errors"][0]["code"] == (
        "APPLICATION_RESPONSE_INPUT_INVALID"
    )
    assert result["failure_stage"] == "build_application_response"


def test_state_nao_mutado_e_resultados_preservados() -> None:
    node = create_build_application_response_node()
    state = _state()
    original = deepcopy(state)
    result = node(state)
    assert state == original
    assert result["current_stage"] == "build_application_response"
    assert state["serialized_result"] == original["serialized_result"]
    assert state["run_record"] == original["run_record"]
    assert state["persistence_result"] == original["persistence_result"]
    assert state["audit_result"] == original["audit_result"]
    assert state["observability_result"] == original["observability_result"]


def test_erro_de_construcao_gera_resposta_minima() -> None:
    calls = {"count": 0}

    def failing_builder(**kwargs):
        del kwargs
        calls["count"] += 1
        raise RuntimeError("SELECT secret FROM hidden")

    node = create_build_application_response_node(failing_builder)
    result = node(_state())
    response = result["application_response"]
    text = repr(response).casefold()
    assert calls["count"] == 1
    assert response["status"] == "infrastructure_error"
    assert response["data"] is None
    assert response["errors"][0]["code"] == (
        "APPLICATION_RESPONSE_BUILD_FAILED"
    )
    assert "select secret" not in text


def test_builder_chamado_uma_vez_sem_sinks_e_resposta_presente() -> None:
    calls = {"count": 0}

    def fake_builder(**kwargs):
        calls["count"] += 1
        assert "run_repository" not in kwargs
        assert "audit_sink" not in kwargs
        assert "observability_sink" not in kwargs
        return {
            "contract_version": "test",
            "response_id": "response-test",
            "request_id": kwargs["request_id"],
            "run_id": kwargs["run_id"],
            "status": "success",
            "original_outcome": "success",
            "message": "ok",
            "data": None,
            "errors": [],
            "warnings": [],
            "metadata": {},
            "finalization": {},
            "response_fingerprint": "fingerprint-test",
        }

    node = create_build_application_response_node(fake_builder)
    result = node(_state())
    assert calls["count"] == 1
    assert result["current_stage"] == "build_application_response"
    assert result["application_response"]["response_id"] == "response-test"


def main() -> None:
    tests = [
        test_construcao_success_rejected_infra,
        test_persistence_audit_observability,
        test_application_response_anterior_bloqueia_reconstrucao,
        test_state_nao_mutado_e_resultados_preservados,
        test_erro_de_construcao_gera_resposta_minima,
        test_builder_chamado_uma_vez_sem_sinks_e_resposta_presente,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()

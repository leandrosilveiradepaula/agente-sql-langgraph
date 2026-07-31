from __future__ import annotations

from copy import deepcopy

from app.domain.application_response import (
    build_application_response,
    default_application_response_limits,
    to_canonical_application_response_json,
)
from app.domain.result_normalization import stable_fingerprint


def _serialized(value: int = 1, rows: list | None = None) -> dict:
    safe_rows = rows if rows is not None else [
        {"ordinal": 0, "cells": [{"type": "integer", "value": value}]}
    ]
    fingerprint = stable_fingerprint({"rows": safe_rows})
    return {
        "status": "success",
        "contract_version": "serialization-test",
        "columns": [
            {
                "ordinal": 0,
                "original_name": "id",
                "provider_type_name": "int",
                "normalized_type": "integer",
                "nullable": False,
                "metadata": {},
            }
        ],
        "rows": safe_rows,
        "lineage": {
            "request_id": "request-test",
            "run_id": "run-test",
            "execution_provider_name": "fake_sql_executor",
            "serialized_result_fingerprint": fingerprint,
        },
        "diagnostics": [],
        "warnings": [],
        "error_code": None,
        "result_fingerprint": fingerprint,
        "canonical_json": None,
    }


def _run_record(**overrides) -> dict:
    record = {
        "contract_version": "run-record-test",
        "request_id": "request-test",
        "run_id": "run-test",
        "status": "built",
        "outcome": "success",
        "lineage": {
            "context_version": "context-test",
            "context_fingerprint": "a" * 64,
            "intent_name": "generic_test_intent",
            "query_plan_fingerprint": "b" * 64,
            "current_sql_fingerprint": "c" * 64,
            "preflight_result_fingerprint": "d" * 64,
            "execution_request_fingerprint": "e" * 64,
            "execution_response_fingerprint": "f" * 64,
            "normalized_result_fingerprint": "1" * 64,
            "serialized_result_fingerprint": "2" * 64,
        },
        "metrics": {
            "row_count": 1,
            "column_count": 1,
            "bytes": 100,
            "duration_ms": 9,
            "truncated": False,
            "repair_attempts": 0,
        },
        "errors": [],
        "warnings": [],
        "serialized_result": _serialized(),
        "fingerprint": "3" * 64,
        "error_code": None,
    }
    record.update(overrides)
    return record


def _persisted(**overrides) -> dict:
    result = {
        "status": "persisted",
        "record_id": "record-test",
        "persisted_fingerprint": "3" * 64,
        "idempotency_key": "persist-key",
        "failure_category": "none",
        "diagnostic": None,
        "duration_ms": 1,
    }
    result.update(overrides)
    return result


def _audited(**overrides) -> dict:
    result = {
        "status": "written",
        "event_id": "event-test",
        "event_fingerprint": "4" * 64,
        "idempotency_key": "audit-key",
        "failure_category": "none",
        "diagnostic": None,
        "duration_ms": 1,
    }
    result.update(overrides)
    return result


def _observed(**overrides) -> dict:
    result = {
        "status": "emitted",
        "event_fingerprint": "5" * 64,
        "diagnostic": None,
        "duration_ms": 1,
    }
    result.update(overrides)
    return result


def _execution(**overrides) -> dict:
    result = {"status": "success", "executed": True, "provider_name": "fake"}
    result.update(overrides)
    return result


def _normalized(**overrides) -> dict:
    result = {"status": "success", "result_fingerprint": "6" * 64}
    result.update(overrides)
    return result


def _response(**overrides) -> dict:
    kwargs = {
        "request_id": "request-test",
        "run_id": "run-test",
        "original_outcome": "success",
        "finalization_status": "observed",
        "serialized_result": _serialized(),
        "normalized_result": _normalized(),
        "execution_result": _execution(),
        "run_record": _run_record(),
        "persistence_result": _persisted(),
        "audit_result": _audited(),
        "observability_result": _observed(),
        "errors": [],
        "warnings": [],
        "limits": default_application_response_limits(),
    }
    kwargs.update(overrides)
    return build_application_response(**kwargs)


def test_success_com_data_e_vazio() -> None:
    success = _response()
    empty = _response(
        serialized_result=_serialized(rows=[]),
        run_record=_run_record(
            metrics={
                "row_count": 0,
                "column_count": 1,
                "bytes": 80,
                "duration_ms": 1,
                "truncated": False,
                "repair_attempts": 0,
            }
        ),
    )
    assert success["status"] == "success"
    assert success["data"]["result"]["rows"][0]["cells"][0]["value"] == 1
    assert empty["status"] == "success"
    assert empty["data"]["pagination"]["returned_rows"] == 0


def test_rejected_sem_data_em_varios_estagios() -> None:
    for stage in [
        "receive_question",
        "classify_intent",
        "security_gate",
        "contract_gate",
        "repair_sql",
    ]:
        response = _response(
            original_outcome="rejected",
            finalization_status="observed",
            serialized_result=None,
            errors=[
                {
                    "code": f"{stage}_REJECTED",
                    "source": "graph",
                    "stage": stage,
                    "repairable": False,
                }
            ],
        )
        assert response["status"] == "rejected"
        assert response["data"] is None
        assert response["errors"][0]["stage"] == stage


def test_infrastructure_error_sem_data() -> None:
    response = _response(
        original_outcome="infrastructure_error",
        serialized_result=_serialized(),
        errors=[
            {
                "code": "CONTEXT_LOAD_FAILED",
                "message": "raw provider message",
                "source": "context",
                "stage": "load_context",
            }
        ],
    )
    assert response["status"] == "infrastructure_error"
    assert response["data"] is None
    assert response["message"] == "O processamento nao pode ser concluido."


def test_persistence_e_audit_failed_sao_fail_closed() -> None:
    persistence_failed = _response(
        finalization_status="persistence_failed",
        persistence_result={
            "status": "error",
            "record_id": None,
            "persisted_fingerprint": None,
            "idempotency_key": "persist-key",
            "failure_category": "unexpected_error",
            "diagnostic": {
                "code": "PERSIST_RUN_UNEXPECTED_ERROR",
                "message": "raw",
            },
            "duration_ms": None,
        },
    )
    audit_failed = _response(
        finalization_status="audit_failed",
        audit_result={
            "status": "error",
            "event_id": None,
            "event_fingerprint": None,
            "idempotency_key": "audit-key",
            "failure_category": "unexpected_error",
            "diagnostic": {
                "code": "AUDIT_UNEXPECTED_ERROR",
                "message": "raw",
            },
            "duration_ms": None,
        },
    )
    observed_after_persistence_failure = _response(
        finalization_status="observed",
        persistence_result={
            "status": "error",
            "record_id": None,
            "persisted_fingerprint": None,
            "idempotency_key": "persist-key",
            "failure_category": "unexpected_error",
            "diagnostic": {
                "code": "PERSIST_RUN_UNEXPECTED_ERROR",
                "message": "raw",
            },
            "duration_ms": None,
        },
    )
    assert persistence_failed["status"] == "infrastructure_error"
    assert persistence_failed["data"] is None
    assert persistence_failed["finalization"]["status"] == (
        "persistence_failed"
    )
    assert persistence_failed["metadata"]["original_outcome"] == "success"
    assert audit_failed["status"] == "infrastructure_error"
    assert audit_failed["data"] is None
    assert audit_failed["finalization"]["status"] == "audit_failed"
    assert observed_after_persistence_failure["finalization"]["status"] == (
        "persistence_failed"
    )


def test_observability_degraded_preserva_outcome() -> None:
    response = _response(
        finalization_status="observability_degraded",
        observability_result={
            "status": "degraded",
            "event_fingerprint": None,
            "diagnostic": {
                "code": "OBSERVABILITY_UNEXPECTED_ERROR",
                "message": "raw",
            },
            "duration_ms": None,
        },
        warnings=["OBSERVABILITY_UNEXPECTED_ERROR: raw"],
    )
    assert response["status"] == "success"
    assert response["data"] is not None
    assert response["finalization"]["status"] == "observability_degraded"
    assert response["warnings"][0]["code"] == "OBSERVABILITY_UNEXPECTED_ERROR"
    assert any(
        warning["code"] == "OBSERVABILITY_DEGRADED"
        for warning in response["warnings"]
    )


def test_record_failed_e_estado_inconsistente() -> None:
    response = _response(
        finalization_status="record_failed",
        run_record=None,
        persistence_result=None,
        audit_result=None,
        serialized_result=_serialized(),
    )
    assert response["status"] == "infrastructure_error"
    assert response["data"] is None
    assert response["finalization"]["status"] == "record_failed"


def test_erros_warnings_deduplicados_e_ordem_preservada() -> None:
    response = _response(
        errors=[
            {"code": "ORIGINAL", "source": "graph", "stage": "a"},
            {"code": "ORIGINAL", "source": "graph", "stage": "a"},
            {"code": "SECOND", "source": "graph", "stage": "b"},
        ],
        warnings=["W1: raw", "W1: raw", "W2: raw"],
    )
    assert [error["code"] for error in response["errors"]] == [
        "ORIGINAL",
        "SECOND",
    ]
    assert [warning["code"] for warning in response["warnings"]] == [
        "W1",
        "W2",
    ]


def test_mensagens_publicas_e_sem_provider_raw() -> None:
    response = _response(
        errors=[
            {
                "code": "PROVIDER_FAILED",
                "message": "Authorization Bearer raw stack trace",
                "source": "provider",
                "stage": "execute_sql",
            }
        ],
    )
    text = repr(response).casefold()
    assert "authorization" not in text
    assert "bearer" not in text
    assert "stack trace" not in text
    assert response["message"] == "Consulta processada com sucesso."


def test_sem_sql_pergunta_queryplan_payload_em_erro_ou_credenciais() -> None:
    response = _response(
        errors=[
            {
                "code": "SQL_FAILED",
                "message": "SELECT secret FROM hidden",
                "source": "provider",
                "stage": "execute_sql",
                "details": {"token": "secret"},
            }
        ],
        warnings=["Authorization header leaked"],
    )
    text = repr(response).casefold()
    assert "select secret" not in text
    assert "selected_pattern" not in text
    assert "planning_context" not in text
    assert "contextsnapshot" not in text
    assert "token" not in text
    assert "authorization" not in text
    assert "canonical_json" not in text


def test_metadata_lineage_paginacao() -> None:
    response = _response()
    metadata = response["metadata"]
    lineage = metadata["lineage"]
    pagination = response["data"]["pagination"]
    assert metadata["context_version"] == "context-test"
    assert metadata["intent"] == "generic_test_intent"
    assert metadata["row_count"] == 1
    assert metadata["column_count"] == 1
    assert metadata["persisted"] is True
    assert metadata["audited"] is True
    assert "current_sql_fingerprint" in lineage
    assert "run_record_fingerprint" in lineage
    assert pagination == {
        "mode": "none",
        "has_more": False,
        "next_cursor": None,
        "total_rows": 1,
        "returned_rows": 1,
    }


def test_fingerprint_deterministico_sem_ciclo_e_mudancas_relevantes() -> None:
    first = _response()
    second = _response()
    without_fingerprint = deepcopy(first)
    without_fingerprint.pop("response_fingerprint")
    changed_status = _response(original_outcome="rejected")
    changed_data = _response(serialized_result=_serialized(2))
    changed_error = _response(errors=[{"code": "DIFFERENT", "stage": "x"}])
    assert first["response_fingerprint"] == second["response_fingerprint"]
    assert first["response_fingerprint"] == stable_fingerprint(
        without_fingerprint
    )
    assert len(
        {
            first["response_fingerprint"],
            changed_status["response_fingerprint"],
            changed_data["response_fingerprint"],
            changed_error["response_fingerprint"],
        }
    ) == 4


def test_ordem_arbitraria_metadata_nao_altera_fingerprint() -> None:
    lineage_a = {"context_version": "context-test", "intent_name": "x"}
    lineage_b = {"intent_name": "x", "context_version": "context-test"}
    assert _response(run_record=_run_record(lineage=lineage_a))[
        "response_fingerprint"
    ] == _response(run_record=_run_record(lineage=lineage_b))[
        "response_fingerprint"
    ]


def test_nao_muta_e_copia_independente() -> None:
    serialized = _serialized()
    original = deepcopy(serialized)
    response = _response(serialized_result=serialized)
    assert serialized == original
    serialized["rows"][0]["cells"][0]["value"] = 99
    assert response["data"]["result"]["rows"][0]["cells"][0]["value"] == 1
    response["data"]["result"]["rows"][0]["cells"][0]["value"] = 77
    assert serialized["rows"][0]["cells"][0]["value"] == 99


def test_json_safe_e_canonical_sob_demanda() -> None:
    response = _response()
    canonical = to_canonical_application_response_json(response)
    assert isinstance(canonical, str)
    assert "response_fingerprint" in canonical
    assert "canonical_json" not in canonical


def test_limite_de_bytes_erros_warnings_e_data() -> None:
    byte_limited = _response(
        limits={**default_application_response_limits(), "max_response_bytes": 1000}
    )
    assert byte_limited["status"] == "infrastructure_error"
    assert byte_limited["data"] is None
    assert byte_limited["errors"][0]["code"] == (
        "APPLICATION_RESPONSE_LIMIT_EXCEEDED"
    )
    for field, value in [
        ("max_errors", 1),
        ("max_warnings", 1),
        ("max_data_rows", 0),
        ("max_data_columns", 0),
    ]:
        try:
            _response(
                errors=[{"code": "A"}, {"code": "B"}],
                warnings=["A", "B"],
                limits={**default_application_response_limits(), field: value},
            )
        except Exception as error:
            assert getattr(error, "code", "") == (
                "APPLICATION_RESPONSE_LIMIT_EXCEEDED"
            )
        else:
            raise AssertionError("Era esperado erro de limite.")


def test_data_presente_somente_em_success_finalizado() -> None:
    cases = [
        _response(serialized_result={**_serialized(), "status": "rejected"}),
        _response(normalized_result={"status": "rejected"}),
        _response(execution_result={"status": "success", "executed": False}),
        _response(persistence_result=None),
        _response(audit_result=None),
    ]
    for response in cases:
        assert response["status"] == "infrastructure_error"
        assert response["data"] is None


def main() -> None:
    tests = [
        test_success_com_data_e_vazio,
        test_rejected_sem_data_em_varios_estagios,
        test_infrastructure_error_sem_data,
        test_persistence_e_audit_failed_sao_fail_closed,
        test_observability_degraded_preserva_outcome,
        test_record_failed_e_estado_inconsistente,
        test_erros_warnings_deduplicados_e_ordem_preservada,
        test_mensagens_publicas_e_sem_provider_raw,
        test_sem_sql_pergunta_queryplan_payload_em_erro_ou_credenciais,
        test_metadata_lineage_paginacao,
        test_fingerprint_deterministico_sem_ciclo_e_mudancas_relevantes,
        test_ordem_arbitraria_metadata_nao_altera_fingerprint,
        test_nao_muta_e_copia_independente,
        test_json_safe_e_canonical_sob_demanda,
        test_limite_de_bytes_erros_warnings_e_data,
        test_data_presente_somente_em_success_finalizado,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()

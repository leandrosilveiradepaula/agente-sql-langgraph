from __future__ import annotations

from copy import deepcopy

from app.domain.result_normalization import stable_fingerprint
from app.domain.run_record import (
    RunRecordError,
    build_run_record,
    default_finalization_limits,
)


def _serialized_result(value: int = 1) -> dict:
    return {
        "status": "success",
        "contract_version": "serialization-test",
        "columns": [
            {
                "ordinal": 0,
                "original_name": "id",
                "normalized_type": "integer",
            }
        ],
        "rows": [
            {
                "ordinal": 0,
                "cells": [{"type": "integer", "value": value}],
            }
        ],
        "lineage": {
            "serialized_result_fingerprint": stable_fingerprint(
                {"value": value}
            )
        },
        "diagnostics": [],
        "warnings": [],
        "error_code": None,
        "result_fingerprint": stable_fingerprint({"value": value}),
        "canonical_json": None,
    }


def _state(**overrides) -> dict:
    state = {
        "request_id": "request-test",
        "run_id": "run-test",
        "final_status": "approved",
        "failure_stage": "",
        "current_stage": "serialize_result",
        "context_version": "context-test",
        "context": {"fingerprint": "a" * 64},
        "intent": "generic_test_intent",
        "intent_confidence": 0.98,
        "query_plan": {"intent_name": "generic_test_intent"},
        "generated_sql": "SELECT id FROM schema_test.table_test",
        "current_sql": "SELECT id FROM schema_test.table_test",
        "security_result": {"status": "approved"},
        "contract_result": {"status": "approved"},
        "engine_preflight_result": {"status": "approved"},
        "sql_execution_result": {
            "status": "success",
            "row_count": 1,
            "bytes_received": 10,
            "duration_ms": 7,
            "truncated": False,
            "request_fingerprint": "b" * 64,
            "response_fingerprint": "c" * 64,
            "sql_fingerprint": "d" * 64,
        },
        "normalized_result": {
            "status": "success",
            "result_fingerprint": "e" * 64,
        },
        "serialized_result": _serialized_result(),
        "repair_attempts": 0,
        "repair_history": [],
        "errors": [],
        "warnings": [],
    }
    state.update(overrides)
    return state


def _limits(**overrides) -> dict:
    limits = default_finalization_limits()
    limits.update(overrides)
    return limits


def test_success_com_resultado() -> None:
    record = build_run_record(_state(), limits=_limits())
    assert record["outcome"] == "success"
    assert record["previous_stage"] == "serialize_result"
    assert record["serialized_result"]["status"] == "success"
    assert record["metrics"]["row_count"] == 1
    assert record["metrics"]["column_count"] == 1


def test_rejected_antes_de_sql() -> None:
    state = _state(
        final_status="rejected",
        current_stage="classify_intent",
        failure_stage="classify_intent",
        generated_sql="",
        current_sql="",
        serialized_result=None,
        sql_execution_result=None,
        errors=[
            {
                "code": "INTENT_NOT_RESOLVED",
                "source": "intent",
                "stage": "classify_intent",
                "repairable": False,
            }
        ],
    )
    record = build_run_record(state, limits=_limits())
    assert record["outcome"] == "rejected"
    assert record["serialized_result"] is None
    assert record["errors"][0]["code"] == "INTENT_NOT_RESOLVED"


def test_security_contract_repair_e_infra() -> None:
    security = build_run_record(
        _state(
            final_status="rejected",
            current_stage="security_gate",
            failure_stage="security_gate",
            security_result={"status": "rejected"},
        ),
        limits=_limits(),
    )
    contract = build_run_record(
        _state(
            final_status="rejected",
            current_stage="contract_gate",
            failure_stage="contract_gate",
            contract_result={"status": "rejected"},
        ),
        limits=_limits(),
    )
    repair_limit = build_run_record(
        _state(
            final_status="rejected",
            current_stage="repair_sql",
            failure_stage="repair_sql",
            repair_attempts=1,
            repair_history=[
                {
                    "attempt": 1,
                    "failed_stage": "engine_preflight",
                    "sql_before": "SELECT raw FROM hidden",
                    "sql_after": "SELECT raw FROM hidden",
                    "sql_before_fingerprint": "f" * 64,
                    "sql_after_fingerprint": "0" * 64,
                    "request_fingerprint": "1" * 64,
                    "response_fingerprint": "2" * 64,
                    "repair_applied": True,
                }
            ],
        ),
        limits=_limits(),
    )
    infra = build_run_record(
        _state(
            final_status="infrastructure_error",
            current_stage="finalize_infrastructure_error",
            failure_stage="load_context",
            serialized_result=None,
        ),
        limits=_limits(),
    )
    assert security["lineage"]["security_status"] == "rejected"
    assert contract["lineage"]["contract_status"] == "rejected"
    assert repair_limit["lineage"]["repair_attempts"] == 1
    assert "SELECT raw" not in repr(repair_limit)
    assert infra["outcome"] == "infrastructure_error"


def test_fingerprint_deterministico_sem_auto_referencia() -> None:
    first = build_run_record(_state(), limits=_limits())
    second = build_run_record(_state(), limits=_limits())
    without_fingerprint = deepcopy(first)
    without_fingerprint.pop("fingerprint")
    assert first["fingerprint"] == second["fingerprint"]
    assert first["fingerprint"] == stable_fingerprint(without_fingerprint)
    assert "fingerprint" not in without_fingerprint


def test_ordem_de_dict_nao_altera_fingerprint() -> None:
    state_a = _state(query_plan={"a": 1, "b": 2})
    state_b = _state(query_plan={"b": 2, "a": 1})
    assert build_run_record(state_a, limits=_limits())["fingerprint"] == (
        build_run_record(state_b, limits=_limits())["fingerprint"]
    )


def test_mudancas_relevantes_alteram_fingerprint() -> None:
    base = build_run_record(_state(), limits=_limits())["fingerprint"]
    outcome = build_run_record(
        _state(final_status="rejected", failure_stage="security_gate"),
        limits=_limits(),
    )["fingerprint"]
    error = build_run_record(
        _state(
            errors=[
                {
                    "code": "DIFFERENT_ERROR",
                    "source": "test",
                    "stage": "stage",
                }
            ]
        ),
        limits=_limits(),
    )["fingerprint"]
    result = build_run_record(
        _state(serialized_result=_serialized_result(2)),
        limits=_limits(),
    )["fingerprint"]
    assert len({base, outcome, error, result}) == 4


def test_nao_inclui_sql_integral_nem_credenciais() -> None:
    record = build_run_record(
        _state(
            errors=[
                {
                    "code": "AUTHORIZATION_BEARER_TOKEN",
                    "message": "Authorization Bearer token",
                    "source": "provider",
                    "stage": "stage",
                    "details": {
                        "body": "SELECT password FROM secret_table",
                    },
                }
            ]
        ),
        limits=_limits(),
    )
    serialized = repr(record).casefold()
    assert "select id from" not in serialized
    assert "select password" not in serialized
    assert "bearer" not in serialized
    assert "authorization" not in serialized


def test_payload_limites_e_copia_independente() -> None:
    state = _state()
    original = deepcopy(state)
    record = build_run_record(state, limits=_limits())
    assert state == original
    state["serialized_result"]["rows"][0]["cells"][0]["value"] = 99
    assert record["serialized_result"]["rows"][0]["cells"][0]["value"] == 1
    try:
        build_run_record(
            _state(serialized_result=_serialized_result(123456)),
            limits=_limits(max_persisted_payload_bytes=10),
        )
    except RunRecordError as error:
        assert error.code == "RUN_RECORD_LIMIT_EXCEEDED"
    else:
        raise AssertionError("Era esperado RunRecordError.")


def test_limites_de_estagios_erros_warnings() -> None:
    for limits in [
        _limits(max_stage_records=1),
        _limits(max_error_records=1),
        _limits(max_warning_records=1),
    ]:
        try:
            build_run_record(
                _state(
                    errors=[
                        {"code": "E1", "source": "s", "stage": "a"},
                        {"code": "E2", "source": "s", "stage": "b"},
                    ],
                    warnings=["W1", "W2"],
                ),
                limits=limits,
            )
        except RunRecordError as error:
            assert error.code == "RUN_RECORD_LIMIT_EXCEEDED"
        else:
            raise AssertionError("Era esperado RunRecordError.")


def main() -> None:
    tests = [
        test_success_com_resultado,
        test_rejected_antes_de_sql,
        test_security_contract_repair_e_infra,
        test_fingerprint_deterministico_sem_auto_referencia,
        test_ordem_de_dict_nao_altera_fingerprint,
        test_mudancas_relevantes_alteram_fingerprint,
        test_nao_inclui_sql_integral_nem_credenciais,
        test_payload_limites_e_copia_independente,
        test_limites_de_estagios_erros_warnings,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()

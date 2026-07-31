from __future__ import annotations

from copy import deepcopy

from app.adapters.testing.fake_observability_sink import (
    FakeObservabilitySink,
)
from app.domain.run_record import default_finalization_limits
from app.graph.nodes.emit_observability import (
    create_emit_observability_node,
)
from testar_persist_run import _record
from testar_record_audit import _persistence_result


def _audit_result() -> dict:
    return {
        "status": "written",
        "event_id": "event-test",
        "event_fingerprint": "a" * 64,
        "idempotency_key": "audit-key",
        "failure_category": "none",
        "diagnostic": None,
        "duration_ms": 1,
    }


def _state(record: dict | None = None, **overrides) -> dict:
    selected = record if record is not None else _record()
    state = {
        "original_outcome": selected["outcome"],
        "run_record": selected,
        "persistence_result": _persistence_result(selected),
        "audit_result": _audit_result(),
        "serialized_result": selected.get("serialized_result"),
        "errors": [],
        "warnings": [],
        "current_stage": "record_audit",
        "final_status": "approved",
        "failure_stage": "",
        "finalization_status": "audited",
        "options": {
            "run_finalization_limits": default_finalization_limits(),
        },
    }
    state.update(overrides)
    return state


def test_success_rejected_infra() -> None:
    for outcome, final_status in [
        ("success", "approved"),
        ("rejected", "rejected"),
        ("infrastructure_error", "infrastructure_error"),
    ]:
        record = _record()
        record["outcome"] = outcome
        sink = FakeObservabilitySink()
        result = create_emit_observability_node(sink)(
            _state(
                record,
                original_outcome=outcome,
                failure_stage=(
                    "security_gate" if outcome == "rejected" else ""
                ),
            )
        )
        assert sink.calls == 1
        assert result["final_status"] == final_status
        assert result["observability_result"]["status"] == "emitted"
        assert result["observability_degraded"] is False


def test_metricas_seguras_sem_alta_cardinalidade() -> None:
    sink = FakeObservabilitySink()
    create_emit_observability_node(sink)(_state())
    event = sink.events[0]
    metric_names = {metric["name"] for metric in event["metrics"]}
    assert "run_completed_total" in metric_names
    assert "result_row_count" in metric_names
    assert "result_bytes" in metric_names
    for metric in event["metrics"]:
        labels = metric["labels"]
        assert set(labels) == {"outcome", "finalization_status"}
        assert "request_id" not in labels
        assert "run_id" not in labels
        assert "sql_fingerprint" not in labels


def test_sem_sql_payload_ou_valores() -> None:
    sink = FakeObservabilitySink()
    create_emit_observability_node(sink)(_state())
    event = sink.events[0]
    serialized = repr(event).casefold()
    assert "serialized_result" not in event
    assert "current_sql" not in serialized
    assert "generated_sql" not in serialized
    assert "select " not in serialized
    assert "cells" not in serialized


def test_degraded_preserva_resultados() -> None:
    state = _state()
    original_result = deepcopy(state["serialized_result"])
    original_persistence = deepcopy(state["persistence_result"])
    original_audit = deepcopy(state["audit_result"])
    result = create_emit_observability_node(
        FakeObservabilitySink(exceptions=[RuntimeError("provider down")])
    )(state)
    assert result["observability_degraded"] is True
    assert result["finalization_status"] == "observability_degraded"
    assert result["final_status"] == "approved"
    assert state["serialized_result"] == original_result
    assert state["persistence_result"] == original_persistence
    assert state["audit_result"] == original_audit


def test_timeout_excecao_e_state_nao_mutado() -> None:
    for exception, code in [
        (TimeoutError(), "OBSERVABILITY_TIMEOUT"),
        (RuntimeError("SELECT hidden"), "OBSERVABILITY_UNEXPECTED_ERROR"),
    ]:
        state = _state()
        original = deepcopy(state)
        result = create_emit_observability_node(
            FakeObservabilitySink(exceptions=[exception])
        )(state)
        assert state == original
        assert result["observability_result"]["status"] == "degraded"
        assert result["observability_result"]["diagnostic"]["code"] == code
        assert "select hidden" not in repr(result).casefold()


def test_limite_de_atributos() -> None:
    record = _record()
    state = _state(record)
    state["options"] = {
        "run_finalization_limits": {
            "max_persisted_payload_bytes": 262144,
            "max_stage_records": 32,
            "max_error_records": 32,
            "max_warning_records": 32,
            "max_audit_error_codes": 16,
            "max_observability_attributes": 3,
            "max_attribute_length": 8,
            "max_provider_name_length": 64,
        }
    }
    sink = FakeObservabilitySink()
    create_emit_observability_node(sink)(state)
    assert len(sink.events[0]["attributes"]) == 3
    assert all(
        len(attribute["key"]) <= 8
        for attribute in sink.events[0]["attributes"]
    )


def main() -> None:
    tests = [
        test_success_rejected_infra,
        test_metricas_seguras_sem_alta_cardinalidade,
        test_sem_sql_payload_ou_valores,
        test_degraded_preserva_resultados,
        test_timeout_excecao_e_state_nao_mutado,
        test_limite_de_atributos,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()

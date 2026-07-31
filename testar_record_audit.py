from __future__ import annotations

from copy import deepcopy

from app.adapters.testing.fake_audit_sink import FakeAuditSink
from app.domain.run_record import default_finalization_limits
from app.graph.nodes.record_audit import create_record_audit_node
from testar_persist_run import _record


def _persistence_result(record: dict) -> dict:
    return {
        "status": "persisted",
        "record_id": "record-test",
        "persisted_fingerprint": record["fingerprint"],
        "idempotency_key": "persist-key",
        "failure_category": "none",
        "diagnostic": None,
        "duration_ms": 1,
    }


def _state(record: dict | None = None, **overrides) -> dict:
    selected = record if record is not None else _record()
    state = {
        "run_record": selected,
        "persistence_result": _persistence_result(selected),
        "user": {"profile": "generic"},
        "errors": [],
        "warnings": [],
        "current_stage": "persist_run",
        "final_status": "approved",
        "failure_stage": "",
        "options": {
            "run_finalization_limits": default_finalization_limits(),
        },
    }
    state.update(overrides)
    return state


def test_eventos_por_outcome() -> None:
    for outcome, event_type in [
        ("success", "sql_agent_run_completed"),
        ("rejected", "sql_agent_run_rejected"),
        (
            "infrastructure_error",
            "sql_agent_run_infrastructure_error",
        ),
    ]:
        record = _record()
        record["outcome"] = outcome
        sink = FakeAuditSink()
        result = create_record_audit_node(sink)(_state(record))
        assert result["audit_result"]["status"] == "written"
        assert sink.events[0]["event_type"] == event_type
        assert sink.events[0]["outcome"] == outcome


def test_persistencia_ausente_bloqueia_auditoria() -> None:
    sink = FakeAuditSink()
    result = create_record_audit_node(sink)(
        _state(persistence_result=None)
    )
    assert sink.calls == 0
    assert result["final_status"] == "infrastructure_error"
    assert result["audit_result"]["failure_category"] == "request_invalid"


def test_sink_chamado_uma_vez_sem_payload_ou_sql() -> None:
    sink = FakeAuditSink()
    state = _state()
    original = deepcopy(state)
    result = create_record_audit_node(sink)(state)
    assert state == original
    assert sink.calls == 1
    event = sink.events[0]
    serialized = repr(event).casefold()
    assert result["finalization_status"] == "audited"
    assert "serialized_result" not in event
    assert "rows" not in event
    assert "cells" not in event
    assert "select " not in serialized


def test_resultado_anterior_inconsistente_nao_chama_sink() -> None:
    sink = FakeAuditSink()
    result = create_record_audit_node(sink)(
        _state(
            audit_result={
                "status": "error",
                "event_id": None,
                "event_fingerprint": None,
                "idempotency_key": "old",
                "failure_category": "unexpected_error",
                "diagnostic": {
                    "code": "AUDIT_UNEXPECTED_ERROR",
                    "message": "Auditoria indisponivel.",
                    "failure_category": "unexpected_error",
                },
                "duration_ms": 1,
            }
        )
    )
    assert sink.calls == 0
    assert result["final_status"] == "infrastructure_error"
    assert result["finalization_status"] == "audit_failed"


def test_success_com_failure_category_ou_failure_com_event_id_rejeita() -> None:
    mismatch = create_record_audit_node(
        FakeAuditSink(
            responses=[
                {
                    "status": "written",
                    "event_id": "event-test",
                    "event_fingerprint": "ignored",
                    "idempotency_key": "audit-key",
                    "failure_category": "conflict",
                    "diagnostic": None,
                    "duration_ms": 1,
                }
            ]
        )
    )(_state())
    assert mismatch["errors"][-1]["code"] == "AUDIT_REQUEST_INVALID"

    failure_with_event = create_record_audit_node(
        FakeAuditSink(
            responses=[
                {
                    "status": "error",
                    "event_id": "event-test",
                    "event_fingerprint": None,
                    "idempotency_key": "audit-key",
                    "failure_category": "unexpected_error",
                    "diagnostic": {
                        "code": "AUDIT_UNEXPECTED_ERROR",
                        "message": "Auditoria indisponivel.",
                        "failure_category": "unexpected_error",
                    },
                    "duration_ms": 1,
                }
            ]
        )
    )(_state())
    assert failure_with_event["errors"][-1]["code"] == (
        "AUDIT_REQUEST_INVALID"
    )


def test_idempotencia_conflito_e_fingerprint() -> None:
    sink = FakeAuditSink()
    node = create_record_audit_node(sink)
    first = node(_state())
    second = node(_state(audit_result=first["audit_result"]))
    assert sink.calls == 1
    assert second["finalization_status"] == "audited"

    event = sink.events[0]
    conflict = sink.write({**event, "fingerprint": "different"})
    assert conflict["status"] == "rejected"
    assert conflict["failure_category"] == "conflict"

    mismatch = create_record_audit_node(
        FakeAuditSink(
            responses=[
                {
                    "status": "written",
                    "event_id": "event-test",
                    "event_fingerprint": "different",
                    "idempotency_key": "audit-key",
                    "failure_category": "none",
                    "diagnostic": None,
                    "duration_ms": 1,
                }
            ]
        )
    )(_state())
    assert mismatch["errors"][-1]["code"] == "AUDIT_FINGERPRINT_MISMATCH"


def test_timeout_autenticacao_excecao_sanitizados() -> None:
    for exception, code, category in [
        (TimeoutError(), "AUDIT_TIMEOUT", "timeout"),
        (PermissionError(), "AUDIT_AUTHENTICATION_FAILED", "authentication_failed"),
        (RuntimeError("SELECT hidden"), "AUDIT_UNEXPECTED_ERROR", "unexpected_error"),
    ]:
        result = create_record_audit_node(
            FakeAuditSink(exceptions=[exception])
        )(_state())
        assert result["final_status"] == "infrastructure_error"
        assert result["errors"][-1]["code"] == code
        assert result["audit_result"]["failure_category"] == category
        assert "select hidden" not in repr(result["errors"]).casefold()


def main() -> None:
    tests = [
        test_eventos_por_outcome,
        test_persistencia_ausente_bloqueia_auditoria,
        test_sink_chamado_uma_vez_sem_payload_ou_sql,
        test_resultado_anterior_inconsistente_nao_chama_sink,
        test_success_com_failure_category_ou_failure_com_event_id_rejeita,
        test_idempotencia_conflito_e_fingerprint,
        test_timeout_autenticacao_excecao_sanitizados,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()

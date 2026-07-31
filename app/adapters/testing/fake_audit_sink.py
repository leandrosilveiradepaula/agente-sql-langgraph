from __future__ import annotations

from copy import deepcopy

from app.domain.run_audit_types import AuditEvent, AuditResult


class FakeAuditSink:
    """
    Sink de auditoria fake em memoria para testes locais.
    """

    def __init__(
        self,
        *,
        responses: list[AuditResult] | None = None,
        exceptions: list[Exception] | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.exceptions = list(exceptions or [])
        self.calls = 0
        self.events: list[AuditEvent] = []
        self._by_key: dict[str, AuditEvent] = {}

    def write(
        self,
        event: AuditEvent,
    ) -> AuditResult:
        self.calls += 1
        captured = deepcopy(event)
        self.events.append(captured)
        serialized = repr(captured).casefold()
        assert "serialized_result" not in captured
        assert "select " not in serialized
        assert "password" not in serialized
        assert "token" not in serialized
        assert "dsn" not in serialized
        if self.exceptions:
            raise self.exceptions.pop(0)
        if self.responses:
            return deepcopy(self.responses.pop(0))

        key = event["idempotency_key"]
        fingerprint = event["fingerprint"]
        previous = self._by_key.get(key)
        if previous is None:
            self._by_key[key] = deepcopy(event)
            return {
                "status": "written",
                "event_id": event["event_id"],
                "event_fingerprint": fingerprint,
                "idempotency_key": key,
                "failure_category": "none",
                "diagnostic": None,
                "duration_ms": 1,
            }
        if previous["fingerprint"] == fingerprint:
            return {
                "status": "already_written",
                "event_id": previous["event_id"],
                "event_fingerprint": fingerprint,
                "idempotency_key": key,
                "failure_category": "none",
                "diagnostic": None,
                "duration_ms": 1,
            }
        return {
            "status": "rejected",
            "event_id": None,
            "event_fingerprint": previous["fingerprint"],
            "idempotency_key": key,
            "failure_category": "conflict",
            "diagnostic": {
                "code": "AUDIT_CONFLICT",
                "message": "Evento ja existe com fingerprint diferente.",
                "failure_category": "conflict",
            },
            "duration_ms": 1,
        }

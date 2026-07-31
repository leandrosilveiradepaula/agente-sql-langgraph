from __future__ import annotations

from copy import deepcopy

from app.domain.run_observability_types import (
    ObservabilityEvent,
    ObservabilityResult,
)


class FakeObservabilitySink:
    """
    Sink de observabilidade fake em memoria para testes locais.
    """

    def __init__(
        self,
        *,
        responses: list[ObservabilityResult] | None = None,
        exceptions: list[Exception] | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.exceptions = list(exceptions or [])
        self.calls = 0
        self.events: list[ObservabilityEvent] = []
        self.degraded = False

    def emit(
        self,
        event: ObservabilityEvent,
    ) -> ObservabilityResult:
        self.calls += 1
        captured = deepcopy(event)
        self.events.append(captured)
        serialized = repr(captured).casefold()
        assert "serialized_result" not in captured
        assert "current_sql" not in serialized
        assert "generated_sql" not in serialized
        assert "select " not in serialized
        assert "password" not in serialized
        assert "token" not in serialized
        assert "dsn" not in serialized
        for metric in captured.get("metrics", []):
            labels = metric.get("labels", {})
            assert "request_id" not in labels
            assert "run_id" not in labels
            assert "sql_fingerprint" not in labels
        if self.exceptions:
            self.degraded = True
            raise self.exceptions.pop(0)
        if self.responses:
            result = deepcopy(self.responses.pop(0))
            self.degraded = result["status"] == "degraded"
            return result
        return {
            "status": "emitted",
            "event_fingerprint": event["fingerprint"],
            "diagnostic": None,
            "duration_ms": 1,
        }

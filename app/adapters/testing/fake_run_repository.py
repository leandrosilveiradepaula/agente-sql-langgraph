from __future__ import annotations

from copy import deepcopy

from app.domain.run_persistence_types import (
    PersistRunRequest,
    PersistRunResult,
)


class FakeRunRepository:
    """
    Repositorio fake em memoria para testes locais.

    Nao escreve arquivos, nao acessa banco e nao e fallback de producao.
    """

    def __init__(
        self,
        *,
        responses: list[PersistRunResult] | None = None,
        exceptions: list[Exception] | None = None,
        record_id: str = "run-record-test-1",
    ) -> None:
        self.responses = list(responses or [])
        self.exceptions = list(exceptions or [])
        self.record_id = record_id
        self.calls = 0
        self.requests: list[PersistRunRequest] = []
        self.records: dict[str, PersistRunRequest] = {}

    def save(
        self,
        request: PersistRunRequest,
    ) -> PersistRunResult:
        self.calls += 1
        captured = deepcopy(request)
        self.requests.append(captured)
        serialized = repr(captured).casefold()
        assert "graphstate" not in serialized
        assert "contextsnapshot" not in serialized
        assert "current_sql" not in captured
        assert "generated_sql" not in captured
        assert "password" not in serialized
        assert "token" not in serialized
        assert "dsn" not in serialized
        if self.exceptions:
            raise self.exceptions.pop(0)
        if self.responses:
            return deepcopy(self.responses.pop(0))

        key = request["idempotency_key"]
        fingerprint = request["run_record_fingerprint"]
        previous = self.records.get(key)
        if previous is None:
            self.records[key] = deepcopy(request)
            return {
                "status": "persisted",
                "record_id": self.record_id,
                "persisted_fingerprint": fingerprint,
                "idempotency_key": key,
                "failure_category": "none",
                "diagnostic": None,
                "duration_ms": 1,
            }
        previous_fingerprint = previous["run_record_fingerprint"]
        if previous_fingerprint == fingerprint:
            return {
                "status": "already_persisted",
                "record_id": self.record_id,
                "persisted_fingerprint": fingerprint,
                "idempotency_key": key,
                "failure_category": "none",
                "diagnostic": None,
                "duration_ms": 1,
            }
        return {
            "status": "rejected",
            "record_id": None,
            "persisted_fingerprint": previous_fingerprint,
            "idempotency_key": key,
            "failure_category": "conflict",
            "diagnostic": {
                "code": "PERSIST_RUN_CONFLICT",
                "message": "Registro ja existe com fingerprint diferente.",
                "failure_category": "conflict",
                "safe_details": {},
            },
            "duration_ms": 1,
        }

from __future__ import annotations

from copy import deepcopy

from app.domain.sql_generation import (
    SqlGenerationProviderResult,
    SqlGenerationRequest,
)


class FakeSqlGenerator:
    """
    Deterministic SQL generator for local/offline tests.

    It never calls Gemini or any external provider.
    """

    def __init__(
        self,
        sql: str = "SELECT id FROM schema_test.table_test",
    ) -> None:
        self.sql = sql
        self.calls = 0
        self.requests: list[SqlGenerationRequest] = []

    @property
    def last_request(self) -> SqlGenerationRequest | None:
        return self.requests[-1] if self.requests else None

    def generate(
        self,
        request: SqlGenerationRequest,
    ) -> SqlGenerationProviderResult:
        self.calls += 1
        self.requests.append(deepcopy(request))
        serialized = repr(request).casefold()
        assert "password" not in serialized
        assert "token" not in serialized
        assert "secret" not in serialized
        assert "dsn" not in serialized
        return {
            "provider_name": "fake_sql_generator",
            "provider_version": "local-shadow-e2e",
            "output_text": self.sql,
            "duration_ms": 1,
        }

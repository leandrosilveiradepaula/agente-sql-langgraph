from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.domain.sql_repair import (
    SqlRepairProviderResult,
    SqlRepairRequest,
)


class FakeSqlRepairer:
    """
    Fake configuravel para testes locais.

    Nao deve ser usado como provider padrao em producao.
    """

    def __init__(
        self,
        *,
        responses: list[str | SqlRepairProviderResult] | None = None,
        exceptions: list[Exception] | None = None,
        duration_ms: int = 5,
        provider_name: str = "fake_sql_repairer",
    ) -> None:
        self.responses = list(
            responses
            if responses is not None
            else ["SELECT id FROM schema_test.table_test"]
        )
        self.exceptions = list(exceptions or [])
        self.duration_ms = duration_ms
        self.provider_name = provider_name
        self.calls = 0
        self.requests: list[SqlRepairRequest] = []

    @property
    def last_request(self) -> SqlRepairRequest | None:
        return self.requests[-1] if self.requests else None

    def repair(
        self,
        request: SqlRepairRequest,
    ) -> SqlRepairProviderResult:
        self.calls += 1
        self.requests.append(deepcopy(request))
        serialized = repr(request).casefold()
        assert "graphstate" not in serialized
        assert "contextsnapshot" not in serialized
        assert "intent_catalog" not in serialized
        assert "query_patterns" not in serialized
        assert "table_catalog" not in serialized
        assert "password" not in serialized
        assert "token" not in serialized
        assert "dsn" not in serialized
        if self.exceptions:
            raise self.exceptions.pop(0)
        response = self.responses.pop(0) if self.responses else ""
        if isinstance(response, dict):
            return deepcopy(response)
        return {
            "provider_name": self.provider_name,
            "output_text": response,
            "raw_response": {"present": True},
            "duration_ms": self.duration_ms,
        }

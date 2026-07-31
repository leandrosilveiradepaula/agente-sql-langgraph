from __future__ import annotations

from copy import deepcopy

from app.domain.sql_execution import (
    SqlExecutionColumn,
    SqlExecutionProviderResult,
    SqlExecutionRequest,
    SqlExecutionRow,
)


class FakeSqlExecutor:
    """
    Fake configuravel para testes locais.

    Nao executa nem interpreta SQL e nunca deve ser fallback em producao.
    """

    def __init__(
        self,
        *,
        responses: list[SqlExecutionProviderResult] | None = None,
        exceptions: list[Exception] | None = None,
        provider_name: str = "fake_sql_executor",
        provider_version: str = "test-v1",
        duration_ms: int = 7,
        columns: list[SqlExecutionColumn] | None = None,
        rows: list[SqlExecutionRow] | None = None,
        row_count: int | None = None,
        bytes_received: int | None = None,
        truncated: bool = False,
    ) -> None:
        self.responses = list(responses or [])
        self.exceptions = list(exceptions or [])
        self.provider_name = provider_name
        self.provider_version = provider_version
        self.duration_ms = duration_ms
        self.columns = deepcopy(
            columns if columns is not None else [{"name": "id", "type": "int"}]
        )
        self.rows = deepcopy(rows if rows is not None else [{"id": 1}])
        self.row_count = row_count
        self.bytes_received = bytes_received
        self.truncated = truncated
        self.calls = 0
        self.requests: list[SqlExecutionRequest] = []

    @property
    def last_request(self) -> SqlExecutionRequest | None:
        return self.requests[-1] if self.requests else None

    def execute(
        self,
        request: SqlExecutionRequest,
    ) -> SqlExecutionProviderResult:
        self.calls += 1
        self.requests.append(deepcopy(request))
        serialized = repr(request).casefold()
        assert "graphstate" not in serialized
        assert "contextsnapshot" not in serialized
        assert "context" not in request
        assert "query_plan" not in request
        assert "intent_catalog" not in serialized
        assert "table_catalog" not in serialized
        assert "password" not in serialized
        assert "token" not in serialized
        assert "dsn" not in serialized
        if self.exceptions:
            raise self.exceptions.pop(0)
        if self.responses:
            return deepcopy(self.responses.pop(0))
        result: SqlExecutionProviderResult = {
            "status": "success",
            "provider_name": self.provider_name,
            "provider_version": self.provider_version,
            "columns": deepcopy(self.columns),
            "rows": deepcopy(self.rows),
            "row_count": (
                self.row_count
                if self.row_count is not None
                else len(self.rows)
            ),
            "duration_ms": self.duration_ms,
            "truncated": self.truncated,
            "executed": True,
            "statement_type": "select",
            "warnings": [],
        }
        if self.bytes_received is not None:
            result["bytes_received"] = self.bytes_received
        return result

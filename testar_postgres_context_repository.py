from __future__ import annotations

from copy import deepcopy
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.adapters.postgres.context_repository import (
    LOAD_SEMANTIC_CONTEXT_SQL,
    PostgresContextRepository,
)
from app.ports.context_repository import ContextRepositoryError


def _physical_snapshot() -> dict[str, Any]:
    return {
        "semantic_agent_version": "semantic-test-v1",
        "semantic_context_source": (
            "postgres_versioned_semantic_context"
        ),
        "regras": [
            {
                "rule_group": "configuration",
                "rule_name": "resolver_configuration",
                "rule_content": {
                    "component": "intent_resolver",
                    "minimum_score": 100,
                },
                "applies_to_intents": [],
                "validation_hint": None,
                "severity": "configuration",
                "priority": 1,
            },
            {
                "rule_group": "general",
                "rule_name": "generic_rule",
                "rule_content": {
                    "enabled": True,
                },
                "applies_to_intents": [
                    "generic_intent",
                ],
                "validation_hint": None,
                "severity": "mandatory",
                "priority": 2,
            },
        ],
        "entidades": [
            {
                "entity_type": "intent_signal",
                "user_term": "generic analysis",
                "canonical_value": "generic_intent",
                "target_table": None,
                "target_column": None,
                "sql_filter_hint": {
                    "resolver": {
                        "match_mode": "contains",
                        "polarity": "positive",
                        "score": 120,
                    }
                },
                "business_rule": None,
                "priority": 1,
            }
        ],
        "dre": [],
        "padroes": [
            {
                "intent_name": "generic_intent",
                "pattern_name": "generic_pattern",
                "business_question_examples": [],
                "required_tables": [
                    "schema_test.table_test",
                ],
                "required_rules": [
                    "generic_rule",
                ],
                "sql_pattern": "SELECT 1",
                "notes": None,
                "priority": 1,
            }
        ],
        "catalogo": [
            {
                "table_name": "table_test",
                "schema_name": "schema_test",
                "table_type": "table",
                "description": None,
                "grain": None,
                "primary_key": [
                    "id",
                ],
                "key_columns": [
                    "id",
                ],
                "metric_columns": [
                    "value",
                ],
                "date_columns": [
                    "event_date",
                ],
                "join_rules": [],
                "ai_hint": None,
                "priority": 1,
            }
        ],
        "context_counts": {
            "regras": 2,
            "entidades": 1,
            "dre": 0,
            "padroes": 1,
            "catalogo": 1,
        },
    }


class FakeCursor:
    def __init__(self, row: Any) -> None:
        self._row = row
        self.executed_query: str | None = None
        self.executed_parameters: dict[str, Any] | None = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> bool:
        return False

    def execute(
        self,
        query: str,
        parameters: dict[str, Any],
    ) -> None:
        self.executed_query = query
        self.executed_parameters = parameters

    def fetchone(self) -> Any:
        return deepcopy(self._row)


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor
        self.cursor_calls = 0

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> bool:
        return False

    def cursor(self) -> FakeCursor:
        self.cursor_calls += 1
        return self._cursor


class FakeConnect:
    def __init__(
        self,
        *,
        row: Any = None,
        error: Exception | None = None,
    ) -> None:
        self.cursor = FakeCursor(row)
        self.connection = FakeConnection(self.cursor)
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        dsn: str,
        **kwargs: Any,
    ) -> FakeConnection:
        self.calls.append(
            {
                "dsn": dsn,
                **kwargs,
            }
        )

        if self.error is not None:
            raise self.error

        return self.connection


def _repository(fake_connect: FakeConnect) -> PostgresContextRepository:
    return PostgresContextRepository(
        dsn="postgresql://example.invalid/database",
        semantic_agent_version="semantic-test-v1",
        connect_timeout_seconds=7,
        connect=fake_connect,
    )


def test_carrega_snapshot_com_query_parametrizada() -> None:
    fake_connect = FakeConnect(row=_physical_snapshot())
    repository = _repository(fake_connect)

    snapshot = repository.load_active_context(
        user_profile="admin",
    )

    assert snapshot["version"] == "semantic-test-v1"
    assert snapshot["source"] == (
        "postgres_versioned_semantic_context"
    )
    assert snapshot["allowed_schemas"] == [
        "schema_test",
    ]
    assert len(snapshot["fingerprint"]) == 64

    assert len(fake_connect.calls) == 1
    connection_call = fake_connect.calls[0]
    assert connection_call["dsn"] == (
        "postgresql://example.invalid/database"
    )
    assert connection_call["connect_timeout"] == 7
    assert connection_call["row_factory"] is dict_row

    assert fake_connect.connection.cursor_calls == 1
    assert fake_connect.cursor.executed_query == (
        LOAD_SEMANTIC_CONTEXT_SQL
    )
    assert fake_connect.cursor.executed_parameters == {
        "agent_version": "semantic-test-v1",
    }

    assert "%(agent_version)s" in LOAD_SEMANTIC_CONTEXT_SQL
    assert "semantic-test-v1" not in LOAD_SEMANTIC_CONTEXT_SQL


def test_rejeita_consulta_sem_resultado() -> None:
    fake_connect = FakeConnect(row=None)
    repository = _repository(fake_connect)

    try:
        repository.load_active_context(
            user_profile="admin",
        )
    except ContextRepositoryError as error:
        assert str(error) == (
            "A consulta de contexto não retornou um snapshot."
        )
    else:
        raise AssertionError(
            "Era esperado ContextRepositoryError."
        )


def test_rejeita_snapshot_fisico_invalido() -> None:
    invalid_snapshot = _physical_snapshot()
    invalid_snapshot["regras"] = {
        "rule_name": "not_a_list",
    }

    fake_connect = FakeConnect(row=invalid_snapshot)
    repository = _repository(fake_connect)

    try:
        repository.load_active_context(
            user_profile="admin",
        )
    except ContextRepositoryError as error:
        assert str(error) == (
            "O PostgreSQL retornou um snapshot semântico inválido."
        )
        assert error.__cause__ is not None
    else:
        raise AssertionError(
            "Era esperado ContextRepositoryError."
        )


def test_converte_erro_do_driver_sem_expor_dsn() -> None:
    fake_connect = FakeConnect(
        error=psycopg.OperationalError(
            "simulated database failure"
        )
    )
    repository = _repository(fake_connect)

    try:
        repository.load_active_context(
            user_profile="admin",
        )
    except ContextRepositoryError as error:
        message = str(error)
        assert message == (
            "Falha ao consultar o contexto semântico no PostgreSQL."
        )
        assert "example.invalid" not in message
        assert error.__cause__ is not None
    else:
        raise AssertionError(
            "Era esperado ContextRepositoryError."
        )


def test_valida_configuracao_do_adapter() -> None:
    invalid_cases = [
        {
            "dsn": " ",
            "semantic_agent_version": "version",
            "connect_timeout_seconds": 10,
            "expected": "dsn não pode estar vazio.",
        },
        {
            "dsn": "postgresql://example.invalid/database",
            "semantic_agent_version": " ",
            "connect_timeout_seconds": 10,
            "expected": (
                "semantic_agent_version não pode estar vazio."
            ),
        },
        {
            "dsn": "postgresql://example.invalid/database",
            "semantic_agent_version": "version",
            "connect_timeout_seconds": 0,
            "expected": (
                "connect_timeout_seconds deve ser um inteiro positivo."
            ),
        },
    ]

    for case in invalid_cases:
        try:
            PostgresContextRepository(
                dsn=case["dsn"],
                semantic_agent_version=(
                    case["semantic_agent_version"]
                ),
                connect_timeout_seconds=(
                    case["connect_timeout_seconds"]
                ),
            )
        except ValueError as error:
            assert str(error) == case["expected"]
        else:
            raise AssertionError(
                "Era esperado ValueError."
            )


def main() -> None:
    tests = [
        (
            "carrega snapshot com query parametrizada",
            test_carrega_snapshot_com_query_parametrizada,
        ),
        (
            "rejeita consulta sem resultado",
            test_rejeita_consulta_sem_resultado,
        ),
        (
            "rejeita snapshot físico inválido",
            test_rejeita_snapshot_fisico_invalido,
        ),
        (
            "converte erro do driver sem expor DSN",
            test_converte_erro_do_driver_sem_expor_dsn,
        ),
        (
            "valida configuração do adapter",
            test_valida_configuracao_do_adapter,
        ),
    ]

    for index, (name, test_function) in enumerate(
        tests,
        start=1,
    ):
        test_function()
        print(f"TESTE {index} — {name}: OK")


if __name__ == "__main__":
    main()

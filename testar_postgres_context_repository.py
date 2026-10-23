from __future__ import annotations

from copy import deepcopy
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.adapters.postgres.context_repository import (
    LOAD_SEMANTIC_CONTEXT_SQL,
    LOAD_SEMANTIC_CONTEXT_SQL_TEMPLATE,
    PostgresContextRepository,
    render_versioned_context_sql,
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


def _repository(
    fake_connect: FakeConnect,
    *,
    context_schema: str = "public",
) -> PostgresContextRepository:
    return PostgresContextRepository(
        dsn="postgresql://example.invalid/database",
        semantic_agent_version="semantic-test-v1",
        context_schema=context_schema,
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

    assert LOAD_SEMANTIC_CONTEXT_SQL_TEMPLATE.format(
        context_schema="public"
    ) == LOAD_SEMANTIC_CONTEXT_SQL
    assert "%(agent_version)s" in LOAD_SEMANTIC_CONTEXT_SQL
    assert "semantic-test-v1" not in LOAD_SEMANTIC_CONTEXT_SQL


def test_schema_padrao_preserva_public() -> None:
    fake_connect = FakeConnect(row=_physical_snapshot())
    repository = _repository(fake_connect)

    repository.load_active_context(user_profile="admin")

    query = fake_connect.cursor.executed_query
    assert query is not None
    assert "public.ai_ducklake_agent_rules" in query
    assert "public.ai_ducklake_entity_aliases" in query
    assert "public.ai_ducklake_dre_mapping" in query
    assert "public.ai_ducklake_sql_patterns" in query
    assert "public.ai_ducklake_table_catalog" in query


def test_schema_configurado_aplica_nas_cinco_tabelas() -> None:
    fake_connect = FakeConnect(row=_physical_snapshot())
    repository = _repository(
        fake_connect,
        context_schema="semantic_context",
    )

    repository.load_active_context(user_profile="admin")

    query = fake_connect.cursor.executed_query
    assert query is not None
    expected_tables = [
        "ai_ducklake_agent_rules",
        "ai_ducklake_entity_aliases",
        "ai_ducklake_dre_mapping",
        "ai_ducklake_sql_patterns",
        "ai_ducklake_table_catalog",
    ]
    for table_name in expected_tables:
        assert f"semantic_context.{table_name}" in query
        assert f"public.{table_name}" not in query

    assert query.count("semantic_context.ai_ducklake_") == 5
    assert "%(agent_version)s" in query
    assert "semantic-test-v1" not in query
    assert fake_connect.cursor.executed_parameters == {
        "agent_version": "semantic-test-v1",
    }


def test_schema_configurado_nao_acessa_benchmark() -> None:
    fake_connect = FakeConnect(row=_physical_snapshot())
    repository = _repository(
        fake_connect,
        context_schema="semantic_context",
    )

    repository.load_active_context(user_profile="admin")

    query = fake_connect.cursor.executed_query
    assert query is not None
    assert "benchmark" not in query.casefold()


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
        {
            "dsn": "postgresql://example.invalid/database",
            "semantic_agent_version": "version",
            "context_schema": "public.foo",
            "connect_timeout_seconds": 10,
            "expected": (
                "context_schema deve ser um identificador PostgreSQL simples."
            ),
        },
        {
            "dsn": "postgresql://example.invalid/database",
            "semantic_agent_version": "version",
            "context_schema": "public;drop table x",
            "connect_timeout_seconds": 10,
            "expected": (
                "context_schema deve ser um identificador PostgreSQL simples."
            ),
        },
        {
            "dsn": "postgresql://example.invalid/database",
            "semantic_agent_version": "version",
            "context_schema": '"public schema"',
            "connect_timeout_seconds": 10,
            "expected": (
                "context_schema deve ser um identificador PostgreSQL simples."
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
                context_schema=case.get("context_schema", "public"),
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


def test_portabilidade_contextos_fisicamente_distintos() -> None:
    """Same adapter process with independent source schema and catalog names."""
    first_connection = FakeConnect(row=_physical_snapshot())
    first = _repository(first_connection)
    first_context = first.load_active_context(user_profile="user")
    assert first_context["allowed_schemas"] == ["schema_test"]

    other = _physical_snapshot()
    other["catalogo"][0]["table_name"] = "facts_other"
    other["catalogo"][0]["schema_name"] = "other_data"
    other["catalogo"][0]["key_columns"] = ["other_key"]
    other["catalogo"][0]["primary_key"] = ["other_key"]
    other["catalogo"][0]["metric_columns"] = ["other_amount"]
    other["padroes"][0]["required_tables"] = ["other_data.facts_other"]
    alternate_connection = FakeConnect(row=other)
    second = PostgresContextRepository(
        dsn="postgresql://another.invalid/context",
        semantic_agent_version="semantic-test-v1",
        context_schema="another_context",
        catalog_tables={
            "rules": "versioned_rules",
            "entities": "versioned_entities",
            "dre": None,
            "patterns": "versioned_patterns",
            "catalog": "versioned_catalog",
        },
        connect=alternate_connection,
    )
    second_context = second.load_active_context(user_profile="user")

    assert second_context["version"] == first_context["version"]
    assert second_context["allowed_schemas"] == ["other_data"]
    assert second_context["fingerprint"] != first_context["fingerprint"]
    compiled = alternate_connection.cursor.executed_query
    assert compiled is not None
    for relation in (
        "another_context.versioned_rules",
        "another_context.versioned_entities",
        "another_context.versioned_patterns",
        "another_context.versioned_catalog",
    ):
        assert relation in compiled
    assert "another_context.ai_ducklake" not in compiled
    assert "ai_ducklake_dre_mapping" not in compiled
    assert "WHERE FALSE" in compiled
    assert "NULL::text AS dre_code" in compiled
    assert "benchmark" not in compiled.casefold()
    assert alternate_connection.cursor.executed_parameters == {
        "agent_version": "semantic-test-v1",
    }


def test_rejeita_catalogos_injetados_ou_ausentes() -> None:
    for config in (
        {"rules": "other_schema.rules"},
        {"rules": "rules; DROP TABLE catalog"},
        {"dre": "public.dre"},
        {"dre": " "},
        {"rules": None},
        {"patterns": None},
        {"catalog": "invalid-id"},
        {"entities": "Name With Space"},
        {"unknown_collection": "safe_name"},
        ["rules_v1"],
    ):
        try:
            render_versioned_context_sql(
                context_schema="tenant_context",
                catalog_tables=config,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("An unsafe or unknown source should be rejected")

    for schema in ("tenant.context", "tenant;DROP", " ", "data\\schema"):
        try:
            render_versioned_context_sql(context_schema=schema)
        except ValueError:
            pass
        else:
            raise AssertionError("An invalid schema must be rejected")

    # The optional collection can be omitted explicitly but must not be
    # emulated with a made-up financial mapping or default fallback.
    safe = render_versioned_context_sql(
        context_schema="tenant_context",
        catalog_tables={"dre": None},
    )
    assert "ai_ducklake_dre_mapping" not in safe
    assert "WHERE FALSE" in safe
    assert "tenant_context.ai_ducklake_agent_rules" in safe


def test_fingerprint_pin_allows_only_attested_semantic_content() -> None:
    from app.domain.context_normalizer import normalize_context_snapshot

    raw = _physical_snapshot()
    expected = normalize_context_snapshot(raw)["fingerprint"]
    connection = FakeConnect(row=raw)
    repo = PostgresContextRepository(
        dsn="postgresql://one.invalid/context",
        semantic_agent_version="semantic-test-v1",
        connect=connection,
        expected_context_fingerprint=expected,
    )
    loaded = repo.load_active_context(user_profile="audit")
    assert loaded["fingerprint"] == expected

    # Version identity alone is insufficient: any meaning-changing edit
    # from the same schema/version must be rejected before downstream
    # semantic resolution or a generator could observe the changed rules.
    drifted = deepcopy(raw)
    drifted["entidades"][0]["user_term"] = "unexpected-different-intent-signal"
    bad_connector = FakeConnect(row=drifted)
    drifted_repo = PostgresContextRepository(
        dsn="postgresql://other.invalid/context",
        semantic_agent_version="semantic-test-v1",
        connect=bad_connector,
        expected_context_fingerprint=expected,
    )
    try:
        drifted_repo.load_active_context(user_profile="audit")
    except ContextRepositoryError as error:
        assert "fingerprint" in str(error).lower()
        assert expected not in str(error)
        assert "unexpected-different-intent-signal" not in str(error)
        assert "postgresql://" not in str(error)
    else:
        raise AssertionError("Semantic drift with same version must fail")

    try:
        PostgresContextRepository(
            dsn="postgresql://fake.invalid/ctx",
            semantic_agent_version="semantic-test-v1",
            connect=FakeConnect(row=raw),
            expected_context_fingerprint="invalid-SQL;DROP",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid fingerprint pin must fail at construction")


def main() -> None:
    tests = [
        (
            "carrega snapshot com query parametrizada",
            test_carrega_snapshot_com_query_parametrizada,
        ),
        (
            "schema padrão preserva public",
            test_schema_padrao_preserva_public,
        ),
        (
            "schema configurado aplica nas cinco tabelas",
            test_schema_configurado_aplica_nas_cinco_tabelas,
        ),
        (
            "schema configurado não acessa benchmark",
            test_schema_configurado_nao_acessa_benchmark,
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
        (
            "carrega dois contextos materialmente distintos",
            test_portabilidade_contextos_fisicamente_distintos,
        ),
        (
            "rejeita fontes de catálogo inválidas e DRE ausente",
            test_rejeita_catalogos_injetados_ou_ausentes,
        ),
        ("pin imutável contra drift semântico", test_fingerprint_pin_allows_only_attested_semantic_content),
    ]

    for index, (name, test_function) in enumerate(
        tests,
        start=1,
    ):
        test_function()
        print(f"TESTE {index} — {name}: OK")


if __name__ == "__main__":
    main()

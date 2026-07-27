from copy import deepcopy
from pprint import pprint
from typing import Callable

from app.domain.context import ContextSnapshot
from app.domain.context_normalizer import normalize_context_snapshot
from app.graph.builder import create_graph
from app.graph.state import GraphState
from app.ports.context_repository import (
    ContextRepositoryError,
)


def _raw_context_snapshot() -> dict:
    """
    Fixture física genérica usada somente nos testes locais.
    """

    return {
        "semantic_agent_version": "context-test-v3",
        "semantic_context_source": (
            "postgres_versioned_semantic_context"
        ),
        "regras": [
            {
                "rule_group": "configuration",
                "rule_name": "intent_resolver_config",
                "rule_content": {
                    "component": "intent_resolver",
                    "minimum_score": 100,
                    "ambiguity_margin": 20,
                    "applied_confidence": 0.98,
                    "fallback_to_previous_intent": True,
                    "token_fallback": {
                        "enabled": False,
                    },
                },
                "applies_to_intents": [],
                "validation_hint": None,
                "severity": "info",
                "priority": 1,
            },
            {
                "rule_group": "general",
                "rule_name": "generic_test_rule",
                "rule_content": {
                    "enabled": True,
                },
                "applies_to_intents": [
                    "generic_test_intent",
                ],
                "validation_hint": None,
                "severity": "error",
                "priority": 2,
            },
        ],
        "entidades": [
            {
                "entity_type": "intent_signal",
                "user_term": "generic analysis",
                "canonical_value": "generic_test_intent",
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
                "intent_name": "generic_test_intent",
                "pattern_name": "generic_test_pattern",
                "business_question_examples": [],
                "required_tables": [
                    "schema_test.table_test",
                ],
                "required_rules": [
                    "generic_test_rule",
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
                "description": (
                    "Tabela genérica usada somente no teste."
                ),
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


class SuccessContextRepository:
    """
    Retorna um snapshot canônico válido para o grafo.
    """

    def load_active_context(
        self,
        *,
        user_profile: str,
    ) -> ContextSnapshot:
        return normalize_context_snapshot(
            _raw_context_snapshot()
        )


class InvalidContextRepository:
    """
    Retorna um snapshot canônico estruturalmente inválido.
    """

    def load_active_context(
        self,
        *,
        user_profile: str,
    ) -> ContextSnapshot:
        context = normalize_context_snapshot(
            _raw_context_snapshot()
        )
        invalid_context = deepcopy(context)
        invalid_context["table_catalog"] = []
        invalid_context["tables"] = []
        invalid_context["allowed_schemas"] = []
        invalid_context["counts"]["table_catalog"] = 0
        return invalid_context


class FailureContextRepository:
    """
    Simula falha conhecida ao acessar a fonte de contexto.
    """

    def load_active_context(
        self,
        *,
        user_profile: str,
    ) -> ContextSnapshot:
        raise ContextRepositoryError(
            "Falha simulada ao carregar o contexto."
        )


class ShouldNotBeCalledRepository:
    """
    Confirma que entrada inválida não carrega contexto.
    """

    def load_active_context(
        self,
        *,
        user_profile: str,
    ) -> ContextSnapshot:
        raise AssertionError(
            "O repositório não deveria ser chamado."
        )


def run_test(
    title: str,
    repository,
    initial_state: GraphState,
    assertion: Callable[[GraphState], None],
) -> None:
    print("=" * 70)
    print(title)
    print("=" * 70)

    graph = create_graph(repository)

    result = graph.invoke(
        initial_state,
        config={
            "recursion_limit": 10,
        },
    )

    pprint(
        result,
        sort_dicts=False,
    )

    assertion(result)

    print("ASSERTIONS: OK")
    print()


def _assert_valid_context(result: GraphState) -> None:
    assert result["final_status"] == "processing"
    assert (
        result["current_stage"]
        == "ready_for_classify_intent"
    )
    assert result["failure_stage"] == ""
    assert result["context_version"] == "context-test-v3"
    assert result["errors"] == []
    assert result["warnings"] == []

    context = result["context"]
    assert len(context["fingerprint"]) == 64
    assert context["allowed_schemas"] == [
        "schema_test",
    ]
    assert context["table_catalog"][0]["table_name"] == (
        "table_test"
    )
    assert context["intent_resolution"]["config"][
        "ambiguity_margin"
    ] == 20.0


def _assert_invalid_context(result: GraphState) -> None:
    assert result["final_status"] == "infrastructure_error"
    assert (
        result["current_stage"]
        == "finalize_infrastructure_error"
    )
    assert result["failure_stage"] == "load_context"

    error_codes = {
        error["code"]
        for error in result["errors"]
    }
    assert "TABLE_CATALOG_EMPTY" in error_codes


def _assert_repository_failure(result: GraphState) -> None:
    assert result["final_status"] == "infrastructure_error"
    assert (
        result["current_stage"]
        == "finalize_infrastructure_error"
    )
    assert result["failure_stage"] == "load_context"

    error_codes = {
        error["code"]
        for error in result["errors"]
    }
    assert "CONTEXT_LOAD_FAILED" in error_codes


def _assert_invalid_input(result: GraphState) -> None:
    assert result["final_status"] == "invalid_request"
    assert (
        result["current_stage"]
        == "finalize_invalid_request"
    )
    assert result["failure_stage"] == "receive_question"

    error_codes = {
        error["code"]
        for error in result["errors"]
    }
    assert "EMPTY_QUESTION" in error_codes


def main() -> None:
    valid_initial_state: GraphState = {
        "question": "Execute uma consulta genérica de teste.",
        "user": {
            "id": "usuario-1",
            "email": "admin@local.com",
            "profile": "admin",
        },
        "options": {
            "use_cache": False,
            "max_repair_attempts": 2,
            "shadow_mode": False,
        },
    }

    run_test(
        "TESTE 1 — CONTEXTO CANÔNICO VÁLIDO",
        SuccessContextRepository(),
        valid_initial_state,
        _assert_valid_context,
    )

    run_test(
        "TESTE 2 — CONTEXTO CANÔNICO INVÁLIDO",
        InvalidContextRepository(),
        valid_initial_state,
        _assert_invalid_context,
    )

    run_test(
        "TESTE 3 — FALHA AO CARREGAR CONTEXTO",
        FailureContextRepository(),
        valid_initial_state,
        _assert_repository_failure,
    )

    run_test(
        "TESTE 4 — ENTRADA INVÁLIDA NÃO ACESSA CONTEXTO",
        ShouldNotBeCalledRepository(),
        {
            "question": "   ",
            "options": {
                "max_repair_attempts": 2,
            },
        },
        _assert_invalid_input,
    )


if __name__ == "__main__":
    main()

from copy import deepcopy
from pprint import pprint
from typing import Callable

from app.adapters.testing.fake_engine_preflight import FakeEnginePreflight
from app.adapters.testing.fake_sql_repairer import FakeSqlRepairer
from app.domain.context import ContextSnapshot
from app.domain.context_normalizer import normalize_context_snapshot
from app.graph.builder import create_graph
from app.graph.routing import (
    route_after_build_plan,
    route_after_classify_intent,
    route_after_contract_gate,
    route_after_engine_preflight,
    route_after_generate_sql,
    route_after_repair_sql,
    route_after_security_gate,
)
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


def _catalog_only_raw_context_snapshot() -> dict:
    """
    Fixture em que a intenção é resolvida sem sinal simples.
    """

    snapshot = deepcopy(_raw_context_snapshot())
    snapshot["entidades"] = [
        {
            "entity_type": "intent_definition",
            "user_term": "generic_catalog_definition",
            "canonical_value": "generic_test_intent",
            "target_table": None,
            "target_column": None,
            "sql_filter_hint": None,
            "business_rule": {
                "intent_catalog": {
                    "semantic_description": (
                        "Definição semântica genérica usada "
                        "somente no teste."
                    ),
                    "rules": [
                        {
                            "rule_name": (
                                "generic_catalog_score"
                            ),
                            "effect": "positive_score",
                            "concepts": [
                                {
                                    "concept_name": (
                                        "generic_subject"
                                    ),
                                    "terms": [
                                        "generic analysis",
                                    ],
                                    "match_mode": "contains",
                                    "minimum_term_matches": 1,
                                }
                            ],
                            "minimum_concept_matches": 1,
                            "score": 120,
                            "priority": 1,
                        }
                    ],
                }
            },
            "priority": 1,
        }
    ]
    snapshot["context_counts"]["entidades"] = 1
    return snapshot


class SuccessContextRepository:
    """
    Retorna um snapshot canônico válido para o grafo.
    """

    def load_active_context(
        self,
        *,
        user_profile: str,
    ) -> ContextSnapshot:
        del user_profile
        return normalize_context_snapshot(
            _raw_context_snapshot()
        )


class CatalogOnlyContextRepository:
    """
    Retorna contexto cuja intenção depende apenas do catálogo.
    """

    def load_active_context(
        self,
        *,
        user_profile: str,
    ) -> ContextSnapshot:
        del user_profile
        return normalize_context_snapshot(
            _catalog_only_raw_context_snapshot()
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
        del user_profile
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
        del user_profile
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
        del user_profile
        raise AssertionError(
            "O repositório não deveria ser chamado."
        )


class FakeSqlGenerator:
    def __init__(
        self,
        output_text: str = (
            "SELECT id FROM schema_test.table_test"
        ),
    ) -> None:
        self.output_text = output_text
        self.calls = 0
        self.last_request = None

    def generate(self, request):
        self.calls += 1
        self.last_request = deepcopy(request)
        assert "context" not in request
        return {
            "provider_name": "fake_sql_generator",
            "output_text": self.output_text,
            "duration_ms": 1,
        }


def run_test(
    title: str,
    repository,
    initial_state: GraphState,
    assertion: Callable[[GraphState], None],
    *,
    sql_generator: FakeSqlGenerator | None = None,
    engine_preflight: FakeEnginePreflight | None = None,
    sql_repairer: FakeSqlRepairer | None = None,
) -> GraphState:
    print("=" * 70)
    print(title)
    print("=" * 70)

    generator = sql_generator or FakeSqlGenerator()
    preflight = engine_preflight or FakeEnginePreflight()
    repairer = sql_repairer or FakeSqlRepairer()
    graph = create_graph(repository, generator, preflight, repairer)

    result = graph.invoke(
        initial_state,
        config={
            "recursion_limit": 20,
        },
    )

    pprint(
        result,
        sort_dicts=False,
    )

    assertion(result)

    print("ASSERTIONS: OK")
    print()
    return result


def _assert_classified_intent(
    result: GraphState,
) -> None:
    assert result["final_status"] == "processing"
    assert result["current_stage"] == "engine_preflight"
    assert result["failure_stage"] == ""
    assert result["context_version"] == "context-test-v3"
    assert result["intent"] == "generic_test_intent"
    assert result["intent_confidence"] == 0.98
    assert result["query_plan"]["intent_name"] == "generic_test_intent"
    assert result["query_plan"]["selected_pattern"]["pattern_name"] == (
        "generic_test_pattern"
    )
    assert result["query_plan"]["planning_context"][
        "required_tables"
    ][0]["qualified_name"] == "schema_test.table_test"
    assert result["generated_sql"] == (
        "SELECT id FROM schema_test.table_test"
    )
    assert result["current_sql"] == result["generated_sql"]
    assert result["sql_generation_result"]["status"] == "generated"
    assert result["security_result"]["status"] == "approved"
    assert result["contract_result"]["status"] == "approved"
    assert result["engine_preflight_result"]["status"] == "approved"
    assert result["engine_preflight_result"]["executed"] is False
    assert result["sql_analysis"]["statement_type"] == "select"
    assert result["errors"] == []
    assert result["warnings"] == []

    resolution = result["intent_resolution_result"]
    assert resolution["applied"] is True
    assert resolution["reason"] == (
        "configured_intent_selected"
    )
    assert resolution["best_candidate"] is not None
    assert resolution["best_candidate"][
        "intent_name"
    ] == "generic_test_intent"
    assert resolution["intent_catalog"][
        "available"
    ] is False

    context = result["context"]
    assert len(context["fingerprint"]) == 64
    assert context["allowed_schemas"] == [
        "schema_test",
    ]
    assert context["table_catalog"][0]["table_name"] == (
        "table_test"
    )


def _assert_catalog_only_classification(
    result: GraphState,
) -> None:
    assert result["final_status"] == "processing"
    assert result["current_stage"] == "engine_preflight"
    assert result["failure_stage"] == ""
    assert result["intent"] == "generic_test_intent"
    assert result["intent_confidence"] == 0.98
    assert result["query_plan"]["intent_name"] == "generic_test_intent"
    assert result["generated_sql"] == (
        "SELECT id FROM schema_test.table_test"
    )
    assert result["current_sql"] == result["generated_sql"]
    assert result["security_result"]["status"] == "approved"
    assert result["contract_result"]["status"] == "approved"
    assert result["engine_preflight_result"]["status"] == "approved"
    assert result["errors"] == []

    context = result["context"]
    intent_resolution = context["intent_resolution"]
    assert intent_resolution["signals"] == []
    assert len(intent_resolution["intent_catalog"]) == 1
    assert "generic_catalog_definition" not in (
        context["aliases"]
    )

    resolution = result["intent_resolution_result"]
    diagnostic = resolution["intent_catalog"]
    assert resolution["applied"] is True
    assert diagnostic["available"] is True
    assert diagnostic["entries_evaluated"] == 1
    assert diagnostic["used_for_selected_intent"] is True
    assert diagnostic[
        "contributed_score_to_selected_intent"
    ] is True
    assert diagnostic["evaluations"][0]["eligible"] is True
    assert resolution["best_candidate"] is not None
    assert resolution["best_candidate"]["matches"][0][
        "match_strategy"
    ] == "intent_catalog_rule"


def _assert_unresolved_intent(
    result: GraphState,
) -> None:
    assert result["final_status"] == "rejected"
    assert result["current_stage"] == "classify_intent"
    assert result["failure_stage"] == "classify_intent"
    assert result["intent"] is None
    assert result["intent_confidence"] is None

    resolution = result["intent_resolution_result"]
    assert resolution["applied"] is False
    assert resolution["reason"] == (
        "minimum_score_not_reached"
    )

    error_codes = {
        error["code"]
        for error in result["errors"]
    }
    assert (
        "INTENT_RESOLUTION_MINIMUM_SCORE_NOT_REACHED"
        in error_codes
    )


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


def _assert_generate_sql_rejected(result: GraphState) -> None:
    assert result["final_status"] == "rejected"
    assert result["current_stage"] == "generate_sql"
    assert result["failure_stage"] == "generate_sql"
    assert result["sql_generation_result"]["status"] == "rejected"
    assert result["security_result"]["status"] == "not_run"
    assert result["contract_result"]["status"] == "not_run"
    assert result["engine_preflight_result"]["status"] == "not_run"


def _assert_security_rejected(result: GraphState) -> None:
    assert result["final_status"] == "rejected"
    assert result["current_stage"] == "security_gate"
    assert result["failure_stage"] == "security_gate"
    assert result["security_result"]["status"] == "rejected"
    assert result["contract_result"]["status"] == "not_run"
    assert result["engine_preflight_result"]["status"] == "not_run"


def _assert_contract_rejected(result: GraphState) -> None:
    assert result["final_status"] == "rejected"
    assert result["current_stage"] == "contract_gate"
    assert result["failure_stage"] == "contract_gate"
    assert result["security_result"]["status"] == "approved"
    assert result["contract_result"]["status"] == "rejected"
    assert result["engine_preflight_result"]["status"] == "not_run"


def _assert_engine_preflight_rejected(result: GraphState) -> None:
    assert result["final_status"] == "rejected"
    assert result["current_stage"] == "engine_preflight"
    assert result["failure_stage"] == "engine_preflight"
    assert result["security_result"]["status"] == "approved"
    assert result["contract_result"]["status"] == "approved"
    assert result["engine_preflight_result"]["status"] == "rejected"
    assert result["errors"][0]["code"] == (
        "ENGINE_PREFLIGHT_COLUMN_NOT_FOUND"
    )


def _assert_repair_loop_success(result: GraphState) -> None:
    assert result["final_status"] == "processing"
    assert result["current_stage"] == "engine_preflight"
    assert result["failure_stage"] == ""
    assert result["generated_sql"] == (
        "SELECT id FROM schema_test.table_test"
    )
    assert result["current_sql"] == (
        "SELECT value FROM schema_test.table_test"
    )
    assert result["repair_attempts"] == 1
    assert len(result["repair_history"]) == 1
    assert result["repair_history"][0]["repair_applied"] is True
    assert "sql_before_fingerprint" in result["repair_history"][0]
    assert "sql_after_fingerprint" in result["repair_history"][0]
    assert "SELECT missing_column" not in repr(result["repair_history"])
    assert result["security_result"]["status"] == "approved"
    assert result["contract_result"]["status"] == "approved"
    assert result["engine_preflight_result"]["status"] == "approved"


def _assert_repair_limit_reached(result: GraphState) -> None:
    assert result["final_status"] == "rejected"
    assert result["current_stage"] == "repair_sql"
    assert result["failure_stage"] == "repair_sql"
    assert result["errors"][-1]["code"] == "SQL_REPAIR_LIMIT_REACHED"
    assert result["repair_attempts"] == 1
    assert len(result["repair_history"]) == 1


def _assert_repaired_sql_security_rejected(result: GraphState) -> None:
    assert result["final_status"] == "rejected"
    assert result["current_stage"] == "security_gate"
    assert result["failure_stage"] == "security_gate"
    assert result["generated_sql"] == (
        "SELECT id FROM schema_test.table_test"
    )
    assert result["current_sql"] == (
        "SELECT id FROM schema_test.table_other"
    )
    assert result["repair_attempts"] == 1
    assert len(result["repair_history"]) == 1
    assert result["engine_preflight_result"]["status"] == "not_run"


def _assert_repaired_sql_contract_rejected(result: GraphState) -> None:
    assert result["final_status"] == "rejected"
    assert result["current_stage"] == "contract_gate"
    assert result["failure_stage"] == "contract_gate"
    assert result["generated_sql"] == (
        "SELECT id FROM schema_test.table_test"
    )
    assert result["current_sql"] == (
        "SELECT missing_column FROM schema_test.table_test"
    )
    assert result["repair_attempts"] == 1
    assert len(result["repair_history"]) == 1
    assert result["security_result"]["status"] == "approved"
    assert result["contract_result"]["status"] == "rejected"
    assert result["engine_preflight_result"]["status"] == "not_run"


def _assert_engine_preflight_infra(result: GraphState) -> None:
    assert result["final_status"] == "infrastructure_error"
    assert result["current_stage"] == "finalize_infrastructure_error"
    assert result["failure_stage"] == "engine_preflight"
    assert result["engine_preflight_result"]["status"] == "error"


def test_classify_routing() -> None:
    assert route_after_classify_intent(
        {
            "final_status": "processing",
            "intent": "generic_test_intent",
        }
    ) == "build_plan"
    assert route_after_classify_intent(
        {
            "final_status": "processing",
            "intent": None,
        }
    ) == "infrastructure_error"
    assert route_after_classify_intent(
        {
            "final_status": "rejected",
        }
    ) == "complete"
    assert route_after_classify_intent(
        {
            "final_status": "infrastructure_error",
        }
    ) == "infrastructure_error"
    assert route_after_classify_intent({}) == (
        "infrastructure_error"
    )

    assert route_after_build_plan(
        {
            "final_status": "processing",
            "query_plan": {
                "intent_name": "generic_test_intent",
            },
        }
    ) == "generate_sql"
    assert route_after_build_plan(
        {
            "final_status": "rejected",
        }
    ) == "complete"
    assert route_after_build_plan(
        {
            "final_status": "infrastructure_error",
        }
    ) == "infrastructure_error"

    assert route_after_generate_sql(
        {
            "final_status": "processing",
            "generated_sql": "SELECT 1",
            "current_sql": "SELECT 1",
            "query_plan": {
                "intent_name": "generic_test_intent",
            },
        }
    ) == "security_gate"
    assert route_after_generate_sql(
        {
            "final_status": "rejected",
        }
    ) == "complete"
    assert route_after_generate_sql(
        {
            "final_status": "infrastructure_error",
        }
    ) == "infrastructure_error"

    assert route_after_security_gate(
        {
            "final_status": "processing",
            "security_result": {
                "status": "approved",
            },
        }
    ) == "contract_gate"
    assert route_after_security_gate(
        {
            "final_status": "rejected",
        }
    ) == "complete"
    assert route_after_security_gate(
        {
            "final_status": "infrastructure_error",
        }
    ) == "infrastructure_error"

    assert route_after_contract_gate(
        {
            "final_status": "processing",
            "contract_result": {
                "status": "approved",
            },
        }
    ) == "engine_preflight"
    assert route_after_contract_gate(
        {
            "final_status": "rejected",
        }
    ) == "complete"
    assert route_after_contract_gate(
        {
            "final_status": "infrastructure_error",
        }
    ) == "infrastructure_error"

    assert route_after_engine_preflight(
        {
            "final_status": "processing",
            "engine_preflight_result": {
                "status": "approved",
            },
        }
    ) == "complete"
    assert route_after_engine_preflight(
        {
            "final_status": "rejected",
            "engine_preflight_result": {
                "status": "rejected",
                "repairable": True,
            },
        }
    ) == "repair_sql"
    assert route_after_engine_preflight(
        {
            "final_status": "rejected",
            "engine_preflight_result": {
                "status": "rejected",
                "repairable": False,
            },
        }
    ) == "complete"
    assert route_after_engine_preflight(
        {
            "final_status": "infrastructure_error",
        }
    ) == "infrastructure_error"

    assert route_after_repair_sql(
        {
            "final_status": "processing",
            "current_sql": "SELECT 1",
            "query_plan": {
                "intent_name": "generic_test_intent",
            },
        }
    ) == "security_gate"
    assert route_after_repair_sql(
        {
            "final_status": "rejected",
        }
    ) == "complete"
    assert route_after_repair_sql(
        {
            "final_status": "infrastructure_error",
        }
    ) == "infrastructure_error"


def main() -> None:
    valid_initial_state: GraphState = {
        "question": "Execute uma generic analysis de teste.",
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

    unresolved_initial_state: GraphState = {
        "question": (
            "Execute uma operação sem correspondência "
            "semântica configurada."
        ),
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
        "TESTE 1 — INTENÇÃO CLASSIFICADA POR SINAL",
        SuccessContextRepository(),
        valid_initial_state,
        _assert_classified_intent,
    )

    run_test(
        "TESTE 2 — INTENÇÃO CLASSIFICADA PELO CATÁLOGO",
        CatalogOnlyContextRepository(),
        valid_initial_state,
        _assert_catalog_only_classification,
    )

    run_test(
        "TESTE 3 — INTENÇÃO NÃO RESOLVIDA",
        SuccessContextRepository(),
        unresolved_initial_state,
        _assert_unresolved_intent,
    )

    run_test(
        "TESTE 4 — CONTEXTO CANÔNICO INVÁLIDO",
        InvalidContextRepository(),
        valid_initial_state,
        _assert_invalid_context,
    )

    run_test(
        "TESTE 5 — FALHA AO CARREGAR CONTEXTO",
        FailureContextRepository(),
        valid_initial_state,
        _assert_repository_failure,
    )

    run_test(
        "TESTE 6 — ENTRADA INVÁLIDA NÃO ACESSA CONTEXTO",
        ShouldNotBeCalledRepository(),
        {
            "question": "   ",
            "options": {
                "max_repair_attempts": 2,
            },
        },
        _assert_invalid_input,
    )

    rejected_generator = FakeSqlGenerator(
        "UPDATE schema_test.table_test SET id = 1"
    )
    should_not_preflight_1 = FakeEnginePreflight()
    run_test(
        "TESTE 7 — GERAÇÃO SQL REJEITADA NÃO CHAMA SECURITY",
        SuccessContextRepository(),
        valid_initial_state,
        _assert_generate_sql_rejected,
        sql_generator=rejected_generator,
        engine_preflight=should_not_preflight_1,
    )
    assert rejected_generator.calls == 1
    assert should_not_preflight_1.calls == 0

    security_generator = FakeSqlGenerator(
        "SELECT id FROM schema_test.table_other"
    )
    should_not_preflight_2 = FakeEnginePreflight()
    run_test(
        "TESTE 8 — SECURITY REJEITADO NÃO CHAMA CONTRACT",
        SuccessContextRepository(),
        valid_initial_state,
        _assert_security_rejected,
        sql_generator=security_generator,
        engine_preflight=should_not_preflight_2,
    )
    assert security_generator.calls == 1
    assert should_not_preflight_2.calls == 0

    contract_generator = FakeSqlGenerator(
        "SELECT missing_column FROM schema_test.table_test"
    )
    should_not_preflight_3 = FakeEnginePreflight()
    run_test(
        "TESTE 9 — CONTRACT REJEITADO ENCERRA REJECTED",
        SuccessContextRepository(),
        valid_initial_state,
        _assert_contract_rejected,
        sql_generator=contract_generator,
        engine_preflight=should_not_preflight_3,
    )
    assert contract_generator.calls == 1
    assert should_not_preflight_3.calls == 0

    rejected_preflight = FakeEnginePreflight(
        status="rejected",
        failure_category="column_not_found",
        message="column not found",
        repairable=False,
    )
    run_test(
        "TESTE 10 - PREFLIGHT SQL INVALIDO ENCERRA REJECTED",
        SuccessContextRepository(),
        valid_initial_state,
        _assert_engine_preflight_rejected,
        engine_preflight=rejected_preflight,
    )
    assert rejected_preflight.calls == 1

    repairable_then_approved = FakeEnginePreflight(
        responses=[
            {
                "status": "rejected",
                "provider_name": "fake_engine_preflight",
                "failure_category": "column_not_found",
                "message": "column not found",
                "repairable": True,
                "executed": False,
                "rows_returned": 0,
            },
            {
                "status": "approved",
                "provider_name": "fake_engine_preflight",
                "duration_ms": 1,
                "statement_planned": True,
                "executed": False,
                "rows_returned": 0,
            },
        ]
    )
    successful_repairer = FakeSqlRepairer(
        responses=["SELECT value FROM schema_test.table_test"]
    )
    success_result = run_test(
        "TESTE 11 - PREFLIGHT REPARAVEL VOLTA AOS GATES",
        SuccessContextRepository(),
        valid_initial_state,
        _assert_repair_loop_success,
        engine_preflight=repairable_then_approved,
        sql_repairer=successful_repairer,
    )
    assert success_result["repair_attempts"] == 1
    assert repairable_then_approved.calls == 2
    assert successful_repairer.calls == 1

    limit_preflight = FakeEnginePreflight(
        responses=[
            {
                "status": "rejected",
                "provider_name": "fake_engine_preflight",
                "failure_category": "column_not_found",
                "message": "column not found",
                "repairable": True,
                "executed": False,
                "rows_returned": 0,
            },
            {
                "status": "rejected",
                "provider_name": "fake_engine_preflight",
                "failure_category": "column_not_found",
                "message": "column not found again",
                "repairable": True,
                "executed": False,
                "rows_returned": 0,
            },
        ]
    )
    one_attempt_state = deepcopy(valid_initial_state)
    one_attempt_state["options"] = {
        "use_cache": False,
        "max_repair_attempts": 1,
        "shadow_mode": False,
    }
    limit_repairer = FakeSqlRepairer(
        responses=["SELECT value FROM schema_test.table_test"]
    )
    run_test(
        "TESTE 12 - LIMITE DE REPARO ENCERRA REJECTED",
        SuccessContextRepository(),
        one_attempt_state,
        _assert_repair_limit_reached,
        engine_preflight=limit_preflight,
        sql_repairer=limit_repairer,
    )
    assert limit_preflight.calls == 2
    assert limit_repairer.calls == 1

    security_after_repair_preflight = FakeEnginePreflight(
        responses=[
            {
                "status": "rejected",
                "provider_name": "fake_engine_preflight",
                "failure_category": "column_not_found",
                "message": "column not found",
                "repairable": True,
                "executed": False,
                "rows_returned": 0,
            },
        ]
    )
    security_bad_repairer = FakeSqlRepairer(
        responses=["SELECT id FROM schema_test.table_other"]
    )
    run_test(
        "TESTE 13 - SECURITY REJEITA SQL REPARADA",
        SuccessContextRepository(),
        valid_initial_state,
        _assert_repaired_sql_security_rejected,
        engine_preflight=security_after_repair_preflight,
        sql_repairer=security_bad_repairer,
    )
    assert security_after_repair_preflight.calls == 1
    assert security_bad_repairer.calls == 1

    contract_after_repair_preflight = FakeEnginePreflight(
        responses=[
            {
                "status": "rejected",
                "provider_name": "fake_engine_preflight",
                "failure_category": "column_not_found",
                "message": "column not found",
                "repairable": True,
                "executed": False,
                "rows_returned": 0,
            },
        ]
    )
    contract_bad_repairer = FakeSqlRepairer(
        responses=["SELECT missing_column FROM schema_test.table_test"]
    )
    run_test(
        "TESTE 14 - CONTRACT REJEITA SQL REPARADA",
        SuccessContextRepository(),
        valid_initial_state,
        _assert_repaired_sql_contract_rejected,
        engine_preflight=contract_after_repair_preflight,
        sql_repairer=contract_bad_repairer,
    )
    assert contract_after_repair_preflight.calls == 1
    assert contract_bad_repairer.calls == 1

    infra_preflight = FakeEnginePreflight(
        status="error",
        failure_category="provider_unavailable",
        message="provider unavailable",
    )
    run_test(
        "TESTE 15 - PREFLIGHT INFRA VAI AO FINALIZADOR",
        SuccessContextRepository(),
        valid_initial_state,
        _assert_engine_preflight_infra,
        engine_preflight=infra_preflight,
    )
    assert infra_preflight.calls == 1

    print("=" * 70)
    print("TESTE 10 — ROTEAMENTO APÓS CLASSIFICAÇÃO")
    print("=" * 70)
    test_classify_routing()
    print("ASSERTIONS: OK")


if __name__ == "__main__":
    main()

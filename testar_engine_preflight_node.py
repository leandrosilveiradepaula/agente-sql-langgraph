from __future__ import annotations

from copy import deepcopy

from app.adapters.testing.fake_engine_preflight import FakeEnginePreflight
from app.domain.engine_preflight import EnginePreflightProviderError
from app.domain.planner import build_query_plan
from app.graph.nodes.engine_preflight import create_engine_preflight_node
from app.graph.state import GraphState
from testar_planner import _context


def _query_plan() -> dict:
    result = build_query_plan(
        context=_context(),
        intent_name="generic_test_intent",
        intent_confidence=0.98,
        normalized_question="generic analysis",
    )
    assert result["query_plan"] is not None
    return result["query_plan"]


def _state(**overrides) -> GraphState:
    state: GraphState = {
        "current_sql": "SELECT id FROM schema_test.table_test",
        "query_plan": _query_plan(),
        "security_result": {
            "status": "approved",
            "errors": [],
            "warnings": [],
        },
        "contract_result": {
            "status": "approved",
            "errors": [],
            "warnings": [],
        },
        "errors": [],
        "warnings": [],
        "options": {
            "max_repair_attempts": 2,
            "shadow_mode": False,
        },
    }
    state.update(overrides)
    return state


def test_sucesso() -> None:
    provider = FakeEnginePreflight()
    node = create_engine_preflight_node(provider)
    state = _state()
    original = deepcopy(state)

    result = node(state)

    assert result["final_status"] == "processing"
    assert result["current_stage"] == "engine_preflight"
    assert result["failure_stage"] == ""
    assert result["engine_preflight_result"]["status"] == "approved"
    assert result["engine_preflight_result"]["executed"] is False
    assert result["engine_preflight_result"]["rows_returned"] == 0
    assert provider.calls == 1
    assert provider.last_request is not None
    assert provider.last_request["sql"] == state["current_sql"]
    assert state == original


def test_sql_ausente() -> None:
    provider = FakeEnginePreflight()
    node = create_engine_preflight_node(provider)
    result = node(_state(current_sql=""))

    assert result["final_status"] == "infrastructure_error"
    assert result["errors"][0]["code"] == "ENGINE_PREFLIGHT_SQL_MISSING"
    assert provider.calls == 0


def test_query_plan_ausente() -> None:
    provider = FakeEnginePreflight()
    node = create_engine_preflight_node(provider)
    result = node(_state(query_plan={}))

    assert result["final_status"] == "infrastructure_error"
    assert result["errors"][0]["code"] == "ENGINE_PREFLIGHT_PLAN_MISSING"
    assert provider.calls == 0


def test_security_nao_aprovado() -> None:
    provider = FakeEnginePreflight()
    node = create_engine_preflight_node(provider)
    result = node(_state(security_result={"status": "rejected"}))

    assert result["final_status"] == "infrastructure_error"
    assert result["errors"][0]["code"] == (
        "ENGINE_PREFLIGHT_SECURITY_NOT_APPROVED"
    )
    assert provider.calls == 0


def test_contract_nao_aprovado() -> None:
    provider = FakeEnginePreflight()
    node = create_engine_preflight_node(provider)
    result = node(_state(contract_result={"status": "rejected"}))

    assert result["final_status"] == "infrastructure_error"
    assert result["errors"][0]["code"] == (
        "ENGINE_PREFLIGHT_CONTRACT_NOT_APPROVED"
    )
    assert provider.calls == 0


def test_erro_sql_reparavel_rejected() -> None:
    provider = FakeEnginePreflight(
        status="rejected",
        failure_category="column_not_found",
        message="column not found",
    )
    node = create_engine_preflight_node(provider)
    result = node(_state())

    assert result["final_status"] == "rejected"
    assert result["failure_stage"] == "engine_preflight"
    assert result["errors"][0]["repairable"] is True
    assert result["errors"][0]["code"] == (
        "ENGINE_PREFLIGHT_COLUMN_NOT_FOUND"
    )


def test_erro_sql_nao_reparavel_rejected() -> None:
    provider = FakeEnginePreflight(
        status="rejected",
        failure_category="planning_error",
        message="planner refused",
        repairable=False,
    )
    node = create_engine_preflight_node(provider)
    result = node(_state())

    assert result["final_status"] == "rejected"
    assert result["errors"][0]["repairable"] is False


def test_provider_indisponivel_infra() -> None:
    provider = FakeEnginePreflight(
        status="error",
        failure_category="provider_unavailable",
        message="provider offline",
    )
    node = create_engine_preflight_node(provider)
    result = node(_state())

    assert result["final_status"] == "infrastructure_error"
    assert result["errors"][0]["code"] == (
        "ENGINE_PREFLIGHT_PROVIDER_UNAVAILABLE"
    )


def test_timeout_infra() -> None:
    provider = FakeEnginePreflight(raises=TimeoutError("timeout"))
    node = create_engine_preflight_node(provider)
    result = node(_state())

    assert result["final_status"] == "infrastructure_error"
    assert result["errors"][0]["code"] == "ENGINE_PREFLIGHT_TIMEOUT"


def test_excecao_inesperada_infra() -> None:
    provider = FakeEnginePreflight(raises=RuntimeError("password=hidden"))
    node = create_engine_preflight_node(provider)
    result = node(_state())

    assert result["final_status"] == "infrastructure_error"
    assert result["errors"][0]["code"] == (
        "ENGINE_PREFLIGHT_UNEXPECTED_ERROR"
    )
    assert "hidden" not in repr(result)


def test_provider_error_infra() -> None:
    provider = FakeEnginePreflight(
        raises=EnginePreflightProviderError("dsn=hidden")
    )
    node = create_engine_preflight_node(provider)
    result = node(_state())

    assert result["final_status"] == "infrastructure_error"
    assert result["errors"][0]["code"] == (
        "ENGINE_PREFLIGHT_PROVIDER_FAILED"
    )
    assert "hidden" not in repr(result)


def test_request_e_diagnostico_seguros() -> None:
    provider = FakeEnginePreflight(
        status="rejected",
        failure_category="syntax_error",
        message="bad SQL near token",
    )
    node = create_engine_preflight_node(provider)
    state = _state()
    result = node(state)
    serialized_request = repr(provider.last_request).casefold()
    serialized_result = repr(result).casefold()

    assert provider.calls == 1
    assert provider.last_request is not state
    assert "intent_catalog" not in serialized_request
    assert "table_catalog" not in serialized_request
    assert "'context'" not in serialized_request
    assert state["current_sql"].casefold() not in serialized_result
    assert "password" not in serialized_result
    assert result["errors"][0]["details"]["attempt"] == 1


def main() -> None:
    tests = [
        ("sucesso", test_sucesso),
        ("SQL ausente", test_sql_ausente),
        ("QueryPlan ausente", test_query_plan_ausente),
        ("Security nao aprovado", test_security_nao_aprovado),
        ("Contract nao aprovado", test_contract_nao_aprovado),
        ("SQL reparavel", test_erro_sql_reparavel_rejected),
        ("SQL nao reparavel", test_erro_sql_nao_reparavel_rejected),
        ("provider indisponivel", test_provider_indisponivel_infra),
        ("timeout", test_timeout_infra),
        ("excecao inesperada", test_excecao_inesperada_infra),
        ("provider error", test_provider_error_infra),
        ("diagnostico seguro", test_request_e_diagnostico_seguros),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

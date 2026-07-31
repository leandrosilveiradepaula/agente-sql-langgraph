from __future__ import annotations

from copy import deepcopy

from app.adapters.testing.fake_sql_executor import FakeSqlExecutor
from app.domain.sql_execution import SqlExecutionProviderError
from app.graph.nodes.execute_sql import create_execute_sql_node
from app.graph.state import GraphState
from testar_sql_execution import SQL, _approved_inputs


def _state(**overrides) -> GraphState:
    state: GraphState = {
        **_approved_inputs(),
        "errors": [],
        "warnings": [],
    }
    state.update(overrides)
    return state


def test_execucao_autorizada() -> None:
    executor = FakeSqlExecutor()
    node = create_execute_sql_node(executor)
    state = _state()
    original = deepcopy(state)
    result = node(state)

    assert result["final_status"] == "processing"
    assert result["current_stage"] == "execute_sql"
    assert result["failure_stage"] == ""
    assert result["sql_execution_result"]["status"] == "success"
    assert executor.calls == 1
    assert state == original


def test_request_correta() -> None:
    executor = FakeSqlExecutor()
    result = create_execute_sql_node(executor)(_state())

    assert result["sql_execution_result"]["request_fingerprint"]
    assert executor.last_request is not None
    assert executor.last_request["current_sql"] == SQL
    assert "query_plan" not in executor.last_request


def test_executor_chamado_uma_vez() -> None:
    executor = FakeSqlExecutor()
    create_execute_sql_node(executor)(_state())
    assert executor.calls == 1


def test_nao_chama_sem_security() -> None:
    executor = FakeSqlExecutor()
    result = create_execute_sql_node(executor)(
        _state(security_result={"status": "rejected"})
    )
    assert result["final_status"] == "rejected"
    assert executor.calls == 0


def test_nao_chama_sem_contract() -> None:
    executor = FakeSqlExecutor()
    create_execute_sql_node(executor)(
        _state(contract_result={"status": "rejected"})
    )
    assert executor.calls == 0


def test_nao_chama_sem_preflight() -> None:
    executor = FakeSqlExecutor()
    create_execute_sql_node(executor)(
        _state(engine_preflight_result={"status": "rejected"})
    )
    assert executor.calls == 0


def test_nao_chama_capability_unavailable() -> None:
    executor = FakeSqlExecutor()
    state = _state()
    state["engine_preflight_result"] = {
        **state["engine_preflight_result"],
        "failure_category": "capability_unavailable",
    }
    create_execute_sql_node(executor)(state)
    assert executor.calls == 0


def test_nao_chama_infrastructure_error() -> None:
    executor = FakeSqlExecutor()
    state = _state(final_status="infrastructure_error")
    state["engine_preflight_result"] = {
        **state["engine_preflight_result"],
        "status": "error",
    }
    create_execute_sql_node(executor)(state)
    assert executor.calls == 0


def test_current_sql_exata() -> None:
    sql = "  SELECT id\nFROM schema_test.table_test  "
    executor = FakeSqlExecutor()
    create_execute_sql_node(executor)(_state(**_approved_inputs(sql)))
    assert executor.last_request is not None
    assert executor.last_request["current_sql"] == sql


def test_generated_sql_preservada() -> None:
    executor = FakeSqlExecutor()
    state = _state(generated_sql="SELECT original")
    create_execute_sql_node(executor)(state)
    assert state["generated_sql"] == "SELECT original"


def test_query_plan_preservado() -> None:
    executor = FakeSqlExecutor()
    state = _state()
    original_plan = deepcopy(state["query_plan"])
    create_execute_sql_node(executor)(state)
    assert state["query_plan"] == original_plan


def test_resposta_sucesso() -> None:
    result = create_execute_sql_node(FakeSqlExecutor())(_state())
    assert result["sql_execution_result"]["status"] == "success"


def test_resposta_rejeitada() -> None:
    executor = FakeSqlExecutor(
        responses=[{"status": "rejected", "message": "rejected"}]
    )
    result = create_execute_sql_node(executor)(_state())
    assert result["final_status"] == "rejected"


def test_timeout() -> None:
    executor = FakeSqlExecutor(exceptions=[TimeoutError("timeout")])
    result = create_execute_sql_node(executor)(_state())
    assert result["final_status"] == "infrastructure_error"
    assert result["errors"][0]["code"] == "SQL_EXECUTION_TIMEOUT"


def test_excecao() -> None:
    executor = FakeSqlExecutor(exceptions=[RuntimeError("token=hidden")])
    result = create_execute_sql_node(executor)(_state())
    assert result["final_status"] == "infrastructure_error"
    assert "hidden" not in repr(result)


def test_provider_error() -> None:
    executor = FakeSqlExecutor(
        exceptions=[SqlExecutionProviderError("dsn=hidden")]
    )
    result = create_execute_sql_node(executor)(_state())
    assert result["errors"][0]["code"] == "SQL_EXECUTION_PROVIDER_FAILED"
    assert "hidden" not in repr(result)


def test_limite_linhas() -> None:
    executor = FakeSqlExecutor(rows=[{"id": index} for index in range(6)])
    result = create_execute_sql_node(executor)(_state())
    assert result["errors"][0]["code"] == "SQL_EXECUTION_ROW_LIMIT_EXCEEDED"


def test_limite_bytes() -> None:
    state = _state()
    state["options"]["sql_execution_limits"]["max_response_bytes"] = 10
    result = create_execute_sql_node(FakeSqlExecutor())(state)
    assert result["errors"][0]["code"] == "SQL_EXECUTION_BYTE_LIMIT_EXCEEDED"


def test_state_nao_mutado() -> None:
    executor = FakeSqlExecutor()
    node = create_execute_sql_node(executor)
    state = _state()
    original = deepcopy(state)
    node(state)
    assert state == original


def test_resultado_anterior_nao_chama_executor() -> None:
    executor = FakeSqlExecutor()
    state = _state(
        sql_execution_result={
            "status": "success",
        }
    )
    result = create_execute_sql_node(executor)(state)
    assert result["final_status"] == "rejected"
    assert executor.calls == 0


def test_erros_sanitizados() -> None:
    executor = FakeSqlExecutor(
        responses=[
            {
                "status": "error",
                "failure_category": "provider_failed",
                "message": f"failed {SQL} password=hidden",
            }
        ]
    )
    result = create_execute_sql_node(executor)(_state())
    serialized = repr(result).casefold()
    assert SQL.casefold() not in serialized
    assert "hidden" not in serialized


def main() -> None:
    tests = [
        ("execucao autorizada", test_execucao_autorizada),
        ("request correta", test_request_correta),
        ("executor chamado uma vez", test_executor_chamado_uma_vez),
        ("nao chama sem Security", test_nao_chama_sem_security),
        ("nao chama sem Contract", test_nao_chama_sem_contract),
        ("nao chama sem Preflight", test_nao_chama_sem_preflight),
        ("nao chama capability unavailable", test_nao_chama_capability_unavailable),
        ("nao chama infrastructure_error", test_nao_chama_infrastructure_error),
        ("current_sql exata", test_current_sql_exata),
        ("generated_sql preservada", test_generated_sql_preservada),
        ("query_plan preservado", test_query_plan_preservado),
        ("resposta sucesso", test_resposta_sucesso),
        ("resposta rejeitada", test_resposta_rejeitada),
        ("timeout", test_timeout),
        ("excecao", test_excecao),
        ("provider error", test_provider_error),
        ("limite linhas", test_limite_linhas),
        ("limite bytes", test_limite_bytes),
        ("state nao mutado", test_state_nao_mutado),
        (
            "resultado anterior nao chama executor",
            test_resultado_anterior_nao_chama_executor,
        ),
        ("erros sanitizados", test_erros_sanitizados),
    ]
    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

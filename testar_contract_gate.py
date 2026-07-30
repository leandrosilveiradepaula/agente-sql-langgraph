from __future__ import annotations

from copy import deepcopy

from app.domain.planner import build_query_plan
from app.domain.sql_security import run_sql_security_gate
from app.graph.nodes.contract_gate import contract_gate
from app.graph.state import GraphState
from testar_sql_contract import _with_second_table
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


def _state(
    *,
    current_sql: str = "SELECT id FROM schema_test.table_test",
    query_plan: dict | None = None,
) -> GraphState:
    plan = query_plan if query_plan is not None else _query_plan()
    security_result, analysis = run_sql_security_gate(
        current_sql=current_sql,
        query_plan=plan,
    )
    assert security_result["status"] == "approved"
    return {
        "current_sql": current_sql,
        "query_plan": plan,
        "security_result": security_result,
        "sql_analysis": analysis,
        "errors": [],
        "warnings": [],
    }


def test_contract_gate_aprovado() -> None:
    result = contract_gate(_state())

    assert result["final_status"] == "processing"
    assert result["current_stage"] == "contract_gate"
    assert result["contract_result"]["status"] == "approved"


def test_contract_gate_rejeitado() -> None:
    result = contract_gate(
        _state(
            current_sql="SELECT id FROM schema_test.table_test",
            query_plan=_with_second_table(),
        )
    )

    assert result["final_status"] == "rejected"
    assert result["failure_stage"] == "contract_gate"
    assert result["errors"][0]["code"] == (
        "SQL_CONTRACT_REQUIRED_TABLE_MISSING"
    )


def test_contract_gate_exige_security_aprovado() -> None:
    result = contract_gate(
        {
            "current_sql": "SELECT id FROM schema_test.table_test",
            "query_plan": _query_plan(),
            "security_result": {"status": "rejected"},
            "errors": [],
        }
    )

    assert result["final_status"] == "infrastructure_error"
    assert result["errors"][0]["code"] == (
        "SQL_CONTRACT_SECURITY_NOT_APPROVED"
    )


def test_contract_gate_current_sql_ausente() -> None:
    state = _state()
    del state["current_sql"]

    result = contract_gate(state)

    assert result["final_status"] == "infrastructure_error"
    assert result["errors"][0]["code"] == "SQL_CONTRACT_INPUT_INVALID"


def test_contract_gate_query_plan_ausente() -> None:
    state = _state()
    del state["query_plan"]

    result = contract_gate(state)

    assert result["final_status"] == "infrastructure_error"
    assert result["errors"][0]["code"] == "SQL_CONTRACT_INPUT_INVALID"


def test_contract_gate_sem_mutacao_e_sem_sql_completa() -> None:
    state = _state()
    original = deepcopy(state)

    result = contract_gate(state)

    assert state == original
    assert state["current_sql"] not in repr(result["contract_result"])


def main() -> None:
    tests = [
        ("aprovado", test_contract_gate_aprovado),
        ("rejeitado", test_contract_gate_rejeitado),
        ("exige security", test_contract_gate_exige_security_aprovado),
        ("current_sql ausente", test_contract_gate_current_sql_ausente),
        ("query_plan ausente", test_contract_gate_query_plan_ausente),
        ("sem mutacao", test_contract_gate_sem_mutacao_e_sem_sql_completa),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

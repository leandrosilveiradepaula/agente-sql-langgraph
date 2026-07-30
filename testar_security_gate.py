from __future__ import annotations

from copy import deepcopy

from app.domain.planner import build_query_plan
from app.graph.nodes.security_gate import security_gate
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


def _state(
    *,
    current_sql: str = "SELECT id FROM schema_test.table_test",
    query_plan: dict | None = None,
) -> GraphState:
    return {
        "current_sql": current_sql,
        "query_plan": query_plan if query_plan is not None else _query_plan(),
        "errors": [],
        "warnings": [],
    }


def test_security_gate_aprovado() -> None:
    result = security_gate(_state())

    assert result["final_status"] == "processing"
    assert result["current_stage"] == "security_gate"
    assert result["security_result"]["status"] == "approved"
    assert result["sql_analysis"]["statement_type"] == "select"


def test_security_gate_rejeitado() -> None:
    result = security_gate(
        _state(current_sql="SELECT id FROM schema_test.table_other")
    )

    assert result["final_status"] == "rejected"
    assert result["failure_stage"] == "security_gate"
    assert result["errors"][0]["code"] == (
        "SQL_SECURITY_UNAUTHORIZED_TABLE"
    )


def test_security_gate_current_sql_ausente() -> None:
    result = security_gate(
        {
            "query_plan": _query_plan(),
            "errors": [],
        }
    )

    assert result["final_status"] == "infrastructure_error"
    assert result["errors"][0]["code"] == "SQL_SECURITY_INPUT_INVALID"


def test_security_gate_query_plan_ausente() -> None:
    result = security_gate(
        {
            "current_sql": "SELECT id FROM schema_test.table_test",
            "errors": [],
        }
    )

    assert result["final_status"] == "infrastructure_error"
    assert result["errors"][0]["code"] == "SQL_SECURITY_INPUT_INVALID"


def test_security_gate_sem_mutacao_e_sem_sql_completa() -> None:
    state = _state()
    original = deepcopy(state)

    result = security_gate(state)

    assert state == original
    assert state["current_sql"] not in repr(result["security_result"])


def main() -> None:
    tests = [
        ("aprovado", test_security_gate_aprovado),
        ("rejeitado", test_security_gate_rejeitado),
        ("current_sql ausente", test_security_gate_current_sql_ausente),
        ("query_plan ausente", test_security_gate_query_plan_ausente),
        ("sem mutacao", test_security_gate_sem_mutacao_e_sem_sql_completa),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

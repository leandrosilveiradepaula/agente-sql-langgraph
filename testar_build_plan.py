from __future__ import annotations

from copy import deepcopy

from app.graph.nodes.build_plan import build_plan
from app.graph.state import GraphState
from testar_planner import _context, _pattern


def _state(context: dict | None = None) -> GraphState:
    return {
        "question": "generic analysis",
        "normalized_question": "generic analysis",
        "context": _context() if context is None else context,
        "context_version": "context-test-v1",
        "intent": "generic_test_intent",
        "intent_confidence": 0.98,
        "errors": [],
        "warnings": [],
        "final_status": "processing",
        "failure_stage": "",
    }


def _error_codes(result: GraphState) -> set[str]:
    return {
        error["code"]
        for error in result.get("errors", [])
    }


def test_build_plan_sucesso_sem_mutacao() -> None:
    state = _state()
    original = deepcopy(state)

    result = build_plan(state)

    assert result["final_status"] == "processing"
    assert result["current_stage"] == "build_plan"
    assert result["failure_stage"] == ""
    assert result["query_plan"]["intent_name"] == "generic_test_intent"
    assert result["query_plan"]["selected_pattern"]["pattern_name"] == (
        "generic_pattern"
    )
    assert state == original


def test_build_plan_rejeicao_sem_padrao() -> None:
    context = _context()
    context["query_patterns"] = []
    result = build_plan(_state(context))

    assert result["final_status"] == "rejected"
    assert result["failure_stage"] == "build_plan"
    assert "PLANNING_PATTERN_NOT_FOUND" in _error_codes(result)


def test_build_plan_erro_de_contrato_contexto_ausente() -> None:
    state = _state()
    state["context"] = None

    result = build_plan(state)

    assert result["final_status"] == "infrastructure_error"
    assert result["failure_stage"] == "build_plan"
    assert "PLANNING_CONTEXT_INVALID" in _error_codes(result)


def test_build_plan_required_table_inexistente_rejeita() -> None:
    context = _context()
    context["query_patterns"] = [
        _pattern(required_tables=["schema_test.missing_table"])
    ]

    result = build_plan(_state(context))

    assert result["final_status"] == "rejected"
    assert "PLANNING_REQUIRED_TABLE_NOT_FOUND" in _error_codes(result)


def main() -> None:
    tests = [
        ("build_plan sucesso", test_build_plan_sucesso_sem_mutacao),
        (
            "build_plan rejeicao sem padrao",
            test_build_plan_rejeicao_sem_padrao,
        ),
        (
            "build_plan erro de contrato",
            test_build_plan_erro_de_contrato_contexto_ausente,
        ),
        (
            "build_plan required_table inexistente",
            test_build_plan_required_table_inexistente_rejeita,
        ),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

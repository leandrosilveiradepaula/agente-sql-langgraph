from __future__ import annotations

from copy import deepcopy

from app.graph.nodes.normalize_result import normalize_result
from testar_result_normalization import LIMITS, _result


def _state(**overrides):
    state = {
        "sql_execution_result": _result(),
        "options": {"result_normalization_limits": LIMITS},
        "errors": [],
        "warnings": [],
    }
    state.update(overrides)
    return state


def test_success() -> None:
    result = normalize_result(_state())
    assert result["final_status"] == "processing"
    assert result["current_stage"] == "normalize_result"
    assert result["normalized_result"]["status"] == "success"


def test_execution_result_ausente_not_run_rejected_executed_false() -> None:
    states = [
        {
            "options": {"result_normalization_limits": LIMITS},
            "errors": [],
            "warnings": [],
        },
        _state(sql_execution_result={"status": "not_run"}),
        _state(sql_execution_result=_result(status="rejected")),
        _state(sql_execution_result=_result(executed=False)),
    ]
    for state in states:
        result = normalize_result(state)
        assert result["final_status"] == "rejected"


def test_fingerprint_inconsistente_dado_invalido_limite() -> None:
    bad_fingerprint = _result(response_fingerprint=None)
    bad_value = _result(rows=[{"value": object()}])
    too_many = _result(rows=[{"value": 1}, {"value": 2}])
    cases = [
        (bad_fingerprint, LIMITS),
        (bad_value, LIMITS),
        (too_many, {**LIMITS, "max_rows": 1}),
    ]
    for execution_result, limits in cases:
        result = normalize_result(
            _state(
                sql_execution_result=execution_result,
                options={"result_normalization_limits": limits},
            )
        )
        assert result["final_status"] == "rejected"
        assert "object at" not in repr(result)


def test_state_nao_mutado_e_execution_preservado() -> None:
    state = _state()
    original = deepcopy(state)
    result = normalize_result(state)
    assert state == original
    assert "sql_execution_result" not in result


def main() -> None:
    tests = [
        test_success,
        test_execution_result_ausente_not_run_rejected_executed_false,
        test_fingerprint_inconsistente_dado_invalido_limite,
        test_state_nao_mutado_e_execution_preservado,
    ]
    for index, test_function in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {test_function.__name__}: OK")


if __name__ == "__main__":
    main()

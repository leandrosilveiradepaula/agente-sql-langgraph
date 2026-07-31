from __future__ import annotations

from copy import deepcopy

from app.domain.result_normalization import normalize_execution_result
from app.graph.nodes.serialize_result import serialize_result
from testar_result_normalization import LIMITS, _result


def _normalized(value="x"):
    return normalize_execution_result(
        _result(rows=[{"value": value}]),
        limits=LIMITS,
    )


def _state(**overrides):
    state = {
        "normalized_result": _normalized(),
        "options": {"result_normalization_limits": LIMITS},
        "errors": [],
        "warnings": [],
    }
    state.update(overrides)
    return state


def test_success() -> None:
    result = serialize_result(_state())
    assert result["final_status"] == "approved"
    assert result["current_stage"] == "serialize_result"
    assert result["serialized_result"]["status"] == "success"


def test_normalized_ausente_invalido_acima_limite() -> None:
    states = [
        {
            "options": {"result_normalization_limits": LIMITS},
            "errors": [],
            "warnings": [],
        },
        _state(normalized_result={"status": "rejected"}),
        _state(
            options={
                "result_normalization_limits": {
                    **LIMITS,
                    "max_serialized_bytes": 1,
                }
            }
        ),
    ]
    for state in states:
        result = serialize_result(state)
        assert result["final_status"] == "rejected"


def test_state_nao_mutado_resultado_e_lineage_preservados() -> None:
    state = _state()
    original = deepcopy(state)
    result = serialize_result(state)
    assert state == original
    assert "normalized_result" not in result
    assert result["serialized_result"]["lineage"]["execution_request_fingerprint"]


def test_erro_sem_dados_integrais() -> None:
    result = serialize_result(
        _state(
            options={
                "result_normalization_limits": {
                    **LIMITS,
                    "max_serialized_bytes": 1,
                }
            }
        )
    )
    assert "password=hidden" not in repr(result)
    assert "SELECT id FROM schema_test.table_test" not in repr(result)


def main() -> None:
    tests = [
        test_success,
        test_normalized_ausente_invalido_acima_limite,
        test_state_nao_mutado_resultado_e_lineage_preservados,
        test_erro_sem_dados_integrais,
    ]
    for index, test_function in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {test_function.__name__}: OK")


if __name__ == "__main__":
    main()

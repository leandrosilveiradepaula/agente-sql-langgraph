from __future__ import annotations

from copy import deepcopy

from app.adapters.testing.fake_sql_repairer import FakeSqlRepairer
from app.domain.engine_preflight import normalize_engine_preflight_result
from app.domain.sql_repair import SqlRepairProviderError, sql_fingerprint
from app.graph.nodes.repair_sql import create_repair_sql_node
from app.graph.state import GraphState
from testar_engine_preflight import _query_plan, _request


CURRENT_SQL = "SELECT id FROM schema_test.table_test"
REPAIRED_SQL = "SELECT value FROM schema_test.table_test"


def _preflight_result(*, repairable: bool = True) -> dict:
    return normalize_engine_preflight_result(
        request=_request(CURRENT_SQL),
        provider_result={
            "status": "rejected",
            "provider_name": "fake_engine_preflight",
            "failure_category": "column_not_found",
            "message": "column not found",
            "repairable": repairable,
            "executed": False,
            "rows_returned": 0,
        },
    )


def _state(**overrides) -> GraphState:
    state: GraphState = {
        "current_sql": CURRENT_SQL,
        "generated_sql": CURRENT_SQL,
        "query_plan": _query_plan(),
        "engine_preflight_result": _preflight_result(),
        "security_result": {"status": "approved", "errors": [], "warnings": []},
        "contract_result": {"status": "approved", "errors": [], "warnings": []},
        "repair_attempts": 0,
        "max_repair_attempts": 2,
        "repair_history": [],
        "errors": [],
        "warnings": [],
    }
    state.update(overrides)
    return state


def test_reparo_bem_sucedido() -> None:
    repairer = FakeSqlRepairer(responses=[REPAIRED_SQL])
    node = create_repair_sql_node(repairer)
    state = _state()
    original = deepcopy(state)

    result = node(state)

    assert result["final_status"] == "processing"
    assert result["current_stage"] == "repair_sql"
    assert result["failure_stage"] == ""
    assert result["current_sql"] == REPAIRED_SQL
    assert result["repair_attempts"] == 1
    assert len(result["repair_history"]) == 1
    assert result["repair_history"][0]["repair_applied"] is True
    assert result["generated_sql"] != REPAIRED_SQL if "generated_sql" in result else True
    assert result["security_result"]["status"] == "not_run"
    assert result["contract_result"]["status"] == "not_run"
    assert result["engine_preflight_result"]["status"] == "not_run"
    assert repairer.calls == 1
    assert repairer.last_request is not None
    assert repairer.last_request["current_sql"] == CURRENT_SQL
    assert state == original


def test_preflight_aprovado_ou_nao_reparavel_nao_chama_provider() -> None:
    approved = {
        "status": "approved",
        "repairable": False,
        "errors": [],
        "warnings": [],
    }
    cases = [
        approved,
        _preflight_result(repairable=False),
    ]
    for preflight in cases:
        repairer = FakeSqlRepairer()
        node = create_repair_sql_node(repairer)
        result = node(_state(engine_preflight_result=preflight))

        assert result["final_status"] == "rejected"
        assert result["failure_stage"] == "repair_sql"
        assert repairer.calls == 0


def test_limite_zero_e_limite_atingido_nao_chamam_provider() -> None:
    cases = [
        (0, 0, "SQL_REPAIR_DISABLED"),
        (2, 2, "SQL_REPAIR_LIMIT_REACHED"),
    ]
    for attempts, max_attempts, code in cases:
        repairer = FakeSqlRepairer()
        node = create_repair_sql_node(repairer)
        result = node(
            _state(
                repair_attempts=attempts,
                max_repair_attempts=max_attempts,
            )
        )

        assert result["final_status"] == "rejected"
        assert result["errors"][-1]["code"] == code
        assert repairer.calls == 0


def test_resposta_invalida_inalterada_e_repetida() -> None:
    history = [
        {
            "attempt": 1,
            "failed_stage": "engine_preflight",
            "failure_category": "column_not_found",
            "sql_before_fingerprint": sql_fingerprint(CURRENT_SQL),
            "sql_after_fingerprint": sql_fingerprint(REPAIRED_SQL),
            "request_fingerprint": "a" * 64,
            "response_fingerprint": "b" * 64,
            "repair_applied": True,
            "reason": "sql_repair_applied",
            "provider_name": "fake_sql_repairer",
            "errors": [],
            "warnings": [],
        }
    ]
    cases = [
        ("", "SQL_REPAIR_RESPONSE_EMPTY", []),
        (CURRENT_SQL, "SQL_REPAIR_UNCHANGED_SQL", []),
        (REPAIRED_SQL, "SQL_REPAIR_REPEATED_SQL", history),
    ]
    for output_text, code, repair_history in cases:
        repairer = FakeSqlRepairer(responses=[output_text])
        node = create_repair_sql_node(repairer)
        result = node(_state(repair_history=repair_history))

        assert result["final_status"] == "rejected"
        assert result["errors"][-1]["code"] == code
        assert result["repair_attempts"] == 1
        assert repairer.calls == 1


def test_provider_indisponivel_timeout_e_excecao() -> None:
    cases = [
        SqlRepairProviderError("dsn=hidden"),
        TimeoutError("token=hidden"),
        RuntimeError("password=hidden"),
    ]
    for exception in cases:
        repairer = FakeSqlRepairer(exceptions=[exception])
        node = create_repair_sql_node(repairer)
        result = node(_state())
        serialized = repr(result).casefold()

        assert result["final_status"] == "infrastructure_error"
        assert result["failure_stage"] == "repair_sql"
        assert result["repair_attempts"] == 1
        assert repairer.calls == 1
        assert "hidden" not in serialized


def test_diagnostico_sem_sql_ou_credenciais() -> None:
    repairer = FakeSqlRepairer(
        responses=[
            {
                "provider_name": f"provider token=abc {CURRENT_SQL}",
                "output_text": "",
                "duration_ms": 1,
            }
        ]
    )
    node = create_repair_sql_node(repairer)
    result = node(_state())
    serialized = repr(result).casefold()

    assert CURRENT_SQL.casefold() not in serialized
    assert "token=abc" not in serialized
    assert "password" not in serialized


def main() -> None:
    tests = [
        ("reparo bem-sucedido", test_reparo_bem_sucedido),
        (
            "preflight sem reparo",
            test_preflight_aprovado_ou_nao_reparavel_nao_chama_provider,
        ),
        (
            "limites sem provider",
            test_limite_zero_e_limite_atingido_nao_chamam_provider,
        ),
        (
            "respostas invalidas",
            test_resposta_invalida_inalterada_e_repetida,
        ),
        (
            "falhas provider",
            test_provider_indisponivel_timeout_e_excecao,
        ),
        (
            "diagnostico seguro",
            test_diagnostico_sem_sql_ou_credenciais,
        ),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

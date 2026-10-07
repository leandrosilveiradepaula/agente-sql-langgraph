from __future__ import annotations

from copy import deepcopy

from app.adapters.testing.fake_engine_preflight import FakeEnginePreflight
from app.adapters.testing.fake_sql_repairer import FakeSqlRepairer
from app.application.internal_sql_agent_v1 import (
    ExecuteApprovedSqlShadowUseCase,
    GenerateSqlUseCase,
)
from app.application.internal_sql_agent_v1_generate import (
    validate_generate_request,
)
from app.application.internal_sql_agent_v1_shared import metadata
from app.domain.sql_generation import SqlGenerationProviderError
from testar_grafo_base import SuccessContextRepository


class FakeSqlGenerator:
    def __init__(
        self,
        sql: str = "SELECT id FROM schema_test.table_test",
        *,
        exception: Exception | None = None,
    ) -> None:
        self.sql = sql
        self.exception = exception
        self.calls = 0
        self.requests = []

    def generate(self, request):
        self.calls += 1
        self.requests.append(deepcopy(request))
        assert "context" not in request
        if self.exception is not None:
            raise self.exception
        return {
            "provider_name": "fake_sql_generator",
            "provider_version": "test-v1",
            "output_text": self.sql,
        }


class Ids:
    def __init__(self) -> None:
        self.index = 0

    def __call__(self) -> str:
        self.index += 1
        return f"lg-run-{self.index}"


def _principal() -> dict:
    return {
        "id": "user-1",
        "email": "user@example.invalid",
        "profile": "admin",
        "organization_id": "org-1",
    }


def _generate_use_case(
    *,
    generator=None,
    preflight=None,
    repairer=None,
) -> tuple[GenerateSqlUseCase, object, FakeEnginePreflight, FakeSqlRepairer]:
    generator = generator or FakeSqlGenerator()
    preflight = preflight or FakeEnginePreflight()
    repairer = repairer or FakeSqlRepairer()
    return (
        GenerateSqlUseCase(
            context_repository=SuccessContextRepository(),
            sql_generator=generator,
            engine_preflight=preflight,
            sql_repairer=repairer,
            id_generator=Ids(),
        ),
        generator,
        preflight,
        repairer,
    )


def _execute_shadow_use_case(
    *,
    preflight=None,
    repairer=None,
) -> tuple[
    ExecuteApprovedSqlShadowUseCase,
    FakeEnginePreflight,
    FakeSqlRepairer,
]:
    preflight = preflight or FakeEnginePreflight()
    repairer = repairer or FakeSqlRepairer()
    return (
        ExecuteApprovedSqlShadowUseCase(
            engine_preflight=preflight,
            sql_repairer=repairer,
            id_generator=Ids(),
        ),
        preflight,
        repairer,
    )


def test_generate_valido_para_antes_de_execute_sql() -> None:
    use_case, generator, preflight, repairer = _generate_use_case()
    response = use_case.execute(
        {
            "contract_version": "1",
            "agent_run_id": "agent-run-1",
            "question": "Execute uma generic analysis de teste.",
            "principal": _principal(),
        }
    )

    assert response["status"] == "success"
    assert response["agent_run_id"] == "agent-run-1"
    assert response["run_id"] == "lg-run-1"
    assert response["run_id"] != response["agent_run_id"]
    assert response["sql"] == "SELECT id FROM schema_test.table_test"
    assert response["intent"] == "generic_test_intent"
    assert response["gates"]["security"]["status"] == "approved"
    assert response["gates"]["contract"]["status"] == "approved"
    assert response["preflight"]["status"] == "approved"
    assert response["preflight"]["executed"] is False
    assert generator.calls == 1
    assert preflight.calls == 1
    assert repairer.calls == 0


def test_generate_repair_loop_reaplica_gates_e_preflight() -> None:
    preflight = FakeEnginePreflight(
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
    repairer = FakeSqlRepairer(
        responses=["SELECT id FROM schema_test.table_test"]
    )
    use_case, generator, preflight, repairer = _generate_use_case(
        generator=FakeSqlGenerator("SELECT value FROM schema_test.table_test"),
        preflight=preflight,
        repairer=repairer,
    )
    response = use_case.execute(
        {
            "contract_version": "1",
            "agent_run_id": "agent-run-2",
            "question": "Execute uma generic analysis de teste.",
            "principal": _principal(),
        }
    )

    assert response["status"] == "success"
    assert response["sql"] == "SELECT id FROM schema_test.table_test"
    assert response["repair_attempts"] == 1
    assert generator.calls == 1
    assert preflight.calls == 2
    assert repairer.calls == 1


def test_generate_aceita_pergunta_multilinha() -> None:
    errors = validate_generate_request(
        {
            "contract_version": "1",
            "agent_run_id": "agent-run-multiline",
            "question": (
                "Execute uma generic analysis de teste.\n"
                "Detalhe por unidade e período."
            ),
            "principal": _principal(),
        }
    )

    assert not any(
        item["code"] == "INTERNAL_GENERATE_QUESTION_REQUIRED"
        for item in errors
    )


def test_generate_aceita_tab_e_crlf_na_pergunta() -> None:
    for question in (
        "Execute uma generic analysis\tpor unidade.",
        "Execute uma generic analysis.\r\nDetalhe por periodo.",
    ):
        errors = validate_generate_request(
            {
                "contract_version": "1",
                "agent_run_id": "agent-run-whitespace",
                "question": question,
                "principal": _principal(),
            }
        )

        assert not any(
            item["code"] == "INTERNAL_GENERATE_QUESTION_REQUIRED"
            for item in errors
        )


def test_generate_rejeita_controle_invisivel_na_pergunta() -> None:
    errors = validate_generate_request(
        {
            "contract_version": "1",
            "agent_run_id": "agent-run-control",
            "question": "Execute uma generic analysis.\x00",
            "principal": _principal(),
        }
    )

    assert any(
        item["code"] == "INTERNAL_GENERATE_QUESTION_REQUIRED"
        for item in errors
    )


def test_generate_expoe_resumo_seguro_da_resolucao_de_intencao() -> None:
    use_case, generator, preflight, repairer = _generate_use_case()
    response = use_case.execute(
        {
            "contract_version": "1",
            "agent_run_id": "agent-run-intent-diagnostic",
            "question": "Execute uma generic analysis de teste.",
            "principal": _principal(),
        }
    )

    diagnostic = response["metadata"]["intent_resolution"]

    assert diagnostic["available"] is True
    assert diagnostic["applied"] is True
    assert diagnostic["reason"] == "configured_intent_selected"
    assert diagnostic["resolver_version"]
    assert diagnostic["best_candidate"]["intent_name"] == (
        "generic_test_intent"
    )
    assert isinstance(diagnostic["minimum_score"], float)
    assert isinstance(diagnostic["ambiguity_margin"], float)

    serialized = repr(diagnostic).casefold()
    for forbidden in (
        "signals",
        "rules",
        "business_question_examples",
        "sql_filter_hint",
        "raw_pattern",
    ):
        assert forbidden not in serialized


def test_generate_expoe_resumo_seguro_do_query_plan() -> None:
    use_case, generator, preflight, repairer = _generate_use_case()
    response = use_case.execute(
        {
            "contract_version": "1",
            "agent_run_id": "agent-run-plan-diagnostic",
            "question": "Execute uma generic analysis de teste.",
            "principal": _principal(),
        }
    )

    plan = response["metadata"]["query_plan"]

    assert plan["available"] is True
    assert plan["intent_name"] == "generic_test_intent"
    assert plan["selected_pattern_name"]
    assert isinstance(plan["required_tables"], list)
    assert isinstance(plan["detected_dimensions"], list)
    assert isinstance(plan["analytical_operations"], list)
    assert isinstance(plan["planned_metrics"], list)
    assert isinstance(plan["planned_filters"], list)

    serialized = repr(plan).casefold()
    for forbidden in (
        "business_question_examples",
        "sql_pattern",
        "required_rules",
        "rule_content",
        "semantic_description",
    ):
        assert forbidden not in serialized


def test_generate_rejeita_contract_version_invalida() -> None:
    use_case, generator, preflight, repairer = _generate_use_case()
    response = use_case.execute(
        {
            "contract_version": "2",
            "agent_run_id": "agent-run-3",
            "question": "Execute uma generic analysis de teste.",
            "principal": _principal(),
        }
    )

    assert response["status"] == "rejected"
    assert response["errors"][0]["code"] == (
        "INTERNAL_CONTRACT_VERSION_UNSUPPORTED"
    )
    assert generator.calls == 0
    assert preflight.calls == 0
    assert repairer.calls == 0


def test_generate_erro_provider_sanitizado() -> None:
    use_case, generator, preflight, repairer = _generate_use_case(
        generator=FakeSqlGenerator(
            exception=SqlGenerationProviderError("token=hidden")
        )
    )
    response = use_case.execute(
        {
            "contract_version": "1",
            "agent_run_id": "agent-run-4",
            "question": "Execute uma generic analysis de teste.",
            "principal": _principal(),
        }
    )

    serialized = repr(response).casefold()
    assert response["status"] == "infrastructure_error"
    assert generator.calls == 1
    assert preflight.calls == 0
    assert repairer.calls == 0
    assert "token=hidden" not in serialized


def test_execute_approved_shadow_valida_sql_sem_generate_ou_execute() -> None:
    use_case, preflight, repairer = _execute_shadow_use_case()
    response = use_case.execute(
        {
            "contract_version": "1",
            "agent_run_id": "agent-run-5",
            "approved_sql": "SELECT id FROM schema_test.table_test",
            "principal": _principal(),
        }
    )

    assert response["status"] == "success"
    assert response["agent_run_id"] == "agent-run-5"
    assert response["run_id"] == "lg-run-1"
    assert response["run_id"] != response["agent_run_id"]
    assert response["approved_sql_original"] == (
        "SELECT id FROM schema_test.table_test"
    )
    assert response["repaired_sql_proposal"] is None
    assert response["requires_reapproval"] is False
    assert response["validation"]["security"]["status"] == "approved"
    assert response["validation"]["contract"]["status"] == "approved"
    assert response["validation"]["preflight"]["status"] == "approved"
    assert response["validation"]["preflight"]["executed"] is False
    assert preflight.calls == 1
    assert repairer.calls == 0


def test_execute_approved_shadow_repair_exige_reapproval() -> None:
    preflight = FakeEnginePreflight(
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
    repairer = FakeSqlRepairer(
        responses=["SELECT id FROM schema_test.table_test"]
    )
    use_case, preflight, repairer = _execute_shadow_use_case(
        preflight=preflight,
        repairer=repairer,
    )
    response = use_case.execute(
        {
            "contract_version": "1",
            "agent_run_id": "agent-run-6",
            "approved_sql": "SELECT value FROM schema_test.table_test",
            "principal": _principal(),
        }
    )

    assert response["status"] == "rejected"
    assert response["approved_sql_original"] == (
        "SELECT value FROM schema_test.table_test"
    )
    assert response["repaired_sql_proposal"] == (
        "SELECT id FROM schema_test.table_test"
    )
    assert response["requires_reapproval"] is True
    assert preflight.calls == 1
    assert repairer.calls == 1


def test_execute_approved_shadow_rejeita_contract_version_invalida() -> None:
    use_case, preflight, repairer = _execute_shadow_use_case()
    response = use_case.execute(
        {
            "contract_version": "2",
            "agent_run_id": "agent-run-8",
            "approved_sql": "SELECT id FROM schema_test.table_test",
            "principal": _principal(),
        }
    )

    serialized = repr(response).casefold()
    assert response["status"] == "rejected"
    assert response["errors"][0]["code"] == (
        "INTERNAL_CONTRACT_VERSION_UNSUPPORTED"
    )
    assert response["validation"]["security"]["status"] == "not_run"
    assert response["validation"]["contract"]["status"] == "not_run"
    assert response["validation"]["preflight"]["status"] == "not_run"
    assert response["validation"]["preflight"].get("executed") is None
    assert "token" not in serialized
    assert "secret" not in serialized
    assert "password" not in serialized
    assert "raw_response" not in serialized
    assert preflight.calls == 0
    assert repairer.calls == 0


def test_execute_approved_shadow_rejeita_payload_com_secret() -> None:
    use_case, preflight, repairer = _execute_shadow_use_case()
    response = use_case.execute(
        {
            "contract_version": "1",
            "agent_run_id": "agent-run-7",
            "approved_sql": "SELECT id FROM schema_test.table_test",
            "principal": _principal(),
            "token": "hidden",
        }
    )

    assert response["status"] == "rejected"
    assert response["errors"][0]["code"] == (
        "INTERNAL_REQUEST_SECRET_FIELD_FORBIDDEN"
    )
    assert preflight.calls == 0
    assert repairer.calls == 0


def test_metadata_expoe_diagnostico_estrutural_dos_gates_sem_sql() -> None:
    diagnostic = metadata(
        {
            "security_result": {
                "status": "rejected",
                "tables": ["schema_test.table_extra"],
                "findings": [
                    {
                        "code": "SQL_SECURITY_UNAUTHORIZED_TABLE",
                        "details": {"table": "schema_test.table_extra"},
                    }
                ],
            },
            "contract_result": {
                "status": "rejected",
                "referenced_tables": [
                    {
                        "table": "schema_test.table_test",
                        "status": "satisfied",
                        "reason": "present",
                    }
                ],
                "joins": [
                    {
                        "left_table": "schema_test.table_test",
                        "right_table": "schema_test.table_extra",
                        "status": "violated",
                        "reason": "join_not_authorized_by_plan",
                    }
                ],
                "findings": [
                    {
                        "code": "SQL_CONTRACT_JOIN_VIOLATED",
                        "details": {"reason": "join_not_authorized_by_plan"},
                    }
                ],
            },
        }
    )["gate_diagnostics"]

    assert diagnostic["security"]["available"] is True
    assert diagnostic["security"]["referenced_tables"] == [
        "schema_test.table_extra"
    ]
    assert diagnostic["contract"]["joins"][0]["status"] == "violated"
    assert diagnostic["contract"]["joins"][0]["reason"] == (
        "join_not_authorized_by_plan"
    )

    serialized = repr(diagnostic).casefold()
    assert "select " not in serialized
    assert "current_sql" not in serialized
    assert "sql_pattern" not in serialized
    assert "raw_response" not in serialized
    assert "authorization" not in serialized
    assert "token" not in serialized


def main() -> None:
    tests = [
        test_metadata_expoe_diagnostico_estrutural_dos_gates_sem_sql,
        test_generate_valido_para_antes_de_execute_sql,
        test_generate_repair_loop_reaplica_gates_e_preflight,
        test_generate_aceita_pergunta_multilinha,
        test_generate_aceita_tab_e_crlf_na_pergunta,
        test_generate_rejeita_controle_invisivel_na_pergunta,
        test_generate_expoe_resumo_seguro_da_resolucao_de_intencao,
        test_generate_expoe_resumo_seguro_do_query_plan,
        test_generate_rejeita_contract_version_invalida,
        test_generate_erro_provider_sanitizado,
        test_execute_approved_shadow_valida_sql_sem_generate_ou_execute,
        test_execute_approved_shadow_repair_exige_reapproval,
        test_execute_approved_shadow_rejeita_contract_version_invalida,
        test_execute_approved_shadow_rejeita_payload_com_secret,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()

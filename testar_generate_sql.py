from __future__ import annotations

from copy import deepcopy

from app.adapters.testing.fake_engine_preflight import FakeEnginePreflight
from app.domain.context_normalizer import normalize_context_snapshot
from app.domain.planner import build_query_plan
from app.domain.sql_generation import SqlGenerationProviderError
from app.graph.builder import create_graph
from app.graph.nodes.generate_sql import create_generate_sql_node
from app.graph.state import GraphState
from testar_grafo_base import _raw_context_snapshot
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


class FakeSqlGenerator:
    def __init__(
        self,
        *,
        output_text: str = (
            "SELECT id FROM schema_test.table_test"
        ),
        raises: Exception | None = None,
    ) -> None:
        self.output_text = output_text
        self.raises = raises
        self.calls = 0
        self.last_request = None

    def generate(self, request):
        self.calls += 1
        self.last_request = deepcopy(request)
        assert "context" not in request
        assert "intent_catalog" not in repr(request).casefold()
        if self.raises is not None:
            raise self.raises
        return {
            "provider_name": "fake_sql_generator",
            "output_text": self.output_text,
            "raw_response": {
                "secret": "must-not-leak",
            },
            "duration_ms": 7,
        }


class SuccessContextRepository:
    def __init__(self, raw_context: dict | None = None) -> None:
        self.raw_context = raw_context or _raw_context_snapshot()

    def load_active_context(
        self,
        *,
        user_profile: str,
    ) -> dict:
        del user_profile
        return normalize_context_snapshot(self.raw_context)


def _state(query_plan: dict | None = None) -> GraphState:
    state: GraphState = {
        "question": "Execute uma generic analysis de teste.",
        "normalized_question": "generic analysis",
        "intent": "generic_test_intent",
        "intent_confidence": 0.98,
        "context": _context(),
        "query_plan": query_plan if query_plan is not None else _query_plan(),
        "errors": [],
        "warnings": [],
    }
    return state


def _graph_state(question: str) -> GraphState:
    return {
        "question": question,
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


def test_generate_sql_sucesso_sem_mutar_estado_ou_plano() -> None:
    generator = FakeSqlGenerator()
    node = create_generate_sql_node(generator)
    state = _state()
    original = deepcopy(state)

    result = node(state)

    assert result["final_status"] == "processing"
    assert result["current_stage"] == "generate_sql"
    assert result["generated_sql"] == (
        "SELECT id FROM schema_test.table_test"
    )
    assert result["current_sql"] == result["generated_sql"]
    assert result["sql_generation_result"]["status"] == "generated"
    assert generator.calls == 1
    assert state == original


def test_requisicao_do_provider_usa_somente_query_plan() -> None:
    generator = FakeSqlGenerator()
    node = create_generate_sql_node(generator)

    node(_state())

    request = generator.last_request
    assert request is not None
    serialized = repr(request).casefold()
    assert request["generation_context"]["intent_name"] == (
        "generic_test_intent"
    )
    assert "intent_catalog" not in serialized
    assert "'context'" not in serialized
    assert "table_catalog" not in serialized
    assert "query_patterns" not in serialized
    assert "postgres_dsn" not in serialized


def test_rejeita_sql_invalida_sem_finalizador() -> None:
    generator = FakeSqlGenerator(
        output_text="UPDATE schema_test.table_test SET id = 1"
    )
    node = create_generate_sql_node(generator)

    result = node(_state())

    assert result["final_status"] == "rejected"
    assert result["failure_stage"] == "generate_sql"
    assert result["errors"][0]["code"] == (
        "SQL_GENERATION_NON_READ_ONLY"
    )
    assert result["sql_generation_result"]["provider_result"][
        "output_text"
    ] == ""


def test_falha_provider_vai_para_infra_sem_vazar_resposta() -> None:
    generator = FakeSqlGenerator(
        raises=SqlGenerationProviderError("credential=hidden")
    )
    node = create_generate_sql_node(generator)

    result = node(_state())

    assert result["final_status"] == "infrastructure_error"
    assert result["failure_stage"] == "generate_sql"
    assert result["errors"][0]["code"] == (
        "SQL_GENERATION_PROVIDER_FAILED"
    )
    assert "credential=hidden" not in repr(result)


def test_query_plan_ausente_gera_erro_de_contrato() -> None:
    generator = FakeSqlGenerator()
    node = create_generate_sql_node(generator)
    state = _state(query_plan={})

    result = node(state)

    assert result["final_status"] == "infrastructure_error"
    assert result["errors"][0]["code"] == (
        "SQL_GENERATION_PLAN_MISSING"
    )
    assert generator.calls == 0


def test_query_plan_invalido_gera_erro_de_contrato() -> None:
    generator = FakeSqlGenerator()
    node = create_generate_sql_node(generator)
    state = _state(
        query_plan={
            "intent_name": "generic_test_intent",
        }
    )

    result = node(state)

    assert result["final_status"] == "infrastructure_error"
    assert result["errors"][0]["code"] == (
        "SQL_GENERATION_PLAN_INVALID"
    )
    assert generator.calls == 0


def test_grafo_nao_chama_generator_quando_intencao_rejeitada() -> None:
    generator = FakeSqlGenerator()
    preflight = FakeEnginePreflight()
    graph = create_graph(SuccessContextRepository(), generator, preflight)

    result = graph.invoke(
        _graph_state(
            "Execute uma operacao sem correspondencia configurada."
        ),
        config={
            "recursion_limit": 10,
        },
    )

    assert result["final_status"] == "rejected"
    assert result["current_stage"] == "classify_intent"
    assert generator.calls == 0
    assert preflight.calls == 0


def test_grafo_nao_chama_generator_quando_build_plan_rejeita() -> None:
    generator = FakeSqlGenerator()
    preflight = FakeEnginePreflight()
    raw_context = _raw_context_snapshot()
    raw_context["padroes"][0]["required_rules"] = [
        "missing_rule",
    ]
    graph = create_graph(
        SuccessContextRepository(raw_context),
        generator,
        preflight,
    )

    result = graph.invoke(
        _graph_state("Execute uma generic analysis de teste."),
        config={
            "recursion_limit": 10,
        },
    )

    assert result["final_status"] == "rejected"
    assert result["current_stage"] == "build_plan"
    assert result["failure_stage"] == "build_plan"
    assert generator.calls == 0
    assert preflight.calls == 0


def test_grafo_chama_generator_apos_build_plan_processing() -> None:
    generator = FakeSqlGenerator()
    preflight = FakeEnginePreflight()
    graph = create_graph(SuccessContextRepository(), generator, preflight)

    result = graph.invoke(
        _graph_state("Execute uma generic analysis de teste."),
        config={
            "recursion_limit": 10,
        },
    )

    assert result["final_status"] == "processing"
    assert result["current_stage"] == "engine_preflight"
    assert result["generated_sql"] == (
        "SELECT id FROM schema_test.table_test"
    )
    assert result["security_result"]["status"] == "approved"
    assert result["contract_result"]["status"] == "approved"
    assert result["engine_preflight_result"]["status"] == "approved"
    assert generator.calls == 1
    assert preflight.calls == 1


def main() -> None:
    tests = [
        (
            "sucesso sem mutacao",
            test_generate_sql_sucesso_sem_mutar_estado_ou_plano,
        ),
        (
            "provider recebe somente query plan",
            test_requisicao_do_provider_usa_somente_query_plan,
        ),
        (
            "rejeita SQL invalida",
            test_rejeita_sql_invalida_sem_finalizador,
        ),
        (
            "falha provider para infra",
            test_falha_provider_vai_para_infra_sem_vazar_resposta,
        ),
        (
            "query plan ausente",
            test_query_plan_ausente_gera_erro_de_contrato,
        ),
        (
            "query plan invalido",
            test_query_plan_invalido_gera_erro_de_contrato,
        ),
        (
            "intent rejeitada nao chama generator",
            test_grafo_nao_chama_generator_quando_intencao_rejeitada,
        ),
        (
            "build_plan rejeitado nao chama generator",
            test_grafo_nao_chama_generator_quando_build_plan_rejeita,
        ),
        (
            "build_plan processing chama generator",
            test_grafo_chama_generator_apos_build_plan_processing,
        ),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

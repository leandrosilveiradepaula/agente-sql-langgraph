from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.adapters.testing.fake_engine_preflight import FakeEnginePreflight
from app.adapters.testing.fake_shadow_evidence_repository import (
    FakeShadowEvidenceRepository,
)
from app.adapters.testing.fake_sql_repairer import FakeSqlRepairer
from app.application.internal_sql_agent_v1 import GenerateSqlUseCase
from app.domain.context_normalizer import normalize_context_snapshot


class RepresentativeContextRepository:
    def load_active_context(
        self,
        *,
        user_profile: str,
    ) -> dict[str, Any]:
        del user_profile
        return normalize_context_snapshot(
            {
                "semantic_agent_version": "semantic-version-test",
                "semantic_context_source": "representative_test_context",
                "regras": [
                    {
                        "rule_group": "configuration",
                        "rule_name": "intent_resolver_config",
                        "rule_content": {
                            "component": "intent_resolver",
                            "minimum_score": 100,
                            "ambiguity_margin": 20,
                            "applied_confidence": 0.98,
                            "fallback_to_previous_intent": True,
                            "token_fallback": {"enabled": False},
                        },
                        "applies_to_intents": [],
                        "validation_hint": None,
                        "severity": "info",
                        "priority": 1,
                    },
                    {
                        "rule_group": "metric",
                        "rule_name": "metric_rule",
                        "rule_content": {"metric": "revenue"},
                        "applies_to_intents": ["metric_query"],
                        "validation_hint": None,
                        "severity": "error",
                        "priority": 2,
                    },
                ],
                "entidades": [
                    {
                        "entity_type": "intent_signal",
                        "user_term": "receita",
                        "canonical_value": "metric_query",
                        "target_table": None,
                        "target_column": None,
                        "sql_filter_hint": {
                            "resolver": {
                                "match_mode": "contains",
                                "polarity": "positive",
                                "score": 120,
                            }
                        },
                        "business_rule": None,
                        "priority": 1,
                    }
                ],
                "dre": [],
                "padroes": [
                    {
                        "intent_name": "metric_query",
                        "pattern_name": "metric_pattern",
                        "business_question_examples": [
                            "Receita por periodo"
                        ],
                        "required_tables": [
                            "schema_test.metric_fact"
                        ],
                        "required_rules": ["metric_rule"],
                        "sql_pattern": "aggregate_metric_by_period",
                        "notes": None,
                        "priority": 1,
                    }
                ],
                "catalogo": [
                    {
                        "table_name": "metric_fact",
                        "schema_name": "schema_test",
                        "table_type": "table",
                        "description": "Representative metric table.",
                        "grain": "one row per period",
                        "primary_key": ["period_id"],
                        "key_columns": ["period_id"],
                        "metric_columns": ["metric_value"],
                        "date_columns": ["period_start"],
                        "join_rules": [],
                        "ai_hint": None,
                        "priority": 1,
                    }
                ],
                "context_counts": {
                    "regras": 2,
                    "entidades": 1,
                    "dre": 0,
                    "padroes": 1,
                    "catalogo": 1,
                },
            }
        )


class CapturingSqlGenerator:
    def __init__(self) -> None:
        self.calls = 0
        self.requests: list[dict[str, Any]] = []

    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        self.requests.append(deepcopy(request))
        return {
            "provider_name": "google_gemini",
            "provider_model": "gemini-2.5-flash",
            "output_text": "SELECT metric_value FROM schema_test.metric_fact",
            "duration_ms": 3,
            "token_usage": {
                "provider": "google_gemini",
                "model": "gemini-2.5-flash",
                "prompt_tokens": 101,
                "response_tokens": 17,
                "total_tokens": 118,
            },
        }


class Ids:
    def __init__(self) -> None:
        self.index = 0

    def __call__(self) -> str:
        self.index += 1
        return f"lg-run-{self.index}"


def _principal() -> dict[str, str]:
    return {
        "id": "user-1",
        "email": "user@example.invalid",
        "profile": "admin",
    }


def _request(question: str) -> dict[str, Any]:
    return {
        "contract_version": "1",
        "agent_run_id": "agent-run-shadow-real-test",
        "question": question,
        "principal": _principal(),
        "correlation_metadata": {
            "benchmark_id": "benchmark-correlation-only",
            "benchmark_mode": True,
            "benchmark_target": "TEST",
            "tabelas_obrigatorias": "forbidden",
            "filtros_obrigatorios": "forbidden",
            "deve_conter_sql": "forbidden",
            "nao_deve_conter_sql": "forbidden",
            "criterio_semantico": "forbidden",
            "expected_sql": "forbidden",
            "expected_answer": "forbidden",
        },
    }


def _use_case() -> tuple[
    GenerateSqlUseCase,
    FakeShadowEvidenceRepository,
    CapturingSqlGenerator,
    FakeEnginePreflight,
    FakeSqlRepairer,
]:
    repository = FakeShadowEvidenceRepository()
    generator = CapturingSqlGenerator()
    preflight = FakeEnginePreflight()
    repairer = FakeSqlRepairer()
    return (
        GenerateSqlUseCase(
            context_repository=RepresentativeContextRepository(),
            sql_generator=generator,
            engine_preflight=preflight,
            sql_repairer=repairer,
            id_generator=Ids(),
            shadow_repository=repository,
            langgraph_version="test-version",
            langgraph_commit="test-commit",
        ),
        repository,
        generator,
        preflight,
        repairer,
    )


def test_pergunta_representativa_chega_ao_generate_sql() -> None:
    use_case, repository, generator, preflight, repairer = _use_case()

    response = use_case.execute(
        _request("Quais foram as receitas do ultimo mes?")
    )

    assert response["status"] == "success"
    assert response["intent"] == "metric_query"
    assert generator.calls == 1
    assert preflight.calls == 1
    assert repairer.calls == 0
    evidence = repository.updated_records[-1]["langgraph_evidence"]
    assert evidence["provider_metadata"][
        "sql_generation_result_provider_name"
    ] == "google_gemini"
    assert evidence["provider_metadata"][
        "sql_generation_result_provider_model"
    ] == "gemini-2.5-flash"
    assert evidence["provider_metadata"][
        "sql_generation_result_token_usage"
    ]["total_tokens"] == 118


def test_pergunta_equivalente_nao_exata_chega_ao_generate_sql() -> None:
    use_case, _repository, generator, _preflight, _repairer = _use_case()

    response = use_case.execute(
        _request("Qual foi o total de receita no periodo anterior?")
    )

    assert response["status"] == "success"
    assert response["intent"] == "metric_query"
    assert generator.calls == 1


def test_pergunta_fora_do_dominio_continua_rejected() -> None:
    use_case, _repository, generator, preflight, repairer = _use_case()

    response = use_case.execute(
        _request("Explique a previsao do tempo para amanha.")
    )

    assert response["status"] == "rejected"
    assert response["intent"] is None
    assert generator.calls == 0
    assert preflight.calls == 0
    assert repairer.calls == 0


def test_benchmark_metadata_nao_chega_ao_generator_prompt() -> None:
    use_case, repository, generator, _preflight, _repairer = _use_case()

    response = use_case.execute(
        _request("Quais foram as receitas do ultimo mes?")
    )

    assert response["status"] == "success"
    serialized_request = repr(generator.requests[-1]).casefold()
    assert "benchmark-correlation-only" not in serialized_request
    assert "benchmark_id" not in serialized_request
    assert "benchmark_mode" not in serialized_request
    assert "benchmark_target" not in serialized_request
    assert "tabelas_obrigatorias" not in serialized_request
    assert "filtros_obrigatorios" not in serialized_request
    assert "deve_conter_sql" not in serialized_request
    assert "nao_deve_conter_sql" not in serialized_request
    assert "criterio_semantico" not in serialized_request
    assert "expected_sql" not in serialized_request
    assert "expected_answer" not in serialized_request
    correlation_metadata = repository.updated_records[-1]["correlation_metadata"]
    assert repository.updated_records[-1]["correlation_metadata"][
        "benchmark_id"
    ] == "benchmark-correlation-only"
    assert "expected_sql" not in correlation_metadata
    assert "expected_answer" not in correlation_metadata
    assert "tabelas_obrigatorias" not in correlation_metadata


def main() -> None:
    tests = [
        test_pergunta_representativa_chega_ao_generate_sql,
        test_pergunta_equivalente_nao_exata_chega_ao_generate_sql,
        test_pergunta_fora_do_dominio_continua_rejected,
        test_benchmark_metadata_nao_chega_ao_generator_prompt,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()

from __future__ import annotations

from copy import deepcopy

from app.domain.planner import build_query_plan
from app.domain.sql_generation import (
    SQL_GENERATION_CONTRACT_VERSION,
    SqlGenerationInputError,
    SqlGenerationValidationError,
    build_sql_generation_request,
    request_fingerprint,
    validate_sql_generation_response,
)
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


def _provider_result(output_text):
    return {
        "provider_name": "fake_sql_generator",
        "output_text": output_text,
        "duration_ms": 1,
    }


def _comparison_query_plan(
    *,
    grouped: bool = False,
    same_source: bool = False,
    join_semantics: str | None = None,
    operand_refs: list[str] | None = None,
    multiple_metric_sources: bool | None = None,
) -> dict:
    query_plan = _query_plan()
    second_table = (
        "schema_test.fact_a" if same_source else "schema_test.fact_b"
    )
    query_plan["planning_context"]["planned_metrics"] = [
        {
            "metric_ref": "metric-a",
            "metric_concept": "amount",
            "target_table": "schema_test.fact_a",
            "target_column": "metric_a",
            "aggregate": None,
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "metric_binding",
            "binding_ref": "binding-a",
            "binding_conditions": {"when_present": ["mode_a"], "when_absent": []},
            "binding_source": "entity_alias",
        },
        {
            "metric_ref": "metric-b",
            "metric_concept": "amount",
            "target_table": second_table,
            "target_column": "metric_b",
            "aggregate": None,
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "metric_binding",
            "binding_ref": "binding-b",
            "binding_conditions": {"when_present": ["mode_b"], "when_absent": []},
            "binding_source": "entity_alias",
        },
    ]
    if grouped:
        query_plan["planning_context"]["detected_dimensions"] = [
            {
                "canonical_value": "region",
                "target_table": "schema_test.dim_region",
                "target_column": "region_key",
                "grouping_requested": True,
                "source": "entity_alias",
            }
        ]
    operation = {
        "operation_type": "comparison",
        "canonical_value": "comparison",
        "output_behavior": "side_by_side",
        "combination_strategy": "aggregate_then_combine",
        "operand_metric_refs": operand_refs or ["metric-a", "metric-b"],
        "multiple_metric_sources": (
            (not same_source)
            if multiple_metric_sources is None
            else multiple_metric_sources
        ),
        "binding_cardinality": {
            "mode": "multiple",
            "minimum": 2,
            "maximum": 2,
            "same_metric_concept": True,
            "distinct_bindings": True,
        },
        "detection_source": "intent_semantic_evidence",
        "mapping_source": "entity_alias",
    }
    if join_semantics is not None:
        operation["join_semantics"] = join_semantics
    query_plan["planning_context"]["analytical_operations"] = [operation]
    return query_plan


def test_constroi_requisicao_do_query_plan() -> None:
    request = build_sql_generation_request(_query_plan())

    assert request["contract_version"] == (
        SQL_GENERATION_CONTRACT_VERSION
    )
    context = request["generation_context"]
    assert context["context_version"] == "context-test-v1"
    assert context["intent_name"] == "generic_test_intent"
    assert context["authorized_tables"][0]["qualified_name"] == (
        "schema_test.table_test"
    )
    assert context["pattern_metadata"]["sql_pattern_metadata"] == (
        "SELECT 1"
    )
    assert context["grouping_dimensions"] == []


def test_requisicao_propaga_dimensao_de_agrupamento_planejada() -> None:
    query_plan = _query_plan()
    query_plan["planning_context"]["detected_dimensions"] = [
        {
            "canonical_value": "dimension_test",
            "target_table": "schema_test.dimension_test",
            "target_column": "business_key",
            "grouping_requested": True,
            "source": "entity_alias",
        }
    ]

    request = build_sql_generation_request(query_plan)

    assert request["generation_context"]["grouping_dimensions"] == [
        {
            "canonical_value": "dimension_test",
            "target_table": "schema_test.dimension_test",
            "target_column": "business_key",
            "grouping_requested": True,
            "source": "entity_alias",
        }
    ]


def test_requisicao_propaga_operacoes_analiticas_planejadas() -> None:
    query_plan = _query_plan()
    query_plan["planning_context"]["planned_metrics"] = [
        {
            "metric_ref": "metric-synthetic",
            "metric_concept": "amount",
            "target_table": "schema_test.fact_metrics",
            "target_column": "measure_value",
            "aggregate": None,
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "entity_alias",
        }
    ]
    query_plan["planning_context"]["analytical_operations"] = [
        {
            "operation_type": "ranking",
            "canonical_value": "ranking",
            "direction": "descending",
            "requested_limit": None,
            "metric_ref": "metric-synthetic",
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "entity_alias",
            "matched_user_term": "highest",
        }
    ]

    request = build_sql_generation_request(query_plan)

    assert request["generation_context"]["analytical_operations"] == [
        {
            "operation_type": "ranking",
            "canonical_value": "ranking",
            "direction": "descending",
            "requested_limit": None,
            "metric_ref": "metric-synthetic",
            "binding_cardinality": {
                "mode": "single",
                "minimum": 1,
                "maximum": 1,
                "same_metric_concept": True,
                "distinct_bindings": True,
            },
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "entity_alias",
        }
    ]
    assert request["generation_context"]["planned_metrics"] == [
        {
            "metric_ref": "metric-synthetic",
            "metric_concept": "amount",
            "target_table": "schema_test.fact_metrics",
            "target_column": "measure_value",
            "aggregate": None,
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "entity_alias",
        }
    ]
    assert "ORDER BY" in repr(request)


def test_requisicao_propaga_metric_binding_planejado() -> None:
    query_plan = _query_plan()
    query_plan["planning_context"]["planned_metrics"] = [
        {
            "metric_ref": "metric-synthetic",
            "metric_concept": "amount",
            "target_table": "schema_test.fact_metrics",
            "target_column": "measure_value",
            "aggregate": None,
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "metric_binding",
            "binding_ref": "binding-synthetic",
            "binding_conditions": {
                "when_present": ["mode_a"],
                "when_absent": ["mode_b"],
            },
            "binding_source": "entity_alias",
        }
    ]

    request = build_sql_generation_request(query_plan)
    metric = request["generation_context"]["planned_metrics"][0]

    assert metric["mapping_source"] == "metric_binding"
    assert metric["binding_ref"] == "binding-synthetic"
    assert metric["binding_conditions"] == {
        "when_present": ["mode_a"],
        "when_absent": ["mode_b"],
    }
    assert metric["binding_source"] == "entity_alias"


def test_requisicao_filtra_metric_ref_sem_planned_metric() -> None:
    query_plan = _query_plan()
    query_plan["planning_context"]["planned_metrics"] = []
    query_plan["planning_context"]["analytical_operations"] = [
        {
            "operation_type": "ranking",
            "canonical_value": "ranking",
            "direction": "descending",
            "requested_limit": None,
            "metric_ref": "metric-missing",
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "entity_alias",
        }
    ]

    request = build_sql_generation_request(query_plan)

    assert request["generation_context"]["analytical_operations"] == []
    assert "planned_metric referenciada" not in repr(request)


def test_ranking_sem_metric_ref_nao_emite_instrucao_enganosa() -> None:
    query_plan = _query_plan()
    query_plan["planning_context"]["planned_metrics"] = []
    query_plan["planning_context"]["analytical_operations"] = [
        {
            "operation_type": "ranking",
            "canonical_value": "ranking",
            "direction": "descending",
            "requested_limit": None,
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "entity_alias",
        }
    ]

    request = build_sql_generation_request(query_plan)

    assert request["generation_context"]["analytical_operations"] == [
        {
            "operation_type": "ranking",
            "canonical_value": "ranking",
            "direction": "descending",
            "requested_limit": None,
            "metric_ref": "",
            "binding_cardinality": {
                "mode": "single",
                "minimum": 1,
                "maximum": 1,
                "same_metric_concept": True,
                "distinct_bindings": True,
            },
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "entity_alias",
        }
    ]
    assert "planned_metric referenciada" not in repr(request)


def test_planned_metric_com_aggregate_nao_e_propagada() -> None:
    query_plan = _query_plan()
    query_plan["planning_context"]["planned_metrics"] = [
        {
            "metric_ref": "metric-synthetic",
            "metric_concept": "amount",
            "target_table": "schema_test.fact_metrics",
            "target_column": "measure_value",
            "aggregate": "sum",
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "entity_alias",
        }
    ]

    request = build_sql_generation_request(query_plan)

    assert request["generation_context"]["planned_metrics"] == []


def test_comparison_multi_source_sem_dimensao_entra_no_contexto() -> None:
    request = build_sql_generation_request(
        _comparison_query_plan(
            join_semantics="preserve_all_operand_categories",
        )
    )

    operation = request["generation_context"]["analytical_operations"][0]

    assert operation["operation_type"] == "comparison"
    assert operation["operand_metric_refs"] == ["metric-a", "metric-b"]
    assert operation["multiple_metric_sources"] is True
    assert operation["combine_strategy"] == "cross_join"
    assert request["generation_context"]["grouping_dimensions"] == []


def test_comparison_multi_source_com_dimensao_entra_no_contexto() -> None:
    request = build_sql_generation_request(
        _comparison_query_plan(
            grouped=True,
            join_semantics="preserve_all_operand_categories",
        )
    )

    context = request["generation_context"]
    operation = context["analytical_operations"][0]

    assert context["grouping_dimensions"][0]["canonical_value"] == "region"
    assert operation["operation_type"] == "comparison"
    assert operation["join_semantics"] == "preserve_all_operand_categories"


def test_comparison_operand_refs_resolvem_planned_metrics_exatamente() -> None:
    request = build_sql_generation_request(
        _comparison_query_plan(
            join_semantics="preserve_all_operand_categories",
        )
    )
    context = request["generation_context"]

    planned_refs = {
        metric["metric_ref"] for metric in context["planned_metrics"]
    }
    operation_refs = set(
        context["analytical_operations"][0]["operand_metric_refs"]
    )

    assert operation_refs == planned_refs


def test_comparison_ref_inexistente_falha_fechado() -> None:
    request = build_sql_generation_request(
        _comparison_query_plan(
            join_semantics="preserve_all_operand_categories",
            operand_refs=["metric-a", "metric-missing"],
        )
    )

    assert request["generation_context"]["analytical_operations"] == []
    assert "comparison_operations" not in [
        instruction["name"] for instruction in request["instructions"]
    ]


def test_comparison_duas_tabelas_com_flag_false_falha_fechado() -> None:
    request = build_sql_generation_request(
        _comparison_query_plan(
            join_semantics="preserve_all_operand_categories",
            multiple_metric_sources=False,
        )
    )

    assert request["generation_context"]["analytical_operations"] == []


def test_comparison_uma_tabela_com_flag_true_falha_fechado() -> None:
    request = build_sql_generation_request(
        _comparison_query_plan(
            same_source=True,
            multiple_metric_sources=True,
        )
    )

    assert request["generation_context"]["analytical_operations"] == []


def test_comparison_operand_sem_target_table_falha_fechado() -> None:
    query_plan = _comparison_query_plan(
        same_source=True,
        multiple_metric_sources=False,
    )
    query_plan["planning_context"]["planned_metrics"][1].pop(
        "target_table",
        None,
    )

    request = build_sql_generation_request(query_plan)

    assert request["generation_context"]["analytical_operations"] == []


def test_comparison_operand_target_table_vazio_falha_fechado() -> None:
    query_plan = _comparison_query_plan(
        same_source=True,
        multiple_metric_sources=False,
    )
    query_plan["planning_context"]["planned_metrics"][1][
        "target_table"
    ] = ""

    request = build_sql_generation_request(query_plan)

    assert request["generation_context"]["analytical_operations"] == []


def test_comparison_duas_tabelas_com_flag_true_e_valida() -> None:
    request = build_sql_generation_request(
        _comparison_query_plan(
            join_semantics="preserve_all_operand_categories",
            multiple_metric_sources=True,
        )
    )

    assert request["generation_context"]["analytical_operations"][0][
        "multiple_metric_sources"
    ] is True


def test_comparison_uma_tabela_com_flag_false_e_valida() -> None:
    request = build_sql_generation_request(
        _comparison_query_plan(
            same_source=True,
            multiple_metric_sources=False,
        )
    )

    assert request["generation_context"]["analytical_operations"][0][
        "multiple_metric_sources"
    ] is False


def test_comparison_multi_source_agrupada_sem_join_semantics_falha_fechado() -> None:
    request = build_sql_generation_request(
        _comparison_query_plan(grouped=True)
    )

    assert request["generation_context"]["analytical_operations"] == []


def test_comparison_join_semantics_desconhecida_falha_fechado() -> None:
    request = build_sql_generation_request(
        _comparison_query_plan(join_semantics="unsupported_strategy")
    )

    assert request["generation_context"]["analytical_operations"] == []


def test_comparison_preserve_all_orienta_preservacao_bilateral() -> None:
    request = build_sql_generation_request(
        _comparison_query_plan(
            grouped=True,
            join_semantics="preserve_all_operand_categories",
        )
    )
    serialized = repr(request)

    assert "preserve_all_operand_categories" in serialized
    assert "FULL OUTER JOIN" in serialized


def test_comparison_sem_dimensao_nao_vira_full_outer_join_por_preserve_all() -> None:
    request = build_sql_generation_request(
        _comparison_query_plan(
            join_semantics="preserve_all_operand_categories",
        )
    )
    operation = request["generation_context"]["analytical_operations"][0]
    serialized = repr(request)

    assert operation["combine_strategy"] == "cross_join"
    assert "FULL OUTER JOIN" in serialized
    assert "combine os operands agregados com CROSS JOIN" in serialized


def test_comparison_common_only_orienta_intersecao() -> None:
    request = build_sql_generation_request(
        _comparison_query_plan(
            grouped=True,
            join_semantics="common_operand_categories_only",
        )
    )
    serialized = repr(request)

    assert "common_operand_categories_only" in serialized
    assert "INNER JOIN" in serialized


def test_comparison_same_source_nao_forca_cte_multi_source() -> None:
    request = build_sql_generation_request(
        _comparison_query_plan(same_source=True)
    )
    operation = request["generation_context"]["analytical_operations"][0]

    assert operation["multiple_metric_sources"] is False
    assert operation["combine_strategy"] == ""


def test_comparison_nao_solicita_delta_ou_percentual() -> None:
    request = build_sql_generation_request(
        _comparison_query_plan(
            join_semantics="preserve_all_operand_categories",
        )
    )
    serialized = repr(request).casefold()

    assert "side_by_side" in serialized
    assert "nao calcule diferenca" in serialized
    assert "percentual" in serialized
    assert "metrica derivada" in serialized


def test_comparison_preserva_regressao_ranking() -> None:
    query_plan = _query_plan()
    query_plan["planning_context"]["planned_metrics"] = [
        {
            "metric_ref": "metric-synthetic",
            "metric_concept": "amount",
            "target_table": "schema_test.fact_metrics",
            "target_column": "measure_value",
            "aggregate": None,
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "entity_alias",
        }
    ]
    query_plan["planning_context"]["analytical_operations"] = [
        {
            "operation_type": "ranking",
            "canonical_value": "ranking",
            "direction": "descending",
            "requested_limit": None,
            "metric_ref": "metric-synthetic",
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "entity_alias",
        }
    ]

    request = build_sql_generation_request(query_plan)

    assert request["generation_context"]["analytical_operations"][0][
        "operation_type"
    ] == "ranking"


def test_contexto_sem_comparison_sem_regressao() -> None:
    request = build_sql_generation_request(_query_plan())

    assert request["generation_context"]["analytical_operations"] == []
    assert "comparison_operations" not in [
        instruction["name"] for instruction in request["instructions"]
    ]


def test_requisicao_ignora_dimensao_sem_agrupamento_ou_incompleta() -> None:
    query_plan = _query_plan()
    query_plan["planning_context"]["detected_dimensions"] = [
        {
            "canonical_value": "not_grouped",
            "target_table": "schema_test.dimension_test",
            "target_column": "business_key",
            "grouping_requested": False,
            "source": "entity_alias",
        },
        {
            "canonical_value": "missing_column",
            "target_table": "schema_test.dimension_test",
            "grouping_requested": True,
            "source": "entity_alias",
        },
    ]

    request = build_sql_generation_request(query_plan)

    assert request["generation_context"]["grouping_dimensions"] == []


def test_requisicao_nao_contem_snapshot_catalogo_ou_credenciais() -> None:
    request = build_sql_generation_request(_query_plan())
    serialized = repr(request).casefold()

    assert "intent_catalog" not in serialized
    assert "signals" not in serialized
    assert "postgres_dsn" not in serialized
    assert "password" not in serialized
    assert "token" not in serialized
    assert "'context'" not in serialized
    assert "table_catalog" not in serialized
    assert "query_patterns" not in serialized


def test_requisicao_nao_contem_campos_esperados_de_benchmark() -> None:
    query_plan = _query_plan()
    query_plan["benchmark_id"] = "benchmark-1"
    query_plan["benchmark_mode"] = True
    query_plan["benchmark_target"] = "TEST"
    query_plan["tabelas_obrigatorias"] = ["forbidden_table"]
    query_plan["filtros_obrigatorios"] = ["forbidden_filter"]
    query_plan["deve_conter_sql"] = ["forbidden_must"]
    query_plan["nao_deve_conter_sql"] = ["forbidden_must_not"]
    query_plan["criterio_semantico"] = "forbidden_criterion"
    query_plan["expected_sql"] = "SELECT forbidden"
    query_plan["expected_answer"] = "forbidden_answer"
    query_plan["golden answer"] = "forbidden_golden"

    request = build_sql_generation_request(query_plan)
    serialized = repr(request).casefold()

    assert "benchmark-1" not in serialized
    assert "benchmark_mode" not in serialized
    assert "benchmark_target" not in serialized
    assert "tabelas_obrigatorias" not in serialized
    assert "filtros_obrigatorios" not in serialized
    assert "deve_conter_sql" not in serialized
    assert "nao_deve_conter_sql" not in serialized
    assert "criterio_semantico" not in serialized
    assert "expected_sql" not in serialized
    assert "expected_answer" not in serialized
    assert "golden" not in serialized
    assert "forbidden" not in serialized


def test_ordem_fingerprint_e_imutabilidade() -> None:
    query_plan = _query_plan()
    original = deepcopy(query_plan)

    first = build_sql_generation_request(query_plan)
    second = build_sql_generation_request(query_plan)

    assert first == second
    assert request_fingerprint(first) == request_fingerprint(second)
    assert query_plan == original


def test_rejeita_plano_invalido() -> None:
    try:
        build_sql_generation_request({})
    except SqlGenerationInputError as error:
        assert "planning_context" in str(error)
    else:
        raise AssertionError("Era esperado SqlGenerationInputError.")


def test_aceita_select_simples() -> None:
    sql = validate_sql_generation_response(
        _provider_result("SELECT id FROM schema_test.table_test")
    )

    assert sql == "SELECT id FROM schema_test.table_test"


def test_aceita_with_cte() -> None:
    sql = validate_sql_generation_response(
        _provider_result(
            "WITH generic_cte AS (SELECT id FROM schema_test.table_test) "
            "SELECT id FROM generic_cte"
        )
    )

    assert sql.startswith("WITH generic_cte")


def test_normaliza_ponto_e_virgula_final() -> None:
    sql = validate_sql_generation_response(
        _provider_result("SELECT id FROM schema_test.table_test;")
    )

    assert sql == "SELECT id FROM schema_test.table_test"


def _assert_validation_error(output_text, expected_code: str) -> None:
    try:
        validate_sql_generation_response(
            _provider_result(output_text)
        )
    except SqlGenerationValidationError as error:
        assert error.code == expected_code
    else:
        raise AssertionError(
            f"Era esperado {expected_code}."
        )


def test_rejeita_markdown() -> None:
    _assert_validation_error(
        "```sql\nSELECT id FROM schema_test.table_test\n```",
        "SQL_GENERATION_RESPONSE_INVALID",
    )


def test_rejeita_texto_explicativo() -> None:
    _assert_validation_error(
        "Aqui esta a SQL: SELECT id FROM schema_test.table_test",
        "SQL_GENERATION_RESPONSE_INVALID",
    )


def test_rejeita_resposta_vazia() -> None:
    _assert_validation_error(
        "   ",
        "SQL_GENERATION_RESPONSE_EMPTY",
    )


def test_rejeita_multiplas_instrucoes() -> None:
    _assert_validation_error(
        "SELECT id FROM schema_test.table_test; SELECT id FROM schema_test.table_test",
        "SQL_GENERATION_MULTIPLE_STATEMENTS",
    )


def test_rejeita_comandos_de_escrita_e_ddl() -> None:
    cases = [
        ("INSERT INTO schema_test.table_test VALUES (1)", "INSERT"),
        ("UPDATE schema_test.table_test SET id = 1", "UPDATE"),
        ("DELETE FROM schema_test.table_test", "DELETE"),
        ("DROP TABLE schema_test.table_test", "DROP"),
        ("CREATE TABLE schema_test.table_test (id int)", "CREATE"),
        ("COPY schema_test.table_test TO STDOUT", "COPY"),
    ]

    for sql, command in cases:
        try:
            validate_sql_generation_response(_provider_result(sql))
        except SqlGenerationValidationError as error:
            assert error.code == "SQL_GENERATION_NON_READ_ONLY"
        else:
            raise AssertionError(f"{command} deveria ser rejeitado.")


def test_palavra_perigosa_em_literal_nao_rejeita() -> None:
    sql = validate_sql_generation_response(
        _provider_result(
            "SELECT id FROM schema_test.table_test "
            "WHERE generic_text = 'DROP VALUE'"
        )
    )

    assert "DROP VALUE" in sql


def test_rejeita_apenas_ponto_e_virgula_comentario_e_controle() -> None:
    _assert_validation_error(";", "SQL_GENERATION_RESPONSE_EMPTY")
    _assert_validation_error("-- generic comment", "SQL_GENERATION_RESPONSE_INVALID")
    _assert_validation_error(
        "SELECT id FROM schema_test.table_test\x00",
        "SQL_GENERATION_RESPONSE_INVALID",
    )


def test_rejeita_resposta_nao_textual() -> None:
    try:
        validate_sql_generation_response(
            {
                "provider_name": "fake_sql_generator",
                "output_text": None,
            }
        )
    except SqlGenerationValidationError as error:
        assert error.code == "SQL_GENERATION_RESPONSE_INVALID"
    else:
        raise AssertionError("Era esperado erro estrutural.")


def test_comportamento_deterministico_repetido() -> None:
    query_plan = _query_plan()
    outputs = [
        build_sql_generation_request(query_plan)
        for _ in range(3)
    ]

    assert outputs[0] == outputs[1] == outputs[2]
    assert len({request_fingerprint(item) for item in outputs}) == 1


def main() -> None:
    tests = [
        ("constroi requisicao", test_constroi_requisicao_do_query_plan),
        (
            "propaga dimensao de agrupamento",
            test_requisicao_propaga_dimensao_de_agrupamento_planejada,
        ),
        (
            "propaga operacoes analiticas",
            test_requisicao_propaga_operacoes_analiticas_planejadas,
        ),
        (
            "propaga metric binding planejado",
            test_requisicao_propaga_metric_binding_planejado,
        ),
        (
            "filtra metric ref invalido",
            test_requisicao_filtra_metric_ref_sem_planned_metric,
        ),
        (
            "ranking sem metric ref sem instrucao enganosa",
            test_ranking_sem_metric_ref_nao_emite_instrucao_enganosa,
        ),
        (
            "planned metric aggregate nao propagado",
            test_planned_metric_com_aggregate_nao_e_propagada,
        ),
        (
            "comparison multi-source sem dimensao",
            test_comparison_multi_source_sem_dimensao_entra_no_contexto,
        ),
        (
            "comparison multi-source com dimensao",
            test_comparison_multi_source_com_dimensao_entra_no_contexto,
        ),
        (
            "comparison operand refs",
            test_comparison_operand_refs_resolvem_planned_metrics_exatamente,
        ),
        (
            "comparison ref inexistente",
            test_comparison_ref_inexistente_falha_fechado,
        ),
        (
            "comparison duas tabelas flag false",
            test_comparison_duas_tabelas_com_flag_false_falha_fechado,
        ),
        (
            "comparison uma tabela flag true",
            test_comparison_uma_tabela_com_flag_true_falha_fechado,
        ),
        (
            "comparison operand sem target table",
            test_comparison_operand_sem_target_table_falha_fechado,
        ),
        (
            "comparison operand target table vazio",
            test_comparison_operand_target_table_vazio_falha_fechado,
        ),
        (
            "comparison duas tabelas flag true",
            test_comparison_duas_tabelas_com_flag_true_e_valida,
        ),
        (
            "comparison uma tabela flag false",
            test_comparison_uma_tabela_com_flag_false_e_valida,
        ),
        (
            "comparison agrupada sem join semantics",
            test_comparison_multi_source_agrupada_sem_join_semantics_falha_fechado,
        ),
        (
            "comparison join semantics desconhecida",
            test_comparison_join_semantics_desconhecida_falha_fechado,
        ),
        (
            "comparison preservacao bilateral",
            test_comparison_preserve_all_orienta_preservacao_bilateral,
        ),
        (
            "comparison sem dimensao cross join",
            test_comparison_sem_dimensao_nao_vira_full_outer_join_por_preserve_all,
        ),
        (
            "comparison intersecao",
            test_comparison_common_only_orienta_intersecao,
        ),
        (
            "comparison same-source",
            test_comparison_same_source_nao_forca_cte_multi_source,
        ),
        (
            "comparison sem delta percentual",
            test_comparison_nao_solicita_delta_ou_percentual,
        ),
        (
            "comparison regressao ranking",
            test_comparison_preserva_regressao_ranking,
        ),
        (
            "comparison ausente regressao",
            test_contexto_sem_comparison_sem_regressao,
        ),
        (
            "ignora dimensao sem agrupamento ou incompleta",
            test_requisicao_ignora_dimensao_sem_agrupamento_ou_incompleta,
        ),
        (
            "sem snapshot catalogo ou credenciais",
            test_requisicao_nao_contem_snapshot_catalogo_ou_credenciais,
        ),
        (
            "sem campos esperados de benchmark",
            test_requisicao_nao_contem_campos_esperados_de_benchmark,
        ),
        (
            "ordem fingerprint e imutabilidade",
            test_ordem_fingerprint_e_imutabilidade,
        ),
        ("rejeita plano invalido", test_rejeita_plano_invalido),
        ("aceita SELECT", test_aceita_select_simples),
        ("aceita WITH", test_aceita_with_cte),
        (
            "normaliza ponto e virgula",
            test_normaliza_ponto_e_virgula_final,
        ),
        ("rejeita Markdown", test_rejeita_markdown),
        ("rejeita texto explicativo", test_rejeita_texto_explicativo),
        ("rejeita vazio", test_rejeita_resposta_vazia),
        (
            "rejeita multiplas instrucoes",
            test_rejeita_multiplas_instrucoes,
        ),
        (
            "rejeita comandos proibidos",
            test_rejeita_comandos_de_escrita_e_ddl,
        ),
        (
            "literal com palavra perigosa",
            test_palavra_perigosa_em_literal_nao_rejeita,
        ),
        (
            "rejeita pontuacao comentario e controle",
            test_rejeita_apenas_ponto_e_virgula_comentario_e_controle,
        ),
        ("rejeita nao textual", test_rejeita_resposta_nao_textual),
        (
            "deterministico repetido",
            test_comportamento_deterministico_repetido,
        ),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()



def _plan_with_required_filter() -> dict:
    query_plan = _query_plan()
    query_plan["planning_context"]["planned_filters"] = [
        {
            "filter_ref": "filter-synthetic",
            "filter_concept": "synthetic_category",
            "binding_ref": "binding-synthetic",
            "required": True,
            "scope": "row",
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "filter_binding",
            "matched_user_term": "synthetic",
            "provenance": {"context_version": "context-test-v1"},
        }
    ]
    query_plan["planning_context"]["resolved_filter_bindings"] = [
        {
            "binding_ref": "binding-synthetic",
            "filter_concept": "synthetic_category",
            "target_table": "schema_test.table_test",
            "target_column": "category_key",
            "operator": "=",
            "value": "synthetic_value",
            "join_path": [],
            "required": True,
            "scope": "row",
        }
    ]
    return query_plan


def test_required_filter_e_binding_fisico_sao_separados() -> None:
    request = build_sql_generation_request(_plan_with_required_filter())
    context = request["generation_context"]
    assert context["planned_filters"][0]["binding_ref"] == "binding-synthetic"
    assert "target_table" not in context["planned_filters"][0]
    assert context["filter_bindings"] == [
        {
            "binding_ref": "binding-synthetic",
            "filter_concept": "synthetic_category",
            "target_table": "schema_test.table_test",
            "target_column": "category_key",
            "operator": "=",
            "value": "synthetic_value",
            "join_path": [],
            "required": True,
            "scope": "row",
        }
    ]
    instruction = next(item for item in request["instructions"] if item["name"] == "required_filters")
    assert "required=true" in instruction["content"]
    assert "nao adicione filtros extras" in instruction["content"].lower()


def test_required_filter_sem_binding_falha_fechada() -> None:
    query_plan = _plan_with_required_filter()
    query_plan["planning_context"]["resolved_filter_bindings"] = []
    try:
        build_sql_generation_request(query_plan)
    except SqlGenerationInputError as exc:
        assert "obrigatorio ausente" in str(exc)
    else:
        raise AssertionError("binding obrigatorio ausente deveria falhar")


def test_binding_ambiguo_falha_fechada() -> None:
    query_plan = _plan_with_required_filter()
    query_plan["planning_context"]["resolved_filter_bindings"].append(
        deepcopy(query_plan["planning_context"]["resolved_filter_bindings"][0])
    )
    try:
        build_sql_generation_request(query_plan)
    except SqlGenerationInputError as exc:
        assert "ambiguo" in str(exc)
    else:
        raise AssertionError("binding ambiguo deveria falhar")


def test_filtros_sao_deterministicos_e_ignoram_nao_referenciados() -> None:
    query_plan = _plan_with_required_filter()
    second_filter = deepcopy(query_plan["planning_context"]["planned_filters"][0])
    second_filter.update({"filter_ref": "filter-a", "filter_concept": "alpha", "binding_ref": "binding-a"})
    second_binding = deepcopy(query_plan["planning_context"]["resolved_filter_bindings"][0])
    second_binding.update({"filter_concept": "alpha", "binding_ref": "binding-a", "value": "alpha-value"})
    extra_binding = deepcopy(second_binding)
    extra_binding["binding_ref"] = "binding-unreferenced"
    query_plan["planning_context"]["planned_filters"] = [query_plan["planning_context"]["planned_filters"][0], second_filter]
    query_plan["planning_context"]["resolved_filter_bindings"] = [extra_binding, query_plan["planning_context"]["resolved_filter_bindings"][0], second_binding]
    request = build_sql_generation_request(query_plan)
    assert [item["binding_ref"] for item in request["generation_context"]["planned_filters"]] == ["binding-a", "binding-synthetic"]
    assert [item["binding_ref"] for item in request["generation_context"]["filter_bindings"]] == ["binding-a", "binding-synthetic"]


def test_planned_filter_nao_aceita_campos_fisicos() -> None:
    query_plan = _plan_with_required_filter()
    query_plan["planning_context"]["planned_filters"][0]["target_column"] = "forbidden"
    try:
        build_sql_generation_request(query_plan)
    except SqlGenerationInputError as exc:
        assert "detalhes fisicos" in str(exc)
    else:
        raise AssertionError("planned_filter fisico deveria falhar")

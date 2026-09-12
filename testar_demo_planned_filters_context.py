from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DELTA_PATH = Path("semantic_context/demo_planned_filters_v8.delta.json")
EVIDENCE_PATH = Path(
    "semantic_context/evidence/demo_revenue_filter_binding_v1.json"
)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_delta() -> dict[str, Any]:
    return _load(DELTA_PATH)


def test_delta_e_versionado_e_nao_aplicavel_automaticamente() -> None:
    delta = _load_delta()
    assert delta["contract"] == "semantic-context-delta/v1"
    assert delta["source_context_version"] == "v7-planned-metrics"
    assert delta["target_context_version"] == "v8-planned-filters"
    assert delta["source_context_version"] != delta["target_context_version"]
    assert delta["environment"] == "DEMO"
    assert delta["automatic_apply"] is False
    assert delta["activation"]["allowed"] is False


def test_receita_e_semantica_e_nao_equivale_a_rol() -> None:
    concepts = _load_delta()["filter_concepts"]
    revenue = next(item for item in concepts if item["filter_concept"] == "dre_receita")
    assert revenue["aliases"] == ["receita", "receitas"]
    assert revenue["provenance"]["classification"] == "STRUCTURAL"
    physical_fields = {
        "target_table", "target_column", "operator", "value", "scope",
        "join_path", "binding_ref",
    }
    assert not physical_fields.intersection(revenue)
    serialized = json.dumps(concepts, ensure_ascii=False).casefold()
    assert "receita operacional liquida" not in serialized
    assert "receita operacional líquida" not in serialized


def test_aliases_de_receita_resolvem_um_unico_conceito() -> None:
    concepts = _load_delta()["filter_concepts"]
    alias_to_concept = {
        alias.casefold(): item["filter_concept"]
        for item in concepts
        for alias in item["aliases"]
    }
    assert {alias_to_concept[alias] for alias in ("receita", "receitas")} == {
        "dre_receita"
    }


def test_binding_receita_e_completo_e_separado() -> None:
    delta = _load_delta()
    assert delta["filter_bindings"] == [{
        "binding_ref": "demo-dre-receita-v1",
        "filter_concept": "dre_receita",
        "required": True,
        "scope": "row",
        "target_table": "demo_lakehouse.gold_plano_contas",
        "target_column": "grupo_contabil",
        "operator": "=",
        "value": "Receita",
        "join_path": [{
            "source_table": "demo_lakehouse.gold_lancamentos_contabeis",
            "source_column": "nk_conta",
            "target_table": "demo_lakehouse.gold_plano_contas",
            "target_column": "nk_conta",
            "operator": "=",
        }],
        "evidence_ref": EVIDENCE_PATH.as_posix(),
    }]
    concept = next(
        item for item in delta["filter_concepts"]
        if item["filter_concept"] == "dre_receita"
    )
    assert "binding_ref" not in concept


def test_evidencia_e_read_only_e_tem_limites_explicitos() -> None:
    evidence = _load(EVIDENCE_PATH)
    assert evidence["collection_mode"] == "read_only"
    assert evidence["external_write_performed"] is False
    assert evidence["authorizes_apply"] is False
    assert evidence["supports"]["binding_ref"] == "demo-dre-receita-v1"
    limitations = " ".join(evidence["limitations"])
    assert "receita operacional liquida" in limitations
    assert "dre_custos" in limitations
    assert "dre_despesas_operacionais" in limitations


def test_custos_e_opex_permanecem_fail_closed() -> None:
    delta = _load_delta()
    bound = {item["filter_concept"] for item in delta["filter_bindings"]}
    assert "dre_custos" not in bound
    assert "dre_despesas_operacionais" not in bound
    gaps = {item["scope"]: item for item in delta["gaps"]}
    for concept in ("dre_custos", "dre_despesas_operacionais"):
        assert gaps[concept]["status"] == "BLOCKING_FAIL_CLOSED"
        assert gaps[concept]["activation_allowed"] is False


def test_evidencia_transitional_nao_vira_contrato() -> None:
    delta = _load_delta()
    inventory = {item["field"]: item for item in delta["transitional_inventory"]}
    assert inventory["sql_filter_hint"]["allowed_use"] == "migration_inventory_only"
    assert inventory["sql_filter_hint"]["forbidden_use"] == "filter_binding_contract"
    assert inventory["nivel_1_bi"]["forbidden_use"] == "inferred_target_column"
    serialized_contract = json.dumps(
        delta["filter_concepts"] + delta["filter_bindings"], sort_keys=True
    )
    assert "sql_filter_hint" not in serialized_contract
    assert "nivel_1_bi" not in serialized_contract


def test_rollback_nao_remove_dados() -> None:
    rollback = _load_delta()["rollback"]
    assert "v7-planned-metrics" in rollback["action"]
    assert rollback["delete_data"] is False


if __name__ == "__main__":
    tests = [
        test_delta_e_versionado_e_nao_aplicavel_automaticamente,
        test_receita_e_semantica_e_nao_equivale_a_rol,
        test_aliases_de_receita_resolvem_um_unico_conceito,
        test_binding_receita_e_completo_e_separado,
        test_evidencia_e_read_only_e_tem_limites_explicitos,
        test_custos_e_opex_permanecem_fail_closed,
        test_evidencia_transitional_nao_vira_contrato,
        test_rollback_nao_remove_dados,
    ]
    for test in tests:
        test()
        print(f"[OK] {test.__name__}")

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DELTA_PATH = Path("semantic_context/demo_planned_filters_v8.delta.json")


def _load_delta() -> dict[str, Any]:
    return json.loads(DELTA_PATH.read_text(encoding="utf-8"))


def test_delta_e_versionado_e_nao_aplicavel_automaticamente() -> None:
    delta = _load_delta()
    assert delta["contract"] == "semantic-context-delta/v1"
    assert delta["source_context_version"] == "v7-planned-metrics"
    assert delta["target_context_version"] == "v8-planned-filters"
    assert delta["source_context_version"] != delta["target_context_version"]
    assert delta["environment"] == "DEMO"
    assert delta["automatic_apply"] is False
    assert delta["activation"]["allowed"] is False


def test_conceitos_sao_semanticos_com_provenance() -> None:
    concepts = _load_delta()["filter_concepts"]
    assert len(concepts) == 3
    physical_fields = {
        "target_table", "target_column", "operator", "value", "scope",
        "join_path", "binding_ref",
    }
    for concept in concepts:
        assert concept["filter_concept"]
        assert len(concept["aliases"]) == 2
        assert not physical_fields.intersection(concept)
        assert concept["provenance"]["source"].startswith("scripts/migrations/")
        assert concept["provenance"]["classification"] == "TRANSITIONAL"


def test_aliases_equivalentes_apontam_para_um_unico_conceito() -> None:
    concepts = _load_delta()["filter_concepts"]
    alias_to_concept = {
        alias.casefold(): item["filter_concept"]
        for item in concepts
        for alias in item["aliases"]
    }
    for item in concepts:
        resolved = {alias_to_concept[alias.casefold()] for alias in item["aliases"]}
        assert resolved == {item["filter_concept"]}


def test_binding_ausente_preserva_fail_closed() -> None:
    delta = _load_delta()
    assert delta["filter_bindings"] == []
    assert delta["gaps"] == [{
        "id": "DEMO-PF-001",
        "status": "BLOCKING_FAIL_CLOSED",
        "scope": "all_filter_concepts",
        "missing_evidence": [
            "target_table", "target_column", "operator", "value", "scope",
            "join_path",
        ],
        "required_resolution": (
            "Provide one complete, versioned and auditable physical binding "
            "per concept before activation."
        ),
        "activation_allowed": False,
    }]


def test_evidencia_transitional_nao_vira_contrato() -> None:
    delta = _load_delta()
    inventory = {item["field"]: item for item in delta["transitional_inventory"]}
    assert inventory["sql_filter_hint"]["allowed_use"] == "migration_inventory_only"
    assert inventory["sql_filter_hint"]["forbidden_use"] == "filter_binding_contract"
    assert inventory["nivel_1_bi"]["forbidden_use"] == "inferred_target_column"
    serialized_concepts = json.dumps(delta["filter_concepts"], sort_keys=True)
    assert "sql_filter_hint" not in serialized_concepts
    assert "nivel_1_bi" not in serialized_concepts


def test_rollback_nao_remove_dados() -> None:
    rollback = _load_delta()["rollback"]
    assert "v7-planned-metrics" in rollback["action"]
    assert rollback["delete_data"] is False


if __name__ == "__main__":
    tests = [
        test_delta_e_versionado_e_nao_aplicavel_automaticamente,
        test_conceitos_sao_semanticos_com_provenance,
        test_aliases_equivalentes_apontam_para_um_unico_conceito,
        test_binding_ausente_preserva_fail_closed,
        test_evidencia_transitional_nao_vira_contrato,
        test_rollback_nao_remove_dados,
    ]
    for test in tests:
        test()
        print(f"[OK] {test.__name__}")

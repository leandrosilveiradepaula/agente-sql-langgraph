from __future__ import annotations

import json
import re
from pathlib import Path

MIGRATION = (
    Path(__file__).resolve().parent
    / "scripts/migrations/021_prepare_demo_finance_context_v11.sql"
)


def _configured_date_bindings(sql: str) -> list[tuple[str, str, str]]:
    """Inspect only the versioned candidate SQL; no business names in tests."""
    section = sql.split("'date_bindings', jsonb_build_array(", 1)[1].split(
        "'granularities'", 1
    )[0]
    records = re.findall(
        r"jsonb_build_object\(\s*"
        r"'metric_concept',\s*'([^']+)'\s*,\s*"
        r"'target_table',\s*'([^']+)'\s*,\s*"
        r"'target_column',\s*'([^']+)'\s*\)",
        section,
    )
    assert section.count("jsonb_build_object(") == len(records)
    return records


def test_temporal_candidate_has_explicit_source_binding() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "'date_binding_strategy', 'configured_metric_source_date'" in sql
    assert "'date_bindings', jsonb_build_array(" in sql
    assert "'date_binding_strategy', 'unique_metric_source_catalog_date'" not in sql
    bindings = _configured_date_bindings(sql)
    assert bindings
    sources: set[tuple[str, str]] = set()
    for concept, table, column in bindings:
        assert concept.strip() and table.strip() and column.strip()
        assert table.count(".") == 1
        assert re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", column)
        source = (concept.casefold(), table.casefold())
        assert source not in sources, "duplicate temporal binding per metric source"
        sources.add(source)


def test_temporal_binding_sql_equals_versioned_policy() -> None:
    """No financial table/date expectations are embedded in test code."""
    root = Path(__file__).resolve().parent
    sql = MIGRATION.read_text(encoding="utf-8")
    policy = json.loads(
        (root / "semantic_context/candidate_parity_demo_finance_v11.json")
        .read_text(encoding="utf-8")
    )
    component = [
        rule["expected_record"]["rule_content"]
        for rule in policy["allowed_new_rules"]
        if rule["rule_group"] == "component_config"
        and rule["rule_name"] == "temporal_planning_config"
    ]
    assert len(component) == 1
    expected = component[0]["date_bindings"]
    assert isinstance(expected, list) and expected
    sql_bindings = _configured_date_bindings(sql)
    policy_bindings = [
        (binding["metric_concept"], binding["target_table"], binding["target_column"])
        for binding in expected
    ]
    assert sql_bindings == policy_bindings
    assert len({(concept.casefold(), table.casefold()) for concept, table, _ in sql_bindings}) == len(sql_bindings)


def test_transactional_clone_integrity_gate() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "DO $v11_candidate_integrity$" in sql
    assert "copied_source <> copied_target" in sql
    # Same-count copies must still be compared field by field.
    assert "to_jsonb(s) - ''agent_version''" in sql
    assert "to_jsonb(t) - ''agent_version''" in sql
    assert sql.count("EXCEPT ALL") == 2
    assert "cloned_payload_differs" in sql
    assert "clone payload mismatch" in sql
    assert "temporal metric binding is missing or ambiguous" in sql
    assert "temporal date is not authorized by the catalog" in sql
    assert "metric sources lack explicit temporal bindings" in sql
    assert "temporal date bindings are ambiguous" in sql
    assert "jsonb_array_elements(temporal_cfg->'date_bindings')" in sql
    assert sql.rstrip().endswith("COMMIT;")


def test_candidate_remains_immutable_and_non_promoting() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "demo-finance-v11 already exists; immutable context not modified" in sql
    assert "demo-finance-v10 source context is missing" in sql
    assert "SEMANTIC_AGENT_VERSION=" not in sql
    assert "COMMIT;" in sql


if __name__ == "__main__":
    test_temporal_candidate_has_explicit_source_binding()
    test_temporal_binding_sql_equals_versioned_policy()
    test_candidate_remains_immutable_and_non_promoting()
    test_transactional_clone_integrity_gate()
    print("DEMO_V11_TEMPORAL_CANDIDATE=PASS")

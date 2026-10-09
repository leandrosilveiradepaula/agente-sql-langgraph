from __future__ import annotations

import json
from pathlib import Path


RUNNER = Path("scripts/run_shadow_semantic_validation.py")
FULL_FLOW_RUNNER = Path("scripts/run_shadow_full_flow_validation.py")
SHELL = Path("scripts/run_shadow_semantic_validation.sh")
CASES = Path("scripts/validation/demo_finance_generalization_cases.json")


def test_suite_is_evaluation_only() -> None:
    payload = json.loads(CASES.read_text(encoding="utf-8"))
    assert payload["cases"]
    forbidden = {
        "sql",
        "expected_sql",
        "golden_answer",
        "deve_conter_sql",
        "nao_deve_conter_sql",
        "tabelas_obrigatorias",
        "filtros_obrigatorios",
    }
    allowed_plan_keys = {
        "minimum_planned_metrics",
        "operation_type",
        "operation_metric_ref",
        "minimum_operand_metric_refs",
    }
    for case in payload["cases"]:
        assert set(case).isdisjoint(forbidden)
        assert set(case).issubset(
            {"question", "expected_intent", "expected_plan"}
        )
        assert {"question", "expected_intent"}.issubset(case)
        expected_plan = case.get("expected_plan")
        if expected_plan is not None:
            assert isinstance(expected_plan, dict)
            assert set(expected_plan).issubset(allowed_plan_keys)
            assert set(expected_plan).isdisjoint(forbidden)


def test_expected_intent_is_not_input_to_resolver() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    call = "result = resolve_intent(question, ctx)"
    assert call in text
    assert "resolve_intent(question, expected_intent" not in text


def test_expected_plan_is_not_supplied_to_runtime() -> None:
    text = FULL_FLOW_RUNNER.read_text(encoding="utf-8")
    payload_start = text.index("payload = {")
    request_call = text.index("http_status, response = _run_request", payload_start)
    payload_section = text[payload_start:request_call]

    assert "expected_plan" not in payload_section
    assert 'case.get("expected_plan")' in text
    assert text.index('case.get("expected_plan")') > request_call


def test_failure_diagnostics_are_structured() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    assert '"CANDIDATES:"' in text
    assert '"DEFAULTS:"' in text
    assert '"MATCHED_CATALOG_RULES:"' in text
    assert 'result.get("candidates", [])' in text


def test_shell_reuses_running_shadow_without_secrets() -> None:
    text = SHELL.read_text(encoding="utf-8")
    assert "docker exec" in text
    assert "docker cp" in text
    assert "-w /app" in text
    assert "-e PYTHONPATH=/app" in text
    assert "CONTEXT_POSTGRES_DSN=" not in text
    assert "postgresql://" not in text
    assert "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=true" not in text


def main() -> None:
    tests = [
        ("evaluation only", test_suite_is_evaluation_only),
        ("expected intent not supplied", test_expected_intent_is_not_input_to_resolver),
        ("expected plan not supplied", test_expected_plan_is_not_supplied_to_runtime),
        ("structured failure diagnostics", test_failure_diagnostics_are_structured),
        ("reuse running shadow", test_shell_reuses_running_shadow_without_secrets),
    ]
    for index, (name, function) in enumerate(tests, start=1):
        function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

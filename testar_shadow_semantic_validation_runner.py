from __future__ import annotations

import json
from pathlib import Path


RUNNER = Path("scripts/run_shadow_semantic_validation.py")
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
    for case in payload["cases"]:
        assert set(case).isdisjoint(forbidden)
        assert set(case) == {"question", "expected_intent"}


def test_expected_intent_is_not_input_to_resolver() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    call = "result = resolve_intent(question, ctx)"
    assert call in text
    assert "resolve_intent(question, expected_intent" not in text


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
        ("reuse running shadow", test_shell_reuses_running_shadow_without_secrets),
    ]
    for index, (name, function) in enumerate(tests, start=1):
        function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()

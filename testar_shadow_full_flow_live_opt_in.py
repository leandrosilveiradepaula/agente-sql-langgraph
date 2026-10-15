from __future__ import annotations

from unittest.mock import patch

from scripts.run_shadow_full_flow_validation import main


def test_runner_refuses_live_llm_without_opt_in() -> None:
    with patch("sys.argv", ["runner", "--cases", "unread.json"]), patch.dict(
        "os.environ",
        {"LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "false"},
        clear=True,
    ), patch(
        "scripts.run_shadow_full_flow_validation.create_shadow_test_runtime",
        side_effect=AssertionError("runtime must not be created"),
    ):
        assert main() == 3


def test_runner_refuses_sql_execution_even_when_opted_in() -> None:
    with patch("sys.argv", ["runner", "--cases", "unread.json"]), patch.dict(
        "os.environ",
        {
            "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "true",
            "SHADOW_FULL_FLOW_ALLOW_LIVE_LLM": "true",
        },
        clear=True,
    ), patch(
        "scripts.run_shadow_full_flow_validation.create_shadow_test_runtime",
        side_effect=AssertionError("runtime must not be created"),
    ):
        assert main() == 4


if __name__ == "__main__":
    test_runner_refuses_live_llm_without_opt_in()
    test_runner_refuses_sql_execution_even_when_opted_in()
    print("SHADOW_LIVE_OPT_IN=PASS")

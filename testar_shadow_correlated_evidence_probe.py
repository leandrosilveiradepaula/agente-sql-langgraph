from __future__ import annotations

from unittest.mock import patch

from scripts.probe_shadow_correlated_evidence import (
    main,
    validate_evidence,
    validate_rejection,
)


def test_rejected_request_is_the_only_accepted_probe_result():
    run = validate_rejection(
        agent_run_id="test-run",
        status=422,
        response={
            "status": "rejected",
            "agent_run_id": "test-run",
            "sql": None,
            "run_id": "test-langgraph-run",
            "errors": [{"code": "INTERNAL_GENERATE_QUESTION_REQUIRED"}],
        },
    )
    assert run == "test-langgraph-run"
    for response in (
        {"status": "success", "agent_run_id": "test-run", "sql": "SELECT 1"},
        {"status": "rejected", "agent_run_id": "wrong-run", "sql": None},
    ):
        try:
            validate_rejection(agent_run_id="test-run", status=422, response=response)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe result accepted")


def test_evidence_must_match_same_agent_and_langgraph_run():
    record = {
        "agent_run_id": "test-run",
        "run_id": "test-langgraph-run",
        "status": "rejected",
        "event_type": "generate",
        "shadow_record_id": "shadow-test",
    }
    validate_evidence(
        agent_run_id="test-run", run_id="test-langgraph-run",
        status=200,
        response={"agent_run_id": "test-run", "items": [record]},
    )
    try:
        validate_evidence(
            agent_run_id="test-run", run_id="wrong",
            status=200,
            response={"agent_run_id": "test-run", "items": [record]},
        )
    except ValueError:
        pass
    else:
        raise AssertionError("unrelated evidence accepted")


def test_probe_uses_validation_gate_with_no_real_provider():
    calls = []
    def fake_request(method, path, token, payload=None):
        calls.append((method, path, payload))
        if method == "POST":
            assert payload["question"] == ""
            assert payload["correlation_metadata"]["official_flow_modified"] is False
            return 422, {
                "status": "rejected",
                "agent_run_id": payload["agent_run_id"],
                "run_id": "test-langgraph-run",
                "sql": None,
                "errors": [{"code": "INTERNAL_GENERATE_QUESTION_REQUIRED"}],
            }
        assert method == "GET"
        agent_id = calls[0][2]["agent_run_id"]
        return 200, {"agent_run_id": agent_id, "items": [{
            "agent_run_id": agent_id,
            "run_id": "test-langgraph-run",
            "event_type": "generate",
            "status": "rejected",
            "shadow_record_id": "shadow-test",
        }]}
    with patch.dict("os.environ", {
        "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "false",
        "LANGGRAPH_S2S_TOKEN": "test-only",
    }, clear=True):
        with patch("scripts.probe_shadow_correlated_evidence.request", side_effect=fake_request):
            assert main() == 0
    assert [method for method, _, _ in calls] == ["POST", "GET"]


if __name__ == "__main__":
    test_rejected_request_is_the_only_accepted_probe_result()
    test_evidence_must_match_same_agent_and_langgraph_run()
    test_probe_uses_validation_gate_with_no_real_provider()
    print("SHADOW_CORRELATED_EVIDENCE_OFFLINE=PASS")

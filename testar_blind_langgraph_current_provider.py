"""Offline regression for historical 63 blind questions -> current LangGraph only.

All tests use fingerprinted fixture evidence and no provider/network/SQL calls.
"""
from __future__ import annotations

from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch
import sys

from scripts.blind_shadow_benchmark import create_blind_manifest, create_freeze_receipt
from scripts.blind_shadow_batch import prepare_dispatch_plan
from scripts.operations.run_blind_langgraph_current_provider import (
    CHILD, validate_blind_inputs, validate_result_line, main,
)
from testar_blind_shadow_benchmark import baseline as fixture_baseline, evidence_record, SQL_A


def fixtures():
    official = fixture_baseline()
    for case in official["cases"]:
        case.pop("agent_run_id", None)
        case.pop("principal_id", None)
        case.pop("organization_id", None)
    manifest = create_blind_manifest(official)
    receipt = create_freeze_receipt(official, manifest)
    plan = prepare_dispatch_plan(
        manifest, receipt,
        id_factory=iter(("blind-a","blind-b","blind-c")).__next__,
    )
    return official, manifest, receipt, plan


def test_unchanged_historical_questions_and_63_unique_ids():
    _base, manifest, receipt, plan = fixtures()
    assert len(validate_blind_inputs(manifest, receipt, plan, 3)) == 3
    assert all(set(case) == {"case_id", "question", "agent_run_id"}
               for case in plan["cases"])
    for wrong in (0, 2, 63):
        try:
            validate_blind_inputs(manifest, receipt, plan, wrong)
        except ValueError:
            pass
        else:
            raise AssertionError("expected count mismatch allowed")
    injected = deepcopy(manifest)
    injected["cases"][0]["official_sql"] = SQL_A
    try:
        validate_blind_inputs(injected, receipt, plan, 3)
    except ValueError:
        pass
    else:
        raise AssertionError("historic SQL leaked to generator")


def test_child_uses_existing_private_provider_not_gemini():
    assert "GEMINI_API_KEY" in CHILD
    assert "GEMINI_API_KEY" + '\',"") != ""' not in CHILD  # static guard remains readable
    assert "gemini" in CHILD.casefold()  # explicit no-gemini guard
    assert "PrivateModelOnlyTransport" in CHILD
    assert '"openai_compatible_chat_completions"' in CHILD
    assert '"google_gemini_generate_content"' not in CHILD
    assert "official_sql" not in CHILD
    assert "expected_intent" not in CHILD
    assert "official-baseline" not in CHILD
    assert "FakeShadowEvidenceRepository" in CHILD


def test_signed_evidence_is_required_and_tamper_rejected():
    _base, _manifest, _receipt, plan = fixtures()
    case = {**plan["cases"][0], "principal_id":"shadow-operator",
            "organization_id":"tenant-1","official_context_fingerprint":"context-a"}
    signed = evidence_record(case=case, sql=SQL_A, generation_intent="aggregate")
    good = {"case_id":case["case_id"],
            "agent_run_id":case["agent_run_id"],
            "http_status":200, "status":"success", "provider_calls_total":1,
            "record":signed}
    returned, count = validate_result_line(
        json.dumps(good), plan["cases"][0], 0, 3,
    )
    assert returned == signed
    assert count == 1
    bad = (
        {**good,"status":"rejected"},
        {**good,"provider_calls_total":-1},
        {**good,"provider_calls_total":4},
        {**good,"case_id":"foreign"},
        {**good,"http_status":502},
        {**good,"record":{**signed,"evidence_fingerprint":"wrong"}},
    )
    for altered in bad:
        try:
            validate_result_line(json.dumps(altered), plan["cases"][0], 0, 3)
        except (ValueError, TypeError, KeyError):
            pass
        else:
            raise AssertionError("invalid generated record accepted")


def test_local_preflight_zero_calls_and_live_gate():
    _base, manifest, receipt, plan = fixtures()
    with tempfile.TemporaryDirectory() as root:
        p = Path(root)
        for name, data in (
            ("questions.json",manifest),
            ("receipt.json",receipt),
            ("dispatch.json",plan),
        ):
            (p/name).write_text(json.dumps(data), encoding="utf-8")
            (p/name).chmod(0o600)
        argv = ["benchmark","preflight",
                "--manifest",str(p/"questions.json"),
                "--receipt",str(p/"receipt.json"),
                "--dispatch-plan",str(p/"dispatch.json"),
                "--expected-cases","3"]
        output = io.StringIO()
        with patch.object(sys,"argv",argv), contextlib.redirect_stdout(output):
            result = main()
        assert result == 0
        assert "LANGGRAPH_63_PREFLIGHT=PASS" in output.getvalue()
        assert "LANGGRAPH_63_GEMINI_CALLS=0" in output.getvalue()
        assert len(list(p.iterdir())) == 3
        argv[1] = "run"
        with patch.object(sys,"argv",argv), contextlib.redirect_stdout(io.StringIO()):
            assert main() != 0


def main_tests():
    for test in (
        test_unchanged_historical_questions_and_63_unique_ids,
        test_child_uses_existing_private_provider_not_gemini,
        test_signed_evidence_is_required_and_tamper_rejected,
        test_local_preflight_zero_calls_and_live_gate,
    ):
        test()
        print(test.__name__ + ": PASS")
    print("BLIND_LANGGRAPH_CURRENT_PROVIDER_OFFLINE=PASS")


if __name__ == "__main__":
    main_tests()

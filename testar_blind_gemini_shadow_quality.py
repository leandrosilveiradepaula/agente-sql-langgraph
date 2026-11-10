"""No real provider calls: verify blind preflight, signed records and fail-closed cases."""
from __future__ import annotations

from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile

from app.domain.result_normalization import stable_fingerprint
from scripts.blind_shadow_benchmark import create_blind_manifest, create_freeze_receipt
from scripts.blind_shadow_batch import prepare_dispatch_plan
from scripts.operations.run_blind_gemini_shadow_quality import (
    _validated_inputs, _validated_child_line, _evaluate_after_generation,
    CHILD, main as command_main,
)
from testar_blind_shadow_benchmark import (
    baseline as historic_fixture, evidence_record, SQL_A,
)


def _fixture():
    baseline = historic_fixture()
    for case in baseline["cases"]:
        case.pop("agent_run_id", None)
        case.pop("principal_id", None)
        case.pop("organization_id", None)
    manifest = create_blind_manifest(baseline)
    receipt = create_freeze_receipt(baseline, manifest)
    identifiers = iter(("blind-a", "blind-b", "blind-c")).__next__
    plan = prepare_dispatch_plan(manifest, receipt, id_factory=identifiers)
    return baseline, manifest, receipt, plan


def test_blind_inputs_cannot_contain_baseline():
    baseline, manifest, receipt, plan = _fixture()
    assert len(_validated_inputs(manifest, receipt, plan, 3)) == 3
    for mutated in (
        {**manifest, "official_sql": SQL_A},
        {**manifest, "cases": [{**manifest["cases"][0], "sql": SQL_A}] + manifest["cases"][1:]},
    ):
        try:
            _validated_inputs(mutated, receipt, plan, 3)
        except ValueError:
            pass
        else:
            raise AssertionError("generation saw historical SQL")
    for count in (2, 0, 63):
        try:
            _validated_inputs(manifest, receipt, plan, count)
        except ValueError:
            pass
        else:
            raise AssertionError("case count bypassed")
    assert "official_sql" not in CHILD
    assert "baseline" not in CHILD
    assert "expected_intent" not in CHILD


def test_signed_provenance_and_post_generation_assessment():
    baseline, manifest, receipt, plan = _fixture()
    original = historic_fixture()["cases"][0]
    case = {**plan["cases"][0], "principal_id": "quality-operator",
            "organization_id": "tenant-A",
            "official_context_fingerprint": original["official_context_fingerprint"]}
    signed = evidence_record(
        case=case, sql=SQL_A, generation_intent="aggregate",
    )
    valid = {
        "case_id": case["case_id"], "agent_run_id": case["agent_run_id"],
        "record": signed, "status": "success", "http_status": 200,
        "provider_calls_total": 1,
    }
    captured, count = _validated_child_line(
        json.dumps(valid), plan["cases"][0], 0, 3,
    )
    assert count == 1
    assert captured["evidence_fingerprint"] == signed["evidence_fingerprint"]
    correlation, report = _evaluate_after_generation(
        manifest, receipt, plan, baseline, [signed],
    )
    assert len(correlation["records"]) == 1
    assert report["benchmark_fingerprint"] == stable_fingerprint(baseline)
    assert report["post_generation_correlation_verified"] is True
    assert report["financial_parity_proven"] is False
    assert report["summary"]["inconclusivo"] == 1
    assert report["summary"]["sem_evidencia"] == 2
    assert report["cases"][0]["sql_verdict"] == "normalized_sql_match"
    assert report["cases"][0]["reason"] == "historical_tenant_provenance_unattested"
    assert report["provider_calls"] == 0


def test_unattested_or_tampered_child_rejected():
    _base, _manifest, _receipt, plan = _fixture()
    original = historic_fixture()["cases"][0]
    case = {**plan["cases"][0], "principal_id": "quality-operator",
            "organization_id": "tenant-A",
            "official_context_fingerprint": original["official_context_fingerprint"]}
    signed = evidence_record(case=case, sql=SQL_A, generation_intent="aggregate")
    good = {"case_id": case["case_id"], "agent_run_id": case["agent_run_id"],
            "record":signed, "status":"success", "http_status":200,
            "provider_calls_total":1}
    for edit in (
        {"provider_calls_total": 999},
        {"provider_calls_total": -1},
        {"case_id": "wrong"},
        {"status": "rejected"},
        {"http_status": 500},
        {"record":{**signed, "evidence_fingerprint":"tampered"}},
    ):
        invalid = {**good, **edit}
        try:
            _validated_child_line(json.dumps(invalid), plan["cases"][0], 0, 2)
        except (ValueError, TypeError, KeyError):
            pass
        else:
            raise AssertionError("invalid signed record was accepted")


def test_preflight_creates_no_artifacts_or_provider_calls():
    import sys
    from unittest.mock import patch
    _baseline, manifest, receipt, plan = _fixture()
    with tempfile.TemporaryDirectory() as root:
        folder = Path(root)
        for filename, value in (
            ("manifest.json", manifest), ("receipt.json", receipt),
            ("plan.json", plan),
        ):
            target = folder / filename
            target.write_text(json.dumps(value), encoding="utf-8")
            target.chmod(0o600)
        args = [
            "shadow-quality","preflight", "--manifest",str(folder / "manifest.json"),
            "--receipt",str(folder / "receipt.json"),
            "--dispatch-plan",str(folder / "plan.json"),
            "--expected-cases","3",
        ]
        out = io.StringIO()
        with patch.object(sys, "argv", args), contextlib.redirect_stdout(out):
            status = command_main()
        assert status == 0
        assert "BLIND_GEMINI_PREFLIGHT=PASS" in out.getvalue()
        assert "BLIND_GEMINI_PROVIDER_CALLS=0" in out.getvalue()
        assert len(list(folder.iterdir())) == 3
        # Live mode remains impossible without a distinct explicit approval.
        args[1] = "run"
        with patch.object(sys, "argv", args), contextlib.redirect_stdout(io.StringIO()):
            assert command_main() != 0


def main():
    for test in (
        test_blind_inputs_cannot_contain_baseline,
        test_signed_provenance_and_post_generation_assessment,
        test_unattested_or_tampered_child_rejected,
        test_preflight_creates_no_artifacts_or_provider_calls,
    ):
        test()
        print(test.__name__ + ": PASS")
    print("BLIND_GEMINI_SHADOW_QUALITY_OFFLINE=PASS")


if __name__ == "__main__":
    main()

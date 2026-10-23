"""Executable negative/positive tests for the independent blind benchmark.

Pure synthetic evidence; never contacts Gemini, n8n, PostgreSQL or an SQL
engine. Both test sources use different synthetic schemas and filters.
"""
from __future__ import annotations

import contextlib
import io
import json
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from app.domain.shadow_evidence_types import build_generate_shadow_record
from scripts.blind_shadow_benchmark import (
    create_blind_manifest,
    evaluate_blind_benchmark,
    load_baseline,
    main,
    verify_blind_manifest,
)

QUESTION_A = "Show aggregated values from warehouse records for the first quarter"
QUESTION_B = "Count active records in an independent billing ledger"
SQL_A = "SELECT SUM(net_amount) AS total FROM ledger.records WHERE quarter_id = 202601"
SQL_B = "SELECT COUNT(*) FROM billing.invoice_archive WHERE billing_state = 'open'"

def baseline():
    return {
        "contract_version": "1",
        "suite": "synthetic-blind-v1",
        "cases": [
            {
                "case_id": "case-a",
                "question": QUESTION_A,
                "agent_run_id": "official-run-a",
                "principal_id": "operator-one",
                "organization_id": "tenant-A",
                "official_sql": SQL_A,
                "official_intent": "aggregate",
                "official_provider": "google_gemini",
                "official_model": "model-neutral-v1",
                "official_context_fingerprint": "context-a",
            },
            {
                "case_id": "case-b",
                "question": QUESTION_B,
                "agent_run_id": "official-run-b",
                "principal_id": "operator-one",
                "organization_id": "tenant-B",
                "official_sql": SQL_B,
                "official_intent": "count",
                "official_provider": "google_gemini",
                "official_model": "model-neutral-v1",
                "official_context_fingerprint": "context-b",
            },
            {
                "case_id": "case-c",
                "question": "Independent new question without official baseline",
                "agent_run_id": "official-run-c",
                "principal_id": "operator-one",
                "organization_id": "tenant-B",
            },
        ],
    }


def evidence_record(
    *,
    case: dict,
    sql: str,
    generation_intent: str,
    model: str = "model-neutral-v1",
    run_id: str | None = None,
    final_sql: str | None = None,
):
    run = run_id or case["agent_run_id"]
    state = {
        "generated_sql": sql,
        "current_sql": final_sql or sql,
        "intent": generation_intent,
        "context_version": "synthetic-context-v1",
        "context_fingerprint": case.get("official_context_fingerprint", "synthetic-fp"),
        "sql_generation_result": {
            "provider_name": "google_gemini",
            "provider_model": model,
        },
    }
    request = {
        "question": case["question"],
        "principal": {
            "id": case["principal_id"],
            "organization_id": case["organization_id"],
            "profile": "synthetic",
        },
    }
    return build_generate_shadow_record(
        shadow_record_id="shadow-" + run,
        agent_run_id=case["agent_run_id"],
        run_id="langgraph-" + run,
        created_at="2026-10-23T00:00:00Z",
        completed_at="2026-10-23T00:00:01Z",
        status="success",
        request=request,
        state=state,
        response={"status": "success", "gates": {}},
    )


def export(*records):
    return {"contract_version": "1", "records": list(records)}


def evaluate(base, records):
    return evaluate_blind_benchmark(base, create_blind_manifest(base), export(*records))


def test_prepare_strips_all_evaluation_and_provenance() -> None:
    original = baseline()
    frozen = deepcopy(original)
    manifest = create_blind_manifest(original)
    assert original == frozen
    assert set(manifest) == {"contract_version", "suite", "cases"}
    assert all(set(x) == {"case_id", "question"} for x in manifest["cases"])
    serialized = json.dumps(manifest, ensure_ascii=False)
    for sensitive in (
        SQL_A, SQL_B, "official_provider", "official_model",
        "context-a", "expected_intent", "official_run",
        "golden", "organization_id", "tenant-A",
    ):
        assert sensitive not in serialized
    assert "question" in serialized


def test_real_post_generation_comparator_handles_match_divergence_and_missing() -> None:
    base = baseline()
    a, b, _ = base["cases"]
    record_a = evidence_record(
        case=a, sql="select sum(net_amount) as total from ledger.records where quarter_id=202601;",
        generation_intent="aggregate",
    )
    record_b = evidence_record(
        case=b,
        sql="SELECT COUNT(*) FROM billing.invoice_archive WHERE billing_state = 'closed'",
        generation_intent="count",
    )
    report = evaluate(base, [record_a, record_b])
    assert report["case_count"] == 3
    assert report["summary"] == {
        "corresponde": 1, "diverge": 1, "inconclusivo": 0, "sem_evidencia": 1
    }, report
    first, second, third = report["cases"]
    assert first["sql_verdict"] == "normalized_sql_match", first
    assert first["provider_status"] == "matched"
    assert first["context_status"] == "matched"
    assert first["tenant_identity_attested"] is True
    assert "predicates" in second["different_facets"]
    assert second["status"] == "diverge"
    assert third["reason"] == "shadow_record_missing"
    assert report["financial_parity_proven"] is False
    assert report["financial_execution_status"] == "nao_autorizado_executar"
    assert report["provider_calls"] == 0 and report["real_sql_executed"] is False
    data = json.dumps(report, ensure_ascii=False)
    for forbidden in (
        QUESTION_A, QUESTION_B, SQL_A, SQL_B, "net_amount",
        "quarter_id", "invoice_archive", "'closed'",
    ):
        assert forbidden not in data


def test_no_official_sql_cannot_prove_sql_parity() -> None:
    base = baseline()
    case = base["cases"][2]
    row = evidence_record(
        case=case, sql="SELECT count(*) FROM generic_items", generation_intent="count"
    )
    result = evaluate(base, [row])["cases"][2]
    assert result["status"] == "sem_evidencia"
    assert result["reason"] == "official_sql_not_captured"


def test_ambiguity_identity_tenant_and_question_all_fail_closed() -> None:
    base = baseline()
    case = base["cases"][0]
    match = evidence_record(case=case, sql=SQL_A, generation_intent="aggregate")
    duplicate_attempt = evidence_record(
        case=case, sql=SQL_A, generation_intent="aggregate", run_id="retry-a"
    )
    res = evaluate(base, [match, duplicate_attempt])["cases"][0]
    assert res["status"] == "inconclusivo"
    assert res["reason"] == "shadow_attempt_ambiguous"

    for field, incorrect in (
        ("question", "Injected different question"),
        ("agent_run_id", "foreign-run"),
    ):
        tampered_base = deepcopy(base)
        tampered_base["cases"][0][field] = incorrect
        res = evaluate(tampered_base, [match])["cases"][0]
        assert res["status"] in {"inconclusivo", "sem_evidencia"}

    wrong_tenant = deepcopy(base)
    wrong_tenant["cases"][0]["organization_id"] = "tenant-B"
    result = evaluate(wrong_tenant, [match])["cases"][0]
    assert result["status"] == "inconclusivo"
    assert result["reason"] == "correlation_mismatch"


def test_provider_or_intent_mismatch_and_repair_never_count_as_parity() -> None:
    base = baseline()
    case = base["cases"][0]
    wrong_model = evidence_record(
        case=case, sql=SQL_A, generation_intent="aggregate", model="model-neutral-v2"
    )
    result = evaluate(base, [wrong_model])["cases"][0]
    assert result["status"] == "inconclusivo"
    assert result["provider_status"] == "mismatched"
    assert result["sql_verdict"] == "normalized_sql_match"

    wrong_intent = evidence_record(
        case=case, sql=SQL_A, generation_intent="different_intent"
    )
    result = evaluate(base, [wrong_intent])["cases"][0]
    assert result["status"] == "diverge"
    assert result["intent_status"] == "identifier_mismatch"

    repaired = evidence_record(
        case=case, sql="SELECT SUM(net_amount) FROM ledger.records",
        final_sql=SQL_A, generation_intent="aggregate"
    )
    result = evaluate(base, [repaired])["cases"][0]
    assert result["status"] == "inconclusivo"
    assert result["requires_reapproval"] is True


def test_blind_intake_can_never_contain_expected_fields() -> None:
    base = baseline()
    original = create_blind_manifest(base)
    for attacker in (
        {**original, "official_sql": SQL_A},
        {**original, "cases": [{**original["cases"][0], "sql": SQL_A}] + original["cases"][1:]},
        {**original, "cases": [{**original["cases"][0], "question": "different"}] + original["cases"][1:]},
    ):
        try:
            verify_blind_manifest(base, attacker)
        except ValueError:
            pass
        else:
            raise AssertionError("baseline leaked into blind intake")
    invalid = deepcopy(base)
    invalid["cases"][0]["golden_answer"] = {"amount": "999.99"}
    try:
        load_baseline(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("unsupported benchmark payload accepted")


def test_signed_evidence_tamper_prevents_full_evaluation() -> None:
    base = baseline()
    record = evidence_record(
        case=base["cases"][0], sql=SQL_A, generation_intent="aggregate"
    )
    tampered = deepcopy(record)
    tampered["generated_sql"] = "SELECT 1 FROM forbidden_schema.foreign_table"
    try:
        evaluate(base, [tampered])
    except Exception:
        pass
    else:
        raise AssertionError("tampered fingerprint accepted")


def test_cli_is_two_phase_offline_and_private(tmp=None) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        work = Path(temporary)
        baseline_path = work / "baseline.json"
        manifest_path = work / "manifest.json"
        evidence_path = work / "evidence.json"
        result_path = work / "report.json"
        baseline_path.write_text(json.dumps(baseline()), encoding="utf-8")
        row = evidence_record(
            case=baseline()["cases"][0], sql=SQL_A, generation_intent="aggregate"
        )
        evidence_path.write_text(json.dumps(export(row)), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            with patch("sys.argv", [
                "runner", "prepare", "--baseline", str(baseline_path),
                "--output", str(manifest_path),
            ]):
                assert main() == 0
        assert "SELECT" not in stdout.getvalue()
        assert "questions_only" in stdout.getvalue()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        verify_blind_manifest(baseline(), manifest)

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            with patch("sys.argv", [
                "runner", "evaluate", "--baseline", str(baseline_path),
                "--manifest", str(manifest_path), "--evidence", str(evidence_path),
                "--output", str(result_path),
            ]):
                assert main() == 1  # Two missing records are NOT a pass.
        assert "SELECT" not in stdout.getvalue()
        assert result_path.exists()
        assert json.loads(result_path.read_text(encoding="utf-8"))["summary"]["sem_evidencia"] == 2

        with contextlib.redirect_stdout(io.StringIO()):
            with patch("sys.argv", [
                "runner", "prepare", "--baseline", str(baseline_path),
                "--output", str(manifest_path),
            ]):
                assert main() == 2  # Never overwrite a frozen manifest.

        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            with patch.dict("os.environ", {
                "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "true"
            }):
                with patch("sys.argv", [
                    "runner", "prepare", "--baseline", str(baseline_path),
                    "--output", str(work / "new-manifest.json"),
                ]):
                    assert main() == 3
        assert "live_execution_flags_present" in stdout.getvalue()


def main_tests() -> None:
    tests = (
        test_prepare_strips_all_evaluation_and_provenance,
        test_real_post_generation_comparator_handles_match_divergence_and_missing,
        test_no_official_sql_cannot_prove_sql_parity,
        test_ambiguity_identity_tenant_and_question_all_fail_closed,
        test_provider_or_intent_mismatch_and_repair_never_count_as_parity,
        test_blind_intake_can_never_contain_expected_fields,
        test_signed_evidence_tamper_prevents_full_evaluation,
        test_cli_is_two_phase_offline_and_private,
    )
    for test in tests:
        test()
        print(test.__name__ + ": PASS")
    print("BLIND_SHADOW_BENCHMARK_OFFLINE=PASS")


if __name__ == "__main__":
    main_tests()

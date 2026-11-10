"""Real signed evidence fixtures, offline. No n8n, LLM, network or financial SQL."""
from __future__ import annotations

from copy import deepcopy

from app.domain.result_normalization import stable_fingerprint
from scripts.blind_shadow_benchmark import (
    create_blind_manifest, create_freeze_receipt, evaluate_blind_benchmark,
)
from scripts.blind_shadow_batch import (
    prepare_dispatch_plan, verify_dispatch_plan,
    collect_post_generation_correlations, bind_baseline_for_evaluation,
)
from testar_blind_shadow_benchmark import (
    baseline as fixture_baseline, evidence_record, export, SQL_A,
)


def _suite():
    base = fixture_baseline()
    # Historic n8n records do not identify a NEW Shadow attempt.
    for case in base["cases"]:
        case.pop("agent_run_id", None)
        case.pop("principal_id", None)
        case.pop("organization_id", None)
    blind = create_blind_manifest(base)
    freeze = create_freeze_receipt(base, blind)
    factory = iter(("blind-run-a", "blind-run-b", "blind-run-c")).__next__
    dispatch = prepare_dispatch_plan(blind, freeze, id_factory=factory)
    return base, blind, freeze, dispatch


def _record(case, original):
    observed = {
        **case,
        "principal_id": "operator-one",
        "organization_id": original["organization_id"],
        "official_context_fingerprint": original.get(
            "official_context_fingerprint", "context-a",
        ),
    }
    return evidence_record(
        case=observed, sql=SQL_A, generation_intent="aggregate",
    )


def test_frozen_baseline_correlates_only_after_generate():
    base, blind, freeze, dispatch = _suite()
    assert stable_fingerprint(blind) == dispatch["manifest_fingerprint"]
    assert all(set(c) == {"case_id", "question", "agent_run_id"}
               for c in dispatch["cases"])
    assert "official_sql" not in repr(dispatch)
    assert "official_intent" not in repr(dispatch)
    original = fixture_baseline()
    record = _record(dispatch["cases"][0], original["cases"][0])
    evidence = export(record)
    correlation = collect_post_generation_correlations(
        blind, freeze, dispatch, evidence,
    )
    assert len(correlation["records"]) == 1
    assert set(correlation["records"][0]) == {
        "case_id", "agent_run_id", "run_id", "shadow_record_id",
        "evidence_fingerprint", "principal_id", "organization_id",
    }
    enriched = bind_baseline_for_evaluation(
        base, blind, freeze, dispatch, correlation, evidence,
    )
    assert enriched["cases"][0]["agent_run_id"] == dispatch["cases"][0]["agent_run_id"]
    assert "agent_run_id" not in base["cases"][0]
    report = evaluate_blind_benchmark(
        base, blind, evidence, freeze,
        dispatch_plan=dispatch, correlation=correlation,
    )
    assert report["post_generation_correlation_verified"] is True
    assert report["summary"] == {
        "corresponde": 1, "diverge": 0, "inconclusivo": 0, "sem_evidencia": 2,
    }, report
    assert report["benchmark_fingerprint"] == stable_fingerprint(base)
    assert report["financial_parity_proven"] is False
    assert report["real_sql_executed"] is False
    assert report["provider_calls"] == 0


def test_foreign_duplicate_and_changed_evidence_fail_closed():
    base, blind, freeze, dispatch = _suite()
    original = fixture_baseline()
    row = _record(dispatch["cases"][0], original["cases"][0])
    for altered in (
        export(row, row),
        export({**row, "agent_run_id": "foreign-run"}),
        export({**row, "question": "changed question"}),
        export({**row, "evidence_fingerprint": "invalid"}),
    ):
        try:
            collect_post_generation_correlations(blind, freeze, dispatch, altered)
        except (ValueError, TypeError, KeyError):
            pass
        else:
            raise AssertionError("non-unique or tampered evidence accepted")
    evidence = export(row)
    correlation = collect_post_generation_correlations(
        blind, freeze, dispatch, evidence,
    )
    modified = deepcopy(correlation)
    modified["records"][0]["run_id"] = "incorrect-attempt"
    for invalid in (modified, None):
        try:
            evaluate_blind_benchmark(
                base, blind, evidence, freeze,
                dispatch_plan=dispatch, correlation=invalid,
            )
        except (ValueError, TypeError, KeyError):
            pass
        else:
            raise AssertionError("unverified or missing correlation accepted")


def test_frozen_receipt_and_dispatch_plan_are_immutable():
    base, blind, freeze, dispatch = _suite()
    for field, value in (("manifest_fingerprint", "bad"), ("suite", "other")):
        modified = deepcopy(dispatch)
        modified[field] = value
        try:
            verify_dispatch_plan(blind, freeze, modified)
        except ValueError:
            pass
        else:
            raise AssertionError("changed dispatch plan accepted")
    bad = deepcopy(blind)
    bad["cases"][0]["official_sql"] = SQL_A
    try:
        prepare_dispatch_plan(bad, freeze)
    except ValueError:
        pass
    else:
        raise AssertionError("historical answer leaked into dispatch")

    bad_receipt = deepcopy(freeze)
    bad_receipt["case_count"] = 1
    try:
        prepare_dispatch_plan(blind, bad_receipt)
    except ValueError:
        pass
    else:
        raise AssertionError("incorrect case count accepted")


def test_63_cases_generate_unique_blind_ids():
    base = {
        "contract_version": "1", "suite": "synthetic-63",
        "cases": [
            {"case_id": f"case-{i:03}", "question": f"Independent question {i}"}
            for i in range(63)
        ],
    }
    blind = create_blind_manifest(base)
    receipt = create_freeze_receipt(base, blind)
    dispatch = prepare_dispatch_plan(blind, receipt)
    assert len(dispatch["cases"]) == 63
    assert len({case["agent_run_id"] for case in dispatch["cases"]}) == 63
    assert len(collect_post_generation_correlations(
        blind, receipt, dispatch, export(),
    )["records"]) == 0


def main():
    for test in (
        test_frozen_baseline_correlates_only_after_generate,
        test_foreign_duplicate_and_changed_evidence_fail_closed,
        test_frozen_receipt_and_dispatch_plan_are_immutable,
        test_63_cases_generate_unique_blind_ids,
    ):
        test()
        print(test.__name__ + ": PASS")
    print("BLIND_SHADOW_BATCH_OFFLINE=PASS")


if __name__ == "__main__":
    main()

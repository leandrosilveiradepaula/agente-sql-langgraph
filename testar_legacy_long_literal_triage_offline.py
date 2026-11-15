"""Public, safe offline invariant tests; no private source or business literals."""
from __future__ import annotations
from pathlib import Path
import json
from scripts.operations.legacy_long_literal_triage_offline import (
    _candidate_for_line, InventoryRejected, classify_source_literals,
    validate_review_policy,
)
ROOT=Path(__file__).resolve().parent
REPORT=ROOT/"docs/audits/legacy-n8n-long-literal-triage-20261112.json"

def test_automatic_classification_is_conservative():
    policy=validate_review_policy(json.loads(
        (ROOT/"docs/audits/legacy-n8n-review-signal-policy-v1.json").read_text()
    ))
    assert _candidate_for_line(22,"const result = financeMetric;","planDreMensalAnalitica",policy)=="F"
    assert _candidate_for_line(19,"const providerVersion = 1","toText",policy)=="T"
    assert _candidate_for_line(52,"const responseStatus = 'ready'","getHeader",policy)=="S"
    assert _candidate_for_line(8,"const random = 1",None,policy)=="U"

def test_all_long_literals_have_only_sanitized_tuple_pointers():
    r=json.loads(REPORT.read_text())
    assert r["source"]=="PUBLISHED_WORKFLOW_MATCHED_PRIVATE_BASELINE"
    assert r["all_literal_occurrences"]==3403
    assert r["long_literal_occurrences_anchored"]==1987
    assert r["short_literal_occurrences_unanchored"]==1416
    policy=json.loads(
        (ROOT/"docs/audits/legacy-n8n-review-signal-policy-v1.json").read_text()
    )
    expected_digest=__import__("hashlib").sha256(
        json.dumps(policy,ensure_ascii=True,sort_keys=True,separators=(",",":")).encode()
    ).hexdigest()
    assert r["review_policy_sha256"]==expected_digest
    assert r["code_nodes"]==41
    assert len(r["nodes"])==41
    assert len(r["candidate_ledger"])==1987
    assert sum(n["total_literal_count"] for n in r["nodes"])==3403
    assert sum(n["long_anchored_count"] for n in r["nodes"])==1987
    assert sum(n["short_unanchored_count"] for n in r["nodes"])==1416
    assert sum(r["candidate_totals"][k] for k in "FTSU")==1987
    assert r["candidate_totals"]["SHORT_UNANCHORED"]==1416
    assert len({n["ordinal"] for n in r["nodes"]})==41
    assert all(len(n["code_sha256"])==64 for n in r["nodes"])
    assert all(len(e)==5 and e[3] in ("s","d","t") and e[4] in "FTSU" for e in r["candidate_ledger"])
    assert r["raw_literals_published"] is False
    assert r["literal_content_hashes_published"] is False
    assert r["financial_meaning_approved"] is False
    assert r["benchmark_accessed"] is False
    assert r["source_sql_executed"] is False


def test_policy_data_cannot_grant_accounting_authority_or_run_sql():
    from copy import deepcopy
    raw=json.loads((ROOT/"docs/audits/legacy-n8n-review-signal-policy-v1.json").read_text())
    assert validate_review_policy(raw)["human_financial_approval"] is False
    mutations=(
        {"human_financial_approval":True},
        {"source_use":"INJECT_TO_GENERATOR"},
        {"review_stems":["financeira","financeira"]},
        {"review_stems":["DROP TABLE"]},
        {"transitional_review_nodes":[6]},
        {"business_review_nodes":[True]},
    )
    for modification in mutations:
        bad=deepcopy(raw)
        bad.update(modification)
        try:
            validate_review_policy(bad)
        except InventoryRejected:
            pass
        else:
            raise AssertionError("Audit policy accepted unreviewed configuration")


def test_unsafe_baseline_fails_closed():
    try:
        classify_source_literals({}, {}, {}, {}, {})
    except InventoryRejected:
        pass
    else:
        raise AssertionError("Invalid workflow accepted")

def main():
    tests=sorted((name,fn) for name,fn in globals().items() if name.startswith("test_") and callable(fn))
    for name,fn in tests:
        fn()
        print("PASS",name)
    print("TOTAL_TESTS",len(tests))

if __name__=="__main__":
    main()

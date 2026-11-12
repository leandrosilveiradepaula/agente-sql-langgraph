"""CI regression for AST source positions and privacy, without source payload."""
from __future__ import annotations
import json
import gzip
from copy import deepcopy
from pathlib import Path
from scripts.operations.legacy_ast_literal_evidence import (
    AstLiteralEvidenceRejected, verify_ast_literal_evidence,
)

ROOT=Path(__file__).resolve().parent
NEW=ROOT/"docs/audits/legacy-n8n-ast-all-literals-20261112.json.gz"
OLD=ROOT/"docs/audits/legacy-n8n-long-literal-triage-20261112.json"


def _load() -> tuple[dict,dict]:
    with gzip.open(NEW,"rt",encoding="utf-8") as source:
        ast_evidence=json.load(source)
    return ast_evidence,json.loads(OLD.read_text())


def test_ast_full_inventory_reconciles_distinct_historical_census():
    new,old=_load()
    facts=verify_ast_literal_evidence(new,old)
    assert facts["code_nodes"]==41
    assert facts["ast_syntax_literals"]==3698
    assert facts["ast_short"]==1719
    assert facts["ast_long"]==1979
    assert facts["delta_from_legacy"]==295
    assert facts["changed_ordinal_count"]==18
    assert new["candidate_counts"]=={"F":1732,"T":371,"S":830,"U":765}


def test_ast_public_inventory_has_no_source_or_business_literal_values():
    new,_=_load()
    assert new["financial_semantics_approved"] is False
    assert new["benchmark_accessed"] is False
    assert new["node_code_executed"] is False
    assert new["customer_financial_sql_executed"] is False
    assert all(len(entry)==6 for node in new["nodes"] for entry in node["entries"])
    assert not any(
        key in new for key in ("workflow","js_code","literal_values","sql","prompts","secrets")
    )



def test_compressed_audit_evidence_is_inspected_by_secret_scanner():
    from scripts.check_secrets import _read_candidate_text
    scanned=json.loads(_read_candidate_text(NEW))
    verified,_=_load()
    assert scanned["syntax_literal_total"]==verified["syntax_literal_total"]
    assert scanned["raw_literal_values_published"] is False


def test_tampered_nodes_and_positions_reject_before_claims():
    raw,old=_load()
    attempts=(
        lambda t: t["nodes"][0]["entries"][0].__setitem__(1,999999),
        lambda t: t["nodes"][0]["entries"][0].__setitem__(3,"SQL"),
        lambda t: t["nodes"][0]["entries"][0].__setitem__(5,"APPROVED"),
        lambda t: t["nodes"][0].__setitem__("code_sha256","unbound"),
        lambda t: t.__setitem__("financial_semantics_approved",True),
        lambda t: t.__setitem__("benchmark_accessed",True),
        lambda t: t.__setitem__("syntax_literal_total",1),
        lambda t: t["nodes"][0].__setitem__("syntax_literal_count",1),
    )
    for tamper in attempts:
        altered=deepcopy(raw)
        tamper(altered)
        try:
            verify_ast_literal_evidence(altered,old)
        except AstLiteralEvidenceRejected:
            pass
        else:
            raise AssertionError("Changed AST provenance accepted")


def main():
    tests=sorted((n,f) for n,f in globals().items() if n.startswith("test_") and callable(f))
    for name,fn in tests:
        fn()
        print("PASS",name)
    print("TOTAL_TESTS",len(tests))

if __name__=="__main__":
    main()

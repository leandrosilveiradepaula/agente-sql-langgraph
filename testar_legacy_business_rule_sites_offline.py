"""Source-accountability guards; never require private n8n export in CI."""
from __future__ import annotations

import json
from pathlib import Path
from copy import deepcopy
from scripts.operations.legacy_business_rule_sites_offline import (
    _ANCHORS, inspect_anchor, InventoryRejected,
)

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "docs/audits/legacy-n8n-business-rule-sites-20261112.json"


def test_anchor_hashes_deterministic_without_sensitive_output():
    source = ["const sample = 'PRIVATE_CLIENT_PAYLOAD';", "const formula = 3;", "return formula;"]
    import hashlib
    fingerprint = hashlib.sha256(source[1].encode("utf-8")).hexdigest()
    a = inspect_anchor(source, 2, fingerprint)
    assert a == inspect_anchor(deepcopy(source), 2, fingerprint)
    assert len(a["line_sha256"]) == 64
    assert "PRIVATE_CLIENT_PAYLOAD" not in json.dumps(a)


def test_anchor_drift_and_range_fail_closed():
    src = ["const formula = 3;"]
    for line, token in ((2, "a"*64), (0, "b"*64), (1, "c"*64)):
        try:
            inspect_anchor(src, line, token)
        except InventoryRejected:
            pass
        else:
            raise AssertionError((line, token))


def test_public_source_report_provenance_and_coverage():
    result = json.loads(REPORT.read_text())
    assert result["code_nodes_indexed"] == 41
    assert result["source_nodes"] == 68
    assert result["postgres_nodes_indexed"] == 11
    assert result["unique_pinned_sites"] == 24
    assert result["nodes_with_pinned_sites"] == 10
    assert len(result["code_coverage"]) == 41
    assert len(result["sites"]) == len(_ANCHORS)
    assert len({(x["node_ordinal"], x["start_line"]) for x in result["sites"]}) == 24
    assert len({n["node_ordinal"] for n in result["code_coverage"]}) == 41
    assert all(x["financial_value_imported"] is False for x in result["sites"])
    assert result["accounting_approval"] is False
    assert result["benchmark_accessed"] is False
    assert result["source_sql_executed"] is False
    raw = REPORT.read_text().lower()
    for secret in ("select * from", "private_client_payload", "access_token", "authorization: bearer"):
        assert secret not in raw
    for node in result["code_coverage"]:
        assert len(node["code_sha256"]) == 64
        assert node["line_count"] > 0


def main():
    tests = sorted((n,x) for n,x in globals().items() if n.startswith("test_") and callable(x))
    for name, fn in tests:
        fn()
        print("PASS",name)
    print("TOTAL_TESTS",len(tests))


if __name__ == "__main__":
    main()

from __future__ import annotations

"""Integration test of context parity through the *real* read-only repository.

Runs exclusively against the disposable PostgreSQL service in GitHub Actions.
This script never modifies database state or calls a SQL-financial executor.
"""

import argparse
import json
import os
from pathlib import Path

from psycopg.conninfo import make_conninfo

from app.adapters.postgres.context_repository import PostgresContextRepository
from scripts.audit_semantic_candidate_parity_readonly import (
    compare_semantic_snapshots,
    parse_parity_policy,
)
from scripts.preview_semantic_candidate_readonly import (
    evaluate_in_memory_preflight,
    synthesize_candidate_snapshot,
)


ROOT = Path(__file__).resolve().parents[2]
POLICY_FILE = ROOT / "semantic_context/candidate_parity_demo_finance_v11.json"
EXPECTED_CODES = {
    "matching": set(),
    "rule_mutation": {"ALLOWED_RULE_PAYLOAD_MISMATCH"},
    "entity_mutation": {
        "ALLOWED_RULE_PAYLOAD_MISMATCH",
        "COLLECTION_MISMATCH_ENTITIES",
    },
}


def run_check(mode: str) -> None:
    if mode not in EXPECTED_CODES:
        raise ValueError("unsupported test mode")
    if any((
        os.environ.get("V11_DISPOSABLE_POSTGRES_TEST") != "true",
        os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") != "false",
        os.environ.get("PGHOST") != "127.0.0.1",
        os.environ.get("PGPORT") != "5432",
        os.environ.get("PGDATABASE") != "synthetic_ci",
        os.environ.get("PGUSER") != "synthetic_parity_reader",
    )):
        raise RuntimeError("must run with the scoped disposable CI reader")

    policy = parse_parity_policy(
        json.loads(POLICY_FILE.read_text(encoding="utf-8"))
    )
    dsn = make_conninfo(
        "",
        host=os.environ["PGHOST"],
        port=os.environ["PGPORT"],
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
    )
    snapshots = {
        kind: PostgresContextRepository(
            dsn=dsn,
            semantic_agent_version=policy[kind],
            context_schema="test_v11_good",
        ).load_active_context(user_profile="synthetic_ci")
        for kind in ("source_version", "candidate_version")
    }
    source, candidate = snapshots["source_version"], snapshots["candidate_version"]
    report = compare_semantic_snapshots(source, candidate, policy)

    if mode == "matching":
        # Previewing an immutable clone of v10 must reproduce precisely the
        # fingerprint observed after migration to v11 in ephemeral Postgres.
        virtual = synthesize_candidate_snapshot(source, policy)
        assert virtual["fingerprint"] == candidate["fingerprint"]
        preview_report = evaluate_in_memory_preflight(source, policy)
        assert preview_report["parity_status"] == "parity_match"
        assert preview_report["candidate_fingerprint"] == candidate["fingerprint"]
        assert preview_report["persisted_candidate"] is False
        assert preview_report["activation_authorized"] is False
        print("V11_IN_MEMORY_CANDIDATE_FINGERPRINT=PASS")

    if not source.get("fingerprint") or not candidate.get("fingerprint"):
        raise AssertionError("missing versioned fingerprints")
    if source["fingerprint"] == candidate["fingerprint"]:
        raise AssertionError("candidate fingerprint did not change")
    if "temporal_planning" in source["component_configs"]:
        raise AssertionError("synthetic baseline unexpectedly contains temporal config")
    if candidate["component_configs"].get("temporal_planning", {}).get(
        "date_binding_strategy"
    ) != "configured_metric_source_date":
        raise AssertionError("candidate configuration not loaded by real reader")

    expected_codes = EXPECTED_CODES[mode]
    observed_codes = set(report["blocking_codes"])
    if not expected_codes:
        assert report["status"] == "parity_match", report
        assert not observed_codes, observed_codes
    else:
        assert report["status"] == "blocked", report
        assert expected_codes <= observed_codes, (mode, observed_codes)

    assert report["read_only"] is True
    assert report["activation_authorized"] is False
    assert report["financial_validation_complete"] is False
    assert report["benchmark_access"] is False
    assert report["llm_calls"] == 0
    assert report["real_sql_execution"] is False
    print("V11_POSTGRES_CONTEXT_READER_PARITY=PASS", mode)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=sorted(EXPECTED_CODES), required=True)
    args = parser.parse_args()
    try:
        run_check(args.mode)
        return 0
    except Exception as exc:
        # Connection errors can include credentials; never print exception text.
        print("V11_POSTGRES_CONTEXT_READER_PARITY=FAIL",
              args.mode, type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

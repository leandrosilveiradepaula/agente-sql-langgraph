"""Offline bridge from a frozen questions-only suite to *new* Shadow run evidence.

PREPARE may only see the blind manifest and its integrity receipt. BIND may
only see the dispatch plan and fingerprinted, post-generation Shadow evidence.
Neither action reads the historic official SQL, calls a model, dispatches HTTP,
or executes SQL. The evaluation-only baseline is joined later, in memory.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import stat
import uuid
from typing import Any

from app.domain.result_normalization import stable_fingerprint
from app.domain.shadow_evidence_types import validate_shadow_run_record

VERSION = "1"
MAX_CASES = 256
MAX_JSON_BYTES = 64 * 1024 * 1024
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PLAN_KEYS = frozenset({"contract_version", "suite", "manifest_fingerprint", "cases"})
_RECEIPT_KEYS = frozenset({
    "contract_version", "suite", "case_count",
    "baseline_fingerprint", "manifest_fingerprint",
})
_LINK_KEYS = frozenset({
    "case_id", "agent_run_id", "run_id", "shadow_record_id",
    "evidence_fingerprint", "principal_id", "organization_id",
})


def _identifier(value: Any) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _require_questions(manifest: Any, receipt: Any) -> list[dict[str, str]]:
    if not isinstance(manifest, Mapping) or set(manifest) != {
        "contract_version", "suite", "cases",
    } or manifest.get("contract_version") != VERSION or not _identifier(manifest.get("suite")):
        raise ValueError("blind_manifest_invalid")
    if not isinstance(receipt, Mapping) or set(receipt) != _RECEIPT_KEYS:
        raise ValueError("freeze_receipt_invalid")
    cases = manifest["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError("blind_case_count_invalid")
    seen = set()
    for case in cases:
        if not isinstance(case, Mapping) or set(case) != {"case_id", "question"}:
            raise ValueError("blind_case_contains_expectation")
        if not _identifier(case.get("case_id")) or case["case_id"] in seen:
            raise ValueError("blind_case_identity_invalid")
        if not isinstance(case.get("question"), str) or not case["question"].strip() or len(case["question"]) > 16000:
            raise ValueError("blind_question_invalid")
        seen.add(case["case_id"])
    if (receipt.get("contract_version") != VERSION
            or receipt.get("suite") != manifest["suite"]
            or type(receipt.get("case_count")) is not int
            or receipt["case_count"] != len(cases)
            or not isinstance(receipt.get("baseline_fingerprint"), str)
            or not receipt["baseline_fingerprint"]
            or receipt.get("manifest_fingerprint") != stable_fingerprint(manifest)):
        raise ValueError("blind_freeze_integrity_mismatch")
    return [dict(case) for case in cases]


def prepare_dispatch_plan(
    manifest: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    id_factory: Callable[[], str] | None = None,
) -> dict[str, Any]:
    """Allocate NEW attempt IDs. Never reuse a historical n8n run ID."""
    questions = _require_questions(manifest, receipt)
    make_id = id_factory or (lambda: "blind-" + uuid.uuid4().hex)
    plan = {
        "contract_version": VERSION,
        "suite": manifest["suite"],
        "manifest_fingerprint": receipt["manifest_fingerprint"],
        "cases": [
            {"case_id": case["case_id"], "agent_run_id": make_id(),
             "question": case["question"]}
            for case in questions
        ],
    }
    verify_dispatch_plan(manifest, receipt, plan)
    return plan


def verify_dispatch_plan(
    manifest: Mapping[str, Any], receipt: Mapping[str, Any], plan: Any,
) -> None:
    questions = _require_questions(manifest, receipt)
    if (not isinstance(plan, Mapping) or set(plan) != _PLAN_KEYS
            or plan.get("contract_version") != VERSION
            or plan.get("suite") != manifest["suite"]
            or plan.get("manifest_fingerprint") != receipt["manifest_fingerprint"]
            or not isinstance(plan.get("cases"), list)
            or len(plan["cases"]) != len(questions)):
        raise ValueError("dispatch_plan_invalid")
    run_ids: set[str] = set()
    for actual, expected in zip(plan["cases"], questions):
        if (not isinstance(actual, Mapping)
                or set(actual) != {"case_id", "agent_run_id", "question"}
                or actual.get("case_id") != expected["case_id"]
                or actual.get("question") != expected["question"]
                or not _identifier(actual.get("agent_run_id"))
                or actual["agent_run_id"] in run_ids):
            raise ValueError("dispatch_plan_case_invalid")
        run_ids.add(actual["agent_run_id"])


def collect_post_generation_correlations(
    manifest: Mapping[str, Any],
    receipt: Mapping[str, Any],
    dispatch_plan: Mapping[str, Any],
    evidence_export: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive links solely from fingerprint-checked persisted Generate records.

    An omitted attempt remains missing evidence. Duplicate attempts, foreign
    runs, changed questions, or missing authenticated principal fail closed.
    """
    verify_dispatch_plan(manifest, receipt, dispatch_plan)
    if (not isinstance(evidence_export, Mapping)
            or set(evidence_export) != {"contract_version", "records"}
            or evidence_export.get("contract_version") != VERSION
            or not isinstance(evidence_export.get("records"), list)
            or len(evidence_export["records"]) > MAX_CASES * 3):
        raise ValueError("shadow_evidence_export_invalid")
    planned = {case["agent_run_id"]: case for case in dispatch_plan["cases"]}
    observed: dict[str, dict[str, Any]] = {}
    seen_record_ids: set[str] = set()
    for raw in evidence_export["records"]:
        record = validate_shadow_run_record(raw)
        agent = record.get("agent_run_id")
        shadow_id = record.get("shadow_record_id")
        if (agent not in planned or shadow_id in seen_record_ids
                or agent in observed or record.get("event_type") != "generate"):
            raise ValueError("shadow_attempt_not_uniquely_correlated")
        if record.get("question") != planned[agent]["question"]:
            raise ValueError("shadow_question_drift")
        principal = record.get("principal")
        if not isinstance(principal, Mapping) or not _identifier(principal.get("id")):
            raise ValueError("shadow_principal_unattested")
        org = principal.get("organization_id")
        if org is not None and not _identifier(org):
            raise ValueError("shadow_organization_invalid")
        link = {
            "case_id": planned[agent]["case_id"],
            "agent_run_id": agent,
            "run_id": record["run_id"],
            "shadow_record_id": shadow_id,
            "evidence_fingerprint": record["evidence_fingerprint"],
            "principal_id": principal["id"],
        }
        if org is not None:
            link["organization_id"] = org
        observed[agent] = link
        seen_record_ids.add(shadow_id)
    return {
        "contract_version": VERSION,
        "suite": dispatch_plan["suite"],
        "manifest_fingerprint": receipt["manifest_fingerprint"],
        "dispatch_plan_fingerprint": stable_fingerprint(dispatch_plan),
        "records": [
            observed[c["agent_run_id"]] for c in dispatch_plan["cases"]
            if c["agent_run_id"] in observed
        ],
    }


def bind_baseline_for_evaluation(
    baseline: Mapping[str, Any],
    manifest: Mapping[str, Any],
    receipt: Mapping[str, Any],
    dispatch_plan: Mapping[str, Any],
    correlation: Mapping[str, Any],
    evidence_export: Mapping[str, Any],
) -> dict[str, Any]:
    """Apply verified NEW run IDs in evaluation memory, never in the frozen files."""
    from scripts.blind_shadow_benchmark import (
        load_baseline, verify_blind_manifest, verify_freeze_receipt,
    )
    frozen = load_baseline(baseline)
    verify_blind_manifest(frozen, manifest)
    verify_freeze_receipt(frozen, manifest, receipt)
    expected = collect_post_generation_correlations(
        manifest, receipt, dispatch_plan, evidence_export,
    )
    if not isinstance(correlation, Mapping) or dict(correlation) != expected:
        raise ValueError("post_generation_correlation_invalid")
    links = {record["case_id"]: record for record in expected["records"]}
    enriched = deepcopy(frozen)
    for case in enriched["cases"]:
        link = links.get(case["case_id"])
        if link is None:
            continue
        for field, value in (
            ("agent_run_id", link["agent_run_id"]),
            ("principal_id", link["principal_id"]),
            ("organization_id", link.get("organization_id")),
        ):
            if field in case and case[field] is not None and case[field] != value:
                raise ValueError("frozen_provenance_conflicts_with_observed_run")
            if value is not None:
                case[field] = value
    return load_baseline(enriched)


def _read_private_json(path: str) -> Any:
    file = Path(path)
    info = file.lstat()
    if (not stat.S_ISREG(info.st_mode) or (info.st_mode & 0o077)
            or not 0 < info.st_size <= MAX_JSON_BYTES):
        raise ValueError("private_json_input_invalid")
    return json.loads(file.read_text(encoding="utf-8"))


def _write_private(path: str, data: Mapping[str, Any]) -> None:
    target = Path(path)
    if not target.parent.is_dir():
        raise ValueError("private_output_parent_invalid")
    fd = os.open(
        target, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
        getattr(os, "O_NOFOLLOW", 0), 0o600,
    )
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        json.dump(data, out, sort_keys=True, ensure_ascii=False, indent=2)
        out.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline blind dispatch plan and post-generation evidence linkage; no HTTP or LLM"
    )
    subs = parser.add_subparsers(dest="step", required=True)
    plan = subs.add_parser("prepare")
    plan.add_argument("--manifest", required=True)
    plan.add_argument("--receipt", required=True)
    plan.add_argument("--output", required=True)
    bind = subs.add_parser("bind")
    bind.add_argument("--manifest", required=True)
    bind.add_argument("--receipt", required=True)
    bind.add_argument("--dispatch-plan", required=True)
    bind.add_argument("--evidence", required=True)
    bind.add_argument("--output", required=True)
    args = parser.parse_args()
    if (os.environ.get("SHADOW_FULL_FLOW_ALLOW_LIVE_LLM", "").lower() == "true"
            or os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION", "").lower() == "true"):
        print("BLIND_BATCH=BLOCKED_LIVE_FLAGS")
        return 3
    try:
        manifest = _read_private_json(args.manifest)
        receipt = _read_private_json(args.receipt)
        if args.step == "prepare":
            document = prepare_dispatch_plan(manifest, receipt)
        else:
            document = collect_post_generation_correlations(
                manifest, receipt, _read_private_json(args.dispatch_plan),
                _read_private_json(args.evidence),
            )
        _write_private(args.output, document)
        print("BLIND_BATCH=PASS")
        print("BLIND_BATCH_STEP=" + args.step.upper())
        print("BLIND_BATCH_CASES=" +
              str(len(document["cases"] if args.step == "prepare" else document["records"])))
        print("BLIND_BATCH_HTTP_CALLS=0")
        print("BLIND_BATCH_LLM_CALLS=0")
        print("BLIND_BATCH_FINANCIAL_SQL_EXECUTED=false")
        return 0
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        print("BLIND_BATCH=BLOCKED")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

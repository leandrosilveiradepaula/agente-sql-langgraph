"""Two-phase OFFLINE benchmark: blind questions, then post-generation evaluation.

The evaluated n8n baseline must NEVER enter a generator, planner, context
selector, repairer or model prompt. This process imports none of them and
opens no database, socket or provider. SQL here is only parsed/compared
AFTER an independent Shadow run has persisted a fingerprinted record.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from app.adapters.testing.fake_shadow_evidence_repository import (
    FakeShadowEvidenceRepository,
)
from app.application.internal_shadow_sql_comparison import (
    COMPARISON_VERSION,
    CompareShadowSqlUseCase,
)
from app.domain.result_normalization import stable_fingerprint
from app.domain.shadow_evidence_types import validate_shadow_run_record

CONTRACT_VERSION = "1"
MAX_CASES = 256
MAX_QUESTION_LENGTH = 16000
MAX_SQL_LENGTH = 262144
MAX_BASELINE_BYTES = 16 * 1024 * 1024
MAX_EVIDENCE_BYTES = 64 * 1024 * 1024
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_BASELINE_CASE_KEYS = frozenset({
    "case_id", "question", "agent_run_id", "principal_id",
    "organization_id", "official_sql", "official_intent",
    "official_provider", "official_model", "official_context_fingerprint",
})
_ALLOWED_FACETS = frozenset({
    "physical_tables", "joined_relations", "predicates", "projections",
    "groupings", "orderings", "functions", "query_shape",
})


def _identifier(value: Any) -> bool:
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def _text(value: Any, *, maximum: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def load_baseline(raw: Any) -> dict[str, Any]:
    """Validate a PRIVATE n8n baseline. It is never passed to the intake."""
    if not isinstance(raw, Mapping) or set(raw) != {
        "contract_version", "suite", "cases"
    }:
        raise ValueError("benchmark_baseline_invalid")
    if raw["contract_version"] != CONTRACT_VERSION or not _identifier(raw["suite"]):
        raise ValueError("benchmark_identity_invalid")
    cases = raw["cases"]
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError("benchmark_case_count_invalid")
    seen_cases: set[str] = set()
    seen_runs: set[str] = set()
    normalized = []
    for item in cases:
        if not isinstance(item, Mapping) or not {
            "case_id", "question"
        } <= set(item) or set(item) - _BASELINE_CASE_KEYS:
            raise ValueError("benchmark_case_invalid")
        case_id, question = item["case_id"], item["question"]
        if not _identifier(case_id) or case_id in seen_cases:
            raise ValueError("benchmark_case_identity_invalid")
        if not _text(question, maximum=MAX_QUESTION_LENGTH):
            raise ValueError("benchmark_question_invalid")
        for field in ("agent_run_id", "principal_id", "organization_id"):
            if field in item and item[field] is not None and not _identifier(item[field]):
                raise ValueError("benchmark_correlation_invalid")
        for field in ("official_intent", "official_provider", "official_model",
                      "official_context_fingerprint"):
            if field in item and item[field] is not None and not _text(
                item[field], maximum=128
            ):
                raise ValueError("benchmark_provenance_invalid")
        if "official_sql" in item and item["official_sql"] is not None and not _text(
            item["official_sql"], maximum=MAX_SQL_LENGTH
        ):
            raise ValueError("benchmark_official_sql_invalid")
        correlated_run = item.get("agent_run_id")
        if correlated_run is not None:
            if correlated_run in seen_runs:
                raise ValueError("benchmark_agent_run_reused")
            seen_runs.add(correlated_run)
        seen_cases.add(case_id)
        normalized.append(dict(item))
    return {
        "contract_version": CONTRACT_VERSION,
        "suite": raw["suite"],
        "cases": normalized,
    }


def create_blind_manifest(baseline: Mapping[str, Any]) -> dict[str, Any]:
    """Physically drop ALL expected/baseline fields before generation.

    The generator receives one ordinary question at a time from this
    questions-only manifest. No baseline SQL, required filters, provider,
    financial result, intent expectation or run identity is forwarded.
    """
    valid = load_baseline(baseline)
    return {
        "contract_version": CONTRACT_VERSION,
        "suite": valid["suite"],
        "cases": [
            {"case_id": c["case_id"], "question": c["question"]}
            for c in valid["cases"]
        ],
    }


def verify_blind_manifest(
    baseline: Mapping[str, Any], manifest: Any,
) -> None:
    if not isinstance(manifest, Mapping) or set(manifest) != {
        "contract_version", "suite", "cases"
    } or manifest != create_blind_manifest(baseline):
        raise ValueError("blind_manifest_does_not_match_frozen_baseline")


def create_freeze_receipt(
    baseline: Mapping[str, Any], manifest: Mapping[str, Any],
) -> dict[str, Any]:
    """A separate digest receipt; never put it in the generator's manifest.

    A matching receipt attests integrity only. The operator must establish
    independent, pre-generation custody/timestamp before calling it frozen.
    """
    valid = load_baseline(baseline)
    verify_blind_manifest(valid, manifest)
    return {
        "contract_version": CONTRACT_VERSION,
        "suite": valid["suite"],
        "case_count": len(valid["cases"]),
        "baseline_fingerprint": stable_fingerprint(valid),
        "manifest_fingerprint": stable_fingerprint(manifest),
    }


def verify_freeze_receipt(
    baseline: Mapping[str, Any], manifest: Mapping[str, Any], receipt: Any,
) -> None:
    if not isinstance(receipt, Mapping) or dict(receipt) != create_freeze_receipt(
        baseline, manifest
    ):
        raise ValueError("benchmark_freeze_receipt_mismatch")


def _load_json(
    path: str, *, max_bytes: int, require_private: bool = False,
) -> Any:
    source = Path(path)
    try:
        info = source.lstat()
    except OSError:
        raise ValueError("benchmark_input_invalid") from None
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= max_bytes:
        raise ValueError("benchmark_input_invalid")
    if require_private and os.name == "posix" and (info.st_mode & 0o077):
        raise ValueError("benchmark_private_input_required")
    return json.loads(source.read_text(encoding="utf-8"))


def _validate_evidence(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, Mapping) or set(raw) != {
        "contract_version", "records"
    } or raw["contract_version"] != CONTRACT_VERSION:
        raise ValueError("shadow_evidence_export_invalid")
    records = raw["records"]
    if not isinstance(records, list) or len(records) > MAX_CASES * 3:
        raise ValueError("shadow_evidence_record_count_invalid")
    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_record in records:
        # Integrity of full saved evidence is checked before comparison.
        # Tampered fingerprints block the entire evaluation, not just a case.
        captured = validate_shadow_run_record(raw_record)
        record_id = captured["shadow_record_id"]
        if record_id in seen:
            raise ValueError("shadow_evidence_duplicate_record")
        seen.add(record_id)
        validated.append(captured)
    return validated


def _safe_result(case_id: str, status: str, reason: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "status": status,
        "reason": reason,
        "sql_verdict": "unavailable",
        "different_facets": [],
        "intent_status": "unattested",
        "provider_status": "unattested",
        "context_status": "unattested",
        "tenant_identity_attested": False,
        "requires_reapproval": False,
        "financial_result_status": "nao_autorizado_executar",
        "financial_parity_proven": False,
    }


def _attestation(expected: Any, actual: Any) -> str:
    if not _text(expected, maximum=128) or not _text(actual, maximum=128):
        return "unattested"
    return "matched" if expected == actual else "mismatched"


def _score_case(
    case: Mapping[str, Any],
    records: list[Mapping[str, Any]],
    service: CompareShadowSqlUseCase,
) -> dict[str, Any]:
    result = _safe_result(str(case["case_id"]), "inconclusivo", "correlation_unattested")
    agent_run_id = case.get("agent_run_id")
    principal_id = case.get("principal_id")
    if not _identifier(agent_run_id) or not _identifier(principal_id):
        result.update(status="sem_evidencia", reason="official_correlation_missing")
        return result
    # Multiple attempts for a run are not silently collapsed or cherry-picked:
    # operator must explicitly provide a unique successful attempt.
    candidates = [
        r for r in records
        if r.get("agent_run_id") == agent_run_id
        and r.get("event_type") == "generate"
    ]
    if not candidates:
        result.update(status="sem_evidencia", reason="shadow_record_missing")
        return result
    if len(candidates) != 1:
        result.update(reason="shadow_attempt_ambiguous")
        return result
    record = candidates[0]
    expected_tenant = case.get("organization_id")
    stored_principal = record.get("principal")
    if (
        record.get("question") != case["question"]
        or not isinstance(stored_principal, Mapping)
        or stored_principal.get("id") != principal_id
        or stored_principal.get("organization_id") != expected_tenant
    ):
        result.update(reason="correlation_mismatch")
        return result
    sql = case.get("official_sql")
    if not _text(sql, maximum=MAX_SQL_LENGTH):
        result.update(status="sem_evidencia", reason="official_sql_not_captured")
        return result

    comparison = service.execute({
        "contract_version": CONTRACT_VERSION,
        "agent_run_id": agent_run_id,
        "shadow_record_id": record["shadow_record_id"],
        "question": case["question"],
        "official_sql": sql,
        "principal": {
            "id": principal_id,
            **({"organization_id": expected_tenant} if expected_tenant else {}),
        },
        **({"official_detected_intent": case["official_intent"]}
           if case.get("official_intent") else {}),
    })
    if comparison.get("status") != "success":
        error_list = comparison.get("errors")
        code = error_list[0].get("code") if isinstance(error_list, list) and error_list else None
        result["reason"] = (
            code if isinstance(code, str) and _identifier(code)
            else "sql_comparison_unavailable"
        )
        return result
    facets = comparison.get("metadata", {}).get("comparison", {})
    if not isinstance(facets, Mapping):
        result["reason"] = "sql_comparison_unavailable"
        return result
    sql_verdict = facets.get("verdict")
    allowed_facets = facets.get("different_facets")
    result["sql_verdict"] = (
        sql_verdict if sql_verdict in {
            "normalized_sql_match", "structural_differences", "inconclusive"
        } else "unavailable"
    )
    if isinstance(allowed_facets, list):
        result["different_facets"] = sorted({
            facet for facet in allowed_facets
            if isinstance(facet, str) and facet in _ALLOWED_FACETS
        })
    intent_status = facets.get("intent_label_status")
    if intent_status in {"identifiers_matched", "identifier_mismatch"}:
        result["intent_status"] = intent_status
    result["requires_reapproval"] = facets.get("requires_reapproval") is True
    result["tenant_identity_attested"] = facets.get("tenant_identity_attested") is True

    generator_provider = _attestation(
        case.get("official_provider"), facets.get("shadow_generator_provider")
    )
    generator_model = _attestation(
        case.get("official_model"), facets.get("shadow_generator_model")
    )
    result["provider_status"] = (
        "mismatched" if "mismatched" in (generator_provider, generator_model)
        else "matched" if generator_provider == generator_model == "matched"
        else "unattested"
    )
    result["context_status"] = _attestation(
        case.get("official_context_fingerprint"),
        facets.get("shadow_context_fingerprint"),
    )

    if result["sql_verdict"] == "structural_differences" or (
        result["intent_status"] == "identifier_mismatch"
    ):
        result.update(status="diverge", reason="structural_or_intent_difference")
    elif result["sql_verdict"] == "normalized_sql_match":
        # Do not present a structural SQL match as a qualified comparison
        # when the historical run lacks tenant, model, context or intent
        # provenance. Never infer these values from a configured default.
        if result["requires_reapproval"]:
            result.update(status="inconclusivo", reason="repair_requires_reapproval")
        elif not result["tenant_identity_attested"]:
            result.update(status="inconclusivo", reason="tenant_identity_unattested")
        elif result["provider_status"] != "matched":
            result.update(status="inconclusivo", reason="provider_provenance_unattested_or_mismatch")
        elif result["context_status"] != "matched":
            result.update(status="inconclusivo", reason="context_provenance_unattested_or_mismatch")
        elif result["intent_status"] != "identifiers_matched":
            result.update(status="inconclusivo", reason="intent_provenance_unattested")
        else:
            result.update(status="corresponde", reason="sql_structural_match_only")
    else:
        result.update(status="inconclusivo", reason="sql_structure_inconclusive")
    return result


def evaluate_blind_benchmark(
    baseline: Mapping[str, Any],
    manifest: Mapping[str, Any],
    evidence_export: Mapping[str, Any],
    receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate only after checking the separately retained freeze receipt."""
    validated = load_baseline(baseline)
    verify_blind_manifest(validated, manifest)
    verify_freeze_receipt(validated, manifest, receipt)
    records = _validate_evidence(evidence_export)
    authorized_runs = {
        case["agent_run_id"] for case in validated["cases"]
        if _identifier(case.get("agent_run_id"))
    }
    if any(record.get("agent_run_id") not in authorized_runs for record in records):
        raise ValueError("shadow_evidence_unrequested_run")
    fake = FakeShadowEvidenceRepository()
    for record in records:
        if fake.create(record)["status"] != "created":
            raise ValueError("shadow_evidence_duplicate_record")
    service = CompareShadowSqlUseCase(repository=fake)
    cases = [
        _score_case(case, records, service)
        for case in validated["cases"]
    ]
    counts = Counter(case["status"] for case in cases)
    summary = {
        status: counts[status]
        for status in ("corresponde", "diverge", "inconclusivo", "sem_evidencia")
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "suite": validated["suite"],
        "benchmark_fingerprint": stable_fingerprint(validated),
        "manifest_fingerprint": stable_fingerprint(manifest),
        "freeze_receipt_fingerprint": stable_fingerprint(receipt),
        "freeze_receipt_consistent": True,
        "freeze_pre_generation_custody_attested": False,
        "historical_source_authenticity_attested": False,
        "evidence_fingerprint": stable_fingerprint([
            record["evidence_fingerprint"] for record in records
        ]),
        "comparison_version": COMPARISON_VERSION,
        "status": "evaluation_completed",
        "case_count": len(cases),
        "summary": summary,
        "cases": cases,
        "evaluation_only": True,
        "benchmark_exposed_to_generator": False,
        "provider_calls": 0,
        "real_sql_executed": False,
        "financial_parity_proven": False,
        "financial_execution_status": "nao_autorizado_executar",
        "activation_authorized": False,
    }


def _write_exclusive(path: str, document: Mapping[str, Any]) -> None:
    output = Path(path)
    if not output.parent.is_dir() or output.exists():
        raise ValueError("benchmark_output_invalid_or_already_exists")
    # Explicit 0600 on POSIX regardless of caller umask; never overwrite.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(output, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(document, stream, indent=2, ensure_ascii=False, sort_keys=True)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline blind Shadow benchmark; no provider or SQL execution")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare", help="Strip gold/baseline fields into a questions-only manifest")
    prepare.add_argument("--baseline", required=True)
    prepare.add_argument("--output", required=True)
    prepare.add_argument("--receipt-output", required=True)
    score = sub.add_parser("evaluate", help="Compare only AFTER independent Shadow evidence exists")
    score.add_argument("--baseline", required=True)
    score.add_argument("--manifest", required=True)
    score.add_argument("--evidence", required=True)
    score.add_argument("--receipt", required=True)
    score.add_argument("--output", required=True)
    args = parser.parse_args()

    # Defense in depth, despite the fact this module has no execution port.
    if os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION", "").lower() == "true" or (
        os.environ.get("SHADOW_FULL_FLOW_ALLOW_LIVE_LLM", "").lower() == "true"
    ):
        print("BLIND_BENCHMARK_BLOCKED: live_execution_flags_present")
        return 3
    try:
        baseline = load_baseline(_load_json(
            args.baseline, max_bytes=MAX_BASELINE_BYTES, require_private=True
        ))
        if args.command == "prepare":
            if Path(args.output).resolve() == Path(args.receipt_output).resolve():
                raise ValueError("benchmark_output_paths_must_differ")
            if Path(args.output).exists() or Path(args.receipt_output).exists():
                raise ValueError("benchmark_output_invalid_or_already_exists")
            manifest = create_blind_manifest(baseline)
            receipt = create_freeze_receipt(baseline, manifest)
            _write_exclusive(args.output, manifest)
            _write_exclusive(args.receipt_output, receipt)
            print("BLIND_MANIFEST_CREATED: questions_only")
            print("BLIND_FREEZE_RECEIPT_CREATED: integrity_only")
            return 0
        manifest = _load_json(args.manifest, max_bytes=MAX_BASELINE_BYTES)
        receipt = _load_json(args.receipt, max_bytes=4096, require_private=True)
        evidence = _load_json(
            args.evidence, max_bytes=MAX_EVIDENCE_BYTES, require_private=True
        )
        report = evaluate_blind_benchmark(baseline, manifest, evidence, receipt)
        _write_exclusive(args.output, report)
        print("BLIND_EVALUATION_WRITTEN: " + report["status"])
        return 0 if all(
            case["status"] == "corresponde" for case in report["cases"]
        ) else 1
    except Exception as error:
        # No user-supplied SQL, paths, credentials, questions, full records,
        # provider response or raw exception text is exposed.
        print("BLIND_BENCHMARK_BLOCKED: " + type(error).__name__)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

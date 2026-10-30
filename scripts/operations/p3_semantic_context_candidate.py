"""Build a non-persistable ContextSnapshot candidate from an approved P3 review.

This is deliberately a narrow, offline adapter.  It never reads a database,
calls a provider, emits SQL, or derives accounting meaning from physical names.
The reviewer supplies the full semantic contract; this module only proves that
the declared physical contract and the LangGraph contract agree.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
import argparse
import hmac
import os
import re
import json
from pathlib import Path
from typing import Any

from app.domain.context_normalizer import ContextNormalizationError, normalize_context_snapshot
from app.domain.context_validator import validate_context_snapshot
from scripts.operations.p3_semantic_mapping_review_readonly import MappingBlocked, check_review, create_review


class CandidateBlocked(ValueError):
    """Stable, safe reason why a candidate cannot be prepared."""


def _fingerprint(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _blocked(code: str) -> None:
    raise CandidateBlocked(code)


def _as_records(value: Any, code: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        _blocked(code)
    return value


def _physical_columns(review: Mapping[str, Any]) -> dict[tuple[str, str], list[dict[str, str]]]:
    source = review.get("source")
    if not isinstance(source, Mapping) or not isinstance(source.get("schema"), str):
        _blocked("P3_SOURCE_REQUIRED")
    schema = source["schema"]
    result: dict[tuple[str, str], list[dict[str, str]]] = {}
    for table in _as_records(review.get("tables"), "P3_TABLES_REQUIRED"):
        name, table_schema, columns = table.get("table"), table.get("schema"), table.get("columns")
        if not isinstance(name, str) or table_schema != schema:
            _blocked("P3_TABLE_SET_INVALID")
        normalized: list[dict[str, str]] = []
        for column in _as_records(columns, "P3_PHYSICAL_COLUMNS_REQUIRED"):
            col_name, pgtype = column.get("name"), column.get("postgres_type")
            if not isinstance(col_name, str) or not isinstance(pgtype, str):
                _blocked("P3_PHYSICAL_COLUMNS_REQUIRED")
            normalized.append({"name": col_name, "data_type": pgtype})
        if not normalized or (schema, name) in result:
            _blocked("P3_TABLE_SET_INVALID")
        result[(schema, name)] = sorted(normalized, key=lambda item: item["name"].casefold())
    return result


def _physical_fingerprint(review: Mapping[str, Any]) -> str:
    tables = _as_records(review.get("tables"), "P3_TABLES_REQUIRED")
    canonical: list[dict[str, Any]] = []
    for table in tables:
        columns = _as_records(table.get("columns"), "P3_PHYSICAL_COLUMNS_REQUIRED")
        canonical.append({
            "schema": table.get("schema"),
            "table": table.get("table"),
            "columns": sorted(
                [{"name": item.get("name"), "postgres_type": item.get("postgres_type")} for item in columns],
                key=lambda item: str(item["name"]).casefold(),
            ),
        })
    return _fingerprint(sorted(canonical, key=lambda item: (str(item["schema"]), str(item["table"]))))


def _validate_catalog(raw: Mapping[str, Any], physical: Mapping[tuple[str, str], list[dict[str, str]]]) -> None:
    catalog = _as_records(raw.get("catalogo"), "CANDIDATE_CATALOG_REQUIRED")
    seen: set[tuple[str, str]] = set()
    for entry in catalog:
        schema, table = entry.get("schema_name"), entry.get("table_name")
        key = (schema, table)
        if not isinstance(schema, str) or not isinstance(table, str) or key not in physical or key in seen:
            _blocked("CANDIDATE_CATALOG_PHYSICAL_MISMATCH")
        columns = entry.get("columns")
        if not isinstance(columns, list):
            _blocked("CANDIDATE_CATALOG_PHYSICAL_MISMATCH")
        declared = sorted(
            [{"name": item.get("name"), "data_type": item.get("data_type")} for item in columns if isinstance(item, Mapping)],
            key=lambda item: str(item["name"]).casefold(),
        )
        if declared != physical[key]:
            _blocked("CANDIDATE_CATALOG_PHYSICAL_MISMATCH")
        seen.add(key)
    if seen != set(physical):
        _blocked("CANDIDATE_CATALOG_PHYSICAL_MISMATCH")


_APPROVAL_CLAIMS = frozenset({
    "contract", "decision", "review_sha256", "physical_fingerprint",
    "organization_id", "candidate_version", "reviewer_id",
    "approved_at", "evidence_ref",
})
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _validated_p3_baseline(
    review: Mapping[str, Any], trusted_baseline: Mapping[str, Any] | None,
) -> None:
    """Match an independently reconstructed physical P3 baseline.

    Passing the submitted review as its own baseline does NOT prove anything.
    The CLI rebuilds this baseline from the original owner-only audit.
    """
    if not isinstance(trusted_baseline, Mapping):
        _blocked("P3_INDEPENDENT_EVIDENCE_REQUIRED")
    baseline = trusted_baseline
    if (baseline.get("contract") != "p3-semantic-mapping-review-v1"
            or review.get("contract") != baseline["contract"]):
        _blocked("P3_REVIEW_CONTRACT_INVALID")
    if (not isinstance(baseline.get("source"), Mapping)
            or review.get("source") != baseline["source"]):
        _blocked("SOURCE_OR_PHYSICAL_FINGERPRINT_DRIFT")
    if (baseline["source"].get("physical_fingerprint") != _physical_fingerprint(baseline)
            or _physical_fingerprint(review) != baseline["source"]["physical_fingerprint"]
            or _physical_columns(review) != _physical_columns(baseline)):
        _blocked("SOURCE_OR_PHYSICAL_FINGERPRINT_DRIFT")

    # Reuse P3's complete structural gate: PK, typed metrics and dates, joins,
    # cardinality, fanout and evidence. Structural review != accounting approval.
    source = baseline["source"]
    physical_columns = _physical_columns(baseline)
    policy = {
        "schema": source.get("schema"),
        "database": source.get("database"),
        "role_name": source.get("role_name"),
        "relations": sorted(table for _, table in physical_columns),
    }
    physical = [
        (schema, table, col["name"], col["data_type"])
        for (schema, table), columns in physical_columns.items()
        for col in columns
    ]
    try:
        report = check_review(review, policy, physical, source.get("context_version"))
    except (MappingBlocked, KeyError, ValueError, TypeError, AttributeError, IndexError):
        _blocked("P3_SEMANTIC_REVIEW_INCOMPLETE")
    if report["status"] != "structural_preview_only":
        _blocked("P3_SEMANTIC_REVIEW_INCOMPLETE")


def _verified_receipt(
    review: Mapping[str, Any],
    receipt: Mapping[str, Any] | None,
    verification_key: bytes | None,
) -> Mapping[str, Any]:
    """Verify a separately issued HMAC approval binding the entire review.

    The key must be held by the approving authority, not the mapping author.
    An untrusted approval file or a flag in the review is insufficient.
    """
    if not isinstance(receipt, Mapping):
        _blocked("P3_INDEPENDENT_APPROVAL_REQUIRED")
    if not isinstance(verification_key, bytes) or len(verification_key) < 32:
        _blocked("P3_APPROVAL_VERIFIER_UNAVAILABLE")
    claims = receipt.get("claims")
    signature = receipt.get("hmac_sha256")
    if (not isinstance(claims, Mapping) or set(claims) != _APPROVAL_CLAIMS
            or not isinstance(signature, str) or not _SHA256.fullmatch(signature)
            or any(not isinstance(x, str) or not x.strip() for x in claims.values())):
        _blocked("P3_APPROVAL_RECEIPT_INVALID")
    actual = hmac.new(
        verification_key,
        json.dumps(claims, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(),
        sha256,
    ).hexdigest()
    if not hmac.compare_digest(actual, signature):
        _blocked("P3_APPROVAL_SIGNATURE_INVALID")
    review_evidence = review.get("review_evidence")
    accounting = review.get("accounting_approval")
    if (claims["contract"] != "p3-accounting-approval-v1"
            or claims["decision"] != "APPROVED"
            or claims["review_sha256"] != _fingerprint(review)
            or claims["physical_fingerprint"] != review["source"]["physical_fingerprint"]
            or claims["organization_id"] != review.get("organization_id")
            or claims["candidate_version"] != review.get("candidate_version")
            or not isinstance(review_evidence, Mapping)
            or not isinstance(accounting, Mapping)
            or claims["reviewer_id"] != review_evidence.get("reviewer")
            or claims["approved_at"] != review_evidence.get("review_timestamp")
            or claims["evidence_ref"] != review_evidence.get("source_definition_ref")
            or claims["evidence_ref"] != accounting.get("reference")):
        _blocked("P3_APPROVAL_SCOPE_MISMATCH")
    return claims


def build_candidate(
    review: Mapping[str, Any],
    *,
    trusted_baseline: Mapping[str, Any] | None = None,
    approval_receipt: Mapping[str, Any] | None = None,
    approval_verification_key: bytes | None = None,
) -> dict[str, Any]:
    """Pure offline candidate builder, non-activatable without independent proofs.

    The caller must reconstruct trusted_baseline from the audited physical P3
    snapshot, and separately authenticate approval_receipt via a verifier key.
    """
    if not isinstance(review, Mapping):
        _blocked("P3_REVIEW_INVALID")
    if review.get("status") != "APPROVED":
        _blocked("NEEDS_BUSINESS_APPROVAL")
    accounting = review.get("accounting_approval")
    if not isinstance(accounting, Mapping) or accounting.get("status") != "APPROVED":
        _blocked("NEEDS_BUSINESS_APPROVAL")
    if (review.get("can_import_into_semantic_catalog") is not False
            or review.get("can_execute_financial_sql") is not False):
        _blocked("UNAUTHORIZED_ACTIVATION_ATTEMPT")
    source = review.get("source")
    if not isinstance(source, Mapping) or not isinstance(source.get("physical_fingerprint"), str):
        _blocked("P3_SOURCE_REQUIRED")
    organization_id = review.get("organization_id")
    if not isinstance(organization_id, str) or not organization_id.strip():
        _blocked("TENANT_REQUIRED")
    if source["physical_fingerprint"] != _physical_fingerprint(review):
        _blocked("SOURCE_OR_PHYSICAL_FINGERPRINT_DRIFT")

    _validated_p3_baseline(review, trusted_baseline)
    raw_semantic = review.get("semantic_context")
    if not isinstance(raw_semantic, Mapping):
        _blocked("SEMANTIC_CONTEXT_REQUIRED")
    raw = deepcopy(dict(raw_semantic))
    candidate_version = review.get("candidate_version")
    if (not isinstance(candidate_version, str) or not candidate_version.strip()
            or raw.get("semantic_agent_version") != candidate_version):
        _blocked("SEMANTIC_VERSION_MISMATCH")
    _validate_catalog(raw, _physical_columns(trusted_baseline))
    try:
        snapshot = normalize_context_snapshot(raw)
    except ContextNormalizationError:
        _blocked("CONTEXT_NORMALIZATION_FAILED")
    validation = validate_context_snapshot(snapshot)
    if validation["status"] != "valid":
        _blocked("CONTEXT_CONTRACT_INVALID")
    claims = _verified_receipt(review, approval_receipt, approval_verification_key)
    bound_identity = {
        "organization_id": organization_id,
        "candidate_version": candidate_version,
        "candidate_fingerprint": snapshot["fingerprint"],
        "physical_fingerprint": source["physical_fingerprint"],
        "approval_sha256": _fingerprint(claims),
    }
    return {
        "status": "CANDIDATE_READY_NOT_ACTIVATED",
        "candidate": snapshot,
        "candidate_fingerprint": snapshot["fingerprint"],
        "physical_fingerprint": source["physical_fingerprint"],
        "organization_id": organization_id,
        "candidate_version": candidate_version,
        "tenant_binding_fingerprint": _fingerprint(bound_identity),
        "provenance_fingerprint": _fingerprint({
            "p3_source": trusted_baseline["source"],
            "signed_approval": approval_receipt,
        }),
        "activation_authorized": False,
        "persisted": False,
        "financial_sql_executed": False,
        "llm_calls": 0,
    }


def _baseline_from_private_p3(audit_dir: Path, policy_file: Path) -> dict[str, Any]:
    """Independently rebuild P3 baseline from existing metadata; no SQL calls."""
    from scripts.operations import p3_source_alignment_readonly as p3
    if audit_dir.is_symlink():
        _blocked("PRIVATE_DIRECTORY_REQUIRED")
    try:
        policy = p3.validate_policy(json.loads(policy_file.read_text(encoding="utf-8")))
        raw = p3.read_private_snapshot(audit_dir / "physical-metadata.json")
        version = raw.get("context_version")
        context, physical, grants, identity = p3.verify_probe_snapshot(raw, policy, version)
        scope = p3.evaluate(policy, version, context, physical, grants, identity)
        if any(block in scope["blockers"] for block in (
            "ROLE_SCOPE_MISMATCH", "ROLE_WRITE_PRIVILEGE", "PHYSICAL_COLUMNS_MISSING",
        )):
            _blocked("P3_READER_SCOPE_NOT_VERIFIED")
        return create_review(policy, physical, version)
    except CandidateBlocked:
        raise
    except Exception:
        _blocked("P3_INDEPENDENT_EVIDENCE_INVALID")


def main(argv: list[str] | None = None) -> int:
    """Verify private original P3 evidence and a separately authenticated approval."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", required=True, type=Path)
    parser.add_argument("--review-file", required=True, type=Path)
    parser.add_argument("--approval-file", required=True, type=Path)
    parser.add_argument("--policy", type=Path,
                        default=Path(__file__).with_name("g1_readonly_rollout.json"))
    args = parser.parse_args(argv)
    try:
        from scripts.operations import p3_source_alignment_readonly as p3
        review = p3.read_private_snapshot(args.review_file)
        baseline = _baseline_from_private_p3(args.audit_dir, args.policy)
        approval = p3.read_private_snapshot(args.approval_file)
        try:
            key = bytes.fromhex(os.environ.get("P3_APPROVAL_HMAC_VERIFY_KEY_HEX", ""))
        except ValueError:
            key = b""
        result = build_candidate(
            review, trusted_baseline=baseline, approval_receipt=approval,
            approval_verification_key=key,
        )
        print("P3_CANDIDATE_STATUS=" + result["status"])
        print("P3_CANDIDATE_FINGERPRINT=" + result["candidate_fingerprint"])
        print("P3_CANDIDATE_TENANT_BINDING=" + result["tenant_binding_fingerprint"])
        print("P3_CANDIDATE_ACTIVATION_AUTHORIZED=false")
        print("P3_CANDIDATE_FINANCIAL_SQL_EXECUTED=false")
        print("P3_CANDIDATE_LLM_CALLS=0")
        return 0
    except CandidateBlocked as error:
        print("P3_CANDIDATE_STATUS=BLOCKED")
        print("P3_CANDIDATE_REASON=" + str(error))
        return 2
    except Exception:
        print("P3_CANDIDATE_STATUS=BLOCKED")
        print("P3_CANDIDATE_REASON=PRIVATE_REVIEW_UNAVAILABLE")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

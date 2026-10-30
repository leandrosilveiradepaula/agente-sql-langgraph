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
import json
from pathlib import Path
from typing import Any

from app.domain.context_normalizer import ContextNormalizationError, normalize_context_snapshot
from app.domain.context_validator import validate_context_snapshot


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


def build_candidate(review: Mapping[str, Any]) -> dict[str, Any]:
    """Return a normalized candidate and evidence, never an activation request.

    ``semantic_context`` is an externally approved, versioned raw ContextSnapshot
    source.  It is intentionally copied, not enriched: missing metric, alias,
    period, join, DRE, tenant, or rule information is a blocking condition.
    """
    if not isinstance(review, Mapping):
        _blocked("P3_REVIEW_INVALID")
    if review.get("status") != "APPROVED":
        _blocked("NEEDS_BUSINESS_APPROVAL")
    approval = review.get("accounting_approval")
    if not isinstance(approval, Mapping) or approval.get("status") != "APPROVED":
        _blocked("NEEDS_BUSINESS_APPROVAL")
    if review.get("can_import_into_semantic_catalog") is not False or review.get("can_execute_financial_sql") is not False:
        _blocked("UNAUTHORIZED_ACTIVATION_ATTEMPT")
    source = review.get("source")
    if not isinstance(source, Mapping) or not isinstance(source.get("physical_fingerprint"), str):
        _blocked("P3_SOURCE_REQUIRED")
    if not isinstance(review.get("organization_id"), str) or not review["organization_id"].strip():
        _blocked("TENANT_REQUIRED")
    if source["physical_fingerprint"] != _physical_fingerprint(review):
        _blocked("SOURCE_OR_PHYSICAL_FINGERPRINT_DRIFT")
    physical = _physical_columns(review)
    semantic = review.get("semantic_context")
    if not isinstance(semantic, Mapping):
        _blocked("SEMANTIC_CONTEXT_REQUIRED")
    raw = deepcopy(dict(semantic))
    _validate_catalog(raw, physical)
    try:
        snapshot = normalize_context_snapshot(raw)
    except ContextNormalizationError:
        _blocked("CONTEXT_NORMALIZATION_FAILED")
    validation = validate_context_snapshot(snapshot)
    if validation["status"] != "valid":
        _blocked("CONTEXT_CONTRACT_INVALID")
    return {
        "status": "CANDIDATE_READY_NOT_ACTIVATED",
        "candidate": snapshot,
        "candidate_fingerprint": snapshot["fingerprint"],
        "physical_fingerprint": source["physical_fingerprint"],
        "organization_id": review.get("organization_id"),
        "provenance_fingerprint": _fingerprint({"approval": approval, "source": source}),
        "activation_authorized": False,
        "persisted": False,
        "financial_sql_executed": False,
        "llm_calls": 0,
    }


def main(argv: list[str] | None = None) -> int:
    """Check a private approved review without printing its semantic payload."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-file", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        review = json.loads(args.review_file.read_text(encoding="utf-8"))
        result = build_candidate(review)
        print("P3_CANDIDATE_STATUS=" + result["status"])
        print("P3_CANDIDATE_FINGERPRINT=" + result["candidate_fingerprint"])
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

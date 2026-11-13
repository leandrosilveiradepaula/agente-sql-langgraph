"""Fail-closed, source-pinned *physical identity* verification for G5 review.

G5/P3 may contain multiple schemas for one unqualified table name.
The independent accounting receipt is insufficient on its own to prove which
physical PostgreSQL columns a financial definition references.

No account names, customer-specific schemas, financial logic, SQL, connection
credentials or benchmark expectations live here. Evidence is metadata-only.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any

from scripts.operations.g5_financial_crosswalk_review import (
    FinancialReviewBlocked, digest, source_ids,
)

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_HINT = {
    "collection", "source_record_sha256", "source_table_ref",
    "source_column_ref", "candidate_status", "column_status",
    "physical_schema_candidate", "source_version_sha256",
    "accounting_equivalence",
}
_DECISION_KEYS = {
    "collection", "source_row_sha256", "qualified_table", "target_column",
}
_REMAP_ATTESTATION = "physical_remap_evidence_sha256"


def deny(code: str) -> None:
    raise FinancialReviewBlocked(code)


def original_physical_reference(
    packet: Mapping[str, Any], hint: Mapping[str, Any],
) -> tuple[str | None, str, str | None]:
    """Resolve a G5 source-row reference, NEVER a physical target.

    Table-catalog hints in the real G5 archive have NULL source_table_ref,
    despite the exact table name/schema being present in that source row.
    A purely hint-based resolver can never approve any of those 8 rows.
    Aliases may inherit an unambiguous *legacy* schema from their catalog,
    which is only historical provenance, never proof of the new P3 schema.
    """
    collection = hint.get("collection")
    record_sha = hint.get("source_record_sha256")
    records = packet.get("collections", {}).get(collection)
    if not isinstance(records, list):
        deny("G5_ORIGINAL_SOURCE_COLLECTION_MISSING")
    matches = [
        row for row in records
        if isinstance(row, Mapping)
        and row.get("source_row_sha256") == record_sha
    ]
    if len(matches) != 1:
        deny("G5_ORIGINAL_SOURCE_ROW_NOT_UNIQUE")
    fields = matches[0].get("source_fields_unreviewed")
    if not isinstance(fields, Mapping):
        deny("G5_ORIGINAL_SOURCE_FIELDS_INVALID")

    schema = fields.get("schema_name")
    if isinstance(fields.get("table_name"), str) and fields["table_name"]:
        table = fields["table_name"]
        column = None
        if not isinstance(schema, str) or not _IDENT.fullmatch(schema):
            deny("G5_ORIGINAL_SOURCE_SCHEMA_INVALID")
    elif isinstance(fields.get("target_table"), str) and fields["target_table"]:
        table = fields["target_table"]
        column = fields.get("target_column")
        if not isinstance(column, str) or not _IDENT.fullmatch(column):
            deny("G5_ORIGINAL_SOURCE_COLUMN_INVALID")
        source_catalog_schemas = {
            original.get("source_fields_unreviewed", {}).get("schema_name")
            for group in packet["collections"].values()
            for original in group
            if isinstance(original, Mapping)
            and isinstance(original.get("source_fields_unreviewed"), Mapping)
            and original["source_fields_unreviewed"].get("table_name") == table
            and isinstance(
                original["source_fields_unreviewed"].get("schema_name"), str
            )
        }
        schema = next(iter(source_catalog_schemas)) if len(source_catalog_schemas) == 1 else None
    else:
        # Structurally different tenant source/fixture without a table
        # catalog: only an explicit source hint is available; never infer
        # an equivalent physical table from business semantics.
        table = hint.get("source_table_ref")
        column = hint.get("source_column_ref")
        schema = None
    if not isinstance(table, str) or not _IDENT.fullmatch(table):
        deny("G5_ORIGINAL_SOURCE_TABLE_INVALID")
    hint_table = hint.get("source_table_ref")
    if hint_table not in (None, "", table, f"{schema}.{table}" if schema else table):
        deny("G5_ORIGINAL_SOURCE_HINT_CONFLICT")
    hint_column = hint.get("source_column_ref")
    if hint_column not in (None, "", column):
        deny("G5_ORIGINAL_COLUMN_HINT_CONFLICT")
    if column is not None and hint_column != column:
        deny("G5_ORIGINAL_COLUMN_HINT_MISSING")
    return schema, table, column


def physical_approval_claims(
    *, packet: Mapping[str, Any], review: Mapping[str, Any],
    approved_catalog: list[Mapping[str, Any]],
    p3_bytes: bytes | None,
) -> dict[str, Any]:
    """Return exact digests to include in signed review claims.

    A source record with P3 physical hints requires one explicit mapping
    bound to the independently sealed metadata snapshot. No automatic
    selection among same-named tables is permitted.
    """
    hints = packet.get("physical_identifier_hints_unapproved")
    if hints is None:
        if "physical_binding_decisions" in review:
            deny("G5_UNSCOPED_PHYSICAL_DECISIONS")
        return {}
    if not isinstance(hints, list) or not hints or len(hints) > 50000:
        deny("G5_P3_SOURCE_HINTS_INVALID")
    source = packet.get("origin", {})
    expected_sha = source.get("p3_snapshot_sha256")
    if (
        not isinstance(expected_sha, str) or not _SHA.fullmatch(expected_sha)
        or not isinstance(p3_bytes, bytes)
        or not 0 < len(p3_bytes) <= 3_000_000
        or hashlib.sha256(p3_bytes).hexdigest() != expected_sha
    ):
        deny("G5_P3_ORIGINAL_METADATA_REQUIRED")
    try:
        metadata = json.loads(p3_bytes)
    except (ValueError, UnicodeError, TypeError):
        deny("G5_P3_METADATA_INVALID")
    if (
        not isinstance(metadata, Mapping)
        or metadata.get("contract") != "p3-metadata-snapshot-v1"
        or metadata.get("sql_executed") is not False
        or metadata.get("llm_calls") != 0
        or not isinstance(metadata.get("physical"), list)
        or not 0 < len(metadata["physical"]) <= 100000
    ):
        deny("G5_P3_PROVENANCE_INVALID")
    physical: dict[tuple[str, str], dict[str, str]] = {}
    for item in metadata["physical"]:
        if (
            not isinstance(item, list) or len(item) != 4
            or not all(isinstance(p, str) and p for p in item)
            or not all(_IDENT.fullmatch(p) for p in item[:3])
        ):
            deny("G5_P3_PHYSICAL_ROW_INVALID")
        schema, table, column, dtype = item
        column_types = physical.setdefault((schema, table), {})
        if column in column_types and column_types[column] != dtype:
            deny("G5_P3_PHYSICAL_TYPE_CONFLICT")
        column_types[column] = dtype

    approved_tables = {}
    for table in approved_catalog:
        if not isinstance(table, Mapping):
            deny("G5_APPROVED_PHYSICAL_CATALOG_INVALID")
        schema = table.get("schema_name")
        name = table.get("table_name")
        columns = table.get("columns")
        if (
            not isinstance(schema, str) or not _IDENT.fullmatch(schema)
            or not isinstance(name, str) or not _IDENT.fullmatch(name)
            or not isinstance(columns, list)
        ):
            deny("G5_APPROVED_PHYSICAL_CATALOG_INVALID")
        key = (schema, name)
        if key in approved_tables:
            deny("G5_APPROVED_PHYSICAL_TABLE_DUPLICATED")
        typed = {}
        for col in columns:
            if not isinstance(col, Mapping):
                deny("G5_APPROVED_PHYSICAL_COLUMN_INVALID")
            cname, ctype = col.get("name"), col.get("data_type")
            if (
                not isinstance(cname, str) or not _IDENT.fullmatch(cname)
                or not isinstance(ctype, str) or not ctype
                or cname in typed
            ):
                deny("G5_APPROVED_PHYSICAL_COLUMN_INVALID")
            typed[cname] = ctype
        approved_tables[key] = typed

    decisions = review.get("physical_binding_decisions")
    if not isinstance(decisions, list) or len(decisions) != len(hints):
        deny("G5_PHYSICAL_DECISIONS_INCOMPLETE")
    by_id = {}
    verified_source_rows = source_ids(packet)
    for item in hints:
        if (
            not isinstance(item, Mapping)
            or not _ALLOWED_HINT <= set(item)
            or not isinstance(item.get("collection"), str)
            or not isinstance(item.get("source_record_sha256"), str)
            or item.get("source_version_sha256")
            != source.get("source_version_sha256")
            or item.get("accounting_equivalence") != "NOT_ATTESTED"
        ):
            deny("G5_PHYSICAL_HINT_INVALID")
        key = (item["collection"], item["source_record_sha256"])
        if key not in verified_source_rows or key in by_id:
            deny("G5_PHYSICAL_HINT_ORPHAN_OR_DUPLICATED")
        by_id[key] = item

    seen = set()
    for decision in decisions:
        if (
            not isinstance(decision, Mapping)
            or set(decision) not in (
                _DECISION_KEYS, _DECISION_KEYS | {_REMAP_ATTESTATION}
            )
        ):
            deny("G5_PHYSICAL_DECISION_FORMAT_INVALID")
        key = (decision.get("collection"), decision.get("source_row_sha256"))
        if key not in by_id or key in seen:
            deny("G5_PHYSICAL_DECISION_ORPHAN")
        seen.add(key)
        hint = by_id[key]
        target = decision.get("qualified_table")
        column = decision.get("target_column")
        if not isinstance(target, str) or len(target.split(".")) != 2:
            deny("G5_PHYSICAL_QUALIFIED_TABLE_REQUIRED")
        schema, table = target.split(".")
        if not _IDENT.fullmatch(schema) or not _IDENT.fullmatch(table):
            deny("G5_PHYSICAL_QUALIFIED_TABLE_INVALID")
        legacy_schema, legacy_table, legacy_column = original_physical_reference(
            packet, hint,
        )
        remapped = (
            table != legacy_table
            or (legacy_schema is not None and schema != legacy_schema)
            or column != legacy_column
        )
        evidence = decision.get(_REMAP_ATTESTATION)
        if remapped:
            # An explicitly reviewed mapping is portable across schema
            # names, table names, and renamed columns. The independent
            # signed receipt binds the evidence digest AND this exact target;
            # neither aliases nor name similarity can authorize a remap.
            if not isinstance(evidence, str) or not _SHA.fullmatch(evidence):
                deny("G5_PHYSICAL_REMAP_INDEPENDENT_EVIDENCE_REQUIRED")
        elif _REMAP_ATTESTATION in decision:
            deny("G5_PHYSICAL_REMAP_EVIDENCE_NOT_APPLICABLE")
        if (schema, table) not in physical or (schema, table) not in approved_tables:
            deny("G5_PHYSICAL_BINDING_NOT_PROVEN")
        if legacy_column is None:
            if column is not None:
                deny("G5_PHYSICAL_COLUMN_NOT_EXPECTED")
            if not physical[(schema, table)]:
                deny("G5_PHYSICAL_EMPTY_TABLE")
            # For a table-only hint, require at least one explicit, typed,
            # physically confirmed column in the canonical catalog.
            if not any(
                c in physical[(schema, table)]
                and dtype.casefold() == physical[(schema, table)][c].casefold()
                for c, dtype in approved_tables[(schema, table)].items()
            ):
                deny("G5_PHYSICAL_TABLE_UNVERIFIED")
        else:
            if (
                not isinstance(column, str)
                or not _IDENT.fullmatch(column)
                or column not in physical[(schema, table)]
                or column not in approved_tables[(schema, table)]
                or physical[(schema, table)][column].casefold()
                != approved_tables[(schema, table)][column].casefold()
            ):
                deny("G5_PHYSICAL_COLUMN_TYPE_UNVERIFIED")
    if seen != set(by_id):
        deny("G5_PHYSICAL_REVIEW_COVERAGE_INVALID")
    return {
        "p3_snapshot_sha256": expected_sha,
        "physical_binding_decisions_sha256": digest(sorted(
            decisions, key=lambda d: (d["collection"], d["source_row_sha256"]),
        )),
        "physical_binding_rows": len(decisions),
    }

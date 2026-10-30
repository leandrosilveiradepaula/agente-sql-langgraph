#!/usr/bin/env python3
"""Offline P3 semantic-mapping review. No SQL, providers, n8n or writes to databases.

Physical existence never proves accounting meaning. Every meaning must come
from a human-reviewed, versioned mapping separate from the legacy benchmark.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
NUMERIC = frozenset(("int2", "int4", "int8", "numeric", "float4", "float8", "money"))
TEMPORAL = frozenset(("date", "timestamp", "timestamptz", "time", "timetz"))
AGGREGATIONS = frozenset(("sum", "avg", "count", "min", "max"))
CARDINALITIES = frozenset(("many_to_one", "one_to_one", "one_to_many"))


class MappingBlocked(Exception):
    pass


def valid_ident(value: Any) -> bool:
    return isinstance(value, str) and bool(IDENT.fullmatch(value))


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 2048


def digest(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=True, sort_keys=True,
                              separators=(",", ":")).encode("utf-8")).hexdigest()


def physical_inventory(policy: Mapping[str, Any], physical: list) -> dict[str, dict[str, str]]:
    schema, allowed = policy.get("schema"), policy.get("relations")
    if (not valid_ident(schema) or not isinstance(allowed, list) or not allowed
            or not all(valid_ident(name) for name in allowed)
            or len(set(allowed)) != len(allowed)):
        raise MappingBlocked("POLICY_INVALID")
    if not isinstance(physical, list) or len(physical) > 100000:
        raise MappingBlocked("PHYSICAL_INVALID")
    tables: dict[str, dict[str, str]] = {name: {} for name in allowed}
    for row in physical:
        if (not isinstance(row, (list, tuple)) or len(row) != 4
                or not all(valid_ident(part) for part in row)):
            raise MappingBlocked("PHYSICAL_INVALID")
        sc, table, column, pgtype = row
        if sc == schema and table in tables:
            if column in tables[table]:
                raise MappingBlocked("PHYSICAL_DUPLICATE_COLUMN")
            tables[table][column] = pgtype
    if any(not cols for cols in tables.values()):
        raise MappingBlocked("PHYSICAL_MISSING_RELATION")
    return tables


def physical_shape(policy: Mapping[str, Any], inventory: Mapping[str, Mapping[str, str]]) -> list:
    return [{"schema": policy["schema"], "table": table,
             "columns": [{"name": col, "postgres_type": pgtype}
                         for col, pgtype in sorted(cols.items())]}
            for table, cols in sorted(inventory.items())]


def create_review(policy: Mapping[str, Any], physical: list, version: str) -> dict:
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise MappingBlocked("CONTEXT_VERSION_INVALID")
    inventory = physical_inventory(policy, physical)
    tables = physical_shape(policy, inventory)
    for table in tables:
        table.update({
            "grain": None, "primary_key": None, "key_columns": None,
            "metric_bindings": None, "dimension_bindings": None,
            "date_bindings": None, "join_bindings": None,
            "dre_mappings": None, "business_evidence": None,
        })
    return {
        "contract": "p3-semantic-mapping-review-v1",
        "status": "UNAPPROVED_DRAFT",
        "source": {"schema": policy["schema"], "role_name": policy.get("role_name"),
                   "database": policy.get("database"), "context_version": version,
                   "physical_fingerprint": digest(physical_shape(policy, inventory))},
        "candidate_version": None, "organization_id": None, "review_evidence": None,
        "tables": tables, "intent_definitions": None, "entity_aliases": None,
        "business_rules": None,
        "can_import_into_semantic_catalog": False,
        "can_execute_financial_sql": False,
    }


def check_review(draft: Mapping[str, Any], policy: Mapping[str, Any],
                 physical: list, version: str) -> dict:
    expected = create_review(policy, physical, version)
    if not isinstance(draft, Mapping) or draft.get("contract") != expected["contract"]:
        raise MappingBlocked("CONTRACT_INVALID")
    if draft.get("source") != expected["source"]:
        raise MappingBlocked("SOURCE_OR_PHYSICAL_FINGERPRINT_DRIFT")
    if (draft.get("can_import_into_semantic_catalog") is not False
            or draft.get("can_execute_financial_sql") is not False):
        raise MappingBlocked("UNAUTHORIZED_ACTIVATION_ATTEMPT")
    inventory = physical_inventory(policy, physical)
    issues: list[tuple[str, str]] = []

    def flag(code: str, at: str = "") -> None:
        issues.append((code, at))

    target = draft.get("candidate_version")
    if not isinstance(target, str) or not VERSION.fullmatch(target) or target == version:
        flag("NEW_VERSION_REQUIRED")
    if not nonempty(draft.get("organization_id")):
        flag("TENANT_REQUIRED")
    proof = draft.get("review_evidence")
    if not isinstance(proof, Mapping) or not all(
        nonempty(proof.get(key)) for key in ("reviewer", "source_definition_ref", "review_timestamp")
    ):
        flag("BUSINESS_REVIEW_EVIDENCE_REQUIRED")
    for name in ("intent_definitions", "entity_aliases", "business_rules"):
        values = draft.get(name)
        if (not isinstance(values, list) or (name == "intent_definitions" and not values)
                or (isinstance(values, list) and any(not isinstance(v, Mapping) for v in values))):
            flag("SEMANTIC_COLLECTION_UNREVIEWED", name)
    rows = draft.get("tables")
    if not isinstance(rows, list) or len(rows) != len(inventory):
        raise MappingBlocked("TABLE_SET_CHANGED")
    by_name: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise MappingBlocked("TABLE_SET_CHANGED")
        name = row.get("table")
        if (not valid_ident(name) or row.get("schema") != policy["schema"]
                or name not in inventory or name in by_name):
            raise MappingBlocked("TABLE_SET_CHANGED")
        baseline = next(t for t in expected["tables"] if t["table"] == name)
        if row.get("columns") != baseline["columns"]:
            raise MappingBlocked("PHYSICAL_COLUMNS_CHANGED")
        by_name[name] = row
    if set(by_name) != set(inventory):
        raise MappingBlocked("TABLE_SET_CHANGED")

    metric_count = 0
    catalog: list[dict] = []
    for name, row in sorted(by_name.items()):
        cols, prefix = inventory[name], "table:" + name
        grain, pk, keys = row.get("grain"), row.get("primary_key"), row.get("key_columns")
        if not nonempty(grain):
            flag("GRAIN_REQUIRED", prefix)
        if not valid_ident(pk) or pk not in cols:
            flag("PRIMARY_KEY_NOT_PHYSICAL", prefix)
        if (not isinstance(keys, list) or not keys
                or not all(valid_ident(key) and key in cols for key in keys)
                or len(set(keys)) != len(keys) or pk not in keys):
            flag("KEY_COLUMNS_NOT_PHYSICAL", prefix)
        if not nonempty(row.get("business_evidence")):
            flag("TABLE_EVIDENCE_REQUIRED", prefix)
        groups = {}
        for group in ("metric_bindings", "dimension_bindings", "date_bindings",
                      "join_bindings", "dre_mappings"):
            value = row.get(group)
            if not isinstance(value, list):
                flag("BINDINGS_NOT_REVIEWED", prefix + "/" + group)
                value = []
            groups[group] = value

        for index, item in enumerate(groups["metric_bindings"]):
            at = f"{prefix}/metric:{index}"
            if not isinstance(item, Mapping):
                flag("METRIC_INVALID", at)
                continue
            col, agg = item.get("column"), item.get("aggregation")
            if (not valid_ident(col) or col not in cols or not isinstance(agg, str)
                    or agg not in AGGREGATIONS
                    or (agg in ("sum", "avg") and cols.get(col) not in NUMERIC)):
                flag("METRIC_COLUMN_OR_TYPE_INVALID", at)
            if not all(nonempty(item.get(k)) for k in ("concept", "sign_convention", "evidence")):
                flag("METRIC_BUSINESS_DEFINITION_REQUIRED", at)
            metric_count += 1

        for group, code, type_set in (
            ("dimension_bindings", "DIMENSION_INVALID", None),
            ("date_bindings", "DATE_REFERENCE_INVALID", TEMPORAL),
        ):
            for index, item in enumerate(groups[group]):
                at = f"{prefix}/{group}:{index}"
                col = item.get("column") if isinstance(item, Mapping) else None
                if (not valid_ident(col) or col not in cols
                        or (type_set is not None and cols.get(col) not in type_set)
                        or not nonempty(item.get("concept" if group == "dimension_bindings" else "reference"))
                        or not nonempty(item.get("evidence"))):
                    flag(code, at)

        for index, item in enumerate(groups["join_bindings"]):
            at = f"{prefix}/join:{index}"
            remote = item.get("to_table") if isinstance(item, Mapping) else None
            left = item.get("from_column") if isinstance(item, Mapping) else None
            right = item.get("to_column") if isinstance(item, Mapping) else None
            if (not isinstance(remote, str) or remote not in inventory
                    or not valid_ident(left) or not valid_ident(right) or left not in cols
                    or right not in inventory.get(remote, {})
                    or cols.get(left) != inventory.get(remote, {}).get(right)):
                flag("JOIN_PHYSICAL_REFERENCE_INVALID", at)
            cardinality = item.get("cardinality") if isinstance(item, Mapping) else None
            if (not isinstance(cardinality, str) or cardinality not in CARDINALITIES
                    or not nonempty(item.get("evidence"))):
                flag("JOIN_CARDINALITY_OR_EVIDENCE_REQUIRED", at)
            if cardinality == "one_to_many":
                flag("JOIN_FANOUT_REVIEW_REQUIRED", at)

        for index, item in enumerate(groups["dre_mappings"]):
            if not isinstance(item, Mapping) or not nonempty(item.get("evidence")):
                flag("DRE_EVIDENCE_REQUIRED", f"{prefix}/dre:{index}")

        # Preview contains no executable SQL, no customer-specific constants.
        if not any(where.startswith(prefix) for _, where in issues):
            catalog.append({
                "schema_name": policy["schema"], "table_name": name,
                "grain": grain, "primary_key": pk, "key_columns": sorted(keys),
                "metric_columns": sorted({m["column"] for m in groups["metric_bindings"]}),
                "date_columns": sorted({d["column"] for d in groups["date_bindings"]}),
                "join_rules": [{"from_column": j["from_column"], "to_table": j["to_table"],
                                "to_column": j["to_column"]} for j in groups["join_bindings"]],
                "columns": [{"name": col, "type": pgtype} for col, pgtype in sorted(cols.items())],
            })
    if metric_count == 0:
        flag("NO_FINANCIAL_METRIC_BINDINGS")
    issues.sort()
    return {
        "status": "structural_preview_only" if not issues else "blocked",
        "candidate_version": target if isinstance(target, str) and VERSION.fullmatch(target) else None,
        "source_version": version, "physical_fingerprint": expected["source"]["physical_fingerprint"],
        "table_count": len(inventory), "mapped_table_count": len(catalog),
        "metric_binding_count": metric_count,
        "issue_codes": sorted({code for code, _ in issues}),
        "issues": [{"code": code, "at": at} for code, at in issues],
        "table_catalog_preview": catalog if not issues else None,
        "finance_semantics_verified": False, "activation_authorized": False,
        "financial_sql_authorized": False, "financial_sql_executed": False, "llm_calls": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit-dir", required=True, type=Path)
    parser.add_argument("--policy", type=Path,
                        default=Path(__file__).with_name("g1_readonly_rollout.json"))
    parser.add_argument("--review-file", type=Path)
    args = parser.parse_args(argv)
    try:
        from scripts.operations import p3_source_alignment_readonly as p3
        policy = p3.validate_policy(json.loads(args.policy.read_text(encoding="utf-8")))
        if args.audit_dir.is_symlink():
            raise MappingBlocked("PRIVATE_DIRECTORY_REQUIRED")
        raw = p3.read_private_snapshot(args.audit_dir / "physical-metadata.json")
        context, physical, grants, identity = p3.verify_probe_snapshot(
            raw, policy, raw.get("context_version")
        )
        version = raw["context_version"]
        scope = p3.evaluate(policy, version, context, physical, grants, identity)
        if any(b in scope["blockers"] for b in (
            "ROLE_SCOPE_MISMATCH", "ROLE_WRITE_PRIVILEGE", "PHYSICAL_COLUMNS_MISSING"
        )):
            raise MappingBlocked("READER_SCOPE_NOT_VERIFIED")
        if args.review_file:
            review = p3.read_private_snapshot(args.review_file)
            report = check_review(review, policy, physical, version)
            print("P3_MAPPING_REVIEW=" + report["status"].upper())
            print("P3_MAPPING_TABLES=" + str(report["table_count"]))
            print("P3_MAPPING_ISSUE_CODES=" + ",".join(report["issue_codes"]))
            print("P3_MAPPING_AUTHORIZED=false")
            print("P3_MAPPING_FINANCIAL_SQL_EXECUTED=false")
            if report["status"] != "structural_preview_only":
                return 2
            p3.create_private_draft(args.audit_dir / "p3-semantic-table-catalog-preview.json", report)
            return 0
        draft = create_review(policy, physical, version)
        p3.create_private_draft(args.audit_dir / "p3-semantic-mapping-review.json", draft)
        print("P3_MAPPING_REVIEW=PRIVATE_TEMPLATE_CREATED")
        print("P3_MAPPING_TABLES=" + str(len(draft["tables"])))
        print("P3_MAPPING_AUTHORIZED=false")
        print("P3_MAPPING_FINANCIAL_SQL_EXECUTED=false")
        print("P3_MAPPING_LLM_CALLS=0")
        return 0
    except MappingBlocked as exc:
        print("P3_MAPPING_REVIEW=BLOCKED")
        print("P3_MAPPING_REASON=" + str(exc))
        return 2
    except Exception:
        print("P3_MAPPING_REVIEW=BLOCKED")
        print("P3_MAPPING_REASON=PRIVATE_EVIDENCE_UNAVAILABLE")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

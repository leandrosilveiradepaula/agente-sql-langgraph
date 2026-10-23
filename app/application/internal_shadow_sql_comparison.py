"""Post-generation comparison of an official SQL with persisted Shadow SQL.

Never used by planner/generator; no SQL execution or provider calls. Structural
agreement cannot establish financial parity. Raw SQL never appears in output.
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import re
from typing import Any

from app.application.internal_sql_agent_v1_shared import (
    organization_scope_matches,
    validated_organization_scope,
)
from app.domain.result_normalization import stable_fingerprint
from app.domain.shadow_evidence_types import validate_shadow_run_record
from app.domain.sql_analysis import SqlAnalysisError, analyze_sql
from app.ports.shadow_evidence_repository import ShadowEvidenceRepository

CONTRACT_VERSION = "1"
COMPARISON_VERSION = "v1.0.0-post-generation-structural"
_MAX_SQL_LENGTH = 262144
_MAX_QUESTION_LENGTH = 16000
_MAX_ID_LENGTH = 128
_COMPARISON_FIELDS = (
    "physical_tables", "joined_relations", "predicates", "projections",
    "groupings", "orderings", "functions", "query_shape",
)


class CompareShadowSqlUseCase:
    """Read existing evidence only, compare statements, return sanitized facets."""

    def __init__(
        self,
        *,
        repository: ShadowEvidenceRepository,
        expected_organization_id: str | None = None,
    ) -> None:
        if repository is None or not callable(getattr(repository, "fetch_by_shadow_record_id", None)):
            raise RuntimeError("Shadow evidence repository must be injected.")
        self._repository = repository
        self._expected_organization_id = validated_organization_scope(
            expected_organization_id
        )

    def execute(self, request: object) -> dict[str, Any]:
        if not isinstance(request, Mapping) or not _valid_request(request):
            return _response("rejected", "SHADOW_COMPARE_REQUEST_INVALID")
        agent_id = str(request["agent_run_id"])
        shadow_id = str(request["shadow_record_id"])
        principal = request["principal"]
        if not organization_scope_matches(request, self._expected_organization_id):
            # No foreign principal may trigger a repository lookup, SQL
            # analysis, provider, benchmark or financial execution.
            return _response("rejected", "SHADOW_COMPARE_TENANT_MISMATCH", agent_id)
        try:
            retrieved = self._repository.fetch_by_shadow_record_id(shadow_id)
        except Exception:
            return _response("infrastructure_error", "SHADOW_COMPARE_REPOSITORY_UNAVAILABLE", agent_id)
        if retrieved.get("status") == "unavailable":
            return _response("infrastructure_error", "SHADOW_COMPARE_REPOSITORY_UNAVAILABLE", agent_id)
        if retrieved.get("status") != "ok" or not retrieved.get("record"):
            return _response("rejected", "SHADOW_COMPARE_EVIDENCE_MISSING", agent_id)
        try:
            record = validate_shadow_run_record(retrieved["record"])
        except Exception:
            return _response("rejected", "SHADOW_COMPARE_EVIDENCE_INVALID", agent_id)

        stored_principal = record.get("principal", {})
        if not isinstance(stored_principal, Mapping):
            return _response("rejected", "SHADOW_COMPARE_IDENTITY_MISMATCH", agent_id)
        if (
            record.get("agent_run_id") != agent_id
            or record.get("shadow_record_id") != shadow_id
            or record.get("event_type") != "generate"
            or stored_principal.get("id") != principal["id"]
        ):
            return _response("rejected", "SHADOW_COMPARE_IDENTITY_MISMATCH", agent_id)

        source_tenant = stored_principal.get("organization_id")
        provided_tenant = principal.get("organization_id")
        if source_tenant != provided_tenant:
            return _response("rejected", "SHADOW_COMPARE_TENANT_MISMATCH", agent_id)
        tenant_attested = bool(source_tenant and provided_tenant)
        if record.get("question") != request["question"]:
            return _response("rejected", "SHADOW_COMPARE_QUESTION_MISMATCH", agent_id)
        fingerprints = record.get("fingerprints", {})
        if not isinstance(fingerprints, Mapping) or fingerprints.get("question") != stable_fingerprint(request["question"]):
            return _response("rejected", "SHADOW_COMPARE_QUESTION_MISMATCH", agent_id)
        if record.get("status") != "success":
            return _response("rejected", "SHADOW_COMPARE_GENERATION_NOT_SUCCESSFUL", agent_id)
        shadow_sql = record.get("generated_sql")
        if not isinstance(shadow_sql, str) or not shadow_sql.strip():
            return _response("rejected", "SHADOW_COMPARE_SHADOW_SQL_MISSING", agent_id)
        if len(shadow_sql) > _MAX_SQL_LENGTH:
            return _response("rejected", "SHADOW_COMPARE_SQL_TOO_LARGE", agent_id)
        if fingerprints.get("langgraph_sql") != stable_fingerprint(shadow_sql):
            return _response("rejected", "SHADOW_COMPARE_SQL_FINGERPRINT_MISMATCH", agent_id)

        # No generator, executor, provider, preflight or repository write port.
        try:
            official = analyze_sql(str(request["official_sql"]))
            shadow = analyze_sql(shadow_sql)
            if not all(_read_only_select(analysis) for analysis in (official, shadow)):
                return _response("rejected", "SHADOW_COMPARE_NON_READ_ONLY_SQL", agent_id)
            lhs, rhs = _structure(official), _structure(shadow)
            differences = [facet for facet in _COMPARISON_FIELDS if lhs[facet] != rhs[facet]]
            normalized_match = (
                _identity_preserving_tokens(official)
                == _identity_preserving_tokens(shadow)
            )
        except SqlAnalysisError:
            return _response("rejected", "SHADOW_COMPARE_SQL_UNSUPPORTED", agent_id)
        except Exception:
            return _response("infrastructure_error", "SHADOW_COMPARE_ANALYSIS_ERROR", agent_id)

        has_unsupported_predicates = any(
            not predicate.get("supported", False)
            for analysis in (official, shadow)
            for predicate in analysis.get("predicates", [])
        )
        # Identical strict token streams outrank the parser's presentation-only
        # facet differences (e.g. uppercase unquoted projection labels). Strict
        # tokens preserve string and quoted-identifier case, unlike the legacy
        # tokenizer normal form.
        if normalized_match and not has_unsupported_predicates:
            verdict = "normalized_sql_match"
            differences = []
        elif differences:
            verdict = "structural_differences"
        else:
            verdict = "inconclusive"
        lineage = record.get("lineage", {})
        lineage = lineage if isinstance(lineage, Mapping) else {}
        provider_identity = _recorded_provider_identity(record)
        intent_identity = _recorded_intent_identity(
            record, request.get("official_detected_intent")
        )
        return _response(
            "success", "SHADOW_COMPARE_COMPLETED", agent_id,
            run_id=str(record.get("run_id", "")),
            details={
                "comparison_version": COMPARISON_VERSION,
                "shadow_record_id": shadow_id,
                "verdict": verdict,
                "different_facets": differences,
                "normalized_sql_match": normalized_match,
                "unsupported_predicates_present": has_unsupported_predicates,
                "official_sql_fingerprint": stable_fingerprint(request["official_sql"]),
                "shadow_sql_fingerprint": stable_fingerprint(shadow_sql),
                "shadow_context_fingerprint": str(lineage.get("context_fingerprint") or ""),
                "shadow_context_version": str(lineage.get("context_version") or ""),
                **provider_identity,
                **intent_identity,
                "tenant_identity_attested": tenant_attested,
                "same_data_snapshot_attested": False,
                "financial_parity_proven": False,
                "real_sql_executed": False,
                "requires_reapproval": bool(record.get("repaired_sql_proposal"))
                or bool(record.get("requires_reapproval")),
            },
        )


_PROVIDER_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:+/-]{0,127}")


def _public_provider_id(value: object) -> str | None:
    """Allowlisted non-secret provider/model label, not transport or keys."""
    if not isinstance(value, str):
        return None
    label = value.strip()
    if not label or len(label) > 128 or _PROVIDER_ID_PATTERN.fullmatch(label) is None:
        return None
    lowered = label.casefold()
    if any(marker in lowered for marker in ("token", "secret", "apikey", "api_key", "bearer")):
        return None
    return label


def _recorded_provider_identity(record: Mapping[str, Any]) -> dict[str, str | None | bool]:
    """Derive identity strictly from the signed, persisted generation evidence.

    If model or provider was not emitted by an adapter, keep the proof absent;
    never infer from a configured default, provider alias or repair output.
    """
    evidence = record.get("langgraph_evidence")
    raw = evidence.get("provider_metadata") if isinstance(evidence, Mapping) else None
    metadata = raw if isinstance(raw, Mapping) else {}
    generation_provider = _public_provider_id(
        metadata.get("sql_generation_result_provider_name")
    )
    generation_model = _public_provider_id(
        metadata.get("sql_generation_result_provider_model")
    )
    repair_provider = _public_provider_id(
        metadata.get("sql_repair_result_provider_name")
    )
    repair_model = _public_provider_id(
        metadata.get("sql_repair_result_provider_model")
    )
    repair_present = bool(record.get("repaired_sql_proposal")) or bool(
        record.get("requires_reapproval")
    )
    return {
        "shadow_generator_provider": generation_provider,
        "shadow_generator_model": generation_model,
        "shadow_repair_provider": repair_provider,
        "shadow_repair_model": repair_model,
        "generator_identity_attested": bool(generation_provider and generation_model),
        "repair_identity_attested": not repair_present or bool(repair_provider and repair_model),
    }


def _recorded_intent_identity(
    record: Mapping[str, Any], official_intent: object
) -> dict[str, str]:
    """Literal post-generation intent-label check; no business alias mapping.

    A label match is only identity of recorded strings, not semantic or
    financial equivalence. Comparisons never read the benchmark.
    """
    evidence = record.get("langgraph_evidence")
    shadow_intent = evidence.get("intent") if isinstance(evidence, Mapping) else None
    if not isinstance(shadow_intent, str) or not shadow_intent.strip():
        return {"intent_label_status": "unattested"}
    if not isinstance(official_intent, str) or not official_intent.strip():
        return {"intent_label_status": "unattested"}
    return {"intent_label_status": (
        "identifiers_matched"
        if official_intent.strip() == shadow_intent.strip()
        else "identifier_mismatch"
    )}


def _valid_request(value: Mapping[str, Any]) -> bool:
    required = {"contract_version", "agent_run_id", "shadow_record_id", "question", "official_sql", "principal"}
    if not required <= set(value) or not set(value) <= (required | {"official_detected_intent"}):
        return False
    if "official_detected_intent" in value:
        intent_label = value["official_detected_intent"]
        if not isinstance(intent_label, str) or not intent_label.strip() or len(intent_label) > 128:
            return False
    if value.get("contract_version") != CONTRACT_VERSION:
        return False
    for key, cap in (
        ("agent_run_id", _MAX_ID_LENGTH), ("shadow_record_id", _MAX_ID_LENGTH),
        ("question", _MAX_QUESTION_LENGTH), ("official_sql", _MAX_SQL_LENGTH),
    ):
        item = value.get(key)
        if not isinstance(item, str) or not item.strip() or len(item) > cap:
            return False
    principal = value.get("principal")
    if not isinstance(principal, Mapping) or not set(principal) <= {"id", "organization_id"}:
        return False
    identifier = principal.get("id")
    if not isinstance(identifier, str) or not identifier.strip() or len(identifier) > 256:
        return False
    tenant = principal.get("organization_id")
    if tenant is not None and (
        not isinstance(tenant, str) or not tenant.strip() or len(tenant) > 256
    ):
        return False
    return True


def _read_only_select(analysis: Mapping[str, Any]) -> bool:
    return (
        analysis.get("status") == "analyzed"
        and analysis.get("statement_count") == 1
        and (
            analysis.get("statement_type") == "select"
            or (
                analysis.get("statement_type") == "with"
                and analysis.get("with_body_is_select") is True
            )
        )
        and analysis.get("has_select_into") is False
    )


def _identity_preserving_tokens(analysis: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    """Normalize SQL keywords, never string contents or quoted identifier case.

    The generic tokenizer's normalized values case-fold strings and quoted
    identifiers, which is unsafe for exact comparison of financial filters.
    Also include token kinds to avoid collapsing different representations.
    """
    tokens = analysis.get("tokens") or []
    return tuple(
        (str(token.get("kind")), (
            str(token.get("value"))
            if token.get("kind") in {"string", "quoted_identifier"}
            else str(token.get("normalized"))
        ))
        for token in tokens
    )


def _structure(analysis: Mapping[str, Any]) -> dict[str, Any]:
    """Conservative facets; matching structure is NOT semantic equivalence."""
    scopes = analysis.get("query_scopes") or []
    return {
        "physical_tables": sorted(analysis.get("tables") or []),
        "joined_relations": sorted(stable_fingerprint({
            "type": join.get("join_type"), "left": join.get("left_table"),
            "right": join.get("right_table"),
            "comparisons": join.get("join_comparisons", []),
        }) for join in (analysis.get("joins") or [])),
        "predicates": sorted(stable_fingerprint({
            "clause": item.get("clause"),
            "qualifier": item.get("qualifier"),
            "column": item.get("column"),
            "operator": item.get("operator"),
            "literal_type": item.get("literal_type"),
            "value": item.get("value"),
            "supported": item.get("supported"),
        }) for item in (analysis.get("predicates") or [])),
        "projections": [
            stable_fingerprint(scope.get("select_items", [])) for scope in scopes
        ],
        "groupings": [
            stable_fingerprint(scope.get("group_by_items", [])) for scope in scopes
        ],
        "orderings": [
            stable_fingerprint(scope.get("order_by_items", [])) for scope in scopes
        ],
        "functions": sorted(analysis.get("functions") or []),
        "query_shape": {
            "scopes": len(scopes),
            "joins": len(analysis.get("joins") or []),
            "has_aggregate": any(scope.get("has_aggregate") for scope in scopes),
            "has_limit": bool(analysis.get("has_limit")),
            "has_select_star": bool(analysis.get("has_select_star")),
            "has_table_star": bool(analysis.get("has_table_star")),
        },
    }


def _response(
    status: str, code: str, agent_run_id: str = "", *,
    run_id: str = "", details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "response_id": stable_fingerprint({
            "operation": "compare_shadow_sql", "agent_run_id": agent_run_id,
            "run_id": run_id, "code": code,
            # Different official SQL stages share the same run ID.
            # Their responses must have distinct audit identities.
            "comparison_payload_fingerprint": stable_fingerprint(details or {}),
        }),
        "agent_run_id": agent_run_id,
        "run_id": run_id,
        "status": status,
        "message": "Shadow comparison finished." if status == "success" else "Shadow comparison unavailable.",
        "errors": [] if status == "success" else [{
            "code": code, "stage": "comparison", "message": "Comparison was not completed.",
            "retryable": status == "infrastructure_error",
        }],
        "metadata": {
            "operation": "compare_shadow_sql",
            **({"comparison": deepcopy(dict(details))} if details else {}),
        },
    }
    body["response_fingerprint"] = stable_fingerprint(body)
    return body

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from app.domain.shadow_evidence_types import (
    FinalizeShadowRunRequest,
    ShadowRepositoryResult,
    ShadowRunRecord,
    strict_json_dumps,
    validate_shadow_run_record,
)


INSERT_SHADOW_RUN_SQL = """
INSERT INTO public.langgraph_shadow_runs (
  shadow_record_id,
  agent_run_id,
  run_id,
  event_type,
  contract_version,
  status,
  created_at,
  completed_at,
  question,
  approved_sql_original,
  generated_sql,
  repaired_sql_proposal,
  requires_reapproval,
  principal,
  correlation_metadata,
  options,
  semantic_context,
  n8n_baseline,
  langgraph_evidence,
  execution_future,
  fingerprints,
  lineage,
  langgraph_version,
  langgraph_commit,
  evidence_fingerprint
) VALUES (
  %(shadow_record_id)s,
  %(agent_run_id)s,
  %(run_id)s,
  %(event_type)s,
  %(contract_version)s,
  %(status)s,
  %(created_at)s::timestamptz,
  %(completed_at)s::timestamptz,
  %(question)s,
  %(approved_sql_original)s,
  %(generated_sql)s,
  %(repaired_sql_proposal)s,
  %(requires_reapproval)s,
  %(principal)s::jsonb,
  %(correlation_metadata)s::jsonb,
  %(options)s::jsonb,
  %(semantic_context)s::jsonb,
  %(n8n_baseline)s::jsonb,
  %(langgraph_evidence)s::jsonb,
  %(execution_future)s::jsonb,
  %(fingerprints)s::jsonb,
  %(lineage)s::jsonb,
  %(langgraph_version)s,
  %(langgraph_commit)s,
  %(evidence_fingerprint)s
)
ON CONFLICT (shadow_record_id) DO NOTHING
"""

UPDATE_SHADOW_EVIDENCE_SQL = """
UPDATE public.langgraph_shadow_runs
SET
  status = %(status)s,
  completed_at = %(completed_at)s::timestamptz,
  question = %(question)s,
  approved_sql_original = %(approved_sql_original)s,
  generated_sql = %(generated_sql)s,
  repaired_sql_proposal = %(repaired_sql_proposal)s,
  requires_reapproval = %(requires_reapproval)s,
  principal = %(principal)s::jsonb,
  correlation_metadata = %(correlation_metadata)s::jsonb,
  options = %(options)s::jsonb,
  semantic_context = %(semantic_context)s::jsonb,
  n8n_baseline = %(n8n_baseline)s::jsonb,
  langgraph_evidence = %(langgraph_evidence)s::jsonb,
  execution_future = %(execution_future)s::jsonb,
  fingerprints = %(fingerprints)s::jsonb,
  lineage = %(lineage)s::jsonb,
  langgraph_version = %(langgraph_version)s,
  langgraph_commit = %(langgraph_commit)s,
  evidence_fingerprint = %(evidence_fingerprint)s,
  updated_at = now()
WHERE shadow_record_id = %(shadow_record_id)s
"""

FINALIZE_SHADOW_RUN_SQL = """
UPDATE public.langgraph_shadow_runs
SET
  status = %(status)s,
  completed_at = %(completed_at)s::timestamptz,
  evidence_fingerprint = %(evidence_fingerprint)s,
  updated_at = now()
WHERE shadow_record_id = %(shadow_record_id)s
"""

FETCH_SHADOW_RUN_SQL = """
SELECT
  shadow_record_id,
  agent_run_id,
  run_id,
  event_type,
  contract_version,
  status,
  created_at,
  completed_at,
  question,
  approved_sql_original,
  generated_sql,
  repaired_sql_proposal,
  requires_reapproval,
  principal,
  correlation_metadata,
  options,
  semantic_context,
  n8n_baseline,
  langgraph_evidence,
  execution_future,
  fingerprints,
  lineage,
  langgraph_version,
  langgraph_commit,
  evidence_fingerprint
FROM public.langgraph_shadow_runs
WHERE shadow_record_id = %(shadow_record_id)s
"""

LIST_SHADOW_RUNS_BY_AGENT_SQL = """
SELECT
  shadow_record_id,
  agent_run_id,
  run_id,
  event_type,
  contract_version,
  status,
  created_at,
  completed_at,
  question,
  approved_sql_original,
  generated_sql,
  repaired_sql_proposal,
  requires_reapproval,
  principal,
  correlation_metadata,
  options,
  semantic_context,
  n8n_baseline,
  langgraph_evidence,
  execution_future,
  fingerprints,
  lineage,
  langgraph_version,
  langgraph_commit,
  evidence_fingerprint
FROM public.langgraph_shadow_runs
WHERE agent_run_id = %(agent_run_id)s
ORDER BY created_at, shadow_record_id
"""


ConnectCallable = Callable[..., Any]


class PostgresShadowEvidenceRepository:
    """
    PostgreSQL implementation for separated LangGraph shadow evidence.

    It receives its connection explicitly. Instantiation does not open a
    connection and does not run migrations.
    """

    def __init__(
        self,
        *,
        dsn: str,
        connect_timeout_seconds: int = 10,
        connect: ConnectCallable = psycopg.connect,
    ) -> None:
        normalized_dsn = dsn.strip()
        if not normalized_dsn:
            raise ValueError("dsn nao pode estar vazio.")
        if (
            not isinstance(connect_timeout_seconds, int)
            or isinstance(connect_timeout_seconds, bool)
            or connect_timeout_seconds <= 0
        ):
            raise ValueError("connect_timeout_seconds deve ser positivo.")
        self._dsn = normalized_dsn
        self._connect_timeout_seconds = connect_timeout_seconds
        self._connect = connect

    def create(self, record: ShadowRunRecord) -> ShadowRepositoryResult:
        captured = validate_shadow_run_record(record)
        return self._execute_write(
            INSERT_SHADOW_RUN_SQL,
            _record_parameters(captured),
            captured,
            status="created",
            zero_status="already_exists",
        )

    def update_evidence(self, record: ShadowRunRecord) -> ShadowRepositoryResult:
        captured = validate_shadow_run_record(record)
        return self._execute_write(
            UPDATE_SHADOW_EVIDENCE_SQL,
            _record_parameters(captured),
            captured,
            status="updated",
            zero_status="not_found",
        )

    def finalize(self, request: FinalizeShadowRunRequest) -> ShadowRepositoryResult:
        parameters = deepcopy(dict(request))
        try:
            with self._connect(
                self._dsn,
                connect_timeout=self._connect_timeout_seconds,
                row_factory=dict_row,
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(FINALIZE_SHADOW_RUN_SQL, parameters)
                    rowcount = int(getattr(cursor, "rowcount", -1))
                _commit(connection)
        except psycopg.Error:
            return _error_result(
                request["shadow_record_id"],
                None,
                None,
                request["evidence_fingerprint"],
            )
        if rowcount == 0:
            return _not_found_result(
                request["shadow_record_id"],
                None,
                None,
                request["evidence_fingerprint"],
            )
        return {
            "status": "finalized",
            "shadow_record_id": request["shadow_record_id"],
            "agent_run_id": None,
            "run_id": None,
            "evidence_fingerprint": request["evidence_fingerprint"],
            "diagnostic": None,
            "duration_ms": None,
        }

    def fetch_by_shadow_record_id(
        self,
        shadow_record_id: str,
    ) -> ShadowRunRecord | None:
        try:
            with self._connect(
                self._dsn,
                connect_timeout=self._connect_timeout_seconds,
                row_factory=dict_row,
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        FETCH_SHADOW_RUN_SQL,
                        {"shadow_record_id": shadow_record_id},
                    )
                    row = cursor.fetchone()
        except psycopg.Error:
            return None
        return _record_from_row(row) if row is not None else None

    def list_by_agent_run_id(self, agent_run_id: str) -> list[ShadowRunRecord]:
        try:
            with self._connect(
                self._dsn,
                connect_timeout=self._connect_timeout_seconds,
                row_factory=dict_row,
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        LIST_SHADOW_RUNS_BY_AGENT_SQL,
                        {"agent_run_id": agent_run_id},
                    )
                    rows = cursor.fetchall()
        except psycopg.Error:
            return []
        return [_record_from_row(row) for row in rows]

    def _execute_write(
        self,
        query: str,
        parameters: dict[str, Any],
        record: ShadowRunRecord,
        *,
        status: str,
        zero_status: str,
    ) -> ShadowRepositoryResult:
        try:
            with self._connect(
                self._dsn,
                connect_timeout=self._connect_timeout_seconds,
                row_factory=dict_row,
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query, parameters)
                    rowcount = int(getattr(cursor, "rowcount", -1))
                _commit(connection)
        except psycopg.Error:
            return _error_result(
                record["shadow_record_id"],
                record["agent_run_id"],
                record["run_id"],
                record["evidence_fingerprint"],
            )
        if rowcount == 0:
            if zero_status == "not_found":
                return _not_found_result(
                    record["shadow_record_id"],
                    record["agent_run_id"],
                    record["run_id"],
                    record["evidence_fingerprint"],
                )
            return {
                "status": zero_status,  # type: ignore[typeddict-item]
                "shadow_record_id": record["shadow_record_id"],
                "agent_run_id": record["agent_run_id"],
                "run_id": record["run_id"],
                "evidence_fingerprint": record["evidence_fingerprint"],
                "diagnostic": None,
                "duration_ms": None,
            }
        return {
            "status": status,  # type: ignore[typeddict-item]
            "shadow_record_id": record["shadow_record_id"],
            "agent_run_id": record["agent_run_id"],
            "run_id": record["run_id"],
            "evidence_fingerprint": record["evidence_fingerprint"],
            "diagnostic": None,
            "duration_ms": None,
        }


def _record_parameters(record: ShadowRunRecord) -> dict[str, Any]:
    return {
        "shadow_record_id": record["shadow_record_id"],
        "agent_run_id": record["agent_run_id"],
        "run_id": record["run_id"],
        "event_type": record["event_type"],
        "contract_version": record["contract_version"],
        "status": record["status"],
        "created_at": record["created_at"],
        "completed_at": record.get("completed_at"),
        "question": record.get("question"),
        "approved_sql_original": record.get("approved_sql_original"),
        "generated_sql": record.get("generated_sql"),
        "repaired_sql_proposal": record.get("repaired_sql_proposal"),
        "requires_reapproval": record["requires_reapproval"],
        "principal": strict_json_dumps(record.get("principal", {})),
        "correlation_metadata": strict_json_dumps(record.get("correlation_metadata", {})),
        "options": strict_json_dumps(record.get("options", {})),
        "semantic_context": strict_json_dumps(record.get("semantic_context") or {}),
        "n8n_baseline": strict_json_dumps(record.get("n8n_baseline", {})),
        "langgraph_evidence": strict_json_dumps(record.get("langgraph_evidence", {})),
        "execution_future": strict_json_dumps(record.get("execution_future", {})),
        "fingerprints": strict_json_dumps(record.get("fingerprints", {})),
        "lineage": strict_json_dumps(record.get("lineage", {})),
        "langgraph_version": record.get("langgraph_version"),
        "langgraph_commit": record.get("langgraph_commit"),
        "evidence_fingerprint": record["evidence_fingerprint"],
    }


def _record_from_row(row: Any) -> ShadowRunRecord:
    raw = dict(row)
    raw["created_at"] = _normalize_timestamp(raw.get("created_at"))
    raw["completed_at"] = _normalize_timestamp(raw.get("completed_at"))
    for key in (
        "principal",
        "correlation_metadata",
        "options",
        "semantic_context",
        "n8n_baseline",
        "langgraph_evidence",
        "execution_future",
        "fingerprints",
        "lineage",
    ):
        value = raw.get(key)
        if isinstance(value, str):
            raw[key] = json.loads(value)
    return validate_shadow_run_record(raw)



def _normalize_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return None
        candidate = normalized.replace(" ", "T", 1)
        if len(candidate) >= 3 and candidate[-3] in {"+", "-"}:
            candidate = f"{candidate}:00"
        try:
            return datetime.fromisoformat(candidate).isoformat()
        except ValueError:
            return normalized
    return str(value)

def _commit(connection: Any) -> None:
    commit = getattr(connection, "commit", None)
    if callable(commit):
        commit()



def _not_found_result(
    shadow_record_id: str,
    agent_run_id: str | None,
    run_id: str | None,
    evidence_fingerprint: str | None,
) -> ShadowRepositoryResult:
    return {
        "status": "not_found",
        "shadow_record_id": shadow_record_id,
        "agent_run_id": agent_run_id,
        "run_id": run_id,
        "evidence_fingerprint": evidence_fingerprint,
        "diagnostic": {
            "code": "SHADOW_RECORD_NOT_FOUND",
            "message": "Shadow record was not found.",
            "failure_category": "not_found",
            "safe_details": {},
        },
        "duration_ms": None,
    }

def _error_result(
    shadow_record_id: str,
    agent_run_id: str | None,
    run_id: str | None,
    evidence_fingerprint: str | None,
) -> ShadowRepositoryResult:
    return {
        "status": "error",
        "shadow_record_id": shadow_record_id,
        "agent_run_id": agent_run_id,
        "run_id": run_id,
        "evidence_fingerprint": evidence_fingerprint,
        "diagnostic": {
            "code": "SHADOW_REPOSITORY_UNAVAILABLE",
            "message": "Shadow evidence repository unavailable.",
            "failure_category": "unavailable",
            "safe_details": {},
        },
        "duration_ms": None,
    }

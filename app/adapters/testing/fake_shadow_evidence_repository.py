from __future__ import annotations

from copy import deepcopy

from app.domain.shadow_evidence_types import (
    FinalizeShadowRunRequest,
    ShadowRepositoryFetchResult,
    ShadowRepositoryListResult,
    ShadowRepositoryResult,
    ShadowRunRecord,
    validate_shadow_run_record,
)


class FakeShadowEvidenceRepository:
    """
    In-memory shadow evidence repository for offline tests.

    It never writes files, never opens a database, and is not a production
    default. Stored records are independent sanitized copies.
    """

    def __init__(self) -> None:
        self.create_calls = 0
        self.update_calls = 0
        self.finalize_calls = 0
        self.created_records: list[ShadowRunRecord] = []
        self.updated_records: list[ShadowRunRecord] = []
        self.finalize_requests: list[FinalizeShadowRunRequest] = []
        self.records: dict[str, ShadowRunRecord] = {}

    def create(self, record: ShadowRunRecord) -> ShadowRepositoryResult:
        self.create_calls += 1
        captured = validate_shadow_run_record(record)
        self.created_records.append(deepcopy(captured))
        shadow_record_id = captured["shadow_record_id"]
        previous = self.records.get(shadow_record_id)
        if previous is not None:
            if previous["evidence_fingerprint"] == captured["evidence_fingerprint"]:
                return _result("already_exists", captured)
            return _diagnostic_result(
                "rejected",
                captured,
                "SHADOW_RECORD_CONFLICT",
                "Shadow record already exists with another fingerprint.",
            )
        self.records[shadow_record_id] = deepcopy(captured)
        return _result("created", captured)

    def update_evidence(self, record: ShadowRunRecord) -> ShadowRepositoryResult:
        self.update_calls += 1
        captured = validate_shadow_run_record(record)
        self.updated_records.append(deepcopy(captured))
        shadow_record_id = captured["shadow_record_id"]
        if shadow_record_id not in self.records:
            return _diagnostic_result(
                "not_found",
                captured,
                "SHADOW_RECORD_NOT_FOUND",
                "Shadow record was not found.",
            )
        self.records[shadow_record_id] = deepcopy(captured)
        return _result("updated", captured)

    def finalize(self, request: FinalizeShadowRunRequest) -> ShadowRepositoryResult:
        self.finalize_calls += 1
        captured = deepcopy(request)
        self.finalize_requests.append(captured)
        record = self.records.get(captured["shadow_record_id"])
        if record is None:
            return {
                "status": "not_found",
                "shadow_record_id": captured["shadow_record_id"],
                "agent_run_id": None,
                "run_id": None,
                "evidence_fingerprint": captured["evidence_fingerprint"],
                "diagnostic": {
                    "code": "SHADOW_RECORD_NOT_FOUND",
                    "message": "Shadow record was not found.",
                    "failure_category": "not_found",
                    "safe_details": {},
                },
                "duration_ms": 0,
            }
        record["status"] = captured["status"]
        record["completed_at"] = captured["completed_at"]
        record["evidence_fingerprint"] = captured["evidence_fingerprint"]
        self.records[captured["shadow_record_id"]] = validate_shadow_run_record(record)
        return _result("finalized", self.records[captured["shadow_record_id"]])

    def fetch_by_shadow_record_id(
        self,
        shadow_record_id: str,
    ) -> ShadowRepositoryFetchResult:
        record = self.records.get(shadow_record_id)
        if record is None:
            return {
                "status": "not_found",
                "record": None,
                "diagnostic": {
                    "code": "SHADOW_RECORD_NOT_FOUND",
                    "message": "Shadow record was not found.",
                    "failure_category": "not_found",
                    "safe_details": {},
                },
            }
        return {"status": "ok", "record": deepcopy(record), "diagnostic": None}

    def list_by_agent_run_id(self, agent_run_id: str) -> ShadowRepositoryListResult:
        return {
            "status": "ok",
            "records": [
                deepcopy(record)
                for record in self.records.values()
                if record["agent_run_id"] == agent_run_id
            ],
            "diagnostic": None,
        }


def _result(status: str, record: ShadowRunRecord) -> ShadowRepositoryResult:
    return {
        "status": status,  # type: ignore[typeddict-item]
        "shadow_record_id": record["shadow_record_id"],
        "agent_run_id": record["agent_run_id"],
        "run_id": record["run_id"],
        "evidence_fingerprint": record["evidence_fingerprint"],
        "diagnostic": None,
        "duration_ms": 0,
    }


def _diagnostic_result(
    status: str,
    record: ShadowRunRecord,
    code: str,
    message: str,
) -> ShadowRepositoryResult:
    return {
        "status": status,  # type: ignore[typeddict-item]
        "shadow_record_id": record["shadow_record_id"],
        "agent_run_id": record["agent_run_id"],
        "run_id": record["run_id"],
        "evidence_fingerprint": record["evidence_fingerprint"],
        "diagnostic": {
            "code": code,
            "message": message,
            "failure_category": status,
            "safe_details": {},
        },
        "duration_ms": 0,
    }

from __future__ import annotations

from typing import Protocol

from app.domain.shadow_evidence_types import (
    FinalizeShadowRunRequest,
    ShadowRepositoryResult,
    ShadowRunRecord,
)


class ShadowEvidenceRepository(Protocol):
    def create(
        self,
        record: ShadowRunRecord,
    ) -> ShadowRepositoryResult:
        """
        Starts a separated shadow evidence record.
        """

    def update_evidence(
        self,
        record: ShadowRunRecord,
    ) -> ShadowRepositoryResult:
        """
        Persists or replaces sanitized shadow evidence for an existing record.
        """

    def finalize(
        self,
        request: FinalizeShadowRunRequest,
    ) -> ShadowRepositoryResult:
        """
        Finalizes status and completion metadata for a shadow record.
        """

    def fetch_by_shadow_record_id(
        self,
        shadow_record_id: str,
    ) -> ShadowRunRecord | None:
        """
        Loads one shadow record by its dedicated identifier.
        """

    def list_by_agent_run_id(
        self,
        agent_run_id: str,
    ) -> list[ShadowRunRecord]:
        """
        Lists all shadow records correlated to one product run id.
        """

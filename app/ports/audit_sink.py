from __future__ import annotations

from typing import Protocol

from app.domain.run_audit_types import AuditEvent, AuditResult


class AuditSink(Protocol):
    def write(
        self,
        event: AuditEvent,
    ) -> AuditResult:
        """
        Registra evento de auditoria por porta explicita.
        """

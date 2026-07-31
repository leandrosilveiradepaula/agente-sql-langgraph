from __future__ import annotations

from typing import Protocol

from app.domain.run_observability_types import (
    ObservabilityEvent,
    ObservabilityResult,
)


class ObservabilitySink(Protocol):
    def emit(
        self,
        event: ObservabilityEvent,
    ) -> ObservabilityResult:
        """
        Emite observabilidade por porta explicita.
        """

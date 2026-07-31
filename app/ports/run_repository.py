from __future__ import annotations

from typing import Protocol

from app.domain.run_persistence_types import (
    PersistRunRequest,
    PersistRunResult,
)


class RunRepository(Protocol):
    def save(
        self,
        request: PersistRunRequest,
    ) -> PersistRunResult:
        """
        Persiste um RunRecord por porta explicita.
        """

from __future__ import annotations

from typing import Protocol

from app.ports.sql_repairer import SqlRepairer


class SqlRepairerResolver(Protocol):
    """Resolve repair using the SAME versioned selection as SQL generation."""

    def resolve(
        self,
        *,
        provider_key: str,
        model_key: str,
        config_version: str,
    ) -> SqlRepairer: ...

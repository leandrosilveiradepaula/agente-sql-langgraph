from __future__ import annotations

from dataclasses import dataclass

from app.ports.sql_repairer import SqlRepairer


class SqlRepairerSelectionError(LookupError):
    """No registered repairer for the explicitly selected provider."""


@dataclass(frozen=True, slots=True)
class SqlRepairerRegistration:
    provider_key: str
    model_key: str
    config_version: str
    repairer: SqlRepairer

    def __post_init__(self) -> None:
        for name in ("provider_key", "model_key", "config_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Invalid SQL repairer registration.")
        if self.repairer is None or not callable(getattr(self.repairer, "repair", None)):
            raise ValueError("SQL repairer is unavailable.")


class SqlRepairerRegistry:
    """Generic registry: no client-specific rules and no default fallback."""

    def __init__(self, registrations: list[SqlRepairerRegistration]) -> None:
        self._items: dict[tuple[str, str, str], SqlRepairer] = {}
        for item in registrations:
            key = (item.provider_key.strip(), item.model_key.strip(),
                   item.config_version.strip())
            if key in self._items:
                raise ValueError("SQL repairer identity is duplicated.")
            self._items[key] = item.repairer

    def resolve(self, *, provider_key: str, model_key: str,
                config_version: str) -> SqlRepairer:
        values = (provider_key, model_key, config_version)
        if not all(isinstance(v, str) and bool(v.strip()) for v in values):
            raise SqlRepairerSelectionError("llm_selection_invalid")
        key = tuple(v.strip() for v in values)
        item = self._items.get(key)
        if item is None:
            raise SqlRepairerSelectionError("llm_selection_unavailable")
        return item

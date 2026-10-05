from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app.ports.sql_generator import SqlGenerator


class SqlGeneratorSelectionError(LookupError):
    """
    Selecao de provider/modelo nao cadastrada ou indisponivel.
    """


@dataclass(frozen=True, slots=True)
class SqlGeneratorRegistration:
    provider_key: str
    model_key: str
    config_version: str
    generator: SqlGenerator

    def __post_init__(self) -> None:
        for field_name in ("provider_key", "model_key", "config_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} deve ser texto nao vazio.")
        if self.generator is None:
            raise ValueError("generator deve ser informado.")


class SqlGeneratorRegistry:
    """
    Registry estrutural de generators.

    A chave vem de configuracao versionada. Nenhuma regra de negocio ou pergunta
    participa da resolucao.
    """

    def __init__(self, registrations: list[SqlGeneratorRegistration]) -> None:
        items: dict[tuple[str, str, str], SqlGenerator] = {}
        for registration in registrations:
            key = self._key(
                registration.provider_key,
                registration.model_key,
                registration.config_version,
            )
            if key in items:
                raise ValueError("Registro LLM duplicado.")
            items[key] = registration.generator
        self._items: Mapping[tuple[str, str, str], SqlGenerator] = items

    def __repr__(self) -> str:
        return f"SqlGeneratorRegistry(registrations={len(self._items)})"

    def resolve(
        self,
        *,
        provider_key: str,
        model_key: str,
        config_version: str,
    ) -> SqlGenerator:
        key = self._key(provider_key, model_key, config_version)
        generator = self._items.get(key)
        if generator is None:
            raise SqlGeneratorSelectionError("llm_selection_unavailable")
        return generator

    @staticmethod
    def _key(
        provider_key: str,
        model_key: str,
        config_version: str,
    ) -> tuple[str, str, str]:
        values = (provider_key, model_key, config_version)
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise SqlGeneratorSelectionError("llm_selection_invalid")
        return tuple(value.strip() for value in values)  # type: ignore[return-value]

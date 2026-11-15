"""Explicit opt-in, deterministic PostgreSQL SqlGenerator port for approved catalogs.

This adapter is NOT automatically registered with Gemini or n8n. Operators
must bind it to an approved canonical tenant/version/fingerprint. It never
calls a model or executes SQL. Its purpose is to make fully structural
multi-fact plans usable without hoping a general LLM reproduces an exact
security-verifiable SQL rendering.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.adapters.postgres.metric_source_composition_sql import (
    PostgresCompositionSqlError,
    build_postgres_metric_source_sql,
)
from app.domain.sql_generation import (
    SQL_GENERATION_CONTRACT_VERSION,
    SqlGenerationProviderError,
    SqlGenerationProviderResult,
    SqlGenerationRequest,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CatalogCompositionSqlGenerator:
    """Catalog-compiled SQL with independent context version and SHA pin."""

    def __init__(
        self,
        *,
        source_mode: str,
        expected_context_version: str,
        expected_context_fingerprint: str,
    ) -> None:
        if source_mode != "canonical_snapshot":
            raise ValueError("CATALOG_GENERATOR_REQUIRES_CANONICAL_CONTEXT")
        if not isinstance(expected_context_version, str) or not (
            0 < len(expected_context_version) <= 128
            and expected_context_version.strip() == expected_context_version
        ):
            raise ValueError("CATALOG_GENERATOR_VERSION_PIN_REQUIRED")
        if not isinstance(expected_context_fingerprint, str) or (
            _SHA256.fullmatch(expected_context_fingerprint) is None
        ):
            raise ValueError("CATALOG_GENERATOR_FINGERPRINT_PIN_REQUIRED")
        self._version = expected_context_version
        self._fingerprint = expected_context_fingerprint

    def __repr__(self) -> str:
        return "CatalogCompositionSqlGenerator(pinned=True)"

    def generate(
        self,
        request: SqlGenerationRequest,
    ) -> SqlGenerationProviderResult:
        if (
            not isinstance(request, Mapping)
            or request.get("contract_version") != SQL_GENERATION_CONTRACT_VERSION
        ):
            raise SqlGenerationProviderError(
                "Contrato estrutural invalido.",
                reason="invalid_compiler_request",
            )
        context = request.get("generation_context")
        if not isinstance(context, Mapping):
            raise SqlGenerationProviderError(
                "Contexto semantico ausente.",
                reason="missing_compiler_context",
            )
        if (
            context.get("context_version") != self._version
            or context.get("context_fingerprint") != self._fingerprint
        ):
            raise SqlGenerationProviderError(
                "Versao e fingerprint do catalogo nao coincidem.",
                reason="compiler_context_pin_mismatch",
            )
        if context.get("metric_source_composition") is None:
            raise SqlGenerationProviderError(
                "Nenhuma composicao autorizada para o compilador.",
                reason="compiler_composition_not_selected",
            )
        try:
            sql = build_postgres_metric_source_sql(request)
        except (PostgresCompositionSqlError, KeyError, TypeError, ValueError):
            raise SqlGenerationProviderError(
                "Composicao semantica invalida.",
                reason="compiler_composition_invalid",
            ) from None
        return {
            "provider_name": "approved_postgres_catalog_compiler",
            "provider_model": "deterministic_v1",
            "output_text": sql,
            "duration_ms": 0,
            "token_usage": {
                "provider": "approved_postgres_catalog_compiler",
                "model": "deterministic_v1",
                "prompt_tokens": 0,
                "response_tokens": 0,
                "total_tokens": 0,
            },
        }

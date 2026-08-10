from __future__ import annotations

from copy import deepcopy

from app.domain.context import ContextSnapshot
from app.domain.context_normalizer import normalize_context_snapshot
from app.domain.engine_preflight import (
    EnginePreflightProviderResult,
    EnginePreflightRequest,
)
from app.domain.sql_generation import (
    SqlGenerationProviderResult,
    SqlGenerationRequest,
)
from app.domain.sql_repair import SqlRepairProviderResult, SqlRepairRequest


OFFLINE_SQL = "SELECT id FROM schema_test.table_test"


class ShadowTestContextRepository:
    def load_active_context(self, *, user_profile: str) -> ContextSnapshot:
        del user_profile
        return normalize_context_snapshot(
            {
                "semantic_agent_version": "context-shadow-test",
                "semantic_context_source": "shadow_test_offline_context",
                "regras": [
                    {
                        "rule_group": "configuration",
                        "rule_name": "intent_resolver_config",
                        "rule_content": {
                            "component": "intent_resolver",
                            "minimum_score": 100,
                            "ambiguity_margin": 20,
                            "applied_confidence": 0.98,
                            "fallback_to_previous_intent": True,
                            "token_fallback": {"enabled": False},
                        },
                        "applies_to_intents": [],
                        "validation_hint": None,
                        "severity": "info",
                        "priority": 1,
                    },
                    {
                        "rule_group": "general",
                        "rule_name": "generic_test_rule",
                        "rule_content": {"enabled": True},
                        "applies_to_intents": ["generic_test_intent"],
                        "validation_hint": None,
                        "severity": "error",
                        "priority": 2,
                    },
                ],
                "entidades": [
                    {
                        "entity_type": "intent_signal",
                        "user_term": "generic analysis",
                        "canonical_value": "generic_test_intent",
                        "target_table": None,
                        "target_column": None,
                        "sql_filter_hint": {
                            "resolver": {
                                "match_mode": "contains",
                                "polarity": "positive",
                                "score": 120,
                            }
                        },
                        "business_rule": None,
                        "priority": 1,
                    }
                ],
                "dre": [],
                "padroes": [
                    {
                        "intent_name": "generic_test_intent",
                        "pattern_name": "generic_test_pattern",
                        "business_question_examples": [],
                        "required_tables": ["schema_test.table_test"],
                        "required_rules": ["generic_test_rule"],
                        "sql_pattern": "SELECT 1",
                        "notes": None,
                        "priority": 1,
                    }
                ],
                "catalogo": [
                    {
                        "table_name": "table_test",
                        "schema_name": "schema_test",
                        "table_type": "table",
                        "description": "Shadow TEST offline table.",
                        "grain": None,
                        "primary_key": ["id"],
                        "key_columns": ["id"],
                        "metric_columns": ["value"],
                        "date_columns": ["event_date"],
                        "join_rules": [],
                        "ai_hint": None,
                        "priority": 1,
                    }
                ],
                "context_counts": {
                    "regras": 2,
                    "entidades": 1,
                    "dre": 0,
                    "padroes": 1,
                    "catalogo": 1,
                },
            }
        )


class ShadowTestSqlGenerator:
    def __init__(self, sql: str = OFFLINE_SQL) -> None:
        self.sql = sql
        self.calls = 0

    def generate(
        self,
        request: SqlGenerationRequest,
    ) -> SqlGenerationProviderResult:
        serialized = repr(request).casefold()
        for forbidden in ("password", "secret", "token", "dsn"):
            assert forbidden not in serialized
        self.calls += 1
        return {
            "provider_name": "shadow_test_offline_sql_generator",
            "output_text": self.sql,
            "duration_ms": 1,
        }


class ShadowTestEnginePreflight:
    def __init__(self) -> None:
        self.calls = 0
        self.last_request: EnginePreflightRequest | None = None

    def preflight(
        self,
        request: EnginePreflightRequest,
    ) -> EnginePreflightProviderResult:
        self.calls += 1
        self.last_request = deepcopy(request)
        return {
            "status": "approved",
            "provider_name": "shadow_test_offline_engine_preflight",
            "provider_version": "shadow-test",
            "duration_ms": 1,
            "statement_planned": True,
            "executed": False,
            "rows_returned": 0,
        }


class ShadowTestSqlRepairer:
    def __init__(self, sql: str = OFFLINE_SQL) -> None:
        self.sql = sql
        self.calls = 0

    def repair(self, request: SqlRepairRequest) -> SqlRepairProviderResult:
        serialized = repr(request).casefold()
        for forbidden in ("password", "secret", "token", "dsn"):
            assert forbidden not in serialized
        self.calls += 1
        return {
            "provider_name": "shadow_test_offline_sql_repairer",
            "output_text": self.sql,
            "duration_ms": 1,
        }


class ShadowTestIds:
    def __init__(self) -> None:
        self.index = 0

    def __call__(self) -> str:
        self.index += 1
        return f"lg-shadow-test-run-{self.index}"

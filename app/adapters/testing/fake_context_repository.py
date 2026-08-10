from __future__ import annotations

from app.domain.context import ContextSnapshot
from app.domain.context_normalizer import normalize_context_snapshot


class FakeContextRepository:
    """
    Static semantic context for local/offline tests.

    It never opens Postgres or any external context source.
    """

    def load_active_context(
        self,
        *,
        user_profile: str,
    ) -> ContextSnapshot:
        del user_profile
        return normalize_context_snapshot(
            {
                "semantic_agent_version": "context-local-shadow-e2e",
                "semantic_context_source": "local_fake_context_repository",
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
                        "description": "Local fake table for shadow E2E tests.",
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

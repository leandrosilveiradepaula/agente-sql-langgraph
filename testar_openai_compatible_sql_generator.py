from __future__ import annotations

import unittest

from app.integrations.openai_compatible.configuration import (
    OpenAiCompatibleConfiguration,
)
from app.integrations.openai_compatible.sql_generator_adapter import (
    OpenAiCompatibleSqlGeneratorAdapter,
)
from app.domain.sql_generation import SQL_GENERATION_CONTRACT_VERSION


class _Client:
    def generate_content(self, request):
        return {
            "status": "success",
            "output_text": "SELECT 1",
            "duration_ms": 12,
            "token_usage": {
                "provider": "local_provider",
                "model": "sql-model",
                "prompt_tokens": 10,
                "response_tokens": 3,
                "total_tokens": 13,
            },
        }



class _FailingClient:
    def __init__(self, error_code):
        self.error_code = error_code

    def generate_content(self, request):
        return {
            "status": "failure",
            "error_code": self.error_code,
        }


class OpenAiCompatibleSqlGeneratorTests(unittest.TestCase):
    def test_preserves_only_sanitized_provider_failure_reason(self):
        configuration = OpenAiCompatibleConfiguration(
            provider_key="local_provider",
            config_version="v1",
            api_base_url="https://llm.example.test",
            model_id="sql-model",
        )
        adapter = OpenAiCompatibleSqlGeneratorAdapter(
            client=_FailingClient("timeout"),
            configuration=configuration,
        )

        with self.assertRaises(Exception) as captured:
            adapter.generate(
                {
                    "contract_version": SQL_GENERATION_CONTRACT_VERSION,
                    "generation_context": {},
                    "instructions": [],
                    "output_constraints": [],
                }
            )

        self.assertEqual(getattr(captured.exception, "reason", None), "timeout")

    def test_unknown_provider_failure_reason_is_redacted(self):
        configuration = OpenAiCompatibleConfiguration(
            provider_key="local_provider",
            config_version="v1",
            api_base_url="https://llm.example.test",
            model_id="sql-model",
        )
        adapter = OpenAiCompatibleSqlGeneratorAdapter(
            client=_FailingClient("token=secret-value"),
            configuration=configuration,
        )

        with self.assertRaises(Exception) as captured:
            adapter.generate(
                {
                    "contract_version": SQL_GENERATION_CONTRACT_VERSION,
                    "generation_context": {},
                    "instructions": [],
                    "output_constraints": [],
                }
            )

        self.assertEqual(
            getattr(captured.exception, "reason", None),
            "provider_failed",
        )
        self.assertNotIn("secret-value", repr(captured.exception))

    def test_normalizes_provider_result(self):
        configuration = OpenAiCompatibleConfiguration(
            provider_key="local_provider",
            config_version="v1",
            api_base_url="https://llm.example.test",
            model_id="sql-model",
        )
        adapter = OpenAiCompatibleSqlGeneratorAdapter(
            client=_Client(),
            configuration=configuration,
        )

        result = adapter.generate(
            {
                "contract_version": SQL_GENERATION_CONTRACT_VERSION,
                "generation_context": {},
                "instructions": [],
                "output_constraints": [],
            }
        )

        self.assertEqual(result["provider_name"], "local_provider")
        self.assertEqual(result["provider_model"], "sql-model")
        self.assertEqual(result["output_text"], "SELECT 1")
        self.assertEqual(result["token_usage"]["total_tokens"], 13)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from app.application.internal_sql_agent_v1_generate import validate_generate_request


class InternalLlmSelectionContractTests(unittest.TestCase):
    def _base(self):
        return {
            "contract_version": "1",
            "agent_run_id": "run-1",
            "question": "Qual foi a receita total?",
            "principal": {
                "id": "user-1",
                "profile": "admin",
            },
        }

    def test_accepts_versioned_llm_selection(self):
        request = self._base()
        request["llm_selection"] = {
            "provider_key": "provider-a",
            "model_key": "model-a",
            "config_version": "v1",
        }

        self.assertEqual(validate_generate_request(request), [])

    def test_rejects_incomplete_selection(self):
        request = self._base()
        request["llm_selection"] = {
            "provider_key": "provider-a",
            "model_key": "model-a",
        }

        errors = validate_generate_request(request)

        self.assertTrue(
            any(error.get("code") == "INTERNAL_LLM_SELECTION_INVALID" for error in errors)
        )

    def test_rejects_extra_selection_fields(self):
        request = self._base()
        request["llm_selection"] = {
            "provider_key": "provider-a",
            "model_key": "model-a",
            "config_version": "v1",
            "endpoint": "https://example.invalid",
        }

        errors = validate_generate_request(request)

        self.assertTrue(
            any(
                error.get("code") == "INTERNAL_LLM_SELECTION_FIELD_FORBIDDEN"
                for error in errors
            )
        )


if __name__ == "__main__":
    unittest.main()

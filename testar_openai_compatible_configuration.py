from __future__ import annotations

import unittest

from app.integrations.openai_compatible.configuration import (
    OpenAiCompatibleConfigurationError,
    load_openai_compatible_configuration,
)


class OpenAiCompatibleConfigurationTests(unittest.TestCase):
    def test_explicit_disabled_provider_ignores_partial_identity(self):
        configuration = load_openai_compatible_configuration(
            {
                "OPENAI_COMPATIBLE_SQL_ENABLED": "false",
                "OPENAI_COMPATIBLE_SQL_PROVIDER_KEY": "infodive_local",
                "OPENAI_COMPATIBLE_SQL_CONFIG_VERSION": "sql-infodive-demo-v1",
                "OPENAI_COMPATIBLE_SQL_MODEL": "sql-infodive",
                "OPENAI_COMPATIBLE_SQL_BASE_URL": "",
            }
        )

        self.assertIsNone(configuration)

    def test_enabled_provider_requires_complete_configuration(self):
        with self.assertRaises(OpenAiCompatibleConfigurationError):
            load_openai_compatible_configuration(
                {
                    "OPENAI_COMPATIBLE_SQL_ENABLED": "true",
                    "OPENAI_COMPATIBLE_SQL_PROVIDER_KEY": "infodive_local",
                    "OPENAI_COMPATIBLE_SQL_CONFIG_VERSION": "sql-infodive-demo-v1",
                    "OPENAI_COMPATIBLE_SQL_MODEL": "sql-infodive",
                    "OPENAI_COMPATIBLE_SQL_BASE_URL": "",
                }
            )

    def test_enabled_provider_accepts_complete_https_configuration(self):
        configuration = load_openai_compatible_configuration(
            {
                "OPENAI_COMPATIBLE_SQL_ENABLED": "true",
                "OPENAI_COMPATIBLE_SQL_PROVIDER_KEY": "infodive_local",
                "OPENAI_COMPATIBLE_SQL_CONFIG_VERSION": "sql-infodive-demo-v1",
                "OPENAI_COMPATIBLE_SQL_MODEL": "sql-infodive",
                "OPENAI_COMPATIBLE_SQL_BASE_URL": "https://llm.example.test",
            }
        )

        self.assertIsNotNone(configuration)
        self.assertEqual(configuration.provider_key, "infodive_local")
        self.assertEqual(configuration.model_id, "sql-infodive")

    def test_invalid_enable_flag_is_rejected(self):
        with self.assertRaises(OpenAiCompatibleConfigurationError):
            load_openai_compatible_configuration(
                {
                    "OPENAI_COMPATIBLE_SQL_ENABLED": "maybe",
                }
            )


if __name__ == "__main__":
    unittest.main()

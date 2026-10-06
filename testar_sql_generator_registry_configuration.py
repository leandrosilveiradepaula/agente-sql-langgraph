from __future__ import annotations

import unittest

from app.test_runtime.composition import _sql_generator_registry


class _Generator:
    def generate(self, request):
        return {
            "provider_name": "test",
            "provider_model": "model",
            "output_text": "SELECT 1",
        }


class SqlGeneratorRegistryConfigurationTests(unittest.TestCase):
    def test_uses_configured_gemini_identity(self):
        registry = _sql_generator_registry(
            environ={
                "GEMINI_SQL_GENERATOR_PROVIDER_KEY": "google_gemini",
                "GEMINI_SQL_GENERATOR_CONFIG_VERSION": "gemini-demo-v1",
                "GEMINI_SQL_GENERATOR_MODEL": "gemini-2.5-flash",
            },
            default_generator=_Generator(),
            http_transport=object(),
            secret_provider=object(),
        )

        resolved = registry.resolve(
            provider_key="google_gemini",
            model_key="gemini-2.5-flash",
            config_version="gemini-demo-v1",
        )

        self.assertIsInstance(resolved, _Generator)


if __name__ == "__main__":
    unittest.main()

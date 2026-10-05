from __future__ import annotations

import unittest

from app.composition.sql_generator_registry import (
    SqlGeneratorRegistration,
    SqlGeneratorRegistry,
    SqlGeneratorSelectionError,
)


class _Generator:
    def generate(self, request):
        return {
            "provider_name": "test",
            "provider_model": "model",
            "output_text": "SELECT 1",
        }


class SqlGeneratorRegistryTests(unittest.TestCase):
    def test_resolve_exact_versioned_selection(self):
        generator = _Generator()
        registry = SqlGeneratorRegistry([
            SqlGeneratorRegistration(
                provider_key="provider_a",
                model_key="model_a",
                config_version="v1",
                generator=generator,
            )
        ])

        resolved = registry.resolve(
            provider_key="provider_a",
            model_key="model_a",
            config_version="v1",
        )

        self.assertIs(resolved, generator)

    def test_rejects_unknown_without_fallback(self):
        registry = SqlGeneratorRegistry([
            SqlGeneratorRegistration(
                provider_key="provider_a",
                model_key="model_a",
                config_version="v1",
                generator=_Generator(),
            )
        ])

        with self.assertRaises(SqlGeneratorSelectionError):
            registry.resolve(
                provider_key="provider_a",
                model_key="model_b",
                config_version="v1",
            )


if __name__ == "__main__":
    unittest.main()

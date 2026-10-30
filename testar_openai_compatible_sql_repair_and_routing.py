from __future__ import annotations

import unittest

from app.adapters.testing.fake_engine_preflight import FakeEnginePreflight
from app.adapters.testing.fake_sql_repairer import FakeSqlRepairer
from app.application.internal_sql_agent_v1 import GenerateSqlUseCase
from app.composition.sql_generator_registry import SqlGeneratorRegistration, SqlGeneratorRegistry
from app.composition.sql_repairer_registry import (
    SqlRepairerRegistration, SqlRepairerRegistry, SqlRepairerSelectionError,
)
from app.domain.sql_repair import SQL_REPAIR_CONTRACT_VERSION, SqlRepairProviderError
from app.test_runtime.composition import _shadow_default_llm_selection, _sql_repairer_registry
from app.integrations.openai_compatible.configuration import OpenAiCompatibleConfiguration
from app.integrations.openai_compatible.sql_repairer_adapter import OpenAiCompatibleSqlRepairerAdapter
from testar_grafo_base import SuccessContextRepository


class Generator:
    def __init__(self, sql="SELECT value FROM schema_test.table_test"):
        self.sql = sql
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        return {"provider_name": "private_provider", "provider_model": "sql-model",
                "output_text": self.sql}


class Client:
    def __init__(self):
        self.calls = []

    def generate_content(self, request):
        self.calls.append(request)
        return {
            "status": "success", "output_text": "SELECT id FROM schema_test.table_test",
            "duration_ms": 7,
            "token_usage": {"prompt_tokens": 13, "completion_tokens": 8, "total_tokens": 21},
        }


class FailingClient:
    def generate_content(self, request):
        return {"status": "failure", "error_code": "sensitive-data-should-never-appear"}


class IDs:
    def __call__(self):
        return "safe-run-id"


def selection():
    return {"provider_key": "private_provider", "model_key": "sql-model",
            "config_version": "context-v1"}


def request():
    return {"contract_version": "1", "agent_run_id": "private-run-id",
            "question": "Execute uma generic analysis de teste.",
            "principal": {"id": "private-test"},
            "llm_selection": selection()}


def config():
    return OpenAiCompatibleConfiguration(
        provider_key="private_provider", config_version="context-v1",
        api_base_url="https://private.example.test", model_id="sql-model",
    )


class Tests(unittest.TestCase):
    def test_adapter_contract_and_tokens(self):
        client = Client()
        adapter = OpenAiCompatibleSqlRepairerAdapter(client=client, configuration=config())
        result = adapter.repair({"contract_version": SQL_REPAIR_CONTRACT_VERSION})
        self.assertEqual(result["provider_name"], "private_provider")
        self.assertEqual(result["token_usage"]["total_tokens"], 21)
        self.assertEqual(len(client.calls), 1)

    def test_adapter_rejects_invalid_contract_without_call(self):
        client = Client()
        adapter = OpenAiCompatibleSqlRepairerAdapter(client=client, configuration=config())
        with self.assertRaises(SqlRepairProviderError):
            adapter.repair({"contract_version": "unknown"})
        self.assertEqual(client.calls, [])

    def test_adapter_failure_does_not_expose_provider_payload(self):
        adapter = OpenAiCompatibleSqlRepairerAdapter(client=FailingClient(),
                                                     configuration=config())
        with self.assertRaises(SqlRepairProviderError) as failure:
            adapter.repair({"contract_version": SQL_REPAIR_CONTRACT_VERSION})
        self.assertNotIn("sensitive-data", str(failure.exception))

    def test_registry_requires_exact_version(self):
        repairer = FakeSqlRepairer()
        registry = SqlRepairerRegistry([
            SqlRepairerRegistration("private_provider", "sql-model", "context-v1", repairer)
        ])
        self.assertIs(registry.resolve(**{
            "provider_key": "private_provider", "model_key": "sql-model",
            "config_version": "context-v1"
        }), repairer)
        with self.assertRaises(SqlRepairerSelectionError):
            registry.resolve(provider_key="private_provider", model_key="sql-model",
                             config_version="other-context")

    def test_selected_provider_handles_generate_and_repair_without_gemini(self):
        generator = Generator()
        selected_repairer = FakeSqlRepairer(responses=["SELECT id FROM schema_test.table_test"])
        old_repairer = FakeSqlRepairer()
        engine = FakeEnginePreflight(responses=[
            {"status": "rejected", "provider_name": "test_preflight",
             "failure_category": "column_not_found", "message": "column not found",
             "repairable": True, "executed": False, "rows_returned": 0},
            {"status": "approved", "provider_name": "test_preflight",
             "duration_ms": 1, "statement_planned": True, "executed": False,
             "rows_returned": 0},
        ])
        use_case = GenerateSqlUseCase(
            context_repository=SuccessContextRepository(),
            sql_generator=Generator("SELECT 1"),
            sql_generator_resolver=SqlGeneratorRegistry([
                SqlGeneratorRegistration("private_provider", "sql-model",
                                         "context-v1", generator),
            ]),
            sql_repairer=old_repairer,
            sql_repairer_resolver=SqlRepairerRegistry([
                SqlRepairerRegistration("private_provider", "sql-model",
                                        "context-v1", selected_repairer),
            ]),
            engine_preflight=engine,
            id_generator=IDs(),
        )
        response = use_case.execute(request())
        self.assertEqual(response["status"], "success")
        self.assertEqual(response["repair_attempts"], 1)
        self.assertEqual(generator.calls, 1)
        self.assertEqual(selected_repairer.calls, 1)
        self.assertEqual(old_repairer.calls, 0)
        self.assertFalse(response["preflight"]["executed"])

    def test_repair_unavailable_fails_before_private_generation(self):
        generator = Generator()
        use_case = GenerateSqlUseCase(
            context_repository=SuccessContextRepository(),
            sql_generator=Generator(),
            sql_generator_resolver=SqlGeneratorRegistry([
                SqlGeneratorRegistration("private_provider", "sql-model",
                                         "context-v1", generator),
            ]),
            sql_repairer=FakeSqlRepairer(),
            sql_repairer_resolver=SqlRepairerRegistry([]),
            engine_preflight=FakeEnginePreflight(),
            id_generator=IDs(),
        )
        response = use_case.execute(request())
        self.assertEqual(response["status"], "rejected")
        self.assertEqual(response["errors"][0]["code"], "INTERNAL_LLM_SELECTION_UNAVAILABLE")
        self.assertEqual(generator.calls, 0)


    def test_explicit_default_private_selection_from_versioned_config(self):
        import json
        value = json.dumps(selection())
        self.assertEqual(
            _shadow_default_llm_selection({"SHADOW_DEFAULT_LLM_SELECTION_JSON": value}),
            selection(),
        )
        self.assertIsNone(_shadow_default_llm_selection({}))
        from unittest.mock import patch
        with patch.dict("os.environ", {"SHADOW_DEFAULT_LLM_SELECTION_JSON": value}):
            self.assertEqual(_shadow_default_llm_selection(None), selection())
        for invalid in ('{}', '{"provider_key":"x"}', '{"provider_key":null}', 'oops'):
            with self.assertRaises(RuntimeError):
                _shadow_default_llm_selection({"SHADOW_DEFAULT_LLM_SELECTION_JSON": invalid})

    def test_private_repairer_registration_uses_selected_adapter(self):
        env = {
            "OPENAI_COMPATIBLE_SQL_ENABLED": "true",
            "OPENAI_COMPATIBLE_SQL_PROVIDER_KEY": "private_provider",
            "OPENAI_COMPATIBLE_SQL_CONFIG_VERSION": "context-v1",
            "OPENAI_COMPATIBLE_SQL_BASE_URL": "https://private.example.test",
            "OPENAI_COMPATIBLE_SQL_MODEL": "sql-model",
        }
        selected = _sql_repairer_registry(
            environ=env,
            default_repairer=FakeSqlRepairer(),
            http_transport=object(),
            secret_provider=object(),
        ).resolve(**selection())
        self.assertIsInstance(selected, OpenAiCompatibleSqlRepairerAdapter)
        self.assertEqual(selected._configuration.provider_key, "private_provider")


if __name__ == "__main__":
    unittest.main()

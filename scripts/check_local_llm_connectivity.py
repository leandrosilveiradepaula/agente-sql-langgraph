from __future__ import annotations

import os

from app.domain.sql_generation import (
    SQL_GENERATION_CONTRACT_VERSION,
    validate_sql_generation_response,
)
from app.infrastructure.http.stdlib_http_transport import StdlibHttpTransport
from app.infrastructure.secrets.environment_secret_provider import (
    EnvironmentSecretProvider,
)
from app.integrations.openai_compatible.client import OpenAiCompatibleClient
from app.integrations.openai_compatible.configuration import (
    OpenAiCompatibleConfigurationError,
    load_openai_compatible_configuration,
)
from app.integrations.openai_compatible.sql_generator_adapter import (
    OpenAiCompatibleSqlGeneratorAdapter,
)


SMOKE_FLAG = "LOCAL_LLM_CONNECTIVITY_SMOKE_ENABLED"


def _enabled() -> bool:
    value = os.environ.get(SMOKE_FLAG, "").strip().casefold()
    if not value:
        return False
    if value in {"true", "1", "yes", "on"}:
        return True
    if value in {"false", "0", "no", "off"}:
        return False
    raise RuntimeError(f"{SMOKE_FLAG} must be boolean.")


def _synthetic_request():
    return {
        "contract_version": SQL_GENERATION_CONTRACT_VERSION,
        "generation_context": {
            "context_version": "smoke-v1",
            "context_fingerprint": "smoke",
            "planner_version": "smoke-v1",
            "intent_name": "connectivity_smoke",
            "normalized_question": "Retorne uma consulta de leitura sintetica sem dados reais.",
            "selected_pattern": {},
            "applicable_rules": [],
            "authorized_tables": [],
            "allowed_schemas": [],
            "catalog_columns": {},
            "authorized_joins": [],
            "operational_entities": [],
            "dre_mappings": [],
            "grouping_dimensions": [],
            "analytical_operations": [],
            "planned_metrics": [],
            "planned_filters": [],
            "filter_bindings": [],
            "pattern_metadata": {},
        },
        "instructions": [
            {
                "name": "smoke",
                "content": "Retorne somente: SELECT 1",
            }
        ],
        "output_constraints": [
            "Retorne exatamente uma instrucao SQL de leitura.",
            "Nao use Markdown.",
            "Nao inclua explicacoes.",
        ],
    }


def main() -> int:
    try:
        if not _enabled():
            print("NO-GO: connectivity smoke is disabled.")
            return 1

        configuration = load_openai_compatible_configuration(os.environ)
        if configuration is None:
            print("NO-GO: local LLM provider is disabled.")
            return 2

        secret_provider = EnvironmentSecretProvider()
        client = OpenAiCompatibleClient(
            configuration=configuration,
            secret_provider=secret_provider,
            http_transport=StdlibHttpTransport(),
        )
        adapter = OpenAiCompatibleSqlGeneratorAdapter(
            client=client,
            configuration=configuration,
        )

        result = adapter.generate(_synthetic_request())
        validate_sql_generation_response(result)

        usage = result.get("token_usage") or {}
        print("GO: local LLM connectivity smoke passed.")
        print(f"provider_key={configuration.provider_key}")
        print(f"model_key={configuration.model_id}")
        print(f"config_version={configuration.config_version}")
        print(f"duration_ms={result.get('duration_ms', 0)}")
        print(f"prompt_tokens={usage.get('prompt_tokens')}")
        print(f"response_tokens={usage.get('response_tokens')}")
        print(f"total_tokens={usage.get('total_tokens')}")
        print("sql_output_logged=false")
        print("endpoint_logged=false")
        print("secret_logged=false")
        return 0
    except OpenAiCompatibleConfigurationError:
        print("NO-GO: local LLM configuration is invalid or incomplete.")
        return 3
    except Exception:
        print("NO-GO: local LLM connectivity smoke failed.")
        return 4


if __name__ == "__main__":
    raise SystemExit(main())

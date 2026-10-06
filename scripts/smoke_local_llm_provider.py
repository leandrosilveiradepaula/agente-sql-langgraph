from __future__ import annotations

import os

from app.domain.sql_generation import validate_sql_generation_response
from app.infrastructure.http.stdlib_http_transport import StdlibHttpTransport
from app.infrastructure.secrets.environment_secret_provider import EnvironmentSecretProvider
from app.integrations.openai_compatible.client import OpenAiCompatibleClient
from app.integrations.openai_compatible.configuration import (
    OpenAiCompatibleConfigurationError,
    load_openai_compatible_configuration,
)


SMOKE_ENABLED_ENV = "LOCAL_LLM_SMOKE_ENABLED"


def _enabled(value: str | None) -> bool:
    return isinstance(value, str) and value.strip().casefold() in {
        "true",
        "1",
        "yes",
        "on",
    }


def main() -> int:
    if not _enabled(os.environ.get(SMOKE_ENABLED_ENV)):
        print("NO-GO: network smoke is disabled.")
        return 1

    try:
        configuration = load_openai_compatible_configuration(os.environ)
    except OpenAiCompatibleConfigurationError:
        print("NO-GO: local LLM configuration is invalid or incomplete.")
        return 2

    if configuration is None:
        print("NO-GO: local LLM provider is disabled.")
        return 3

    client = OpenAiCompatibleClient(
        configuration=configuration,
        secret_provider=EnvironmentSecretProvider(),
        http_transport=StdlibHttpTransport(),
    )

    result = client.generate_content(
        {
            "smoke_test": True,
            "instruction": "Retorne somente: SELECT 1;",
        }
    )

    if result.get("status") != "success":
        print("NO-GO: local LLM provider smoke failed.")
        print(f"reason={str(result.get('error_code') or 'provider_failure')[:64]}")
        return 4

    output_text = result.get("output_text")
    if not isinstance(output_text, str):
        print("NO-GO: local LLM response is invalid.")
        return 5

    try:
        normalized = validate_sql_generation_response(
            {
                "provider_name": configuration.provider_key,
                "provider_model": configuration.model_id,
                "output_text": output_text,
            }
        )
    except Exception:
        print("NO-GO: local LLM did not return a valid read-only SQL response.")
        return 6

    if normalized.strip().casefold() != "select 1":
        print("NO-GO: local LLM smoke response did not match the synthetic contract.")
        return 7

    usage = result.get("token_usage")
    usage_available = isinstance(usage, dict) and any(
        usage.get(key) is not None
        for key in ("prompt_tokens", "response_tokens", "total_tokens")
    )

    print("GO: local LLM provider smoke succeeded.")
    print(f"provider_key={configuration.provider_key}")
    print(f"model_key={configuration.model_id}")
    print(f"config_version={configuration.config_version}")
    print(f"duration_ms={int(result.get('duration_ms') or 0)}")
    print(f"token_usage_available={str(usage_available).lower()}")
    print("response_contract=select_1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

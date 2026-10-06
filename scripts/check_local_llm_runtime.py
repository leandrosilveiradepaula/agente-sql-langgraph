from __future__ import annotations

import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from app.integrations.openai_compatible.configuration import (
    OpenAiCompatibleConfigurationError,
    load_openai_compatible_configuration,
)


def main() -> int:
    try:
        configuration = load_openai_compatible_configuration(os.environ)
    except OpenAiCompatibleConfigurationError:
        print("NO-GO: local LLM configuration is invalid or incomplete.")
        return 2

    if configuration is None:
        print("NO-GO: local LLM provider is disabled.")
        return 1

    print("GO: local LLM runtime configuration is complete.")
    print(f"provider_key={configuration.provider_key}")
    print(f"model_key={configuration.model_id}")
    print(f"config_version={configuration.config_version}")
    print("endpoint_configured=true")
    print("credential_reference_configured=true")
    print("network_call_performed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

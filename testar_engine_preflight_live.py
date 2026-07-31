from __future__ import annotations

import getpass
import json
import sys

from app.config.engine_preflight_runtime import (
    EnginePreflightRuntimeConfig,
    EnginePreflightRuntimeConfigError,
    evaluate_engine_preflight_capabilities,
)


def _input_required(label: str) -> str:
    value = input(f"{label}: ").strip()
    if not value:
        raise ValueError(f"{label} nao pode estar vazio.")
    return value


def _input_optional(label: str) -> str | None:
    value = input(f"{label} (Enter para vazio): ").strip()
    return value or None


def _input_default(label: str, default: str) -> str:
    value = input(f"{label} (Enter para {default}): ").strip()
    return value or default


def _input_positive_int(label: str, default: int) -> int:
    raw_value = input(f"{label} (Enter para {default}): ").strip()
    if not raw_value:
        return default
    value = int(raw_value)
    if value <= 0:
        raise ValueError(f"{label} deve ser positivo.")
    return value


def main() -> int:
    print("ENGINE PREFLIGHT LIVE CAPABILITY DIAGNOSTIC")
    print("Este script nao executa SQL, nao usa EXPLAIN e nao acessa rede.")
    print("Ele apenas valida configuracao e capability declarada.")
    print()

    try:
        provider_type = _input_required("ENGINE_PREFLIGHT_PROVIDER_TYPE")
        capability_mode = _input_default(
            "ENGINE_PREFLIGHT_CAPABILITY_MODE",
            "unavailable",
        )
        dialect = _input_optional("ENGINE_PREFLIGHT_DIALECT")
        endpoint = _input_optional("ENGINE_PREFLIGHT_ENDPOINT")
        auth_mode = _input_default("ENGINE_PREFLIGHT_AUTH_MODE", "none")
        operation = _input_optional("ENGINE_PREFLIGHT_OPERATION")
        timeout_seconds = _input_positive_int(
            "ENGINE_PREFLIGHT_TIMEOUT_SECONDS",
            5,
        )

        if auth_mode.strip().casefold() != "none":
            getpass.getpass(
                "SECRET/TOKEN opcional (entrada oculta, nao armazenada): "
            )

        config = EnginePreflightRuntimeConfig(
            provider_type=provider_type,
            capability_mode=capability_mode,  # type: ignore[arg-type]
            dialect=dialect,
            endpoint=endpoint,
            auth_mode=auth_mode,  # type: ignore[arg-type]
            operation=operation,
            timeout_seconds=timeout_seconds,
            ssl_verify=True,
        )
        diagnostic = evaluate_engine_preflight_capabilities(config)
    except (EnginePreflightRuntimeConfigError, ValueError) as error:
        print("CONFIGURACAO: ERRO")
        print(str(error))
        return 2

    print()
    print("DIAGNOSTICO SANITIZADO")
    print(
        json.dumps(
            diagnostic,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    print()
    print("executed=False")
    print("rows_returned=0")

    if diagnostic["can_preflight"]:
        print("CAPABILITY: DISPONIVEL")
        return 0

    print("CAPABILITY: INDISPONIVEL")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

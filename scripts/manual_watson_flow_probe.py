from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from app.composition.watson_test import (
    DeploymentEnvironment,
    build_watson_test_dependencies,
)
from app.domain.engine_preflight_types import (
    ENGINE_PREFLIGHT_CONTRACT_VERSION,
    EnginePreflightRequest,
)
from app.domain.sql_execution_types import (
    SQL_EXECUTION_CONTRACT_VERSION,
    SqlExecutionRequest,
)
from app.infrastructure.http.stdlib_http_transport import StdlibHttpTransport
from app.infrastructure.secrets.environment_secret_provider import (
    EnvironmentSecretProvider,
)
from app.integrations.watson.configuration import IBM_IAM_TOKEN_URL
from app.integrations.watson.flow_limits import (
    WatsonFlowContractError,
    default_watson_flow_limits,
)
from app.integrations.watson.live_configuration import (
    create_live_watson_flow_configuration,
)
from app.integrations.watson.sql_transport import (
    build_watson_flow_payload,
    compact_sql_for_watson_transport,
)
from app.ports.secret_value_provider import SecretLookupResult, SecretName, SecretValueProvider


EXIT_OK = 0
EXIT_USAGE = 2
EXIT_SQL_INVALID = 3
EXIT_CONFIG_INVALID = 4
EXIT_LIVE_CONFIRMATION_MISSING = 5
EXIT_SECRET_INVALID = 6
EXIT_IAM_FAILURE = 7
EXIT_WATSON_FLOW_FAILURE = 8
EXIT_CONTRACT_MISMATCH = 9
EXIT_RESULT_MISMATCH = 10
EXIT_INTERNAL_ERROR = 11

_SQL_FILE_LIMIT_BYTES = 200_000
_SECRET_ENV_NAME = "IBM_CLOUD_API_KEY"


@dataclass(frozen=True, slots=True)
class SqlProbeInput:
    file_name: str
    size_bytes: int
    sha256: str
    sql_transport: str
    transport_size_characters: int
    transport_size_bytes: int


@dataclass(frozen=True, slots=True)
class ConfigurationProbeInput:
    source: str
    api_base_url: str | None
    flow_id: str | None
    api_base_url_configured: bool
    flow_id_configured: bool
    api_base_url_valid: bool | None
    flow_id_valid: bool | None
    api_host: str | None
    instance_path_present: bool | None
    flow_id_fingerprint: str | None
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Probe manual Watson Flow. Pode executar SQL no ambiente "
            "configurado somente com confirmacao explicita."
        )
    )
    parser.add_argument("--execute-live", action="store_true")
    parser.add_argument("--confirm-test-environment", action="store_true")
    parser.add_argument("--confirm-show-rows", action="store_true")
    parser.add_argument("--sql-file")
    parser.add_argument("--purpose", choices=("preflight", "execution"), default="preflight")
    parser.add_argument("--api-base-url")
    parser.add_argument("--flow-id")
    parser.add_argument("--iam-token-url")
    parser.add_argument("--show-rows", action="store_true")
    parser.add_argument("--max-preview-rows", type=int, default=5)
    parser.add_argument("--print-plan-json", action="store_true")
    return parser


def main(argv: list[str] | None = None, *, environ: dict[str, str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    env = os.environ if environ is None else environ

    flags_code = _validate_flags(args)
    if flags_code is not None:
        return flags_code

    sql_result, sql_code = _read_and_validate_sql(args.sql_file)
    if sql_code != EXIT_OK or sql_result is None:
        return sql_code

    config = _resolve_configuration(args, env)
    if config.blockers:
        _print_plan(args, sql_result, config, live=args.execute_live)
        return EXIT_CONFIG_INVALID

    if not args.execute_live:
        _print_plan(args, sql_result, config, live=False)
        return EXIT_OK

    if not args.confirm_test_environment:
        print("confirmacao TEST ausente.")
        return EXIT_LIVE_CONFIRMATION_MISSING
    if not config.api_base_url or not config.flow_id:
        _print_plan(args, sql_result, config, live=True)
        return EXIT_CONFIG_INVALID

    try:
        return _execute_live(args, env, sql_result, config)
    except WatsonFlowContractError:
        print("probe live falhou por contrato sanitizado.")
        return EXIT_CONTRACT_MISMATCH
    except Exception:
        print("probe live falhou de forma sanitizada.")
        return EXIT_INTERNAL_ERROR


def _validate_flags(args: argparse.Namespace) -> int | None:
    if args.show_rows and not args.confirm_show_rows:
        print("show-rows exige --confirm-show-rows.")
        return EXIT_USAGE
    if args.max_preview_rows <= 0 or args.max_preview_rows > 50:
        print("max-preview-rows fora do intervalo.")
        return EXIT_USAGE
    if args.execute_live and not args.confirm_test_environment:
        print("execucao live exige --confirm-test-environment.")
        return EXIT_LIVE_CONFIRMATION_MISSING
    if args.execute_live and not args.sql_file:
        print("execucao live exige --sql-file.")
        return EXIT_USAGE
    return None


def _read_and_validate_sql(sql_file: str | None) -> tuple[SqlProbeInput | None, int]:
    if not sql_file:
        print("arquivo SQL obrigatorio.")
        return None, EXIT_USAGE
    path = Path(sql_file)
    if not path.is_file():
        print("arquivo SQL ausente.")
        return None, EXIT_SQL_INVALID
    raw = path.read_bytes()
    if len(raw) == 0:
        print("arquivo SQL vazio.")
        return None, EXIT_SQL_INVALID
    if len(raw) > _SQL_FILE_LIMIT_BYTES:
        print("arquivo SQL excede limite.")
        return None, EXIT_SQL_INVALID
    try:
        sql_text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        print("arquivo SQL nao esta em UTF-8 estrito.")
        return None, EXIT_SQL_INVALID
    if sql_text.startswith("\ufeff"):
        print("arquivo SQL contem BOM.")
        return None, EXIT_SQL_INVALID
    limits = default_watson_flow_limits()
    transport = compact_sql_for_watson_transport(sql_text, limits)
    if transport.status != "success" or transport.sql_transport is None:
        print("SQL invalida para transporte Watson.")
        return None, EXIT_SQL_INVALID
    try:
        payload = build_watson_flow_payload(transport.sql_transport)
    except WatsonFlowContractError:
        print("payload Watson invalido.")
        return None, EXIT_SQL_INVALID
    if set(payload.keys()) != {"sql_query"}:
        print("payload Watson invalido.")
        return None, EXIT_SQL_INVALID
    encoded_transport = transport.sql_transport.encode("utf-8")
    return (
        SqlProbeInput(
            file_name=path.name,
            size_bytes=len(raw),
            sha256=hashlib.sha256(raw).hexdigest(),
            sql_transport=transport.sql_transport,
            transport_size_characters=len(transport.sql_transport),
            transport_size_bytes=len(encoded_transport),
        ),
        EXIT_OK,
    )


def _resolve_configuration(
    args: argparse.Namespace,
    env: dict[str, str],
) -> ConfigurationProbeInput:
    arg_url = _clean(args.api_base_url)
    arg_flow = _clean(args.flow_id)
    env_url = _clean(env.get("WATSON_API_BASE_URL"))
    env_flow = _clean(env.get("WATSON_FLOW_ID"))
    api_base_url = arg_url or env_url
    flow_id = arg_flow or env_flow
    source = _configuration_source(
        has_arg=bool(arg_url or arg_flow),
        has_env=bool((env_url and not arg_url) or (env_flow and not arg_flow)),
    )
    blockers: list[str] = []
    warnings: list[str] = []
    url_valid: bool | None = None
    api_host: str | None = None
    instance_path_present: bool | None = None
    if api_base_url:
        url_valid, api_host, instance_path_present = _validate_public_url(api_base_url)
        if not url_valid:
            blockers.append("api_base_url_invalid")
    else:
        warnings.append("api_base_url_missing_for_live")
    flow_valid: bool | None = None
    flow_fingerprint: str | None = None
    if flow_id:
        flow_valid = _validate_flow_id(flow_id)
        if not flow_valid:
            blockers.append("flow_id_invalid")
        else:
            flow_fingerprint = hashlib.sha256(flow_id.encode("utf-8")).hexdigest()[:12]
    else:
        warnings.append("flow_id_missing_for_live")
    return ConfigurationProbeInput(
        source=source,
        api_base_url=api_base_url,
        flow_id=flow_id,
        api_base_url_configured=bool(api_base_url),
        flow_id_configured=bool(flow_id),
        api_base_url_valid=url_valid,
        flow_id_valid=flow_valid,
        api_host=api_host,
        instance_path_present=instance_path_present,
        flow_id_fingerprint=flow_fingerprint,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )


def _configuration_source(*, has_arg: bool, has_env: bool) -> str:
    if has_arg and has_env:
        return "mixed"
    if has_arg:
        return "arguments"
    if has_env:
        return "environment"
    return "none"


def _validate_public_url(value: str) -> tuple[bool, str | None, bool | None]:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        return False, None, None
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return False, None, None
    lowered = value.casefold()
    if any(marker in lowered for marker in ("prod", "production", "apikey=", "access_token", "bearer ")):
        return False, None, None
    return True, parsed.hostname, bool(parsed.path and parsed.path != "/")


def _validate_flow_id(value: str) -> bool:
    import uuid

    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return not any(ord(char) < 32 or ord(char) == 127 for char in value)


def _build_plan(
    args: argparse.Namespace,
    sql: SqlProbeInput,
    config: ConfigurationProbeInput,
    *,
    live: bool,
) -> dict[str, object]:
    secret_required = bool(live)
    secret_available = bool(args.execute_live)
    blockers = list(config.blockers)
    warnings = list(config.warnings)
    if live and not args.confirm_test_environment:
        blockers.append("test_confirmation_missing")
    if live and not (config.api_base_url_configured and config.flow_id_configured):
        blockers.append("live_configuration_incomplete")
    operation_ready = bool(live and not blockers)
    return {
        "mode": "live" if live else "dry_run",
        "purpose": args.purpose,
        "sql": {
            "file_name": sql.file_name,
            "size_bytes": sql.size_bytes,
            "sha256": sql.sha256,
            "transport_size_characters": sql.transport_size_characters,
            "transport_size_bytes": sql.transport_size_bytes,
        },
        "payload_keys": ["sql_query"],
        "configuration": {
            "source": config.source,
            "api_base_url_configured": config.api_base_url_configured,
            "api_base_url_valid": config.api_base_url_valid,
            "api_host": config.api_host,
            "instance_path_present": config.instance_path_present,
            "flow_id_configured": config.flow_id_configured,
            "flow_id_valid": config.flow_id_valid,
            "flow_id_fingerprint": config.flow_id_fingerprint,
        },
        "security": {
            "secret_required": secret_required,
            "secret_accessed": False,
            "network_enabled": bool(live),
            "live_confirmation_present": bool(args.confirm_test_environment),
        },
        "operation_ready_for_live": operation_ready,
        "blockers": blockers,
        "warnings": warnings,
    }


def _print_plan(
    args: argparse.Namespace,
    sql: SqlProbeInput,
    config: ConfigurationProbeInput,
    *,
    live: bool,
) -> None:
    plan = _build_plan(args, sql, config, live=live)
    if args.print_plan_json:
        print(json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
        return
    print("Watson Flow manual probe")
    print(f"mode={plan['mode']}")
    print(f"purpose={args.purpose}")
    print(f"sql_file={sql.file_name}")
    print(f"sql_sha256={sql.sha256}")
    print(f"sql_bytes={sql.size_bytes}")
    print(f"sql_transport_bytes={sql.transport_size_bytes}")
    print("payload_keys=sql_query")
    print(f"configuration_source={config.source}")
    print(f"api_base_url_configured={str(config.api_base_url_configured).lower()}")
    print(f"flow_id_configured={str(config.flow_id_configured).lower()}")
    print("secret_accessed=false")
    print(f"network_enabled={str(live).lower()}")
    print(f"operation_ready_for_live={str(plan['operation_ready_for_live']).lower()}")
    if plan["blockers"]:
        print("blockers=" + ",".join(plan["blockers"]))  # type: ignore[arg-type]
    if plan["warnings"]:
        print("warnings=" + ",".join(plan["warnings"]))  # type: ignore[arg-type]


def _execute_live(
    args: argparse.Namespace,
    env: dict[str, str],
    sql: SqlProbeInput,
    config: ConfigurationProbeInput,
) -> int:
    limits = default_watson_flow_limits()
    live_config = create_live_watson_flow_configuration(
        api_base_url=config.api_base_url or "",
        flow_id=config.flow_id or "",
        api_key_secret_name=_SECRET_ENV_NAME,
        enabled=True,
        iam_token_url=args.iam_token_url or env.get("WATSON_IAM_TOKEN_URL") or IBM_IAM_TOKEN_URL,
        connect_timeout_seconds=int(env.get("WATSON_CONNECT_TIMEOUT_SECONDS", "5")),
        read_timeout_seconds=int(env.get("WATSON_READ_TIMEOUT_SECONDS", "30")),
        limits=limits,
    )
    secret_provider = _TrackingSecretValueProvider(
        EnvironmentSecretProvider(environ=env),
    )
    composition = build_watson_test_dependencies(
        environment=DeploymentEnvironment.TEST,
        live_configuration=live_config,
        limits=limits,
        secret_provider=secret_provider,
        http_transport=StdlibHttpTransport(),
    )
    if composition.status != "success" or composition.dependencies is None:
        print("composition_status=" + composition.status)
        return EXIT_CONFIG_INVALID
    deps = composition.dependencies
    if args.purpose == "preflight":
        result = deps.engine_preflight.preflight(_build_preflight_request(sql, live_config))
        print("preflight_status=" + str(result.get("status", "error")))
        print("statement_planned=" + str(result.get("statement_planned", False)).lower())
        print("executed=" + str(result.get("executed", False)).lower())
        print("rows_returned=" + str(result.get("rows_returned", 0)))
        return _preflight_exit_code(result, secret_provider)
    result = deps.sql_executor.execute(_build_execution_request(sql, live_config))
    print("execution_status=" + str(result.get("status", "error")))
    print("executed=" + str(result.get("executed", False)).lower())
    print("row_count=" + str(result.get("row_count", 0)))
    if args.show_rows:
        print(f"preview_rows_limit={args.max_preview_rows}")
    return _execution_exit_code(result, secret_provider)


def _build_preflight_request(
    sql: SqlProbeInput,
    live_config,
) -> EnginePreflightRequest:
    sql_fingerprint = _fingerprint("sql", sql.sha256)
    plan_fingerprint = _fingerprint("query-plan", sql.sha256)
    request_fingerprint = _fingerprint("manual-preflight", sql.sha256)
    return {
        "contract_version": ENGINE_PREFLIGHT_CONTRACT_VERSION,
        "sql": sql.sql_transport,
        "sql_fingerprint": sql_fingerprint,
        "context_version": "manual-watson-test-probe",
        "context_fingerprint": _fingerprint("context", sql.sha256),
        "query_plan_fingerprint": plan_fingerprint,
        "intent_name": "manual_probe",
        "allowed_schemas": [],
        "planned_tables": [],
        "dialect": None,
        "engine_hint": "watson_flow_test",
        "timeout_ms": live_config.watson_configuration.request_timeout_seconds * 1000,
        "attempt": 1,
        "request_fingerprint": request_fingerprint,
    }


def _build_execution_request(
    sql: SqlProbeInput,
    live_config,
) -> SqlExecutionRequest:
    sql_fingerprint = _fingerprint("sql", sql.sha256)
    query_plan_fingerprint = _fingerprint("query-plan", sql.sha256)
    return {
        "contract_version": SQL_EXECUTION_CONTRACT_VERSION,
        "current_sql": sql.sql_transport,
        "sql_fingerprint": sql_fingerprint,
        "request_id": "manual-probe-request",
        "run_id": "manual-probe-run",
        "context_version": "manual-watson-test-probe",
        "intent_name": "manual_probe",
        "query_plan_fingerprint": query_plan_fingerprint,
        "preflight_fingerprint": _fingerprint("preflight", sql.sha256),
        "limits": {
            "timeout_seconds": live_config.watson_configuration.request_timeout_seconds,
            "max_rows": 50,
            "max_response_bytes": 262_144,
            "max_cell_bytes": 8192,
        },
        "attempt": 1,
        "execution_id": "manual-probe-execution",
        "dialect": None,
        "engine_hint": "watson_flow_test",
        "request_fingerprint": _fingerprint("manual-execution", sql.sha256),
    }


def _preflight_exit_code(
    result: dict[str, object],
    secret_provider: "_TrackingSecretValueProvider",
) -> int:
    if result.get("status") == "approved":
        return EXIT_OK
    if _secret_lookup_failed(secret_provider):
        return EXIT_SECRET_INVALID
    if result.get("failure_category") == "authentication_failed":
        return EXIT_IAM_FAILURE
    return EXIT_WATSON_FLOW_FAILURE


def _execution_exit_code(
    result: dict[str, object],
    secret_provider: "_TrackingSecretValueProvider",
) -> int:
    if result.get("status") == "success":
        return EXIT_OK
    if _secret_lookup_failed(secret_provider):
        return EXIT_SECRET_INVALID
    if result.get("failure_category") == "authentication_failed":
        return EXIT_IAM_FAILURE
    return EXIT_WATSON_FLOW_FAILURE


def _secret_lookup_failed(secret_provider: "_TrackingSecretValueProvider") -> bool:
    return secret_provider.last_status in {"missing", "invalid", "unavailable", "unexpected_error"}


def _fingerprint(*parts: str) -> str:
    material = "|".join(parts).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


class _TrackingSecretValueProvider:
    def __init__(self, delegate: SecretValueProvider) -> None:
        self._delegate = delegate
        self.calls = 0
        self.last_status: str | None = None

    def __repr__(self) -> str:
        return "_TrackingSecretValueProvider(<safe>)"

    def get_secret(self, secret_name: SecretName) -> SecretLookupResult:
        self.calls += 1
        result = self._delegate.get_secret(secret_name)
        self.last_status = result.get("status")
        return result


def _clean(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


if __name__ == "__main__":
    raise SystemExit(main())

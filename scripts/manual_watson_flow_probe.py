from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from app.bootstrap import create_stdlib_live_watson_flow_dependencies
from app.infrastructure.secrets.environment_secret_provider import (
    EnvironmentSecretProvider,
)
from app.integrations.watson.configuration import IBM_IAM_TOKEN_URL
from app.integrations.watson.flow_contracts import watson_flow_run_request
from app.integrations.watson.flow_limits import (
    WatsonFlowContractError,
    default_watson_flow_limits,
)
from app.integrations.watson.iam_contracts import iam_token_request
from app.integrations.watson.live_configuration import (
    create_live_watson_flow_configuration,
)
from app.integrations.watson.sql_transport import (
    build_watson_flow_payload,
    compact_sql_for_watson_transport,
)


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

    plan = _build_plan(args, sql_result, config, live=args.execute_live)
    if not args.execute_live:
        _print_plan(args, sql_result, config, live=False)
        return EXIT_OK

    if not args.confirm_test_environment:
        print("confirmacao TEST ausente.")
        return EXIT_LIVE_CONFIRMATION_MISSING
    if not config.api_base_url or not config.flow_id:
        _print_plan(args, sql_result, config, live=True)
        return EXIT_CONFIG_INVALID
    if not env.get(_SECRET_ENV_NAME):
        print("secret live ausente.")
        return EXIT_SECRET_INVALID

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
        print(json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
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
        iam_token_url=env.get("WATSON_IAM_TOKEN_URL", args.iam_token_url or IBM_IAM_TOKEN_URL),
        connect_timeout_seconds=int(env.get("WATSON_CONNECT_TIMEOUT_SECONDS", "5")),
        read_timeout_seconds=int(env.get("WATSON_READ_TIMEOUT_SECONDS", "30")),
        limits=limits,
    )
    deps = create_stdlib_live_watson_flow_dependencies(
        live_configuration=live_config,
        limits=limits,
        secret_provider=EnvironmentSecretProvider(environ=env),
    )
    token_result = deps.iam_token_provider.get_token(
        iam_token_request(
            request_id="manual-probe",
            run_id="manual-probe",
            timeout_seconds=live_config.watson_configuration.request_timeout_seconds,
            force_refresh=True,
            audience=f"watson-flow-manual-probe-{args.purpose}",
        )
    )
    if token_result.get("status") != "success":
        print("iam_status=" + str(token_result.get("status", "failure")))
        return EXIT_IAM_FAILURE
    request = watson_flow_run_request(
        flow_id=live_config.watson_configuration.flow_id,
        bearer_token=token_result["token"],
        payload=build_watson_flow_payload(sql.sql_transport),
        request_id="manual-probe",
        run_id="manual-probe",
        invocation_id=f"manual-probe-{args.purpose}",
        timeout_seconds=live_config.watson_configuration.request_timeout_seconds,
        purpose=args.purpose,
        limits=limits,
    )
    flow_result = deps.flow_client.run_flow(request)
    print("iam_status=success")
    print("flow_status=" + str(flow_result.get("status", "failure")))
    if flow_result.get("http_status") is not None:
        print("flow_http_status=" + str(flow_result.get("http_status")))
    if args.show_rows:
        print(f"preview_rows_limit={args.max_preview_rows}")
    return EXIT_OK if flow_result.get("status") == "success" else EXIT_WATSON_FLOW_FAILURE


def _clean(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


if __name__ == "__main__":
    raise SystemExit(main())

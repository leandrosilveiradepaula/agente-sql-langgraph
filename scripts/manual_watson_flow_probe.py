from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

from app.bootstrap import create_stdlib_live_watson_flow_dependencies
from app.infrastructure.secrets.environment_secret_provider import (
    EnvironmentSecretProvider,
)
from app.integrations.watson.configuration import IBM_IAM_TOKEN_URL
from app.integrations.watson.flow_contracts import watson_flow_run_request
from app.integrations.watson.flow_limits import default_watson_flow_limits
from app.integrations.watson.live_configuration import (
    create_live_watson_flow_configuration,
)
from app.integrations.watson.sql_transport import build_watson_flow_payload


EXIT_OK = 0
EXIT_USAGE = 2
EXIT_CONFIG = 3
EXIT_LIVE_FAILED = 4


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
    parser.add_argument("--show-rows", action="store_true")
    parser.add_argument("--max-preview-rows", type=int, default=5)
    return parser


def main(argv: list[str] | None = None, *, environ: dict[str, str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    env = os.environ if environ is None else environ
    if args.show_rows and not args.confirm_show_rows:
        print("show-rows exige --confirm-show-rows.")
        return EXIT_USAGE
    if args.execute_live and not args.confirm_test_environment:
        print("execucao live exige --confirm-test-environment.")
        return EXIT_USAGE
    if args.execute_live and not args.sql_file:
        print("execucao live exige --sql-file.")
        return EXIT_USAGE

    sql_text = ""
    if args.sql_file:
        path = Path(args.sql_file)
        if not path.is_file():
            print("arquivo SQL ausente.")
            return EXIT_USAGE
        raw = path.read_bytes()
        if len(raw) > 200_000:
            print("arquivo SQL excede limite.")
            return EXIT_USAGE
        sql_text = raw.decode("utf-8", errors="strict")

    sql_hash = hashlib.sha256(sql_text.encode("utf-8")).hexdigest() if sql_text else ""
    print("Watson Flow manual probe")
    print(f"mode={'live' if args.execute_live else 'dry-run'}")
    print(f"purpose={args.purpose}")
    if sql_text:
        print(f"sql_sha256={sql_hash}")
        print(f"sql_bytes={len(sql_text.encode('utf-8'))}")
    if not args.execute_live:
        print("dry-run: nenhuma rede sera acessada.")
        return EXIT_OK

    required = ["WATSON_API_BASE_URL", "WATSON_FLOW_ID", "IBM_CLOUD_API_KEY"]
    if any(not env.get(name) for name in required):
        print("configuracao live ausente.")
        return EXIT_CONFIG
    try:
        limits = default_watson_flow_limits()
        live_config = create_live_watson_flow_configuration(
            api_base_url=env["WATSON_API_BASE_URL"],
            flow_id=env["WATSON_FLOW_ID"],
            api_key_secret_name="IBM_CLOUD_API_KEY",
            enabled=True,
            iam_token_url=env.get("WATSON_IAM_TOKEN_URL", IBM_IAM_TOKEN_URL),
            connect_timeout_seconds=int(env.get("WATSON_CONNECT_TIMEOUT_SECONDS", "5")),
            read_timeout_seconds=int(env.get("WATSON_READ_TIMEOUT_SECONDS", "30")),
            limits=limits,
        )
        deps = create_stdlib_live_watson_flow_dependencies(
            live_configuration=live_config,
            limits=limits,
            secret_provider=EnvironmentSecretProvider(),
        )
        token_result = deps.iam_token_provider.get_token(
            {
                "request_id": "manual-probe",
                "run_id": "manual-probe",
                "timeout_seconds": live_config.watson_configuration.request_timeout_seconds,
                "force_refresh": True,
                "audience": "watson-flow-manual-probe",
            }
        )
        if token_result.get("status") != "success":
            print("IAM token falhou.")
            return EXIT_LIVE_FAILED
        flow_result = deps.flow_client.run_flow(
            watson_flow_run_request(
                flow_id=live_config.watson_configuration.flow_id,
                bearer_token=token_result["token"],
                payload=build_watson_flow_payload(sql_text),
                request_id="manual-probe",
                run_id="manual-probe",
                invocation_id="manual-probe",
                timeout_seconds=live_config.watson_configuration.request_timeout_seconds,
                purpose=args.purpose,
                limits=limits,
            )
        )
        print(f"flow_status={flow_result.get('status')}")
        if args.show_rows:
            print(f"preview_rows_limit={max(0, min(args.max_preview_rows, 50))}")
        return EXIT_OK if flow_result.get("status") == "success" else EXIT_LIVE_FAILED
    except Exception:
        print("probe live falhou de forma sanitizada.")
        return EXIT_LIVE_FAILED


if __name__ == "__main__":
    raise SystemExit(main())

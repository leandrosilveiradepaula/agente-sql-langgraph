from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


STEPS = [
    ("compileall app", [sys.executable, "-m", "compileall", "app"]),
    (
        "testar_intent_resolver.py",
        [sys.executable, "testar_intent_resolver.py"],
    ),
    (
        "testar_context_normalizer.py",
        [sys.executable, "testar_context_normalizer.py"],
    ),
    (
        "testar_context_validator.py",
        [sys.executable, "testar_context_validator.py"],
    ),
    (
        "testar_classify_intent.py",
        [sys.executable, "testar_classify_intent.py"],
    ),
    ("testar_planner.py", [sys.executable, "testar_planner.py"]),
    (
        "testar_build_plan.py",
        [sys.executable, "testar_build_plan.py"],
    ),
    (
        "testar_sql_generation.py",
        [sys.executable, "testar_sql_generation.py"],
    ),
    (
        "testar_sql_execution.py",
        [sys.executable, "testar_sql_execution.py"],
    ),
    (
        "testar_result_normalization.py",
        [sys.executable, "testar_result_normalization.py"],
    ),
    (
        "testar_result_serialization.py",
        [sys.executable, "testar_result_serialization.py"],
    ),
    (
        "testar_run_record.py",
        [sys.executable, "testar_run_record.py"],
    ),
    (
        "testar_persist_run.py",
        [sys.executable, "testar_persist_run.py"],
    ),
    (
        "testar_record_audit.py",
        [sys.executable, "testar_record_audit.py"],
    ),
    (
        "testar_emit_observability.py",
        [sys.executable, "testar_emit_observability.py"],
    ),
    (
        "testar_application_response.py",
        [sys.executable, "testar_application_response.py"],
    ),
    (
        "testar_build_application_response.py",
        [sys.executable, "testar_build_application_response.py"],
    ),
    (
        "testar_application_request.py",
        [sys.executable, "testar_application_request.py"],
    ),
    (
        "testar_sql_agent_service.py",
        [sys.executable, "testar_sql_agent_service.py"],
    ),
    (
        "testar_application_service_graph_integration.py",
        [sys.executable, "testar_application_service_graph_integration.py"],
    ),
    (
        "testar_auth_types.py",
        [sys.executable, "testar_auth_types.py"],
    ),
    (
        "testar_auth_header.py",
        [sys.executable, "testar_auth_header.py"],
    ),
    (
        "testar_http_request.py",
        [sys.executable, "testar_http_request.py"],
    ),
    (
        "testar_http_response.py",
        [sys.executable, "testar_http_response.py"],
    ),
    (
        "testar_sql_agent_http_handler.py",
        [sys.executable, "testar_sql_agent_http_handler.py"],
    ),
    (
        "testar_http_adapter_integration.py",
        [sys.executable, "testar_http_adapter_integration.py"],
    ),
    (
        "testar_http_auth_boundary.py",
        [sys.executable, "testar_http_auth_boundary.py"],
    ),
    (
        "testar_http_auth_integration.py",
        [sys.executable, "testar_http_auth_integration.py"],
    ),
    (
        "testar_asgi_types.py",
        [sys.executable, "testar_asgi_types.py"],
    ),
    (
        "testar_asgi_request_adapter.py",
        [sys.executable, "testar_asgi_request_adapter.py"],
    ),
    (
        "testar_asgi_response_adapter.py",
        [sys.executable, "testar_asgi_response_adapter.py"],
    ),
    (
        "testar_asgi_application.py",
        [sys.executable, "testar_asgi_application.py"],
    ),
    (
        "testar_asgi_http_integration.py",
        [sys.executable, "testar_asgi_http_integration.py"],
    ),
    (
        "testar_watson_flow_configuration.py",
        [sys.executable, "testar_watson_flow_configuration.py"],
    ),
    (
        "testar_watson_sql_transport.py",
        [sys.executable, "testar_watson_sql_transport.py"],
    ),
    (
        "testar_iam_token_contract.py",
        [sys.executable, "testar_iam_token_contract.py"],
    ),
    (
        "testar_watson_flow_client_contract.py",
        [sys.executable, "testar_watson_flow_client_contract.py"],
    ),
    (
        "testar_watson_flow_response_normalizer.py",
        [sys.executable, "testar_watson_flow_response_normalizer.py"],
    ),
    (
        "testar_watson_flow_preflight_adapter.py",
        [sys.executable, "testar_watson_flow_preflight_adapter.py"],
    ),
    (
        "testar_watson_flow_sql_executor.py",
        [sys.executable, "testar_watson_flow_sql_executor.py"],
    ),
    (
        "testar_watson_flow_graph_integration.py",
        [sys.executable, "testar_watson_flow_graph_integration.py"],
    ),
    (
        "testar_engine_preflight.py",
        [sys.executable, "testar_engine_preflight.py"],
    ),
    (
        "testar_engine_preflight_capability_integration.py",
        [sys.executable, "testar_engine_preflight_capability_integration.py"],
    ),
    (
        "testar_sql_repair.py",
        [sys.executable, "testar_sql_repair.py"],
    ),
    (
        "testar_sql_analysis.py",
        [sys.executable, "testar_sql_analysis.py"],
    ),
    (
        "testar_sql_security.py",
        [sys.executable, "testar_sql_security.py"],
    ),
    (
        "testar_security_gate.py",
        [sys.executable, "testar_security_gate.py"],
    ),
    (
        "testar_sql_contract.py",
        [sys.executable, "testar_sql_contract.py"],
    ),
    (
        "testar_contract_gate.py",
        [sys.executable, "testar_contract_gate.py"],
    ),
    (
        "testar_engine_preflight_node.py",
        [sys.executable, "testar_engine_preflight_node.py"],
    ),
    (
        "testar_execute_sql.py",
        [sys.executable, "testar_execute_sql.py"],
    ),
    (
        "testar_normalize_result.py",
        [sys.executable, "testar_normalize_result.py"],
    ),
    (
        "testar_serialize_result.py",
        [sys.executable, "testar_serialize_result.py"],
    ),
    (
        "testar_repair_sql.py",
        [sys.executable, "testar_repair_sql.py"],
    ),
    (
        "testar_generate_sql.py",
        [sys.executable, "testar_generate_sql.py"],
    ),
    ("testar_grafo_base.py", [sys.executable, "testar_grafo_base.py"]),
    (
        "testar_postgres_context_repository.py",
        [sys.executable, "testar_postgres_context_repository.py"],
    ),
    (
        "testar_postgres_context_graph_bootstrap.py",
        [sys.executable, "testar_postgres_context_graph_bootstrap.py"],
    ),
    ("check_hardcodes.py", [sys.executable, "scripts/check_hardcodes.py"]),
    ("check_secrets.py", [sys.executable, "scripts/check_secrets.py"]),
    ("pip check", [sys.executable, "-m", "pip", "check"]),
]


def main() -> int:
    for name, command in STEPS:
        print(f"==> {name}")
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
        )
        if completed.returncode != 0:
            print(f"FALHOU: {name}", file=sys.stderr)
            return completed.returncode
        print(f"OK: {name}")

    print("TODAS AS VERIFICACOES PASSARAM")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import subprocess
import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


STEPS = [
    ("check_compile.py", [sys.executable, "scripts/check_compile.py"]),
    ("check_imports.py", [sys.executable, "scripts/check_imports.py"]),
    (
        "check_tracked_runtime_files.py",
        [sys.executable, "scripts/check_tracked_runtime_files.py"],
    ),
    ("check_no_network.py", [sys.executable, "scripts/check_no_network.py"]),
    (
        "check_workspace_hygiene.py",
        [sys.executable, "scripts/check_workspace_hygiene.py"],
    ),
    ("check_dependencies.py", [sys.executable, "scripts/check_dependencies.py"]),
    ("testar_clean_room.py", [sys.executable, "testar_clean_room.py"]),
    (
        "testar_check_no_network.py",
        [sys.executable, "testar_check_no_network.py"],
    ),
    ("testar_check_imports.py", [sys.executable, "testar_check_imports.py"]),
    (
        "testar_tracked_runtime_files.py",
        [sys.executable, "testar_tracked_runtime_files.py"],
    ),
    (
        "testar_workspace_hygiene.py",
        [sys.executable, "testar_workspace_hygiene.py"],
    ),
    ("testar_dependencies.py", [sys.executable, "testar_dependencies.py"]),
    (
        "testar_offline_ci_contract.py",
        [sys.executable, "testar_offline_ci_contract.py"],
    ),
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
        "testar_semantic_operations_context.py",
        [sys.executable, "testar_semantic_operations_context.py"],
    ),
    (
        "testar_classify_intent.py",
        [sys.executable, "testar_classify_intent.py"],
    ),
    ("testar_planner.py", [sys.executable, "testar_planner.py"]),
    ("testar_planner_explicit_metric_gate.py", [sys.executable, "testar_planner_explicit_metric_gate.py"]),
    ("testar_temporal_explicit_date_binding.py", [sys.executable, "testar_temporal_explicit_date_binding.py"]),
    ("testar_temporal_context_validation.py", [sys.executable, "testar_temporal_context_validation.py"]),
    ("testar_temporal_catalog_without_columns.py", [sys.executable, "testar_temporal_catalog_without_columns.py"]),
    ("testar_semantic_context_audit_readonly.py", [sys.executable, "testar_semantic_context_audit_readonly.py"]),
    ("testar_semantic_candidate_readiness.py", [sys.executable, "testar_semantic_candidate_readiness.py"]),
    ("testar_semantic_candidate_parity_readonly.py", [sys.executable, "testar_semantic_candidate_parity_readonly.py"]),
    ("testar_memory_candidate_preflight.py", [sys.executable, "testar_memory_candidate_preflight.py"]),
    ("testar_memory_candidate_generalization.py", [sys.executable, "testar_memory_candidate_generalization.py"]),
    ("testar_metric_binding_evidence_readonly.py", [sys.executable, "testar_metric_binding_evidence_readonly.py"]),
    ("testar_contextual_single_metric_inference.py", [sys.executable, "testar_contextual_single_metric_inference.py"]),
    ("testar_semantic_overlay_invariants.py", [sys.executable, "testar_semantic_overlay_invariants.py"]),
    ("testar_semantic_v12_readonly_candidate.py", [sys.executable, "testar_semantic_v12_readonly_candidate.py"]),
    ("testar_semantic_v13_readonly_candidate.py", [sys.executable, "testar_semantic_v13_readonly_candidate.py"]),
    ("testar_semantic_v14_readonly_candidate.py", [sys.executable, "testar_semantic_v14_readonly_candidate.py"]),
    ("testar_semantic_v15_readonly_candidate.py", [sys.executable, "testar_semantic_v15_readonly_candidate.py"]),
    ("testar_semantic_v16_negation_temporal.py", [sys.executable, "testar_semantic_v16_negation_temporal.py"]),
    ("testar_semantic_v17_scoped_negation.py", [sys.executable, "testar_semantic_v17_scoped_negation.py"]),
    ("testar_semantic_v18_negation_intent_gate.py", [sys.executable, "testar_semantic_v18_negation_intent_gate.py"]),
    ("testar_semantic_version_comparison_readonly.py", [sys.executable, "testar_semantic_version_comparison_readonly.py"]),
    ("testar_shadow_semantic_overlay_runner.py", [sys.executable, "testar_shadow_semantic_overlay_runner.py"]),
    ("testar_shadow_semantic_preflight_runner.py", [sys.executable, "testar_shadow_semantic_preflight_runner.py"]),
    ("testar_demo_finance_v11_temporal_candidate.py", [sys.executable, "testar_demo_finance_v11_temporal_candidate.py"]),
    ("testar_metric_required_filter_bindings.py", [sys.executable, "testar_metric_required_filter_bindings.py"]),
    ("testar_filter_target_preprovider.py", [sys.executable, "testar_filter_target_preprovider.py"]),
    ("testar_catalog_filter_authorization.py", [sys.executable, "testar_catalog_filter_authorization.py"]),
    ("testar_shadow_s2s_http_smoke.py", [sys.executable, "testar_shadow_s2s_http_smoke.py"]),
    ("testar_shadow_correlated_evidence_probe.py", [sys.executable, "testar_shadow_correlated_evidence_probe.py"]),
    ("testar_n8n_shadow_network_probe.py", [sys.executable, "testar_n8n_shadow_network_probe.py"]),
    ("testar_n8n_isolated_shadow_workflow.py", [sys.executable, "testar_n8n_isolated_shadow_workflow.py"]),
    ("testar_n8n_parallel_shadow_workflow.py", [sys.executable, "testar_n8n_parallel_shadow_workflow.py"]),
    ("testar_n8n_shadow_evidence_read_workflow.py", [sys.executable, "testar_n8n_shadow_evidence_read_workflow.py"]),
    ("testar_n8n_shadow_evidence_binding_audit.py", [sys.executable, "testar_n8n_shadow_evidence_binding_audit.py"]),
    ("testar_n8n_private_shadow_renderer.py", [sys.executable, "testar_n8n_private_shadow_renderer.py"]),
    ("testar_n8n_parallel_shadow_binding_audit.py", [sys.executable, "testar_n8n_parallel_shadow_binding_audit.py"]),
    ("testar_internal_shadow_sql_comparison.py", [sys.executable, "testar_internal_shadow_sql_comparison.py"]),
    ("testar_blind_shadow_benchmark.py", [sys.executable, "testar_blind_shadow_benchmark.py"]),
    ("testar_shadow_read_organization_scope.py", [sys.executable, "testar_shadow_read_organization_scope.py"]),
    ("testar_n8n_workflow_export_audit.py", [sys.executable, "testar_n8n_workflow_export_audit.py"]),
    ("testar_shadow_full_flow_live_opt_in.py", [sys.executable, "testar_shadow_full_flow_live_opt_in.py"]),
    (
        "testar_planned_filters_e2e.py",
        [sys.executable, "testar_planned_filters_e2e.py"],
    ),
    (
        "testar_demo_planned_filters_context.py",
        [sys.executable, "testar_demo_planned_filters_context.py"],
    ),
    (
        "testar_demo_finance_v2_context.py",
        [sys.executable, "testar_demo_finance_v2_context.py"],
    ),
    (
        "testar_demo_finance_v2_apply_runner.py",
        [sys.executable, "testar_demo_finance_v2_apply_runner.py"],
    ),
    (
        "testar_demo_finance_v3_context.py",
        [sys.executable, "testar_demo_finance_v3_context.py"],
    ),
    (
        "testar_demo_finance_v4_context.py",
        [sys.executable, "testar_demo_finance_v4_context.py"],
    ),
    (
        "testar_demo_finance_v5_context.py",
        [sys.executable, "testar_demo_finance_v5_context.py"],
    ),
    (
        "testar_demo_finance_v6_context.py",
        [sys.executable, "testar_demo_finance_v6_context.py"],
    ),
    (
        "testar_demo_finance_v8_context.py",
        [sys.executable, "testar_demo_finance_v8_context.py"],
    ),
    (
        "testar_demo_finance_v9_context.py",
        [sys.executable, "testar_demo_finance_v9_context.py"],
    ),
    (
        "testar_semantic_migration_env_loader.py",
        [sys.executable, "testar_semantic_migration_env_loader.py"],
    ),
    (
        "testar_curated_intent_context.py",
        [sys.executable, "testar_curated_intent_context.py"],
    ),
    (
        "testar_postgres_intent_catalog_curado_live.py",
        [sys.executable, "testar_postgres_intent_catalog_curado_live.py"],
    ),
    (
        "testar_semantic_context_v10_apply_runner.py",
        [sys.executable, "testar_semantic_context_v10_apply_runner.py"],
    ),
    (
        "testar_postgres_consolidation_inventory.py",
        [sys.executable, "testar_postgres_consolidation_inventory.py"],
    ),
    (
        "testar_build_plan.py",
        [sys.executable, "testar_build_plan.py"],
    ),
    (
        "testar_sql_generation.py",
        [sys.executable, "testar_sql_generation.py"],
    ),
    (
        "testar_shadow_context_candidate_readonly.py",
        [sys.executable, "testar_shadow_context_candidate_readonly.py"],
    ),
    (
        "testar_google_gemini_sql_generator.py",
        [sys.executable, "testar_google_gemini_sql_generator.py"],
    ),
    (
        "testar_google_gemini_sql_repairer.py",
        [sys.executable, "testar_google_gemini_sql_repairer.py"],
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
        "testar_internal_sql_agent_v1_use_cases.py",
        [sys.executable, "testar_internal_sql_agent_v1_use_cases.py"],
    ),
    (
        "testar_shadow_evidence_persistence.py",
        [sys.executable, "testar_shadow_evidence_persistence.py"],
    ),
    (
        "testar_internal_sql_agent_v1_http_handler.py",
        [sys.executable, "testar_internal_sql_agent_v1_http_handler.py"],
    ),
    (
        "testar_shadow_test_runtime.py",
        [sys.executable, "testar_shadow_test_runtime.py"],
    ),
    (
        "testar_shadow_semantic_validation_runner.py",
        [sys.executable, "testar_shadow_semantic_validation_runner.py"],
    ),
    (
        "testar_shadow_real_generation_adapters.py",
        [sys.executable, "testar_shadow_real_generation_adapters.py"],
    ),
    (
        "testar_shadow_test_uvicorn_smoke.py",
        [sys.executable, "testar_shadow_test_uvicorn_smoke.py"],
    ),
    (
        "testar_shadow_test_deploy_runbook.py",
        [sys.executable, "testar_shadow_test_deploy_runbook.py"],
    ),
    (
        "testar_langgraph_graph_visualization.py",
        [sys.executable, "testar_langgraph_graph_visualization.py"],
    ),
    (
        "testar_shadow_run_visualization.py",
        [sys.executable, "testar_shadow_run_visualization.py"],
    ),
    (
        "testar_internal_shadow_read_v1_use_cases.py",
        [sys.executable, "testar_internal_shadow_read_v1_use_cases.py"],
    ),
    (
        "testar_internal_shadow_read_v1_http_handler.py",
        [sys.executable, "testar_internal_shadow_read_v1_http_handler.py"],
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
        "testar_internal_service_auth.py",
        [sys.executable, "testar_internal_service_auth.py"],
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
        "testar_sensitive_secret.py",
        [sys.executable, "testar_sensitive_secret.py"],
    ),
    (
        "testar_secret_value_provider.py",
        [sys.executable, "testar_secret_value_provider.py"],
    ),
    (
        "testar_http_transport_contract.py",
        [sys.executable, "testar_http_transport_contract.py"],
    ),
    (
        "testar_stdlib_http_transport.py",
        [sys.executable, "testar_stdlib_http_transport.py"],
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
    ("check_secrets.py", [sys.executable, "scripts/check_secrets.py"]),]

if os.environ.get("SQL_AGENT_CLEAN_ROOM") != "1":
    STEPS.append(("pip check", [sys.executable, "-m", "pip", "check"]))


def main() -> int:
    for name, command in STEPS:
        print(f"==> {name}")
        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONUTF8"] = "1"
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            env=env,
        )
        if completed.returncode != 0:
            print(f"FALHOU: {name}", file=sys.stderr)
            return completed.returncode
        print(f"OK: {name}")

    print("TODAS AS VERIFICACOES PASSARAM")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

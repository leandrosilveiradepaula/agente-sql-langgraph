from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT / "app"

BUSINESS_TERMS = {
    "cliente_",
    "fabricante_",
    "customer_",
    "manufacturer_",
    "benchmark_example",
}

PLANNER_FORBIDDEN_EXTERNALS = {
    "gemini",
    "watson",
    "supabase",
}

LIVE_INTEGRATION_ALLOWED = {
    "app/integrations/watson/configuration.py",
    "app/integrations/watson/live_configuration.py",
    "app/integrations/watson/live_iam_token_provider.py",
    "app/integrations/watson/live_watson_flow_client.py",
    "app/infrastructure/http/http_contracts.py",
    "app/infrastructure/http/stdlib_http_transport.py",
    "app/infrastructure/secrets/environment_secret_provider.py",
}

PLANNER_FILES = {
    "app/domain/planner.py",
    "app/domain/planning.py",
    "app/domain/result_normalization.py",
    "app/domain/result_normalization_types.py",
    "app/domain/result_serialization.py",
    "app/domain/engine_preflight.py",
    "app/domain/engine_preflight_sanitization.py",
    "app/domain/engine_preflight_types.py",
    "app/domain/sql_analysis.py",
    "app/domain/sql_contract.py",
    "app/domain/sql_execution.py",
    "app/domain/sql_execution_types.py",
    "app/domain/sql_generation.py",
    "app/domain/sql_repair.py",
    "app/domain/sql_repair_types.py",
    "app/domain/sql_security.py",
    "app/graph/nodes/build_plan.py",
    "app/graph/nodes/contract_gate.py",
    "app/graph/nodes/engine_preflight.py",
    "app/graph/nodes/execute_sql.py",
    "app/graph/nodes/generate_sql.py",
    "app/graph/nodes/normalize_result.py",
    "app/graph/nodes/repair_sql.py",
    "app/graph/nodes/security_gate.py",
    "app/graph/nodes/serialize_result.py",
    "app/ports/engine_preflight.py",
    "app/ports/sql_executor.py",
    "app/ports/sql_generator.py",
    "app/ports/sql_repairer.py",
}

WATSON_URL_PATTERN = re.compile(
    r"https://[A-Za-z0-9_.-]*watson[A-Za-z0-9_./:-]*",
    re.IGNORECASE,
)
UUID_PATTERN = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
SANITIZED_FILES = {
    "scripts/watson_test_probe.cmd",
    "docs/baselines/pre-live-readiness-baseline.md",
}
SQL_ALLOWED_FILES = {
    "scripts/watson_test_probe.cmd",
    "docs/runbooks/watson-test-first-live-probe.md",
    "docs/runbooks/watson-test-pre-live-checklist.md",
    "testar_manual_watson_flow_probe.py",
    "testar_watson_test_probe_cmd.py",
    "testar_check_no_network.py",
    "scripts/offline_watson_failure_rehearsal.py",
    "testar_offline_watson_failure_rehearsal.py",
    "scripts/check_hardcodes.py",
}


def _versioned_python_files() -> list[str]:
    completed = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "app",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return [
        line.strip().replace("\\", "/")
        for line in completed.stdout.splitlines()
        if line.strip() and line.strip().endswith(".py")
    ]


def _versioned_text_files() -> list[str]:
    completed = subprocess.run(
        [
            "git",
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return [
        line.strip().replace("\\", "/")
        for line in completed.stdout.splitlines()
        if line.strip()
        and Path(line.strip()).suffix.casefold()
        in {".py", ".md", ".cmd", ".yml", ".yaml"}
    ]


def _string_literals(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append(node.value.casefold())
    return values


def main() -> int:
    findings: list[str] = []

    for relative_path in _versioned_python_files():
        path = ROOT / relative_path
        if not path.is_relative_to(APP_ROOT):
            continue

        strings = _string_literals(path)
        for value in strings:
            for term in BUSINESS_TERMS:
                if term in value:
                    findings.append(f"{relative_path}: termo bloqueado {term}")

        if relative_path in PLANNER_FILES:
            raw_text = path.read_text(encoding="utf-8").casefold()
            for term in PLANNER_FORBIDDEN_EXTERNALS:
                if term in raw_text:
                    findings.append(
                        f"{relative_path}: referencia externa bloqueada {term}"
                    )

    for relative_path in _versioned_text_files():
        text = (ROOT / relative_path).read_text(encoding="utf-8").casefold()
        if relative_path in SANITIZED_FILES:
            if WATSON_URL_PATTERN.search(text):
                findings.append(f"{relative_path}: URL Watson fixa bloqueada")
            if UUID_PATTERN.search(text):
                findings.append(f"{relative_path}: flow ID completo bloqueado")
        if "select 1 as adapter_contract_probe" in text and relative_path not in SQL_ALLOWED_FILES:
            findings.append(
                f"{relative_path}: SQL sintetica fora de arquivo autorizado"
            )

    if findings:
        print("Hardcodes bloqueados encontrados:")
        for finding in findings:
            print(f"- {finding}")
        return 1

    print("Nenhum hardcode bloqueado encontrado em app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

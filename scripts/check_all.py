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

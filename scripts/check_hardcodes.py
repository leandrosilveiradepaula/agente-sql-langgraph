from __future__ import annotations

import ast
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

PLANNER_FILES = {
    "app/domain/planner.py",
    "app/domain/planning.py",
    "app/domain/sql_generation.py",
    "app/graph/nodes/build_plan.py",
    "app/graph/nodes/generate_sql.py",
    "app/ports/sql_generator.py",
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

    if findings:
        print("Hardcodes bloqueados encontrados:")
        for finding in findings:
            print(f"- {finding}")
        return 1

    print("Nenhum hardcode bloqueado encontrado em app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

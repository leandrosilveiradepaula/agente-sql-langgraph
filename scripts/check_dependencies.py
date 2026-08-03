from __future__ import annotations

import ast
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements.txt"

FORBIDDEN_DEPENDENCIES = {
    "requests",
    "httpx",
    "aiohttp",
    "urllib3",
    "ibm-watson",
    "ibm-cloud-sdk-core",
    "watson-developer-cloud",
    "google-adk",
    "python-dotenv",
    "dotenv",
    "tenacity",
}

APPROVED_EXTERNALS = {"langgraph", "psycopg"}


def parse_requirements(path: Path = REQUIREMENTS) -> dict[str, str]:
    if not path.is_file():
        raise ValueError("requirements.txt ausente.")
    deps: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if any(marker in line for marker in ("://", "git+", "file:", "\\")):
            raise ValueError("requirements contem origem remota ou caminho local.")
        match = re.fullmatch(
            r"([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?==([A-Za-z0-9_.!*+-]+)",
            line,
        )
        if not match:
            raise ValueError("requirements deve usar pin ==.")
        deps[match.group(1).casefold()] = match.group(2)
    return deps


def external_imports(paths: list[Path]) -> set[str]:
    imports: set[str] = set()
    stdlib = set(getattr(sys, "stdlib_module_names", set()))
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".", 1)[0]
                    _maybe_add(imports, name, stdlib)
            elif isinstance(node, ast.ImportFrom) and node.module:
                name = node.module.split(".", 1)[0]
                _maybe_add(imports, name, stdlib)
    return imports


def _maybe_add(imports: set[str], name: str, stdlib: set[str]) -> None:
    if name in {"app", "scripts", "testar_grafo_base"}:
        return
    if name in stdlib or name == "__future__":
        return
    imports.add(name)


def main() -> int:
    findings: list[str] = []
    try:
        deps = parse_requirements()
    except ValueError as exc:
        print(f"DEPENDENCY_CHECK_FAILED: {exc}")
        return 1
    for name in deps:
        if name in FORBIDDEN_DEPENDENCIES:
            findings.append(f"dependencia proibida: {name}")
    paths = list((ROOT / "app").rglob("*.py")) + list((ROOT / "scripts").glob("*.py"))
    imports = external_imports(paths)
    for name in sorted(imports):
        if name in FORBIDDEN_DEPENDENCIES:
            findings.append(f"import proibido: {name}")
        elif name not in APPROVED_EXTERNALS:
            findings.append(f"import externo nao declarado/aprovado: {name}")
    missing = APPROVED_EXTERNALS & imports - set(deps)
    for name in sorted(missing):
        findings.append(f"dependencia ausente em requirements: {name}")
    if findings:
        print("Dependency findings:")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("DEPENDENCY_CHECK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import ast
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]

CRITICAL_ENTRYPOINTS = (
    "app.bootstrap",
    "app.infrastructure.http",
    "app.infrastructure.secrets",
    "app.infrastructure.secrets.environment_secret_provider",
    "app.infrastructure.secrets.sensitive_secret",
    "app.integrations.google_gemini",
    "app.integrations.google_gemini.sql_repairer_adapter",
)

LOCAL_ROOTS = {"app", "scripts"}


@dataclass(frozen=True)
class Finding:
    path: str
    category: str


def inspect_runtime_files(
    root: Path = ROOT,
    entrypoints: tuple[str, ...] = CRITICAL_ENTRYPOINTS,
) -> list[Finding]:
    root = root.resolve()
    tracked = _tracked_paths(root)
    findings: list[Finding] = []
    visited_modules: set[str] = set()
    visited_paths: set[Path] = set()
    stack = list(entrypoints)

    while stack:
        module = stack.pop()
        if module in visited_modules or not _is_local_module_name(module):
            continue
        visited_modules.add(module)

        paths = _module_paths(root, module)
        if not paths:
            findings.append(Finding(_module_display_path(module), "missing_runtime_module"))
            continue

        for path in _package_init_paths(root, module) + paths:
            if path in visited_paths:
                continue
            visited_paths.add(path)
            relative = _relative(path, root)
            if relative not in tracked:
                category = (
                    "ignored_runtime_file"
                    if _is_ignored(root, relative)
                    else "untracked_runtime_file"
                )
                findings.append(Finding(relative, category))
                continue
            stack.extend(_imports_from_file(root, path))

    return sorted(set(findings), key=lambda item: (item.path, item.category))


def _tracked_paths(root: Path) -> set[str]:
    inside = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        raise RuntimeError("not_git_repository")
    completed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        text=True,
        capture_output=True,
        check=True,
    )
    return {
        path.replace("\\", "/")
        for path in completed.stdout.split("\0")
        if path.strip()
    }


def _imports_from_file(root: Path, path: Path) -> list[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []
    modules: set[str] = set()
    package = _module_package(root, path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_local_module_name(alias.name):
                    modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            base = _absolute_import_base(package, node.module, node.level)
            if not base or not _is_local_module_name(base):
                continue
            if _module_paths(root, base):
                modules.add(base)
            else:
                modules.add(base)
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                candidate = f"{base}.{alias.name}"
                if _module_paths(root, candidate):
                    modules.add(candidate)
    return sorted(modules)


def _absolute_import_base(package: str, module: str | None, level: int) -> str | None:
    if level == 0:
        return module
    package_parts = package.split(".") if package else []
    if level > len(package_parts) + 1:
        return None
    base_parts = package_parts[: len(package_parts) - level + 1]
    if module:
        base_parts.extend(module.split("."))
    return ".".join(part for part in base_parts if part)


def _module_package(root: Path, path: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    else:
        parts.pop()
    return ".".join(parts)


def _module_paths(root: Path, module: str) -> list[Path]:
    parts = module.split(".")
    paths: list[Path] = []
    module_file = root.joinpath(*parts).with_suffix(".py")
    package_init = root.joinpath(*parts, "__init__.py")
    if module_file.is_file():
        paths.append(module_file.resolve())
    if package_init.is_file():
        paths.append(package_init.resolve())
    return paths


def _package_init_paths(root: Path, module: str) -> list[Path]:
    parts = module.split(".")
    paths: list[Path] = []
    for index in range(1, len(parts)):
        package_init = root.joinpath(*parts[:index], "__init__.py")
        if package_init.is_file():
            paths.append(package_init.resolve())
    return paths


def _is_local_module_name(module: str) -> bool:
    return bool(module) and module.split(".", 1)[0] in LOCAL_ROOTS


def _is_ignored(root: Path, relative: str) -> bool:
    completed = subprocess.run(
        ["git", "check-ignore", "-q", "--", relative],
        cwd=root,
        text=True,
        capture_output=True,
    )
    return completed.returncode == 0


def _module_display_path(module: str) -> str:
    return module.replace(".", "/") + ".py"


def _relative(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root).as_posix()


def main() -> int:
    try:
        findings = inspect_runtime_files()
    except RuntimeError as exc:
        print(f"TRACKED_RUNTIME_FILES_FAILED: {exc}")
        return 1
    if findings:
        print("Tracked runtime file findings:")
        for finding in findings:
            print(f"- {finding.path} | {finding.category}")
        return 1
    print("TRACKED_RUNTIME_FILES_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

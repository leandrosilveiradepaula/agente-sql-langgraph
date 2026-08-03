from __future__ import annotations

import subprocess
import sys
from pathlib import Path


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.check_tracked_runtime_files as tracked_runtime
MAX_EXPECTED_FILE_BYTES = 5_000_000

SUSPICIOUS_NAME_MARKERS = {
    "secret",
    "token",
    "credential",
    "apikey",
    "api_key",
}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".log", ".dump"}
FORBIDDEN_NAMES = {".env"}
CACHE_DIR_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
PROJECT_TEMP_DIR_NAMES = {"tmp", "temp"}
EXCLUDED_DIR_NAMES = {".git", ".venv", "venv", "env", "node_modules"}


def _git_files() -> list[str]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return [line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()]


def inspect_workspace(root: Path = ROOT) -> list[tuple[str, str, str]]:
    findings: list[tuple[str, str, str]] = []
    paths = _repo_paths(root) if root == ROOT else _walk_temp(root)
    for relative, path in paths:
        lowered = path.name.casefold()
        if path.is_dir():
            if lowered in CACHE_DIR_NAMES:
                findings.append((relative, "python_cache", "remover cache gerado"))
            elif lowered in PROJECT_TEMP_DIR_NAMES:
                findings.append((relative, "temporary_directory", "remover diretorio temporario"))
            continue
        if not path.exists() or path.is_dir() or path.is_symlink():
            continue
        suffix = path.suffix.casefold()
        if path.name == ".env.example":
            pass
        elif path.name in FORBIDDEN_NAMES or lowered.startswith(".env."):
            findings.append((relative, "env_file", "remover ou manter fora do repositorio"))
        if suffix in FORBIDDEN_SUFFIXES:
            findings.append((relative, "forbidden_artifact", "remover artefato sensivel/local"))
        if any(marker in lowered for marker in SUSPICIOUS_NAME_MARKERS):
            findings.append((relative, "suspicious_name", "verificar se contem apenas fixtures fake"))
        if "watson" in lowered and any(marker in lowered for marker in {"response", "raw", "output"}):
            findings.append((relative, "watson_output", "remover resposta bruta"))
        if suffix == ".sql" and "scripts/" not in relative:
            findings.append((relative, "temporary_sql", "remover SQL temporaria"))
        if path.stat().st_size > MAX_EXPECTED_FILE_BYTES:
            findings.append((relative, "large_file", "validar necessidade antes de versionar"))
    if root == ROOT:
        findings.extend(_runtime_tracking_findings(root))
    return findings


def _runtime_tracking_findings(root: Path) -> list[tuple[str, str, str]]:
    try:
        findings = tracked_runtime.inspect_runtime_files(root)
    except RuntimeError:
        return [(".", "runtime_tracking_unavailable", "executar dentro de um repositorio Git")]
    return [
        (
            finding.path,
            finding.category,
            "rastrear arquivo Python necessario em runtime",
        )
        for finding in findings
    ]


def _repo_paths(root: Path) -> list[tuple[str, Path]]:
    git_seen = set(_git_files())
    paths: dict[str, Path] = {}
    for relative in git_seen:
        paths[relative] = root / relative
    for relative, path in _walk_temp(root):
        paths.setdefault(relative, path)
    return sorted(paths.items())


def _walk_temp(root: Path) -> list[tuple[str, Path]]:
    paths: list[tuple[str, Path]] = []
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        parts = {part.casefold() for part in path.relative_to(root).parts}
        if parts & EXCLUDED_DIR_NAMES:
            continue
        if path.is_symlink():
            continue
        if path.is_dir() and path.name.casefold() in CACHE_DIR_NAMES | PROJECT_TEMP_DIR_NAMES:
            paths.append((relative, path))
            continue
        if path.is_file():
            paths.append((relative, path))
    return paths


def main() -> int:
    findings = inspect_workspace()
    blocking = []
    for item in findings:
        relative, category, _action = item
        if category == "suspicious_name":
            continue
        if category == "watson_output" and relative.startswith("testar_"):
            continue
        blocking.append(item)
    if blocking:
        print("Workspace hygiene findings:")
        for relative, category, action in blocking:
            print(f"- {relative} | {category} | {action}")
        return 1
    print("WORKSPACE_HYGIENE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

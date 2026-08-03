from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
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
    for relative in _git_files() if root == ROOT else _walk_temp(root):
        path = root / relative
        if not path.exists() or path.is_dir() or path.is_symlink():
            continue
        lowered = path.name.casefold()
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
    return findings


def _walk_temp(root: Path) -> list[str]:
    paths: list[str] = []
    for path in root.rglob("*"):
        if path.is_file() and not path.is_symlink():
            paths.append(path.relative_to(root).as_posix())
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

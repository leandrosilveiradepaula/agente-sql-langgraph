from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True

import scripts.check_tracked_runtime_files as check


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _git(root)
        _write_runtime_package(root)
        _write(root / "app" / "bootstrap.py", _bootstrap_import())
        _add(root, "app")
        assert check.inspect_runtime_files(root, ("app.bootstrap",)) == []

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _git(root)
        _write(root / ".gitignore", "secrets/\n")
        _write_runtime_package(root)
        _write(root / "app" / "bootstrap.py", _bootstrap_import())
        _add(root, ".gitignore", "app/bootstrap.py", "app/__init__.py")
        findings = check.inspect_runtime_files(root, ("app.bootstrap",))
        assert ("app/infrastructure/secrets/sensitive_secret.py", "ignored_runtime_file") in _pairs(findings)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _git(root)
        _write(root / "app" / "__init__.py", "")
        _write(root / "app" / "bootstrap.py", "import app.missing.module\n")
        _add(root, "app")
        findings = check.inspect_runtime_files(root, ("app.bootstrap",))
        assert ("app/missing/module.py", "missing_runtime_module") in _pairs(findings)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _git(root)
        _write(root / ".gitignore", ".env\n*.pem\nsecrets/\n!app/infrastructure/secrets/\n!app/infrastructure/secrets/*.py\n")
        _write_runtime_package(root)
        _write(root / "app" / "bootstrap.py", _bootstrap_import())
        _write(root / "app" / "infrastructure" / "secrets" / ".env", "VALUE=hidden\n")
        _write(root / "app" / "infrastructure" / "secrets" / "local.pem", "hidden\n")
        _add(root, ".gitignore", "app")
        assert check.inspect_runtime_files(root, ("app.bootstrap",)) == []
        assert _ignored(root, "app/infrastructure/secrets/.env")
        assert _ignored(root, "app/infrastructure/secrets/local.pem")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _git(root)
        secret_text = "fake-sensitive-value"
        _write_runtime_package(root)
        _write(root / "app" / "bootstrap.py", _bootstrap_import())
        _write(root / "app" / "infrastructure" / "secrets" / "sensitive_secret.py", secret_text)
        findings = check.inspect_runtime_files(root, ("app.bootstrap",))
        output = "\n".join(f"{finding.path} {finding.category}" for finding in findings)
        assert secret_text not in output

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(root / "app" / "bootstrap.py", "")
        try:
            check.inspect_runtime_files(root, ("app.bootstrap",))
        except RuntimeError as exc:
            assert str(exc) == "not_git_repository"
        else:
            raise AssertionError("fora de Git deve falhar fechado")

    assert "app.bootstrap" in check.CRITICAL_ENTRYPOINTS
    assert "app.infrastructure.secrets" in check.CRITICAL_ENTRYPOINTS
    assert "app.infrastructure.secrets.sensitive_secret" in check.CRITICAL_ENTRYPOINTS
    assert "app.infrastructure.secrets.environment_secret_provider" in check.CRITICAL_ENTRYPOINTS
    print("testar_tracked_runtime_files.py: 16/16 OK")


def _bootstrap_import() -> str:
    return "from app.infrastructure.secrets.sensitive_secret import SensitiveSecret\n"


def _write_runtime_package(root: Path) -> None:
    _write(root / "app" / "__init__.py", "")
    _write(root / "app" / "infrastructure" / "secrets" / "__init__.py", "__all__ = []\n")
    _write(root / "app" / "infrastructure" / "secrets" / "sensitive_secret.py", "class SensitiveSecret:\n    pass\n")
    _write(root / "app" / "infrastructure" / "secrets" / "environment_secret_provider.py", "VALUE = 1\n")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _git(root: Path) -> None:
    _run(root, "git", "init")
    _run(root, "git", "config", "user.email", "test@example.invalid")
    _run(root, "git", "config", "user.name", "Test User")


def _add(root: Path, *paths: str) -> None:
    _run(root, "git", "add", "--", *paths)


def _ignored(root: Path, path: str) -> bool:
    return _run(root, "git", "check-ignore", "-q", "--", path, check=False).returncode == 0


def _run(root: Path, *command: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=root,
        text=True,
        capture_output=True,
        check=check,
    )


def _pairs(findings: list[check.Finding]) -> set[tuple[str, str]]:
    return {(finding.path, finding.category) for finding in findings}


if __name__ == "__main__":
    main()

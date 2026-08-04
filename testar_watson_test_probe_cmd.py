from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CMD = ROOT / "scripts" / "watson_test_probe.cmd"
REAL_PYTHON = Path(sys.executable)
SENSITIVE_MARKERS = (
    "test-placeholder-api-key",
    "Authorization",
    "Bearer",
    "00e0284a-d785-448b-aed3-95672dd4d189",
    "https://example.invalid",
)


def main() -> None:
    text = CMD.read_text(encoding="utf-8")
    _assert_success(_run(CMD, "help"), "help")
    _assert_success(_run(CMD, "dry-run"), "dry-run-local")
    _assert_code(_run(CMD, "dry-run-config"), 2, "dry-run-config-sem-config")
    _assert_success(_run(CMD, "clean"), "clean")

    env = _base_env()
    assert _run(CMD, "live-execution", env=env).returncode == 2
    env["WATSON_API_BASE_URL"] = "https://example.invalid"
    env["WATSON_FLOW_ID"] = "00e0284a-d785-448b-aed3-95672dd4d189"
    assert _run(CMD, "live-execution", env=env).returncode == 2
    env["IBM_CLOUD_API_KEY"] = "test-placeholder-api-key"
    denied = _run(CMD, "live-execution", env=env, input_text="NAO\n")
    _assert_code(denied, 5, "live-confirmacao-negada")

    with _sandbox() as sandbox:
        result = _run(sandbox.cmd, "dry-run", env=sandbox.env_without_venv, cwd=sandbox.outside_cwd)
        _assert_success(result, "dry-run-python-path")
        assert "PYTHON:" in result.stdout
        assert "PURPOSE:execution" in result.stdout

    with _sandbox(venv=True) as sandbox:
        result = _run(sandbox.cmd, "dry-run", env=sandbox.env_without_path_python)
        _assert_success(result, "dry-run-prefere-venv")
        assert "PYTHON:" in result.stdout
        assert str(sandbox.root / ".venv" / "Scripts" / "python.exe") in result.stdout

    with _sandbox() as sandbox:
        result = _run(sandbox.cmd, "dry-run", env=sandbox.env_without_any_python)
        _assert_code(result, 2, "dry-run-sem-python")
        assert "Python valido nao encontrado." in result.stdout
        assert not (Path(sandbox.env_without_any_python["TEMP"]) / "watson-flow-probe").exists()

    with _sandbox(invalid_path_python=True) as sandbox:
        result = _run(sandbox.cmd, "dry-run", env=sandbox.env_with_invalid_python)
        _assert_code(result, 2, "dry-run-python-invalido")
        assert "Python valido nao encontrado." in result.stdout

    with _sandbox(path_with_spaces=True) as sandbox:
        result = _run(sandbox.cmd, "dry-run", env=sandbox.env_with_spaced_python)
        _assert_success(result, "dry-run-python-com-espacos")
        assert "PYTHON:" in result.stdout

    no_temp = _base_env()
    no_temp["PATH"] = str(REAL_PYTHON.parent)
    no_temp.pop("TEMP", None)
    no_temp.pop("TMP", None)
    _assert_code(_run(CMD, "dry-run", env=no_temp), 2, "dry-run-sem-temp")

    with tempfile.NamedTemporaryFile() as temp_file:
        invalid_temp = _base_env()
        invalid_temp["PATH"] = str(REAL_PYTHON.parent)
        invalid_temp["TEMP"] = temp_file.name
        invalid_temp["TMP"] = temp_file.name
        _assert_code(_run(CMD, "dry-run", env=invalid_temp), 2, "dry-run-temp-invalido")

    with _sandbox() as sandbox:
        env = dict(sandbox.env_without_venv)
        env["WATSON_API_BASE_URL"] = "https://example.invalid"
        env["WATSON_FLOW_ID"] = "00e0284a-d785-448b-aed3-95672dd4d189"
        result = _run(sandbox.cmd, "dry-run-config", env=env)
        _assert_success(result, "dry-run-config-com-config")
        assert "PURPOSE:execution" in result.stdout

    with _sandbox() as sandbox:
        env = dict(sandbox.env_without_venv)
        env["WATSON_API_BASE_URL"] = "https://example.invalid"
        env["WATSON_FLOW_ID"] = "00e0284a-d785-448b-aed3-95672dd4d189"
        env["IBM_CLOUD_API_KEY"] = "test-placeholder-api-key"
        execution = _run(sandbox.cmd, "live-execution", env=env, input_text="EXECUTAR TEST\n")
        preflight = _run(sandbox.cmd, "live-preflight", env=env, input_text="EXECUTAR TEST\n")
        _assert_success(execution, "live-execution-fake")
        _assert_success(preflight, "live-preflight-fake")
        assert "PURPOSE:execution" in execution.stdout
        assert "PURPOSE:preflight" in preflight.stdout

    with _sandbox() as sandbox:
        env = dict(sandbox.env_without_venv)
        result = _run(sandbox.cmd, "dry-run", env=env)
        _assert_success(result, "cleanup-apos-sucesso")
        assert not (Path(env["TEMP"]) / "watson-flow-probe" / "adapter_contract_probe.sql").exists()

    failing = subprocess.CompletedProcess(
        ["cmd"],
        99,
        stdout="Authorization: Bearer test-placeholder-api-key\nhttps://example.invalid\nSELECT 1 AS adapter_contract_probe\n",
        stderr="flow=00e0284a-d785-448b-aed3-95672dd4d189\n",
    )
    try:
        _assert_success(failing, "diagnostico")
    except AssertionError as exc:
        message = str(exc)
        assert "operation=diagnostico" in message
        assert "returncode=99" in message
        assert "test-placeholder-api-key" not in message
        assert "https://example.invalid" not in message
        assert "00e0284a-d785-448b-aed3-95672dd4d189" not in message
        assert "SELECT 1 AS adapter_contract_probe" not in message
    else:
        raise AssertionError("assert diagnostico deveria falhar")

    assert "cmd.exe" in Path(os.environ.get("ComSpec", "cmd.exe")).name.casefold()
    assert "cmd.exe" in _run_command_name()
    assert "--purpose execution" in text
    assert "--purpose %~1" in text
    assert "--confirm-test-environment" in text
    assert "--show-rows" not in text
    assert "setx" not in text.casefold()
    assert "echo %IBM_CLOUD_API_KEY%" not in text
    assert "retry" not in text.casefold()
    assert "goto :run_live" not in text.casefold()
    assert "%~dp0" in text
    assert ".venv\\Scripts\\python.exe" in text
    assert "where.exe\" python.exe" in text
    assert "%TEMP%\\watson-flow-probe" in text
    assert "del /q" in text
    assert "setlocal" in text.casefold()
    assert "sessao CMD pai" in text
    assert "EXECUTAR TEST" in text
    assert "pip install" not in text.casefold()
    assert "-m pip" not in text.casefold()
    assert "python.exe valido no PATH" in text
    print("testar_watson_test_probe_cmd.py: 40/40 OK")


class _Sandbox:
    def __init__(
        self,
        root: Path,
        *,
        venv: bool = False,
        invalid_path_python: bool = False,
        path_with_spaces: bool = False,
    ) -> None:
        self.root = root
        self.cmd = root / "scripts" / "watson_test_probe.cmd"
        self.outside_cwd = root / "outside cwd"
        self.outside_cwd.mkdir()
        scripts = root / "scripts"
        scripts.mkdir()
        shutil.copy2(CMD, self.cmd)
        _write_fake_probe(scripts / "manual_watson_flow_probe.py")
        self.temp = root / "temp"
        self.temp.mkdir()
        self.path_python_dir = root / ("python path with spaces" if path_with_spaces else "python-path")
        self.path_python_dir.mkdir()
        if invalid_path_python:
            (self.path_python_dir / "python.exe").write_text("not an executable", encoding="utf-8")
        else:
            _copy_python_runtime(self.path_python_dir)
        if venv:
            venv_dir = root / ".venv" / "Scripts"
            venv_dir.mkdir(parents=True)
            _copy_python_runtime(venv_dir)
        self.env_without_venv = _env_with_path(self.path_python_dir, self.temp)
        self.env_without_path_python = _env_with_path(root / "empty-path", self.temp)
        self.env_without_any_python = _env_with_path(root / "empty-path", self.temp)
        self.env_with_invalid_python = _env_with_path(self.path_python_dir, self.temp)
        self.env_with_spaced_python = _env_with_path(self.path_python_dir, self.temp)
        (root / "empty-path").mkdir(exist_ok=True)


def _sandbox(**kwargs):
    class Context:
        def __enter__(self):
            self.tmp = tempfile.TemporaryDirectory()
            self.sandbox = _Sandbox(Path(self.tmp.name), **kwargs)
            return self.sandbox

        def __exit__(self, exc_type, exc, tb):
            self.tmp.cleanup()
            return False

    return Context()


def _run(
    cmd: Path,
    mode: str,
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [_cmd_exe(), "/d", "/c", str(cmd), mode]
    return subprocess.run(
        command,
        cwd=cwd or ROOT,
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
        timeout=30,
    )


def _run_command_name() -> str:
    return _cmd_exe().name.casefold()


def _cmd_exe() -> Path:
    comspec = os.environ.get("ComSpec")
    if comspec:
        return Path(comspec)
    return Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"


def _assert_success(result: subprocess.CompletedProcess[str], operation: str) -> None:
    if result.returncode != 0:
        raise AssertionError(_diagnostic(result, operation))


def _assert_code(result: subprocess.CompletedProcess[str], expected: int, operation: str) -> None:
    if result.returncode != expected:
        raise AssertionError(_diagnostic(result, operation))


def _diagnostic(result: subprocess.CompletedProcess[str], operation: str) -> str:
    return (
        f"operation={operation}\n"
        f"returncode={result.returncode}\n"
        f"stdout={_sanitize(result.stdout)}\n"
        f"stderr={_sanitize(result.stderr)}"
    )


def _sanitize(text: str) -> str:
    sanitized = text.replace("\r", "")
    for marker in SENSITIVE_MARKERS:
        sanitized = sanitized.replace(marker, "<redacted>")
    sanitized = re.sub(r"(?i)authorization\s*:\s*[^\n]+", "Authorization: <redacted>", sanitized)
    sanitized = re.sub(r"(?i)bearer\s+\S+", "Bearer <redacted>", sanitized)
    sanitized = re.sub(r"(?i)(api[_-]?key|token|secret)=\S+", r"\1=<redacted>", sanitized)
    sanitized = re.sub(r"SELECT\s+1\s+AS\s+adapter_contract_probe", "<sql-redacted>", sanitized)
    return sanitized[:1200]


def _base_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PATH"] = os.environ.get("PATH", "")
    temp = os.environ.get("TEMP") or tempfile.gettempdir()
    env["TEMP"] = temp
    env["TMP"] = os.environ.get("TMP", temp)
    for key in ["IBM_CLOUD_API_KEY", "WATSON_API_BASE_URL", "WATSON_FLOW_ID"]:
        env.pop(key, None)
    return env


def _env_with_path(path_dir: Path, temp: Path) -> dict[str, str]:
    env = _base_env()
    env["PATH"] = str(path_dir)
    env["TEMP"] = str(temp)
    env["TMP"] = str(temp)
    return env


def _copy_python_runtime(target: Path) -> None:
    source = Path(getattr(sys, "_base_executable", sys.executable))
    shutil.copy2(source, target / "python.exe")
    for dll in source.parent.glob("python*.dll"):
        shutil.copy2(dll, target / dll.name)
    for dll in source.parent.glob("vcruntime*.dll"):
        shutil.copy2(dll, target / dll.name)


def _write_fake_probe(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "import argparse",
                "import sys",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('--execute-live', action='store_true')",
                "parser.add_argument('--confirm-test-environment', action='store_true')",
                "parser.add_argument('--sql-file', required=True)",
                "parser.add_argument('--purpose', required=True)",
                "parser.add_argument('--print-plan-json', action='store_true')",
                "args = parser.parse_args()",
                "print('PYTHON:' + sys.executable)",
                "print('PURPOSE:' + args.purpose)",
                "print('EXECUTE_LIVE:' + str(args.execute_live).lower())",
            ]
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

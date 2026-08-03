from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CMD = ROOT / "scripts" / "watson_test_probe.cmd"


def _run(mode: str, *, env=None, input_text: str | None = None):
    return subprocess.run(
        [str(CMD), mode],
        cwd=ROOT / "app",
        env=env,
        input=input_text,
        text=True,
        capture_output=True,
    )


def main() -> None:
    text = CMD.read_text(encoding="utf-8")
    assert _run("help").returncode == 0
    assert _run("dry-run").returncode == 0
    assert _run("dry-run-config").returncode == 2
    assert _run("clean").returncode == 0
    env = dict(os.environ)
    env.pop("WATSON_API_BASE_URL", None)
    env.pop("WATSON_FLOW_ID", None)
    env.pop("IBM_CLOUD_API_KEY", None)
    assert _run("live-execution", env=env).returncode == 2
    env["WATSON_API_BASE_URL"] = "https://example.invalid"
    env["WATSON_FLOW_ID"] = "00e0284a-d785-448b-aed3-95672dd4d189"
    assert _run("live-execution", env=env).returncode == 2
    env["IBM_CLOUD_API_KEY"] = "fake-api-key-for-test"
    denied = _run("live-execution", env=env, input_text="NAO\n")
    assert denied.returncode == 5
    assert "manual_watson_flow_probe.py" in text
    assert "--purpose execution" in text
    assert "--purpose %~1" in text
    assert "--confirm-test-environment" in text
    assert "--show-rows" not in text
    assert "setx" not in text.casefold()
    assert "echo %IBM_CLOUD_API_KEY%" not in text
    assert "retry" not in text.casefold()
    assert "%~dp0" in text
    assert ".venv\\Scripts\\python.exe" in text
    assert "%TEMP%\\watson-flow-probe" in text
    assert "del /q" in text
    assert "setlocal" in text.casefold()
    assert "sessao CMD pai" in text
    assert "EXECUTAR TEST" in text
    print("testar_watson_test_probe_cmd.py: 20/20 OK")


if __name__ == "__main__":
    main()

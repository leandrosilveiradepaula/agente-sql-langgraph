from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

import scripts.check_imports as check


def main() -> None:
    assert len(check.MODULES) == 3
    env = dict(os.environ)
    env["TEST_SECRET_KEY"] = "fake-value-not-used"
    completed = subprocess.run(
        [sys.executable, "scripts/check_imports.py"],
        cwd=Path(__file__).resolve().parent,
        env=env,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == "IMPORT_CHECK_OK"
    assert "fake-value" not in completed.stdout + completed.stderr
    source = Path("scripts/check_imports.py").read_text(encoding="utf-8")
    assert "socket.socket.connect" in source
    assert "getaddrinfo" in source
    assert "importlib.import_module" in source
    assert "EnvironmentSecretProvider(" not in source
    assert "StdlibHttpTransport(" not in source
    assert ".write_text" not in source or "TemporaryDirectory" in source
    assert "SQL_AGENT_DISABLE_NETWORK" in source
    print("testar_check_imports.py: 10/10 OK")


if __name__ == "__main__":
    main()

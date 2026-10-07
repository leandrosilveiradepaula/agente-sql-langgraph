from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_LIMIT = 16_000

STEPS = [
    ("check_all", [sys.executable, "scripts/check_all.py"]),
    ("check_hardcodes", [sys.executable, "scripts/check_hardcodes.py"]),
    ("check_secrets", [sys.executable, "scripts/check_secrets.py"]),
    ("check_no_network", [sys.executable, "scripts/check_no_network.py"]),
    ("check_imports", [sys.executable, "scripts/check_imports.py"]),
    (
        "bootstrap_smoke",
        [
            sys.executable,
            "-c",
            "import app.bootstrap; print('BOOTSTRAP_SMOKE_OK')",
        ],
    ),
]


def clean_environment(tmp: Path) -> dict[str, str]:
    env = dict(os.environ)
    for name in _removed_env_names():
        env.pop(name, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUTF8"] = "1"
    env["SQL_AGENT_DISABLE_NETWORK"] = "1"
    env["SQL_AGENT_CLEAN_ROOM"] = "1"
    env["TMP"] = str(tmp)
    env["TEMP"] = str(tmp)
    return env


def _removed_env_names() -> set[str]:
    names = {
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
    }
    return names | {name.lower() for name in names}


def run_step(name: str, command: list[str], env: dict[str, str]) -> int:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    output = ((completed.stdout or "") + (completed.stderr or ""))[-OUTPUT_LIMIT:]
    if completed.returncode != 0:
        print(f"CLEAN_ROOM_FAILED: {name}")
        print(output)
        return completed.returncode
    print(f"OK: {name}")
    return 0


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="sql-agent-clean-room-") as tmp_raw:
        env = clean_environment(Path(tmp_raw))
        for name, command in STEPS:
            code = run_step(name, command, env)
            if code != 0:
                return code
    print("CLEAN_ROOM_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

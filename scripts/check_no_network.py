from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

GUARDED_TESTS = [
    "testar_stdlib_http_transport.py",
    "testar_application_service_graph_integration.py",
    "testar_grafo_base.py",
    "testar_postgres_context_graph_bootstrap.py",
    "testar_google_gemini_sql_generator.py",
    "testar_google_gemini_sql_repairer.py",
    "testar_shadow_real_generation_adapters.py",
]

SITECUSTOMIZE = r'''
from __future__ import annotations

import http.client
import socket
import urllib.request


def _network_blocked(*_args, **_kwargs):
    raise RuntimeError("NETWORK_BLOCKED_OFFLINE_TEST")


socket.socket.connect = _network_blocked
socket.create_connection = _network_blocked
socket.getaddrinfo = _network_blocked
http.client.HTTPConnection.connect = _network_blocked
http.client.HTTPSConnection.connect = _network_blocked
urllib.request.urlopen = _network_blocked
'''


def guarded_environment(site_dir: Path) -> dict[str, str]:
    env = dict(os.environ)
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(site_dir) if not existing else f"{site_dir}{os.pathsep}{existing}"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONUTF8"] = "1"
    env["SQL_AGENT_DISABLE_NETWORK"] = "1"
    for name in _network_env_names():
        env.pop(name, None)
    return env


def run_guarded(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="sql-agent-network-guard-") as tmp:
        site_dir = Path(tmp)
        (site_dir / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
        return subprocess.run(
            command,
            cwd=ROOT,
            env=guarded_environment(site_dir),
            text=True,
            capture_output=capture,
        )


def _network_env_names() -> set[str]:
    names = {
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
    }
    return names | {name.lower() for name in names}


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    if args:
        completed = run_guarded([sys.executable, *args])
        return completed.returncode

    for test in GUARDED_TESTS:
        print(f"==> guarded {test}")
        completed = run_guarded([sys.executable, test])
        if completed.returncode != 0:
            print(f"NETWORK_GUARD_FAILED: {test}", file=sys.stderr)
            return completed.returncode
        print(f"OK: {test}")
    print("NETWORK_GUARD_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

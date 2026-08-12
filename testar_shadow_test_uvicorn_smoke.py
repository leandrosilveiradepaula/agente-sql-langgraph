from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.adapters.testing.fake_shadow_evidence_repository import (
    FakeShadowEvidenceRepository,
)
from app.application.internal_sql_agent_v1_shared import shadow_record_id
from app.test_runtime.composition import create_shadow_test_asgi_app


HOST = "127.0.0.1"
AGENT_RUN_ID = "agent-run-uvicorn-smoke"
S2S_TOKEN = "test-s2s-token"
LOCALHOSTS = {HOST, "localhost", "::1"}
NETWORK_GUARD_SITE = r'''
from __future__ import annotations

import socket

_ORIGINAL_CREATE_CONNECTION = socket.create_connection
_ORIGINAL_GETADDRINFO = socket.getaddrinfo
_ORIGINAL_SOCKET_CONNECT = socket.socket.connect
_LOCALHOSTS = {"127.0.0.1", "localhost", "::1"}


def _host_allowed(host):
    return str(host).casefold() in _LOCALHOSTS


def _guarded_getaddrinfo(host, *args, **kwargs):
    if host is not None and not _host_allowed(host):
        raise RuntimeError("NETWORK_BLOCKED_OFFLINE_TEST")
    return _ORIGINAL_GETADDRINFO(host, *args, **kwargs)


def _guarded_create_connection(address, *args, **kwargs):
    host = address[0] if isinstance(address, tuple) and address else address
    if not _host_allowed(host):
        raise RuntimeError("NETWORK_BLOCKED_OFFLINE_TEST")
    return _ORIGINAL_CREATE_CONNECTION(address, *args, **kwargs)


def _guarded_socket_connect(self, address):
    host = address[0] if isinstance(address, tuple) and address else address
    if not _host_allowed(host):
        raise RuntimeError("NETWORK_BLOCKED_OFFLINE_TEST")
    return _ORIGINAL_SOCKET_CONNECT(self, address)


socket.getaddrinfo = _guarded_getaddrinfo
socket.create_connection = _guarded_create_connection
socket.socket.connect = _guarded_socket_connect
'''


def create_app():
    return create_shadow_test_asgi_app(
        shadow_repository_override=FakeShadowEvidenceRepository()
    )


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def _assert_localhost(url: str) -> None:
    host = urllib.request.urlparse(url).hostname
    assert host in LOCALHOSTS


def _install_network_guard(site_dir: Path) -> None:
    (site_dir / "sitecustomize.py").write_text(
        NETWORK_GUARD_SITE,
        encoding="utf-8",
    )


def _get_json(url: str, *, token: str | None = None) -> dict[str, Any]:
    _assert_localhost(url)
    request = urllib.request.Request(url, method="GET")
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
        request.add_header("Accept", "application/json")
    with urllib.request.urlopen(request, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    token: str | None = S2S_TOKEN,
) -> tuple[int, dict[str, Any]]:
    _assert_localhost(url)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def _generate_payload() -> dict[str, Any]:
    return {
        "contract_version": "1",
        "agent_run_id": AGENT_RUN_ID,
        "question": "Execute uma generic analysis de teste.",
        "principal": {"id": "user-1", "email": "user@example.invalid", "profile": "admin"},
        "correlation_metadata": {"source": "uvicorn_smoke"},
    }


def _execute_payload() -> dict[str, Any]:
    return {
        "contract_version": "1",
        "agent_run_id": AGENT_RUN_ID,
        "approved_sql": "SELECT id FROM schema_test.table_test",
        "principal": {"id": "user-1", "email": "user@example.invalid", "profile": "admin"},
        "correlation_metadata": {"source": "uvicorn_smoke"},
    }


def test_uvicorn_local_smoke() -> bool:
    try:
        import uvicorn  # noqa: F401
    except ModuleNotFoundError:
        print("UVICORN_SMOKE_SKIPPED: uvicorn is not installed in the current venv")
        return False

    port = _free_port()
    env = dict(os.environ)
    env.update(
        {
            "LANGGRAPH_RUNTIME_MODE": "shadow_test",
            "LANGGRAPH_HTTP_HOST": HOST,
            "LANGGRAPH_HTTP_PORT": str(port),
            "LANGGRAPH_SHADOW_PERSISTENCE": "postgres",
            "LANGGRAPH_SHADOW_DATABASE_DSN": "postgresql://shadow-test-placeholder",
            "LANGGRAPH_S2S_TOKEN": S2S_TOKEN,
            "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "false",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
        }
    )
    base_url = f"http://{HOST}:{port}"
    with TemporaryDirectory(prefix="shadow-test-network-guard-") as guard_dir:
        site_dir = Path(guard_dir)
        _install_network_guard(site_dir)
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(site_dir)
            if not existing_pythonpath
            else f"{site_dir}{os.pathsep}{existing_pythonpath}"
        )
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "testar_shadow_test_uvicorn_smoke:create_app",
                "--factory",
                "--host",
                HOST,
                "--port",
                str(port),
                "--log-level",
                "warning",
            ],
            cwd=os.getcwd(),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    stderr = process.stderr.read() if process.stderr else ""
                    raise AssertionError(f"uvicorn exited early: {stderr}")
                try:
                    health = _get_json(f"{base_url}/health")
                    break
                except Exception:
                    time.sleep(0.05)
            else:
                raise AssertionError("uvicorn did not become ready")

            unauth_status, unauth_generate = _post_json(
                f"{base_url}/v1/internal/sql-agent/generate",
                _generate_payload(),
                token=None,
            )
            wrong_status, wrong_generate = _post_json(
                f"{base_url}/v1/internal/sql-agent/generate",
                _generate_payload(),
                token="wrong-token",
            )
            generate_status, generate = _post_json(
                f"{base_url}/v1/internal/sql-agent/generate",
                _generate_payload(),
            )
            generate_shadow_record_id = shadow_record_id(
                agent_run_id=generate["agent_run_id"],
                run_id=generate["run_id"],
                event_type="generate",
            )
            shadow_run = _get_json(
                f"{base_url}/v1/internal/shadow-runs/{generate_shadow_record_id}",
                token=S2S_TOKEN,
            )
            visualization = _get_json(
                f"{base_url}/v1/internal/shadow-runs/{generate_shadow_record_id}/visualization",
                token=S2S_TOKEN,
            )
            execute_status, execute = _post_json(
                f"{base_url}/v1/internal/sql-agent/execute-approved-shadow",
                _execute_payload(),
            )
            listed = _get_json(
                f"{base_url}/v1/internal/agent-runs/{AGENT_RUN_ID}/shadow-runs?limit=10",
                token=S2S_TOKEN,
            )
            assert health["status"] == "ok"
            assert health["runtime_mode"] == "shadow_test"
            assert health["real_sql_execution"] is False
            assert unauth_status == 401
            assert unauth_generate["error"]["code"] == "UNAUTHORIZED_SERVICE"
            assert wrong_status == 401
            assert wrong_generate["error"]["code"] == "UNAUTHORIZED_SERVICE"
            assert generate_status == 200
            assert generate["status"] == "success"
            assert shadow_run["shadow_record_id"] == generate_shadow_record_id
            assert visualization["run"]["shadow_record_id"] == generate_shadow_record_id
            assert execute_status == 200
            assert execute["status"] == "success"
            assert len(listed["items"]) == 2
            safe_outputs = repr(shadow_run) + repr(visualization) + repr(listed)
            assert "Execute uma generic analysis de teste." not in safe_outputs
            assert "SELECT id FROM schema_test.table_test" not in safe_outputs
            return True
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)


def main() -> None:
    ran = test_uvicorn_local_smoke()
    if ran:
        print("TESTE 1 - test_uvicorn_local_smoke: OK")


if __name__ == "__main__":
    main()

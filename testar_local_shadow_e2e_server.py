from __future__ import annotations

import json
import os
import socket
import sys
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import closing, contextmanager
from typing import Any

from app.local_testing.internal_sql_agent_v1_local_server import (
    LocalShadowRuntime,
    create_local_shadow_test_server,
)


AGENT_RUN_ID = "11111111-1111-4111-8111-111111111111"
HOST = "127.0.0.1"
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "::1"}
LOCAL_TEST_ONLY_ENV = "LANGGRAPH_LOCAL_TEST_ONLY"
LOCAL_TEST_ONLY_VALUE = "1"


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])


def _server(runtime: LocalShadowRuntime | None = None):
    with _local_test_flag(LOCAL_TEST_ONLY_VALUE):
        server = create_local_shadow_test_server(
            host=HOST,
            port=_free_port(),
            runtime=runtime,
        )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _url(server, path: str) -> str:
    return f"http://{HOST}:{server.server_address[1]}{path}"


def _post_json(server, path: str, payload: dict) -> dict:
    url = _url(server, path)
    _assert_localhost(url)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


def _get_json(server, path: str) -> dict:
    url = _url(server, path)
    _assert_localhost(url)
    with urllib.request.urlopen(url, timeout=2) as response:
        return json.loads(response.read().decode("utf-8"))


def _assert_localhost(url: str) -> None:
    host = urllib.request.urlparse(url).hostname
    _assert_allowed_network_host(host)


def _assert_allowed_network_host(host: object) -> None:
    assert str(host).casefold() in ALLOWED_HOSTS


@contextmanager
def _local_test_flag(value: str | None) -> Iterator[None]:
    previous = os.environ.get(LOCAL_TEST_ONLY_ENV)
    try:
        if value is None:
            os.environ.pop(LOCAL_TEST_ONLY_ENV, None)
        else:
            os.environ[LOCAL_TEST_ONLY_ENV] = value
        yield
    finally:
        if previous is None:
            os.environ.pop(LOCAL_TEST_ONLY_ENV, None)
        else:
            os.environ[LOCAL_TEST_ONLY_ENV] = previous


@contextmanager
def _guard_external_network() -> Iterator[list[str]]:
    original_create_connection = socket.create_connection
    original_connect = socket.socket.connect
    blocked_hosts: list[str] = []

    def guarded_create_connection(
        address: tuple[Any, ...],
        *args: Any,
        **kwargs: Any,
    ):
        host = str(address[0]).casefold()
        if host not in ALLOWED_HOSTS:
            blocked_hosts.append(host)
            raise AssertionError(f"external network blocked: {host}")
        return original_create_connection(address, *args, **kwargs)

    def guarded_connect(sock: socket.socket, address: Any) -> None:
        host = str(address[0]).casefold()
        if host not in ALLOWED_HOSTS:
            blocked_hosts.append(host)
            raise AssertionError(f"external network blocked: {host}")
        return original_connect(sock, address)

    socket.create_connection = guarded_create_connection
    socket.socket.connect = guarded_connect
    try:
        yield blocked_hosts
    finally:
        socket.create_connection = original_create_connection
        socket.socket.connect = original_connect


def _principal() -> dict:
    return {
        "id": "user-1",
        "email": "user@example.invalid",
        "profile": "admin",
    }


def _generate_payload() -> dict:
    return {
        "contract_version": "1",
        "agent_run_id": AGENT_RUN_ID,
        "question": "Execute uma generic analysis de teste.",
        "principal": _principal(),
        "correlation_metadata": {
            "source": "nextjs_bff",
            "event": "generate",
            "route": "/api/generate-sql",
            "request_id": "request-generate",
        },
    }


def _execute_payload(sql: str = "SELECT id FROM schema_test.table_test") -> dict:
    return {
        "contract_version": "1",
        "agent_run_id": AGENT_RUN_ID,
        "approved_sql": sql,
        "principal": _principal(),
        "correlation_metadata": {
            "source": "nextjs_bff",
            "event": "execute_approved",
            "route": "/api/execute-watson",
            "request_id": "request-execute",
        },
    }


def test_generate_e_execute_persistem_1_n_sem_rede_externa_ou_banco() -> None:
    runtime = LocalShadowRuntime()
    assert (
        "app.infrastructure.persistence.postgres_shadow_evidence_repository"
        not in sys.modules
    )
    with _guard_external_network() as blocked_hosts:
        server, thread = _server(runtime)
        try:
            generate = _post_json(
                server,
                "/v1/internal/sql-agent/generate",
                _generate_payload(),
            )
            execute = _post_json(
                server,
                "/v1/internal/sql-agent/execute-approved-shadow",
                _execute_payload(),
            )
            records = _get_json(
                server,
                f"/__local-test/records?agent_run_id={AGENT_RUN_ID}",
            )["records"]

            assert generate["status"] == "success"
            assert generate["agent_run_id"] == AGENT_RUN_ID
            assert generate["run_id"] != AGENT_RUN_ID
            assert generate["sql"] == "SELECT id FROM schema_test.table_test"
            assert execute["status"] == "success"
            assert execute["agent_run_id"] == AGENT_RUN_ID
            assert execute["run_id"] != AGENT_RUN_ID
            assert execute["approved_sql_original"] == (
                "SELECT id FROM schema_test.table_test"
            )
            assert execute["requires_reapproval"] is False
            assert len(records) == 2
            assert {record["event_type"] for record in records} == {
                "generate",
                "execute_approved_shadow",
            }
            assert len({record["shadow_record_id"] for record in records}) == 2
            assert len({record["run_id"] for record in records}) == 2
            assert {record["agent_run_id"] for record in records} == {AGENT_RUN_ID}
            assert all(record["preflight_executed"] is False for record in records)
            assert runtime.sql_generator.calls == 1
            assert runtime.sql_repairer.calls == 0
            assert blocked_hosts == []
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_payload_sanitizado_recebido_no_adapter_local() -> None:
    runtime = LocalShadowRuntime()
    with _guard_external_network() as blocked_hosts:
        server, thread = _server(runtime)
        try:
            _post_json(server, "/v1/internal/sql-agent/generate", _generate_payload())
            requests = _get_json(server, "/__local-test/received-requests")[
                "requests"
            ]
            captured = requests[0]
            serialized = repr(captured).casefold()

            assert captured["contract_version"] == "1"
            assert captured["agent_run_id"] == AGENT_RUN_ID
            assert captured["question"] == "Execute uma generic analysis de teste."
            assert captured["principal"] == _principal()
            assert "contract_version" in captured["body_keys"]
            assert "agent_run_id" in captured["body_keys"]
            assert "question" in captured["body_keys"]
            assert "principal" in captured["body_keys"]
            assert "id" in captured["principal_keys"]
            assert "email" in captured["principal_keys"]
            assert "profile" in captured["principal_keys"]
            assert "authorization" not in captured["header_names"]
            assert "cookie" not in captured["header_names"]
            assert "credentials" not in serialized
            assert "session" not in serialized
            assert "policy" not in serialized
            assert blocked_hosts == []
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_execute_repair_vira_proposta_com_reapproval_sem_executar_sql() -> None:
    runtime = LocalShadowRuntime(preflight_mode="repairable_once")
    with _guard_external_network() as blocked_hosts:
        server, thread = _server(runtime)
        try:
            response = _post_json(
                server,
                "/v1/internal/sql-agent/execute-approved-shadow",
                _execute_payload("SELECT value FROM schema_test.table_test"),
            )
            records = _get_json(
                server,
                f"/__local-test/records?agent_run_id={AGENT_RUN_ID}",
            )["records"]

            assert response["status"] == "rejected"
            assert response["approved_sql_original"] == (
                "SELECT value FROM schema_test.table_test"
            )
            assert response["repaired_sql_proposal"] == (
                "SELECT id FROM schema_test.table_test"
            )
            assert response["requires_reapproval"] is True
            assert records[0]["approved_sql_original"] == (
                "SELECT value FROM schema_test.table_test"
            )
            assert records[0]["repaired_sql_proposal"] == (
                "SELECT id FROM schema_test.table_test"
            )
            assert records[0]["requires_reapproval"] is True
            assert records[0]["preflight_executed"] is not True
            assert blocked_hosts == []
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


def test_trava_local_exige_flag_explicita_e_preserva_bind_local() -> None:
    for value in (None, "0"):
        with _local_test_flag(value):
            try:
                create_local_shadow_test_server(host=HOST, port=_free_port())
            except RuntimeError:
                pass
            else:
                raise AssertionError("local test flag should be required")

    with _local_test_flag(LOCAL_TEST_ONLY_VALUE):
        server = create_local_shadow_test_server(host=HOST, port=_free_port())
        server.server_close()

    for host in ("0.0.0.0", "192.0.2.10"):
        with _local_test_flag(LOCAL_TEST_ONLY_VALUE):
            try:
                create_local_shadow_test_server(host=host, port=_free_port())
            except ValueError:
                pass
            else:
                raise AssertionError(f"public bind should be rejected: {host}")


def test_network_guard_global_bloqueia_host_nao_local() -> None:
    runtime = LocalShadowRuntime()
    with _guard_external_network() as blocked_hosts:
        server, thread = _server(runtime)
        try:
            assert _get_json(server, "/__local-test/records")["records"] == []
            with closing(
                socket.create_connection(("localhost", server.server_address[1]), 2)
            ):
                pass
            for host in (
                "example.invalid",
                "n8n.example.invalid",
                "generativelanguage.googleapis.com",
                "watson.example.invalid",
            ):
                try:
                    socket.create_connection((host, 443), timeout=0.01)
                except AssertionError:
                    pass
                else:
                    raise AssertionError(f"network guard should reject {host}")
            assert set(blocked_hosts) == {
                "example.invalid",
                "n8n.example.invalid",
                "generativelanguage.googleapis.com",
                "watson.example.invalid",
            }
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    try:
        _assert_localhost("https://example.invalid")
    except AssertionError:
        pass
    else:
        raise AssertionError("network guard should reject remote host")


def main() -> None:
    tests = [
        test_generate_e_execute_persistem_1_n_sem_rede_externa_ou_banco,
        test_payload_sanitizado_recebido_no_adapter_local,
        test_execute_repair_vira_proposta_com_reapproval_sem_executar_sql,
        test_trava_local_exige_flag_explicita_e_preserva_bind_local,
        test_network_guard_global_bloqueia_host_nao_local,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNBOOK = ROOT / "docs" / "deployment" / "shadow-test-vps-supabase-runbook.md"
SYSTEMD = (
    ROOT
    / "deploy"
    / "systemd"
    / "agente-sql-langgraph-shadow-test.service.example"
)
NGINX = ROOT / "deploy" / "nginx" / "langgraph-shadow-test.conf.example"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_templates_exist() -> None:
    assert RUNBOOK.is_file()
    assert SYSTEMD.is_file()
    assert NGINX.is_file()


def test_systemd_template_safe_and_localhost_runtime() -> None:
    text = _read(SYSTEMD)
    assert "User=langgraph-shadow" in text
    assert "Group=langgraph-shadow" in text
    assert "WorkingDirectory=/srv/agente-sql-langgraph/current" in text
    assert "EnvironmentFile=/etc/agente-sql-langgraph/shadow-test.env" in text
    assert "app.test_runtime.sql_agent_test_app:create_app" in text
    assert "--factory" in text
    assert "--host ${LANGGRAPH_HTTP_HOST}" in text
    assert "--port ${LANGGRAPH_HTTP_PORT}" in text
    assert "NoNewPrivileges=true" in text
    assert "PrivateTmp=true" in text
    assert "ProtectSystem=full" in text
    assert "ProtectHome=true" in text
    assert "LANGGRAPH_S2S_TOKEN=" not in text
    assert "LANGGRAPH_SHADOW_DATABASE_DSN=" not in text
    assert "0.0.0.0" not in text


def test_nginx_template_preserves_auth_without_secret() -> None:
    text = _read(NGINX)
    assert "server_name <LANGGRAPH_TEST_HOSTNAME>;" in text
    assert "proxy_pass http://127.0.0.1:<LANGGRAPH_INTERNAL_PORT>;" in text
    assert "proxy_set_header Authorization $http_authorization;" in text
    assert "client_max_body_size 1m;" in text
    assert "proxy_connect_timeout 2s;" in text
    assert "proxy_send_timeout 5s;" in text
    assert "proxy_read_timeout 5s;" in text
    assert "Bearer " not in text
    assert "LANGGRAPH_S2S_TOKEN" not in text


def test_runbook_covers_deploy_contract() -> None:
    text = _read(RUNBOOK)
    required = [
        "Original Product on Vercel",
        "Hostinger VPS",
        "Supabase SaaS PostgreSQL",
        "CPython 3.12.13",
        "python -m pip install -r requirements.txt",
        "/etc/agente-sql-langgraph/shadow-test.env",
        "LANGGRAPH_RUNTIME_MODE=shadow_test",
        "LANGGRAPH_HTTP_HOST=127.0.0.1",
        "LANGGRAPH_SHADOW_PERSISTENCE=postgres",
        "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false",
        "LANGGRAPH_SHADOW_DATABASE_DSN",
        "LANGGRAPH_S2S_TOKEN",
        "Authorization: Bearer <LANGGRAPH_S2S_TOKEN>",
        "product_original_bff",
        "openssl rand -hex 48",
        "app.test_runtime.sql_agent_test_app:create_app",
        "systemd",
        "Nginx",
        "sslmode=require",
        "SELECT",
        "INSERT",
        "UPDATE",
        "`DELETE` is not required",
        "LANGGRAPH_INTERNAL_BASE_URL=https://<LANGGRAPH_TEST_HOSTNAME>",
        "No variable should use `NEXT_PUBLIC_`",
        "curl --fail http://127.0.0.1:<LANGGRAPH_INTERNAL_PORT>/health",
        "negative auth",
        "positive synthetic auth",
        "failure isolation",
        "Do not alter n8n",
        "Database rollback requires explicit review",
        "GO GATE A",
        "GO GATE F",
        "This TEST runbook is not production-ready",
    ]
    for item in required:
        assert item in text


def test_no_real_secret_or_real_host_in_artifacts() -> None:
    combined = "\n".join(_read(path) for path in (RUNBOOK, SYSTEMD, NGINX))
    templates = "\n".join(_read(path) for path in (SYSTEMD, NGINX))
    forbidden = [
        "NEXT_PUBLIC_LANGGRAPH_S2S_TOKEN",
        "LANGGRAPH_S2S_TOKEN=abc",
        "LANGGRAPH_SHADOW_DATABASE_DSN=postgres",
        "postgresql://",
        "supabase.co",
        "hostinger.com",
        "leandro",
    ]
    for item in forbidden:
        assert item.casefold() not in combined.casefold()
    assert "0.0.0.0" not in templates


if __name__ == "__main__":
    tests = [
        test_templates_exist,
        test_systemd_template_safe_and_localhost_runtime,
        test_nginx_template_preserves_auth_without_secret,
        test_runbook_covers_deploy_contract,
        test_no_real_secret_or_real_host_in_artifacts,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")

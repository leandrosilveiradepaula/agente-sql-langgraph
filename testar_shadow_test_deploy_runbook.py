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
DOCKERFILE = ROOT / "deploy" / "docker" / "Dockerfile.shadow-test"
COMPOSE = ROOT / "deploy" / "docker" / "compose.shadow-test.yaml.example"
DOCKER_ENV = ROOT / "deploy" / "docker" / "shadow-test.env.example"
DOCKERIGNORE = ROOT / ".dockerignore"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_templates_exist() -> None:
    for path in (RUNBOOK, SYSTEMD, NGINX, DOCKERFILE, COMPOSE, DOCKER_ENV, DOCKERIGNORE):
        assert path.is_file(), str(path)


def test_dockerfile_runtime_is_minimal_and_non_root() -> None:
    text = _read(DOCKERFILE)
    assert "FROM python:3.12-slim" in text
    assert "WORKDIR /app" in text
    assert "COPY requirements.txt ./requirements.txt" in text
    assert "COPY app ./app" in text
    assert "USER langgraph" in text
    assert "EXPOSE 8000" in text
    assert "app.test_runtime.sql_agent_test_app:create_app" in text
    assert '"--factory"' in text
    assert '"--host", "0.0.0.0"' in text
    assert '"--port", "8000"' in text
    assert "LANGGRAPH_S2S_TOKEN" not in text
    assert "LANGGRAPH_SHADOW_DATABASE_DSN" not in text
    assert "latest" not in text


def test_dockerignore_excludes_sensitive_and_local_artifacts() -> None:
    text = _read(DOCKERIGNORE)
    required = [
        ".git",
        ".env",
        ".env.*",
        ".venv",
        "__pycache__/",
        "*.pyc",
        "docs/",
        "testar_*.py",
        "scripts/",
        "payload.json",
        "response.json",
    ]
    for item in required:
        assert item in text


def test_compose_uses_traefik_network_without_host_ports() -> None:
    text = _read(COMPOSE)
    assert "name: agente-sql-langgraph-shadow-test" in text
    assert "langgraph-shadow-test:" in text
    assert "restart: unless-stopped" in text
    assert "env_file:" in text
    assert "- ./shadow-test.env" in text
    assert "LANGGRAPH_HTTP_HOST: 0.0.0.0" in text
    assert 'LANGGRAPH_HTTP_PORT: "8000"' in text
    assert 'LANGGRAPH_ALLOW_REAL_SQL_EXECUTION: "false"' in text
    assert "expose:" in text
    assert '- "8000"' in text
    assert "ports:" not in text
    assert "n8n_default:" in text
    assert "external: true" in text
    assert "traefik.enable=true" in text
    assert "traefik.docker.network=n8n_default" in text
    assert "Host(`<LANGGRAPH_TEST_HOSTNAME>`)" in text
    assert "entrypoints=websecure" in text
    assert "tls.certresolver=mytlschallenge" in text
    assert "loadbalancer.server.port=8000" in text
    assert "LANGGRAPH_S2S_TOKEN" not in text
    assert "LANGGRAPH_SHADOW_DATABASE_DSN" not in text


def test_compose_healthcheck_uses_python_stdlib() -> None:
    text = _read(COMPOSE)
    assert "healthcheck:" in text
    assert "urllib.request" in text
    assert "http://127.0.0.1:8000/health" in text
    assert "curl" not in text


def test_docker_env_example_has_only_empty_secrets() -> None:
    text = _read(DOCKER_ENV)
    assert "LANGGRAPH_RUNTIME_MODE=shadow_test" in text
    assert "LANGGRAPH_HTTP_HOST=0.0.0.0" in text
    assert "LANGGRAPH_HTTP_PORT=8000" in text
    assert "LANGGRAPH_SHADOW_PERSISTENCE=postgres" in text
    assert "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false" in text
    assert "LANGGRAPH_SHADOW_DATABASE_DSN=" in text
    assert "LANGGRAPH_S2S_TOKEN=" in text
    assert "LANGGRAPH_SHADOW_DATABASE_DSN=postgres" not in text
    assert "LANGGRAPH_S2S_TOKEN=abc" not in text
    assert "GEMINI_SQL_GENERATOR_PROVIDER_KEY=google_gemini" in text
    assert "GEMINI_SQL_GENERATOR_CONFIG_VERSION=gemini-demo-v1" in text
    assert "OPENAI_COMPATIBLE_SQL_PROVIDER_KEY=infodive_local" in text
    assert "OPENAI_COMPATIBLE_SQL_CONFIG_VERSION=sql-infodive-demo-v1" in text
    assert "OPENAI_COMPATIBLE_SQL_MODEL=sql-infodive" in text
    assert "OPENAI_COMPATIBLE_SQL_BASE_URL=" in text
    assert "OPENAI_COMPATIBLE_SQL_API_KEY=" in text


def test_old_nginx_and_systemd_marked_as_alternative() -> None:
    for path in (SYSTEMD, NGINX):
        text = _read(path)
        assert "Alternative deployment template only." in text
        assert "Not used for the current Hostinger VPS target" in text
        assert "Docker Compose + existing Traefik + n8n_default" in text


def test_runbook_covers_real_docker_traefik_contract() -> None:
    text = _read(RUNBOOK)
    required = [
        "Docker: 29.1.5",
        "Docker Compose: v5.0.2",
        "Traefik: 3.6.7",
        "n8n-traefik-1",
        "TLS resolver: mytlschallenge",
        "Shared Docker network: n8n_default",
        "/docker/agente-sql-langgraph/",
        "project: agente-sql-langgraph-shadow-test",
        "service: langgraph-shadow-test",
        "python:3.12-slim",
        "runtime user: non-root `langgraph`",
        "--host 0.0.0.0",
        "--port 8000",
        "zero host port",
        "deploy/docker/compose.shadow-test.yaml.example",
        "traefik.http.routers.langgraph-shadow-test.entrypoints=websecure",
        "traefik.http.routers.langgraph-shadow-test.tls.certresolver=mytlschallenge",
        "LANGGRAPH_TEST_HOSTNAME TO CONFIRM",
        "deploy/docker/shadow-test.env.example",
        "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false",
        "Authorization: Bearer <LANGGRAPH_S2S_TOKEN>",
        "build locally on the VPS from the approved repo commit",
        "SUPABASE CONNECTION MODE TO CONFIRM DURING DEPLOY",
        "LANGGRAPH_INTERNAL_BASE_URL=https://<LANGGRAPH_TEST_HOSTNAME>",
        "OPENAI_COMPATIBLE_SQL_PROVIDER_KEY=infodive_local",
        "OPENAI_COMPATIBLE_SQL_CONFIG_VERSION=sql-infodive-demo-v1",
        "OPENAI_COMPATIBLE_SQL_MODEL=sql-infodive",
        "Product sends only provider_key/model_key/config_version",
        "Do not run these commands against `/docker/n8n`.",
        "docker compose -f compose.yaml exec langgraph-shadow-test",
        "REBOOT_REQUIRED",
        "GO GATE A - Docker",
        "GO GATE B - Traefik",
        "They are not the target for the current Hostinger VPS",
        "This TEST runbook is not production-ready",
    ]
    for item in required:
        assert item in text


def test_no_real_secret_or_real_langgraph_host_in_artifacts() -> None:
    paths = (RUNBOOK, SYSTEMD, NGINX, DOCKERFILE, COMPOSE, DOCKER_ENV, DOCKERIGNORE)
    combined = "\n".join(_read(path) for path in paths)
    forbidden = [
        "NEXT_PUBLIC_LANGGRAPH_S2S_TOKEN",
        "LANGGRAPH_S2S_TOKEN=abc",
        "LANGGRAPH_SHADOW_DATABASE_DSN=postgres",
        "postgresql://",
        "BEGIN PRIVATE KEY",
        "root@",
        "langgraph-test.srv",
        "supabase.co",
    ]
    for item in forbidden:
        assert item.casefold() not in combined.casefold()


if __name__ == "__main__":
    tests = [
        test_templates_exist,
        test_dockerfile_runtime_is_minimal_and_non_root,
        test_dockerignore_excludes_sensitive_and_local_artifacts,
        test_compose_uses_traefik_network_without_host_ports,
        test_compose_healthcheck_uses_python_stdlib,
        test_docker_env_example_has_only_empty_secrets,
        test_old_nginx_and_systemd_marked_as_alternative,
        test_runbook_covers_real_docker_traefik_contract,
        test_no_real_secret_or_real_langgraph_host_in_artifacts,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")

#!/usr/bin/env python3
"""One-command, fail-closed G1 PostgreSQL readonly/n8n binding rollout.

This utility is intentionally not imported by the agent runtime or check_all's
network-facing code.  It is an operator tool: dry-run is the default; apply
and rollback require a local confirmation and secret prompts.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import json
import os
import secrets
import stat
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen


class RolloutError(RuntimeError):
    """A stopped operation; messages must never contain a secret."""


class HttpClient(Protocol):
    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> Any: ...


class DbConnection(Protocol):
    def execute(self, query: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]: ...
    def close(self) -> None: ...


@dataclass(frozen=True)
class RolloutConfig:
    raw: Mapping[str, Any]

    @property
    def n8n(self) -> Mapping[str, Any]:
        return self.raw["n8n"]


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_config(path: Path) -> RolloutConfig:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RolloutError("configuracao de rollout invalida") from exc
    required = {"rollout_id", "database", "role_name", "schema", "relations", "relation_types", "n8n"}
    if not isinstance(raw, dict) or required - raw.keys() or not isinstance(raw["n8n"], dict):
        raise RolloutError("configuracao de rollout incompleta")
    n8n_required = {"workflow_id", "workflow_name", "expected_node_count", "expected_n8n_version", "webhook_path", "credential_type", "old_credential_id", "binding_node_ids", "connection_fields"}
    if n8n_required - raw["n8n"].keys() or len(raw["relations"]) != 8 or len(raw["n8n"]["binding_node_ids"]) != 2:
        raise RolloutError("configuracao de rollout fora do contrato G1")
    if len(set(raw["relations"])) != len(raw["relations"]):
        raise RolloutError("relacoes duplicadas na configuracao")
    return RolloutConfig(raw)


def scram_verifier(password: str, *, iterations: int = 4096, salt: bytes | None = None) -> str:
    """Make a PostgreSQL SCRAM verifier locally; plaintext never enters SQL."""
    if not password or iterations < 4096:
        raise RolloutError("parametro SCRAM invalido")
    salt = salt or secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()
    encoded = lambda data: base64.b64encode(data).decode("ascii")
    return f"SCRAM-SHA-256${iterations}:{encoded(salt)}${encoded(stored_key)}:{encoded(server_key)}"


def quote_ident(value: str) -> str:
    if not value or "\x00" in value:
        raise RolloutError("identificador invalido")
    return '"' + value.replace('"', '""') + '"'


def require_verified_tls_dsn(dsn: str, expected_database: str, project_ref: str) -> None:
    parsed = urlparse(dsn)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise RolloutError("DSN PostgreSQL invalido")
    if parsed.path.lstrip("/") != expected_database:
        raise RolloutError("database no DSN diverge da configuracao")
    query = parsed.query.lower()
    if "sslmode=verify-full" not in query:
        raise RolloutError("TLS verify-full e obrigatorio")
    if project_ref not in (parsed.username or "") and project_ref not in parsed.hostname:
        raise RolloutError("identidade do projeto nao confere no DSN")


def workflow_projection(workflow: Mapping[str, Any]) -> dict[str, Any]:
    """The documented n8n PUT shape, retaining public workflow state only."""
    keys = ("name", "nodes", "connections", "settings", "staticData", "pinData", "meta", "tags")
    projected = {key: workflow[key] for key in keys if key in workflow}
    if {"name", "nodes", "connections", "settings"} - projected.keys():
        raise RolloutError("workflow nao contem a projecao PUT completa")
    return projected


def workflow_fingerprint(workflow: Mapping[str, Any]) -> str:
    return fingerprint(workflow_projection(workflow))


def validate_workflow(workflow: Mapping[str, Any], config: RolloutConfig, *, require_old_bindings: bool = True) -> None:
    n8n = config.n8n
    if workflow.get("id") != n8n["workflow_id"] or workflow.get("name") != n8n["workflow_name"]:
        raise RolloutError("identidade do workflow diverge")
    if len(workflow.get("nodes", [])) != n8n["expected_node_count"]:
        raise RolloutError("quantidade de nos do workflow diverge")
    if workflow.get("active") is not True or not workflow.get("versionId") or workflow.get("versionId") != workflow.get("activeVersionId"):
        raise RolloutError("workflow publicado nao coincide com sua versao ativa")
    if str(workflow.get("n8nVersion", workflow.get("meta", {}).get("n8nVersion", ""))) != n8n["expected_n8n_version"]:
        raise RolloutError("versao n8n nao homologada")
    nodes = {node.get("id"): node for node in workflow["nodes"] if isinstance(node, dict)}
    if set(n8n["binding_node_ids"]) - nodes.keys():
        raise RolloutError("nos financeiros autorizados ausentes")
    if require_old_bindings:
        old_id = n8n["old_credential_id"]
        old_uses = [node_id for node_id, node in nodes.items() if node.get("credentials", {}).get("postgres", {}).get("id") == old_id]
        if set(old_uses) != set(n8n["binding_node_ids"]):
            raise RolloutError("credencial antiga possui uso fora dos dois nos autorizados")
    if n8n["webhook_path"] not in canonical_json(workflow):
        raise RolloutError("webhook esperado nao foi encontrado no workflow")


def rebind_only(workflow: Mapping[str, Any], config: RolloutConfig, new_credential_id: str, new_credential_name: str) -> dict[str, Any]:
    updated = json.loads(canonical_json(workflow_projection(workflow)))
    binding_ids = set(config.n8n["binding_node_ids"])
    changed = 0
    for node in updated["nodes"]:
        if node.get("id") in binding_ids:
            credentials = node.get("credentials")
            if not isinstance(credentials, dict) or not isinstance(credentials.get("postgres"), dict):
                raise RolloutError("no autorizado sem credencial postgres")
            credentials["postgres"] = {"id": new_credential_id, "name": new_credential_name}
            changed += 1
    if changed != 2:
        raise RolloutError("alteracao nao ficou limitada aos dois nos")
    return updated


def assert_only_two_rebindings(before: Mapping[str, Any], after: Mapping[str, Any], config: RolloutConfig) -> None:
    allowed = set(config.n8n["binding_node_ids"])
    before_nodes = {node["id"]: node for node in workflow_projection(before)["nodes"]}
    after_nodes = {node["id"]: node for node in after["nodes"]}
    if before_nodes.keys() != after_nodes.keys():
        raise RolloutError("conjunto de nos mudou")
    for node_id, node in before_nodes.items():
        candidate = after_nodes[node_id]
        if node_id not in allowed and canonical_json(node) != canonical_json(candidate):
            raise RolloutError("no fora do escopo foi alterado")
    for key in ("connections", "settings", "staticData", "pinData", "meta", "tags"):
        if before.get(key) != after.get(key):
            raise RolloutError(f"{key} foi alterado fora do contrato")


class N8nApi:
    def __init__(self, base_url: str, api_key: str, opener: Callable[..., Any] = urlopen):
        if not base_url.startswith("https://"):
            raise RolloutError("n8n exige URL HTTPS")
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._opener = opener

    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> Any:
        payload = None if body is None else canonical_json(body).encode("utf-8")
        request = Request(self._base + path, data=payload, method=method, headers={
            "X-N8N-API-KEY": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        try:
            with self._opener(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise RolloutError(f"n8n API indisponivel ou resposta invalida em {method} {path}") from exc


def validate_credential_schema(schema: Mapping[str, Any], config: RolloutConfig) -> None:
    n8n = config.n8n
    if schema.get("name") not in {None, n8n["credential_type"]} and schema.get("type") != n8n["credential_type"]:
        raise RolloutError("schema de credencial postgres inesperado")
    serialized = canonical_json(schema)
    for field in n8n["connection_fields"].values():
        if field not in serialized:
            raise RolloutError("schema n8n nao comprova o campo de credencial necessario")


def validate_database(connection: DbConnection, config: RolloutConfig) -> None:
    database, = connection.execute("SELECT current_database()", ())[0]
    if database != config.raw["database"]:
        raise RolloutError("database conectado diverge da configuracao")
    relation_rows = connection.execute(
        "SELECT table_name, table_type FROM information_schema.tables WHERE table_schema = %s", (config.raw["schema"],)
    )
    relation_types = dict(relation_rows)
    missing = [name for name in config.raw["relations"] if relation_types.get(name) not in config.raw["relation_types"]]
    if missing:
        raise RolloutError("relacao permitida ausente ou com tipo nao autorizado")
    public_dml = connection.execute(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname=%s AND c.relname = ANY(%s) AND (has_table_privilege('public', c.oid, 'INSERT') "
        "OR has_table_privilege('public', c.oid, 'UPDATE') OR has_table_privilege('public', c.oid, 'DELETE') "
        "OR has_table_privilege('public', c.oid, 'TRUNCATE'))", (config.raw["schema"], config.raw["relations"])
    )
    if public_dml:
        raise RolloutError("PUBLIC possui DML em relacao do contrato")
    definer = connection.execute(
        "SELECT p.oid::text FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE n.nspname=%s AND p.prosecdef AND has_function_privilege('public', p.oid, 'EXECUTE')", (config.raw["schema"],)
    )
    if definer:
        raise RolloutError("SECURITY DEFINER acessivel por PUBLIC no schema do contrato")


def build_pooler_dsn(template: Mapping[str, Any], config: RolloutConfig, project_ref: str, password: str) -> str:
    fields = config.n8n["connection_fields"]
    host, port, database, ssl = (template[fields[key]] for key in ("host", "port", "database", "ssl"))
    if not isinstance(host, str) or not host or not str(port).isdigit() or database != config.raw["database"]:
        raise RolloutError("template da credencial nao identifica o pooler correto")
    if ssl in {False, "false", "disable", ""}:
        raise RolloutError("template n8n nao exige TLS")
    username = f"{config.raw['role_name']}.{project_ref}"
    return f"postgresql://{quote(username, safe='')}:{quote(password, safe='')}@{host}:{port}/{database}?sslmode=verify-full"


def assert_role_effective_permissions(connection: DbConnection, config: RolloutConfig) -> None:
    role = config.raw["role_name"]
    memberships = connection.execute(
        "SELECT 1 FROM pg_auth_members m JOIN pg_roles member ON member.oid=m.member "
        "WHERE member.rolname=%s", (role,)
    )
    if memberships:
        raise RolloutError("role recebeu membership inesperado")
    sequence_access = connection.execute(
        "SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE c.relkind='S' AND has_sequence_privilege(%s, c.oid, 'USAGE,SELECT,UPDATE') LIMIT 1", (role,)
    )
    if sequence_access:
        raise RolloutError("role recebeu privilegio em sequence")
    external_schema = connection.execute(
        "SELECT 1 FROM pg_namespace n WHERE n.nspname NOT IN ('pg_catalog','information_schema',%s) "
        "AND n.nspname NOT LIKE 'pg_toast%%' AND has_schema_privilege(%s, n.oid, 'USAGE,CREATE') LIMIT 1", (config.raw["schema"], role)
    )
    if external_schema:
        raise RolloutError("role recebeu acesso a schema externo")


def read_private_snapshot(path: Path) -> Mapping[str, Any]:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
        # The live target is Linux. Windows' chmod emulation cannot represent
        # POSIX owner-only ACLs, so do not report a false pass/fail in offline CI.
        if os.name != "nt" and mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise RolloutError("snapshot privado possui permissoes inseguras")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RolloutError("snapshot privado indisponivel") from exc
    if not isinstance(value, dict) or not isinstance(value.get("workflow"), dict) or not isinstance(value.get("credential_id"), str):
        raise RolloutError("snapshot privado invalido")
    return value


def provision_role(connection: DbConnection, config: RolloutConfig, password: str) -> None:
    role = quote_ident(config.raw["role_name"])
    database = quote_ident(config.raw["database"])
    schema = quote_ident(config.raw["schema"])
    exists = connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (config.raw["role_name"],))
    if exists:
        raise RolloutError("role de rollout ja existe")
    verifier = scram_verifier(password).replace("'", "''")
    connection.execute(f"CREATE ROLE {role} LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 5 PASSWORD '{verifier}'")
    connection.execute(f"GRANT CONNECT ON DATABASE {database} TO {role}")
    connection.execute(f"GRANT USAGE ON SCHEMA {schema} TO {role}")
    for relation in config.raw["relations"]:
        connection.execute(f"GRANT SELECT ON TABLE {schema}.{quote_ident(relation)} TO {role}")
    connection.execute(f"ALTER ROLE {role} SET default_transaction_read_only = on")
    connection.execute(f"ALTER ROLE {role} SET statement_timeout = '15s'")
    connection.execute(f"ALTER ROLE {role} SET idle_in_transaction_session_timeout = '15s'")


def verify_role(connection: DbConnection, config: RolloutConfig) -> None:
    current_user, read_only = connection.execute("SELECT current_user, current_setting('transaction_read_only')", ())[0]
    if current_user != config.raw["role_name"] or str(read_only).lower() not in {"on", "true"}:
        raise RolloutError("nova conexao nao confirmou identidade/read-only")
    schema = quote_ident(config.raw["schema"])
    for relation in config.raw["relations"]:
        rows = connection.execute(f"SELECT 1 FROM {schema}.{quote_ident(relation)} LIMIT 1")
        _ = rows
    prohibited = connection.execute(
        "SELECT has_database_privilege(current_user, current_database(), 'CREATE') OR "
        "has_schema_privilege(current_user, %s, 'CREATE')", (config.raw["schema"],)
    )[0][0]
    if prohibited:
        raise RolloutError("role recebeu privilegio de criacao")


def private_snapshot(path: Path, content: Mapping[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    path.write_text(canonical_json(content), encoding="utf-8")
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def confirm(token: str = "APPLY-G1") -> None:
    if input(f"Digite {token} para confirmar: ").strip() != token:
        raise RolloutError("confirmacao nao concedida")


def print_status(role: str, bindings: str, rollback: str) -> None:
    print(f"G1_ROLE={role}")
    print(f"G1_N8N_BINDINGS={bindings}")
    print(f"G1_ROLLBACK={rollback}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_suffix(".json"))
    parser.add_argument("--dry-run", action="store_true", help="default: preflight only")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--n8n-url")
    parser.add_argument("--snapshot", type=Path, default=Path.home() / ".local/state/agente-sql-langgraph/g1-readonly-snapshot.json")
    parser.add_argument("--project-ref", default=os.environ.get("G1_SUPABASE_PROJECT_REF"))
    args = parser.parse_args(argv)
    modes = sum((args.apply, args.verify, args.rollback))
    if modes > 1:
        parser.error("use somente um modo mutavel")
    config = load_config(args.config)
    if not args.n8n_url or not args.project_ref:
        raise RolloutError("n8n-url e project-ref sao obrigatorios no host autorizado")
    api_key = getpass.getpass("n8n API key (nao sera exibida): ")
    api = N8nApi(args.n8n_url, api_key)
    workflow = api.request("GET", f"/api/v1/workflows/{config.n8n['workflow_id']}")
    validate_workflow(workflow, config)
    current_fingerprint = workflow_fingerprint(workflow)
    schema = api.request("GET", "/api/v1/credentials/schema/postgres")
    validate_credential_schema(schema, config)
    if args.rollback:
        confirm("ROLLBACK-G1")
        snapshot = read_private_snapshot(args.snapshot)
        current = api.request("GET", f"/api/v1/workflows/{config.n8n['workflow_id']}")
        validate_workflow(current, config, require_old_bindings=False)
        expected = rebind_only(snapshot["workflow"], config, snapshot["credential_id"], snapshot.get("credential_name", ""))
        if workflow_fingerprint(workflow_projection(current)) != workflow_fingerprint(expected):
            raise RolloutError("rollback bloqueado: houve drift concorrente no workflow")
        restored = workflow_projection(snapshot["workflow"])
        api.request("PUT", f"/api/v1/workflows/{config.n8n['workflow_id']}", restored)
        final = api.request("GET", f"/api/v1/workflows/{config.n8n['workflow_id']}")
        validate_workflow(final, config)
        if workflow_fingerprint(final) != snapshot["fingerprint"]:
            raise RolloutError("rollback nao restaurou o fingerprint original")
        print_status("RETAINED_FOR_REVIEW", "ROLLED_BACK", str(args.snapshot))
        return 0
    if args.verify:
        snapshot = read_private_snapshot(args.snapshot)
        validate_workflow(workflow, config, require_old_bindings=False)
        expected = rebind_only(snapshot["workflow"], config, snapshot["credential_id"], snapshot.get("credential_name", ""))
        if workflow_fingerprint(workflow) != workflow_fingerprint(expected):
            raise RolloutError("verificacao bloqueada: bindings nao conferem com o snapshot")
        print_status("VERIFY_REQUIRES_OPERATOR_DB_ACCESS", "PASS", str(args.snapshot))
        return 0
    if not args.apply:
        dsn = getpass.getpass("DSN PostgreSQL administrador (TLS verify-full, nao sera exibido): ")
        require_verified_tls_dsn(dsn, config.raw["database"], args.project_ref)
        try:
            import psycopg
        except ImportError as exc:
            raise RolloutError("psycopg[binary] nao esta disponivel") from exc
        admin = psycopg.connect(dsn, autocommit=True)
        try:
            validate_database(admin, config)
            if admin.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (config.raw["role_name"],)):
                raise RolloutError("role de rollout ja existe")
        finally:
            admin.close()
        print_status("NOT_APPLIED", f"PREFLIGHT:{current_fingerprint[:12]}", "READY")
        return 0
    confirm()
    dsn = getpass.getpass("DSN PostgreSQL administrador (TLS verify-full, nao sera exibido): ")
    require_verified_tls_dsn(dsn, config.raw["database"], args.project_ref)
    try:
        import psycopg  # local import: no connection in dry-run/tests
    except ImportError as exc:
        raise RolloutError("psycopg[binary] nao esta disponivel") from exc
    admin = psycopg.connect(dsn, autocommit=True)
    password = secrets.token_urlsafe(32)
    try:
        validate_database(admin, config)
        provision_role(admin, config, password)
        assert_role_effective_permissions(admin, config)
        # The only way to obtain the connection template is the authorized n8n API;
        # no existing password is read, copied, or logged.
        old = api.request("GET", f"/api/v1/credentials/{config.n8n['old_credential_id']}")
        fields = config.n8n["connection_fields"]
        data = old.get("data", {})
        template = {fields[key]: data[fields[key]] for key in ("host", "port", "database", "ssl") if fields[key] in data}
        if set(template) != {fields[key] for key in ("host", "port", "database", "ssl")}:
            raise RolloutError("credencial antiga nao forneceu parametros publicos de conexao")
        readonly = psycopg.connect(build_pooler_dsn(template, config, args.project_ref, password), autocommit=True)
        try:
            verify_role(readonly, config)
        finally:
            readonly.close()
        credential_name = f"{config.raw['role_name']}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        credential = api.request("POST", "/api/v1/credentials", {"name": credential_name, "type": config.n8n["credential_type"], "data": {**template, fields["user"]: config.raw["role_name"], fields["password"]: password}})
        credential_id = credential.get("id")
        if not isinstance(credential_id, str) or not credential_id:
            raise RolloutError("n8n nao confirmou criacao da nova credencial")
        refreshed = api.request("GET", f"/api/v1/workflows/{config.n8n['workflow_id']}")
        validate_workflow(refreshed, config)
        if workflow_fingerprint(refreshed) != current_fingerprint:
            raise RolloutError("drift concorrente detectado antes do PUT")
        updated = rebind_only(refreshed, config, credential_id, credential_name)
        assert_only_two_rebindings(refreshed, updated, config)
        private_snapshot(args.snapshot, {"fingerprint": current_fingerprint, "workflow": workflow_projection(refreshed), "credential_id": credential_id, "credential_name": credential_name})
        api.request("PUT", f"/api/v1/workflows/{config.n8n['workflow_id']}", updated)
        verified = api.request("GET", f"/api/v1/workflows/{config.n8n['workflow_id']}")
        validate_workflow(verified, config)
        assert_only_two_rebindings(refreshed, workflow_projection(verified), config)
        if verified.get("activeVersionId") != verified.get("versionId"):
            raise RolloutError("workflow deixou de apontar para a versao publicada")
        print_status(config.raw["role_name"], "PASS", str(args.snapshot))
        return 0
    finally:
        password = ""
        admin.close()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RolloutError as exc:
        print(f"G1_ROLE=NOT_APPLIED\nG1_N8N_BINDINGS=NOT_APPLIED\nG1_ROLLBACK=REQUIRED\nERROR={exc}", file=sys.stderr)
        raise SystemExit(2)

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
import ssl
import subprocess
import re
from urllib.request import build_opener, HTTPSHandler, HTTPRedirectHandler
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen


class RolloutError(RuntimeError):
    """A stopped operation; messages must never contain a secret."""


class HttpClient(Protocol):
    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> Any: ...


class DbConnection(Protocol):
    def execute(self, query: str, params: tuple[Any, ...] = ()) -> Any: ...
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
    if n8n_required - raw["n8n"].keys() or not isinstance(raw["relations"], list) \
            or not raw["relations"] or len(raw["n8n"]["binding_node_ids"]) != 2:
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
    if parse_qs(parsed.query).get("sslmode") != ["verify-full"]:
        raise RolloutError("TLS verify-full e obrigatorio")
    if project_ref not in (parsed.username or "") and project_ref not in parsed.hostname:
        raise RolloutError("identidade do projeto nao confere no DSN")


# Public API PUT contract comes from the n8n 2.4.8 schema already audited by
# scripts/n8n/reconcile_parallel_shadow_candidate.py.  Keep the GET snapshot
# separate from the smaller, strictly editable PUT payload.
API_NODE_FIELDS = frozenset((
    "id", "name", "type", "typeVersion", "position", "parameters",
    "credentials", "webhookId", "disabled", "notes", "notesInFlow",
    "executeOnce", "alwaysOutputData", "retryOnFail", "maxTries",
    "waitBetweenTries", "continueOnFail", "onError",
))
API_NODE_READONLY = frozenset(("createdAt", "updatedAt"))
API_SETTINGS_FIELDS = frozenset((
    "executionOrder", "saveDataSuccessExecution", "saveDataErrorExecution",
    "saveManualExecutions", "saveExecutionProgress", "executionTimeout",
    "errorWorkflow", "timezone", "callerPolicy", "callerIds",
    "timeSavedPerExecution", "availableInMCP",
))
API_SETTINGS_RETAINED = frozenset(("timeSavedMode",))
WORKFLOW_STATE_FIELDS = ("name", "nodes", "connections", "settings",
                         "staticData", "pinData", "meta", "tags")


def _node_for_comparison(node: Mapping[str, Any]) -> dict[str, Any]:
    if set(node) - API_NODE_FIELDS - API_NODE_READONLY:
        raise RolloutError("campos nao homologados em um no n8n")
    return {k: node[k] for k in node if k in API_NODE_FIELDS}


def workflow_projection(workflow: Mapping[str, Any]) -> dict[str, Any]:
    """Strict, editable n8n@2.4.8 public PUT fields; no pinData/meta/tags."""
    if not isinstance(workflow.get("name"), str) or not workflow["name"]:
        raise RolloutError("workflow sem nome")
    if not isinstance(workflow.get("connections"), dict):
        raise RolloutError("workflow sem conexoes")
    settings = workflow.get("settings")
    if not isinstance(settings, dict):
        raise RolloutError("workflow sem settings")
    if set(settings) - API_SETTINGS_FIELDS - API_SETTINGS_RETAINED:
        raise RolloutError("settings do n8n fora do contrato PUT")
    if "timeSavedMode" in settings and settings["timeSavedMode"] not in ("fixed", "dynamic"):
        raise RolloutError("settings retidas nao homologadas")
    nodes = workflow.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise RolloutError("workflow sem nos")
    projected_nodes = []
    for node in nodes:
        if not isinstance(node, dict):
            raise RolloutError("no n8n invalido")
        projected_nodes.append(_node_for_comparison(node))
    out = {
        "name": workflow["name"],
        "nodes": projected_nodes,
        "connections": workflow["connections"],
        "settings": {k: v for k, v in settings.items() if k in API_SETTINGS_FIELDS},
    }
    if "staticData" in workflow:
        if workflow["staticData"] is not None and not isinstance(workflow["staticData"], (dict, str)):
            raise RolloutError("staticData n8n invalido")
        out["staticData"] = workflow["staticData"]
    return out


def workflow_state(workflow: Mapping[str, Any]) -> dict[str, Any]:
    """Stable runtime fields for drift detection, not a public PUT payload."""
    state = {k: workflow[k] for k in WORKFLOW_STATE_FIELDS if k in workflow}
    state["nodes"] = [_node_for_comparison(x) for x in workflow["nodes"]]
    return state


def workflow_fingerprint(workflow: Mapping[str, Any]) -> str:
    return fingerprint(workflow_state(workflow))


def validate_workflow(workflow: Mapping[str, Any], config: RolloutConfig,
                      *, require_old_bindings: bool = True) -> None:
    n8n = config.n8n
    if workflow.get("id") != n8n["workflow_id"] or workflow.get("name") != n8n["workflow_name"]:
        raise RolloutError("identidade do workflow diverge")
    nodes_list = workflow.get("nodes")
    if not isinstance(nodes_list, list) or len(nodes_list) != n8n["expected_node_count"]:
        raise RolloutError("quantidade de nos do workflow diverge")
    if workflow.get("active") is not True or not workflow.get("versionId") or \
            workflow.get("versionId") != workflow.get("activeVersionId"):
        raise RolloutError("workflow publicado nao coincide com versao ativa")
    nodes = {node.get("id"): node for node in nodes_list if isinstance(node, dict)}
    if len(nodes) != len(nodes_list) or set(n8n["binding_node_ids"]) - nodes.keys():
        raise RolloutError("nos nao unicos ou financeiros ausentes")
    if require_old_bindings:
        old_id = n8n["old_credential_id"]
        old_uses = {node_id for node_id, node in nodes.items()
                    if node.get("credentials", {}).get("postgres", {}).get("id") == old_id}
        if old_uses != set(n8n["binding_node_ids"]):
            raise RolloutError("credencial antiga possui uso inesperado")
    # Check the webhook's actual path, not arbitrary JSON text.
    webhook_nodes = [n for n in nodes_list if n.get("type") == "n8n-nodes-base.webhook"
                     and (n.get("parameters", {}).get("path") == n8n["webhook_path"]
                          or n.get("webhookId") == n8n["webhook_path"])]
    if len(webhook_nodes) != 1:
        raise RolloutError("webhook oficial nao identificado")
    # Refuse to mutate when API PUT could discard unrecognized fields.
    workflow_projection(workflow)


def rebind_only(workflow: Mapping[str, Any], config: RolloutConfig,
                new_credential_id: str, new_credential_name: str) -> dict[str, Any]:
    updated = json.loads(canonical_json(workflow_projection(workflow)))
    binding_ids = set(config.n8n["binding_node_ids"])
    changed = 0
    for node in updated["nodes"]:
        if node.get("id") in binding_ids:
            creds = node.get("credentials")
            if not isinstance(creds, dict) or not isinstance(creds.get("postgres"), dict):
                raise RolloutError("no autorizado sem credencial postgres")
            creds["postgres"] = {"id": new_credential_id, "name": new_credential_name}
            changed += 1
    if changed != len(binding_ids):
        raise RolloutError("alteracao fora dos dois nos financeiros")
    return updated


def assert_only_two_rebindings(before: Mapping[str, Any], after: Mapping[str, Any],
                               config: RolloutConfig) -> None:
    """Only the two postgres credential references may differ."""
    allowed = set(config.n8n["binding_node_ids"])
    old_nodes = {n["id"]: _node_for_comparison(n) for n in before["nodes"]}
    new_nodes = {n["id"]: _node_for_comparison(n) for n in after["nodes"]}
    if set(old_nodes) != set(new_nodes):
        raise RolloutError("conjunto de nos mudou")
    for node_id in old_nodes:
        a = json.loads(canonical_json(old_nodes[node_id]))
        b = json.loads(canonical_json(new_nodes[node_id]))
        if node_id in allowed:
            if not isinstance(a.get("credentials", {}).get("postgres"), dict) \
                    or not isinstance(b.get("credentials", {}).get("postgres"), dict):
                raise RolloutError("credential postgres ausente")
            a["credentials"]["postgres"] = b["credentials"]["postgres"]
        if a != b:
            raise RolloutError("alteracao indevida nos parametros de um no")
    for key in ("name", "connections", "settings", "staticData", "pinData", "meta", "tags"):
        if before.get(key) != after.get(key):
            raise RolloutError("drift no workflow fora dos dois bindings")


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


class N8nApi:
    def __init__(self, base_url: str, api_key: str, opener: Any = None):
        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password \
                or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise RolloutError("n8n exige uma base HTTPS sem redirecionamento")
        if not isinstance(api_key, str) or len(api_key.strip()) < 16:
            raise RolloutError("n8n API key ausente")
        self._base = base_url.rstrip("/")
        self._api_key = api_key
        self._opener = opener or build_opener(
            HTTPSHandler(context=ssl.create_default_context()), _NoRedirect()
        )

    def request(self, method: str, path: str, body: Mapping[str, Any] | None = None) -> Any:
        if method not in ("GET", "POST", "PUT") or not path.startswith("/api/v1/") or "//" in path:
            raise RolloutError("request n8n fora do contrato")
        payload = None if body is None else canonical_json(body).encode("utf-8")
        request = Request(self._base + path, data=payload, method=method, headers={
            "X-N8N-API-KEY": self._api_key, "Content-Type": "application/json",
            "Accept": "application/json",
        })
        try:
            with self._opener.open(request, timeout=20) as response:
                if response.geturl() != self._base + path:
                    raise RolloutError("redirect n8n bloqueado")
                result = json.loads(response.read().decode("utf-8"))
            return result
        except Exception as exc:
            # Never echo URLs, request/response JSON, exceptions or credentials.
            raise RolloutError("n8n API indisponivel ou resposta inesperada") from exc


def validate_credential_schema(schema: Mapping[str, Any], config: RolloutConfig) -> None:
    n8n = config.n8n
    if schema.get("name") not in {None, n8n["credential_type"]} and schema.get("type") != n8n["credential_type"]:
        raise RolloutError("schema de credencial postgres inesperado")
    serialized = canonical_json(schema)
    for field in n8n["connection_fields"].values():
        if field not in serialized:
            raise RolloutError("schema n8n nao comprova o campo de credencial necessario")


def validate_database(connection: DbConnection, config: RolloutConfig) -> None:
    row = connection.execute("SELECT current_database()", ()).fetchone()
    if not row or row[0] != config.raw["database"]:
        raise RolloutError("database conectado diverge da configuracao")
    relation_rows = connection.execute(
        "SELECT table_name, table_type FROM information_schema.tables WHERE table_schema=%s",
        (config.raw["schema"],),
    ).fetchall()
    known = dict(relation_rows)
    if any(known.get(x) not in config.raw["relation_types"] for x in config.raw["relations"]):
        raise RolloutError("objeto de leitura ausente ou com tipo nao autorizado")
    # PUBLIC is an ACL grantee (oid 0), not a real pg_roles member named "public".
    public_dml = connection.execute(
        "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "JOIN LATERAL aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) a ON true "
        "WHERE n.nspname=%s AND c.relname=ANY(%s) AND a.grantee=0 "
        "AND a.privilege_type IN ('INSERT','UPDATE','DELETE','TRUNCATE','REFERENCES','TRIGGER')",
        (config.raw["schema"], config.raw["relations"]),
    ).fetchall()
    if public_dml:
        raise RolloutError("PUBLIC possui DML em relacao financeira")
    public_definer = connection.execute(
        "SELECT p.oid::text FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "JOIN LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) a ON true "
        "WHERE n.nspname=%s AND p.prosecdef AND a.grantee=0 AND a.privilege_type='EXECUTE'",
        (config.raw["schema"],),
    ).fetchall()
    if public_definer:
        raise RolloutError("SECURITY DEFINER financeiro executavel por PUBLIC")


def pooler_template_from_admin_dsn(dsn: str, config: RolloutConfig,
                                   project_ref: str) -> dict[str, Any]:
    """No credential secrets fetched from n8n. Use the privately prompted admin DSN."""
    require_verified_tls_dsn(dsn, config.raw["database"], project_ref)
    parsed = urlparse(dsn)
    if not parsed.hostname or not parsed.hostname.endswith(".pooler.supabase.com") \
            or parsed.port not in (5432, 6543):
        raise RolloutError("DSN administrador nao aponta para Supavisor autorizado")
    return {"host": parsed.hostname, "port": parsed.port,
            "database": config.raw["database"], "ssl": "require",
            "ignoreSSLIssues": False}


def build_pooler_dsn(template: Mapping[str, Any], config: RolloutConfig,
                     project_ref: str, password: str) -> str:
    fields = config.n8n["connection_fields"]
    host, port, database, ssl_mode = (
        template[fields[key]] for key in ("host", "port", "database", "ssl")
    )
    if not isinstance(host, str) or not host.endswith(".pooler.supabase.com") \
            or str(port) not in ("5432", "6543") or database != config.raw["database"] \
            or ssl_mode != "require" or template.get("ignoreSSLIssues") is not False:
        raise RolloutError("credencial n8n sem TLS e pooler homologados")
    username = f"{config.raw['role_name']}.{project_ref}"
    return (f"postgresql://{quote(username, safe='')}:{quote(password, safe='')}"
            f"@{host}:{port}/{database}?sslmode=verify-full")


def assert_role_effective_permissions(connection: DbConnection, config: RolloutConfig) -> None:
    """Effective rights, including PUBLIC grants, not just explicit role GRANTs."""
    role = config.raw["role_name"]
    flags = connection.execute(
        "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls, "
        "rolcanlogin, rolinherit FROM pg_roles WHERE rolname=%s", (role,)
    ).fetchone()
    if not flags or any(flags[:5]) or not flags[5] or flags[6]:
        raise RolloutError("role recebeu flags administrativas ou heranca")
    members = connection.execute(
        "SELECT 1 FROM pg_auth_members m JOIN pg_roles r ON r.oid=m.member "
        "WHERE r.rolname=%s LIMIT 1", (role,)
    ).fetchone()
    if members:
        raise RolloutError("role recebeu memberships nao autorizados")
    db_or_schema_create = connection.execute(
        "SELECT has_database_privilege(%s, %s, 'CREATE') OR "
        "has_database_privilege(%s, %s, 'TEMPORARY') OR "
        "EXISTS(SELECT 1 FROM pg_namespace n WHERE n.nspname NOT LIKE 'pg_toast%%' "
        "AND n.nspname NOT LIKE 'pg_temp%%' "
        "AND has_schema_privilege(%s, n.oid, 'CREATE'))",
        (role, config.raw["database"], role, config.raw["database"], role),
    ).fetchone()
    if not db_or_schema_create or db_or_schema_create[0]:
        raise RolloutError("role pode criar objetos ou tabelas temporarias")
    unapproved_read = connection.execute(
        "SELECT c.oid::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE c.relkind IN ('r','v','m','p','f') "
        "AND n.nspname NOT IN ('pg_catalog','information_schema') "
        "AND n.nspname NOT LIKE 'pg_toast%%' AND n.nspname NOT LIKE 'pg_temp%%' "
        "AND has_schema_privilege(%s,n.oid,'USAGE') "
        "AND has_table_privilege(%s,c.oid,'SELECT') "
        "AND NOT (n.nspname=%s AND c.relname=ANY(%s)) LIMIT 1",
        (role, role, config.raw["schema"], config.raw["relations"]),
    ).fetchone()
    if unapproved_read:
        raise RolloutError("role le objetos fora do catalogo permitido")
    writable = connection.execute(
        "SELECT c.oid::text FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE c.relkind IN ('r','v','m','p','f') AND "
        "(has_table_privilege(%s,c.oid,'INSERT') OR "
        "has_table_privilege(%s,c.oid,'UPDATE') OR "
        "has_table_privilege(%s,c.oid,'DELETE') OR "
        "has_table_privilege(%s,c.oid,'TRUNCATE') OR "
        "has_table_privilege(%s,c.oid,'REFERENCES') OR "
        "has_table_privilege(%s,c.oid,'TRIGGER')) LIMIT 1",
        (role, role, role, role, role, role),
    ).fetchone()
    if writable:
        raise RolloutError("role pode modificar uma relacao")
    sequence_access = connection.execute(
        "SELECT 1 FROM pg_class c WHERE c.relkind='S' AND "
        "(has_sequence_privilege(%s,c.oid,'USAGE') OR "
        "has_sequence_privilege(%s,c.oid,'SELECT') OR "
        "has_sequence_privilege(%s,c.oid,'UPDATE')) LIMIT 1",
        (role, role, role),
    ).fetchone()
    if sequence_access:
        raise RolloutError("role possui acesso a sequence")
    definer = connection.execute(
        "SELECT p.oid::text FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
        "WHERE p.prosecdef AND n.nspname NOT IN ('pg_catalog','information_schema') "
        "AND has_schema_privilege(%s,n.oid,'USAGE') "
        "AND has_function_privilege(%s,p.oid,'EXECUTE') LIMIT 1",
        (role, role),
    ).fetchone()
    if definer:
        raise RolloutError("role pode chamar SECURITY DEFINER")


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
    exists = connection.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (config.raw["role_name"],)).fetchone()
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
    row = connection.execute(
        "SELECT current_user, current_database(), current_setting('transaction_read_only')"
    ).fetchone()
    if not row or row != (config.raw["role_name"], config.raw["database"], "on"):
        raise RolloutError("sessao read-only nao confirmou usuario, banco e transacao")
    schema = quote_ident(config.raw["schema"])
    for relation in config.raw["relations"]:
        connection.execute(f"SELECT 1 FROM {schema}.{quote_ident(relation)} LIMIT 1").fetchone()
    # Read-only role can see its own privileges; no DML is ever attempted.
    allowed = connection.execute(
        "SELECT has_database_privilege(current_user, current_database(), 'CREATE') OR "
        "has_database_privilege(current_user, current_database(), 'TEMPORARY') OR "
        "has_schema_privilege(current_user, %s, 'CREATE')", (config.raw["schema"],)
    ).fetchone()
    if not allowed or allowed[0]:
        raise RolloutError("nova sessao tem privilegio de escrita/DDL")


def private_snapshot(path: Path, content: Mapping[str, Any]) -> None:
    """Atomic exclusive backup; must be created before the public n8n PUT."""
    parent = path.parent
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if parent.is_symlink() or path.is_symlink():
        raise RolloutError("snapshot privado nao aceita symlinks")
    parent.chmod(0o700)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RolloutError("snapshot ja existe ou nao pode ser criado") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(canonical_json(content))
            file.flush()
            os.fsync(file.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise


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
            if admin.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (config.raw["role_name"],)).fetchone():
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

#!/usr/bin/env python3
"""Resume a partially applied G1 rollout with an existing, verified SQL role.

Only --recover may mutate. It creates the n8n credential BEFORE rotating the
unbound role password: a 403/400 POST cannot change PostgreSQL credentials.
Any uncertain POST/PUT outcome requires read-only reconciliation, never retry.
"""
from __future__ import annotations

import argparse
import getpass
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from g1_partial_reconcile_readonly import find_n8n_container, inventory_credentials
from g1_readonly_rollout import (
    N8nApi,
    RolloutError,
    _assert_post_apply,
    _role_exists,
    assert_binding_id,
    assert_only_two_rebindings,
    assert_role_effective_permissions,
    build_pooler_dsn,
    confirm,
    load_config,
    pooler_template_from_admin_dsn,
    private_snapshot,
    quote_ident,
    read_n8n_runtime_version,
    rebind_only,
    require_verified_tls_dsn,
    scram_verifier,
    validate_created_credential_response,
    validate_credential_schema,
    validate_database,
    validate_workflow,
    verify_role,
    workflow_fingerprint,
)

STATE = {"role": "NOT_CHECKED", "credential": "NOT_CREATED",
         "bindings": "NOT_CHECKED", "snapshot": "NOT_CREATED"}


def emit_status() -> None:
    print("G1_RESUME_ROLE=" + STATE["role"])
    print("G1_RESUME_CREDENTIAL=" + STATE["credential"])
    print("G1_RESUME_BINDINGS=" + STATE["bindings"])
    print("G1_RESUME_SNAPSHOT=" + STATE["snapshot"])


def _role_settings_complete(admin: Any, role: str) -> None:
    row = admin.execute(
        "SELECT rolconfig,rolconnlimit FROM pg_roles WHERE rolname=%s", (role,),
    ).fetchone()
    if not row or not isinstance(row[0], (list, tuple)) or row[1] != 5:
        raise RolloutError("configuracao da role G1 nao corresponde ao contrato")
    expected = {
        "default_transaction_read_only=on",
        "statement_timeout=15s",
        "idle_in_transaction_session_timeout=15s",
    }
    if not expected.issubset(set(row[0])):
        raise RolloutError("timeouts/read-only da role G1 divergentes")


def preflight_role(admin: Any, config: Any) -> None:
    validate_database(admin, config)
    if not _role_exists(admin, config):
        raise RolloutError("role G1 ausente; nao usar recuperacao de role existente")
    assert_role_effective_permissions(admin, config)
    _role_settings_complete(admin, config.raw["role_name"])
    STATE["role"] = "EXISTING_SELECT_ONLY_VERIFIED"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).with_name("g1_readonly_rollout.json"))
    parser.add_argument("--n8n-url", required=True)
    parser.add_argument("--n8n-container", default="")
    parser.add_argument("--project-ref", required=True)
    parser.add_argument("--expected-fingerprint", default="")
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--snapshot", type=Path, default=Path.home() /
                        ".local/state/agente-sql-langgraph/g1-readonly-snapshot.json")
    args = parser.parse_args(argv)
    config = load_config(args.config)
    if not re.fullmatch(r"[a-z0-9]{12,35}", args.project_ref):
        raise RolloutError("referencia Supabase G1 invalida")
    if args.recover and not re.fullmatch(r"[a-f0-9]{12,64}", args.expected_fingerprint):
        raise RolloutError("recuperacao exige fingerprint observado previamente")
    if args.snapshot.exists() or args.snapshot.is_symlink():
        raise RolloutError("snapshot G1 existente; recuperacao duplicada bloqueada")

    container = find_n8n_container(args.n8n_container)
    read_n8n_runtime_version(config, container)
    count = inventory_credentials(container, config.raw["role_name"], config.n8n["credential_type"])
    print("G1_EXISTING_CREDENTIAL_MATCHES=" + str(count))
    if count:
        raise RolloutError("credencial G1 encontrada; requer reconciliacao antes de recuperar")

    api_key = getpass.getpass("n8n API key (sem eco): ")
    api = N8nApi(args.n8n_url, api_key)
    api_key = ""
    workflow_path = "/api/v1/workflows/" + config.n8n["workflow_id"]
    workflow = api.request("GET", workflow_path)
    validate_workflow(workflow, config)
    assert_binding_id(workflow, config, config.n8n["old_credential_id"])
    starting_fingerprint = workflow_fingerprint(workflow)
    if args.expected_fingerprint and not starting_fingerprint.startswith(args.expected_fingerprint):
        raise RolloutError("fingerprint mudou; suspender recuperacao")
    validate_credential_schema(api.request("GET", "/api/v1/credentials/schema/postgres"), config)
    STATE["bindings"] = "OLD_BINDINGS_CONFIRMED"

    admin_dsn = getpass.getpass("DSN admin PostgreSQL do projeto (sem eco): ")
    require_verified_tls_dsn(admin_dsn, config.raw["database"], args.project_ref)
    template = pooler_template_from_admin_dsn(admin_dsn, config, args.project_ref)
    try:
        import psycopg
    except ImportError as exc:
        raise RolloutError("psycopg indisponivel") from exc

    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        preflight_role(admin, config)
        print("G1_RESUME_PREFLIGHT=PASS")
        print("G1_WORKFLOW_FINGERPRINT=" + starting_fingerprint[:12])
        if not args.recover:
            print("G1_RESUME_MODE=DRY_RUN")
            emit_status()
            return 0

        # A second read-only check catches an intervening credential create.
        if inventory_credentials(container, config.raw["role_name"], config.n8n["credential_type"]):
            raise RolloutError("credencial concorrente encontrada")
        if args.snapshot.exists() or args.snapshot.is_symlink():
            raise RolloutError("snapshot criado durante o preflight")
        current = api.request("GET", workflow_path)
        validate_workflow(current, config)
        if workflow_fingerprint(current) != starting_fingerprint:
            raise RolloutError("workflow mudou durante o preflight")
        confirm("RECOVER-G1")

        password = secrets.token_urlsafe(32)
        connection_fields = config.n8n["connection_fields"]
        credential_data = {connection_fields[key]: template[key]
                           for key in ("host", "port", "database", "ssl")}
        credential_data[connection_fields["allow_unauthorized_certs"]] = False
        credential_data[connection_fields["user"]] = (
            config.raw["role_name"] + "." + args.project_ref
        )
        credential_data[connection_fields["password"]] = password
        new_name = (
            config.raw["role_name"] + "-"
            + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        )

        # No DB mutation has happened yet. If n8n rejects the POST (e.g. 403
        # credential:create scope), the existing role/password stays intact.
        STATE["credential"] = "POST_OUTCOME_UNKNOWN"
        created = api.request("POST", "/api/v1/credentials", {
            "name": new_name,
            "type": config.n8n["credential_type"],
            "data": credential_data,
        })
        new_id = validate_created_credential_response(created, config, new_name)
        STATE["credential"] = "CREATED_UNBOUND"
        if inventory_credentials(container, config.raw["role_name"], config.n8n["credential_type"]) != 1:
            raise RolloutError("inventario pos-POST nao confirma credencial unica")

        # Rotate only the already-verified role, not privileges or any other
        # account. The verifier is SCRAM; plaintext never reaches SQL.
        STATE["role"] = "ROTATION_OUTCOME_UNKNOWN"
        verifier = scram_verifier(password).replace("'", "''")
        with admin.transaction():
            admin.execute(
                f"ALTER ROLE {quote_ident(config.raw['role_name'])} "
                f"PASSWORD '{verifier}'"
            )
            assert_role_effective_permissions(admin, config)
            _role_settings_complete(admin, config.raw["role_name"])
        STATE["role"] = "PASSWORD_ROTATED"

        readonly_dsn = build_pooler_dsn(template, config, args.project_ref, password)
        with psycopg.connect(readonly_dsn, autocommit=True) as readonly:
            verify_role(readonly, config)
        STATE["role"] = "SELECT_ONLY_LOGIN_VERIFIED"

        current = api.request("GET", workflow_path)
        validate_workflow(current, config)
        if workflow_fingerprint(current) != starting_fingerprint:
            raise RolloutError("workflow mudou apos criacao da credencial")
        updated = rebind_only(current, config, new_id, new_name)
        assert_only_two_rebindings(current, updated, config)
        backup = {
            "workflow": current,
            "fingerprint": workflow_fingerprint(current),
            "old_credential_id": config.n8n["old_credential_id"],
            "old_credential_name": config.n8n.get("old_credential_name", "Postgres account 2"),
            "credential_id": new_id,
            "credential_name": new_name,
        }
        private_snapshot(args.snapshot, backup)
        STATE["snapshot"] = "PRIVATE_SNAPSHOT_READY"
        STATE["bindings"] = "PUT_ATTEMPTED_VERIFY_REQUIRED"
        api.request("PUT", workflow_path, updated)
        published = api.request("GET", workflow_path)
        _assert_post_apply(published, backup, config)
        assert_only_two_rebindings(current, published, config)
        STATE["bindings"] = "PASS"
        print("G1_RESUME_MODE=RECOVERED")
        emit_status()
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RolloutError as exc:
        emit_status()
        print("ERROR=" + str(exc), file=sys.stderr)
        raise SystemExit(2)
    except Exception:
        emit_status()
        print("ERROR=OPERACAO_FALHOU_REQUER_RECONCILIACAO", file=sys.stderr)
        raise SystemExit(2)

#!/usr/bin/env python3
"""Recover a historic n8n benchmark, never the agent's semantic context.

Reads a verified encrypted SOURCE archive, selects only two legacy benchmark
relations into a no-network, memory-only PostgreSQL 17 Docker container, then
writes owner-only evaluation evidence. Never runs financial SQL or calls LLMs.
"""
from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time

from scripts.blind_shadow_benchmark import (
    create_blind_manifest, create_freeze_receipt, load_baseline,
)
from scripts.operations.g5_archive_supabase_source import (
    ARCHIVE_DIR, ArchiveBlocked, private_directory,
    validate_archive_passphrase, write_exclusive,
)
from scripts.operations.g5_inspect_encrypted_source import validated_archive
from scripts.operations.g5_restore_isolated_rehearsal import (
    IMAGE_TAG, READY_ATTEMPTS, RESTORE_TIMEOUT, check_container_isolation,
    cleanup_container, consume_restore_stderr, docker_executable, docker_query,
    image_id, isolated_docker_env, isolated_exec_args, isolated_run_args,
)

QUESTION_TABLE = "ai_ducklake_benchmarks"
RESULT_TABLE = "ai_ducklake_benchmark_runs"
EXPECTED_QUESTIONS = 63  # Historic evaluation suite contract, not a generator threshold.
OUTPUT_ROOT = Path("/root/.local/share/agente-sql-langgraph/benchmark-private")
_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
MAX_QUERY_BYTES = 24 * 1024 * 1024


def _archive_manifest(directory: Path, manifest: Path | None, project_ref: str) -> Path:
    if manifest is not None:
        return manifest
    found = sorted(directory.glob("source-" + project_ref + "-*.dump.gpg.manifest.json"))
    if len(found) != 1:
        raise ArchiveBlocked("SOURCE_ARCHIVE_MANIFEST_MISSING_OR_AMBIGUOUS")
    return found[0]


def _read_rows(prefix: list[str], name: str, sql: str) -> list[dict]:
    # Only static templates with carefully constrained legacy identifiers can
    # reach this function. All output stays in process memory, never logs.
    command = prefix + isolated_exec_args(
        name, "psql", "-X", "-A", "-t", "-q", "-v", "ON_ERROR_STOP=1",
        "-h", "/var/run/postgresql", "-U", "postgres", "-d", "postgres",
        "-c", sql,
    )
    try:
        run = subprocess.run(command, env=isolated_docker_env(), check=False,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             timeout=60)
    except (OSError, subprocess.SubprocessError):
        raise ArchiveBlocked("BENCHMARK_PRIVATE_READ_FAILED") from None
    if run.returncode != 0 or len(run.stdout) > MAX_QUERY_BYTES:
        raise ArchiveBlocked("BENCHMARK_PRIVATE_READ_FAILED")
    try:
        return [json.loads(line) for line in run.stdout.decode("utf-8").splitlines()
                if line.strip()]
    except (UnicodeError, ValueError):
        raise ArchiveBlocked("BENCHMARK_ROW_ENCODING_INVALID") from None


def _select_group(question_counts: list[dict], result_groups: list[dict]) -> tuple[str, str]:
    versions = {
        x["version"] for x in question_counts
        if isinstance(x.get("version"), str) and _VERSION.fullmatch(x["version"])
        and x.get("rows") == EXPECTED_QUESTIONS
        and x.get("distinct") == EXPECTED_QUESTIONS
    }
    candidates = [
        g for g in result_groups
        if g.get("version") in versions
        and g.get("rows") == EXPECTED_QUESTIONS
        and g.get("distinct") == EXPECTED_QUESTIONS
        and isinstance(g.get("run_id"), str) and _UUID.fullmatch(g["run_id"])
        and isinstance(g.get("latest"), str) and g["latest"]
    ]
    if not candidates:
        raise ArchiveBlocked("NO_COMPLETE_HISTORIC_63_CASE_RUN")
    candidates.sort(key=lambda g: g["latest"], reverse=True)
    if len(candidates) > 1 and candidates[0]["latest"] == candidates[1]["latest"]:
        raise ArchiveBlocked("HISTORIC_RUN_SELECTION_AMBIGUOUS")
    # Latest complete run by timestamp, never by its score or SQL quality.
    return candidates[0]["version"], candidates[0]["run_id"]


def _documents(version: str, run_id: str, questions: list[dict],
               results: list[dict]) -> tuple[dict, dict, dict, dict]:
    if len(questions) != EXPECTED_QUESTIONS or len(results) != EXPECTED_QUESTIONS:
        raise ArchiveBlocked("HISTORIC_CASE_COUNT_MISMATCH")
    by_id = {}
    for run in results:
        rid = run.get("benchmark_id")
        if rid in by_id or run.get("run_id") != run_id or run.get("agent_version") != version:
            raise ArchiveBlocked("HISTORIC_RESULT_IDENTITY_INVALID")
        by_id[rid] = run
    cases = []
    witness = []
    seen = set()
    for question in questions:
        qid = question.get("id")
        if (not isinstance(qid, int) or qid <= 0 or qid in seen
                or question.get("agent_version") != version
                or question.get("ativo") is not True):
            raise ArchiveBlocked("HISTORIC_QUESTION_IDENTITY_INVALID")
        seen.add(qid)
        run = by_id.get(qid)
        if not run:
            raise ArchiveBlocked("HISTORIC_RESULT_COVERAGE_INVALID")
        text = question.get("pergunta")
        if not isinstance(text, str) or not text.strip() or len(text) > 16000:
            raise ArchiveBlocked("HISTORIC_QUESTION_INVALID")
        item = {"case_id": f"legacy-{qid}", "question": text}
        sql = run.get("sql_gerado")
        if isinstance(sql, str) and sql.strip():
            item["official_sql"] = sql
        intent = run.get("intent_detectada")
        if isinstance(intent, str) and intent.strip():
            item["official_intent"] = intent
        # Historical run IDs belong to the old n8n run; future Shadow run
        # correlation MUST be separate. Do not falsely bind them here.
        cases.append(item)
        witness.append({"benchmark": question, "official_run": run})
    if set(by_id) != seen:
        raise ArchiveBlocked("HISTORIC_RESULT_COVERAGE_INVALID")
    import hashlib
    suite = "legacy63-" + hashlib.sha256((version + "|" + run_id).encode()).hexdigest()[:20]
    baseline = load_baseline({"contract_version": "1", "suite": suite, "cases": cases})
    manifest = create_blind_manifest(baseline)
    freeze = create_freeze_receipt(baseline, manifest)
    legacy_witness = {"source_version": version, "source_run_id": run_id,
                      "benchmark_rows": witness, "evaluation_only": True}
    return baseline, manifest, freeze, legacy_witness


def _restore_selected(prefix: list[str], name: str, archive: Path,
                      password: str) -> None:
    # As in G5: GPG -> anonymous pipe -> networkless pg_restore. The host
    # never holds a plaintext dump and the passphrase never enters argv/env.
    validate_archive_passphrase(password)
    secret_r = secret_w = None
    decrypt = restore = reader = None
    categories: list[str] = []
    try:
        secret_r, secret_w = os.pipe()
        gpg_env = {k: os.environ[k] for k in ("HOME", "PATH", "LANG", "GNUPGHOME")
                   if k in os.environ}
        decrypt = subprocess.Popen(
            ["gpg", "--batch", "--no-tty", "--pinentry-mode", "loopback",
             "--no-symkey-cache", "--passphrase-fd", str(secret_r),
             "--decrypt", str(archive)], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, pass_fds=(secret_r,), env=gpg_env,
        )
        os.close(secret_r)
        secret_r = None
        with os.fdopen(secret_w, "wb") as secret:
            secret_w = None
            secret.write(password.encode("ascii") + b"\n")
        restore = subprocess.Popen(
            prefix + isolated_exec_args(
                name, "pg_restore", "--host=/var/run/postgresql",
                "--username=postgres", "--dbname=postgres", "--no-owner",
                "--no-acl", "--single-transaction", "--exit-on-error",
                "--schema=public", "--table=" + QUESTION_TABLE,
                "--table=" + RESULT_TABLE, interactive=True,
            ), stdin=decrypt.stdout, stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, env=isolated_docker_env(),
        )
        assert decrypt.stdout is not None and restore.stderr is not None
        reader = threading.Thread(target=consume_restore_stderr,
                                  args=(restore.stderr, categories), daemon=True)
        reader.start()
        decrypt.stdout.close()
        try:
            status = restore.wait(timeout=RESTORE_TIMEOUT)
            decrypt_status = decrypt.wait(timeout=30)
        except subprocess.TimeoutExpired:
            raise ArchiveBlocked("BENCHMARK_RESTORE_TIMEOUT") from None
        reader.join(timeout=10)
        if status != 0 or decrypt_status != 0 or reader.is_alive():
            raise ArchiveBlocked("BENCHMARK_SELECTED_RESTORE_FAILED")
    finally:
        for fd in (secret_r, secret_w):
            if fd is not None:
                os.close(fd)
        for proc in (restore, decrypt):
            if proc is not None:
                if proc.poll() is None:
                    proc.kill()
                proc.wait(timeout=10)
        if reader is not None:
            reader.join(timeout=5)
        if restore is not None and restore.stderr is not None:
            restore.stderr.close()


def _recover_memory(archive: Path, password: str, prefix: list[str],
                    image_sha: str) -> tuple[dict, dict, dict, dict]:
    name = "g5-restore-" + secrets.token_hex(8)
    started = False
    cleanup_ok = False
    documents = None
    failure: Exception | None = None
    try:
        launched = docker_query(prefix, isolated_run_args(image_sha, name))
        if launched.returncode != 0:
            raise ArchiveBlocked("BENCHMARK_CONTAINER_START_FAILED")
        started = True
        check_container_isolation(prefix, name, image_sha)
        for _ in range(READY_ATTEMPTS):
            if docker_query(prefix, isolated_exec_args(
                name, "pg_isready", "-h", "/var/run/postgresql", "-U", "postgres"
            )).returncode == 0:
                break
            time.sleep(1)
        else:
            raise ArchiveBlocked("BENCHMARK_POSTGRES_NOT_READY")
        _restore_selected(prefix, name, archive, password)
        relations = _read_rows(prefix, name, (
            "SELECT row_to_json(t)::text FROM ("
            "SELECT c.relname, c.relkind FROM pg_catalog.pg_class c "
            "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relname IN ('" + QUESTION_TABLE +
            "','" + RESULT_TABLE + "')) t ORDER BY relname;"
        ))
        if {r.get("relname") for r in relations if r.get("relkind") in ("r", "p")} != {
            QUESTION_TABLE, RESULT_TABLE
        } or len(relations) != 2:
            raise ArchiveBlocked("BENCHMARK_ARCHIVE_TABLES_UNAVAILABLE")
        questions_meta = _read_rows(prefix, name, (
            "SELECT json_build_object('version',agent_version,'rows',count(*),"
            "'distinct',count(DISTINCT id))::text FROM public." + QUESTION_TABLE +
            " WHERE ativo IS TRUE GROUP BY agent_version;"
        ))
        groups = _read_rows(prefix, name, (
            "SELECT json_build_object('version',agent_version,'run_id',run_id,"
            "'rows',count(*),'distinct',count(DISTINCT benchmark_id),"
            "'latest',max(criado_em))::text FROM public." + RESULT_TABLE +
            " GROUP BY agent_version,run_id ORDER BY max(criado_em) DESC LIMIT 1001;"
        ))
        if len(groups) > 1000:
            raise ArchiveBlocked("BENCHMARK_HISTORIC_RUN_GROUP_LIMIT")
        version, run_id = _select_group(questions_meta, groups)
        # Version and UUID are grammar-validated before interpolation.
        q_sql = ("SELECT row_to_json(b)::text FROM public." + QUESTION_TABLE +
                 " b WHERE b.ativo IS TRUE AND b.agent_version='" + version +
                 "' ORDER BY b.prioridade,b.id LIMIT 64;")
        r_sql = ("SELECT row_to_json(r)::text FROM public." + RESULT_TABLE +
                 " r WHERE r.agent_version='" + version +
                 "' AND r.run_id='" + run_id + "'::uuid ORDER BY benchmark_id LIMIT 64;")
        questions = _read_rows(prefix, name, q_sql)
        results = _read_rows(prefix, name, r_sql)
        documents = _documents(version, run_id, questions, results)
    except Exception as exc:
        failure = exc
    finally:
        if started:
            try:
                cleanup_ok = cleanup_container(prefix, name)
            except Exception:
                cleanup_ok = False
        else:
            cleanup_ok = True
    if not cleanup_ok:
        raise ArchiveBlocked("BENCHMARK_ISOLATED_CLEANUP_UNVERIFIED")
    if failure:
        if isinstance(failure, ArchiveBlocked):
            raise failure
        raise ArchiveBlocked("BENCHMARK_RECOVERY_FAILED") from None
    if documents is None:
        raise ArchiveBlocked("BENCHMARK_DOCUMENTS_MISSING")
    return documents


def _save(documents: tuple[dict, dict, dict, dict]) -> Path:
    import hashlib
    private_directory(OUTPUT_ROOT, create=True)
    freeze = documents[2]
    folder = OUTPUT_ROOT / ("legacy63-" + hashlib.sha256(
        freeze["baseline_fingerprint"].encode("ascii")
    ).hexdigest()[:20])
    if folder.exists() or folder.is_symlink():
        raise ArchiveBlocked("BENCHMARK_SNAPSHOT_ALREADY_EXISTS")
    folder.mkdir(mode=0o700)
    try:
        for filename, doc in zip(("official-baseline.json", "questions-only.json",
                                  "freeze-receipt.json", "historical-witness.json"), documents):
            blob = (json.dumps(doc, sort_keys=True, ensure_ascii=False, indent=2)
                    + "\n").encode("utf-8")
            write_exclusive(folder / filename, blob)
        return folder
    except Exception:
        for name in ("official-baseline.json", "questions-only.json",
                     "freeze-receipt.json", "historical-witness.json"):
            (folder / name).unlink(missing_ok=True)
        folder.rmdir()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true")
    mode.add_argument("--recover", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--source-project-ref", required=True)
    args = parser.parse_args()
    print("BENCHMARK_MODE=" + ("RECOVER" if args.recover else "PLAN"))
    try:
        if os.geteuid() != 0:
            raise ArchiveBlocked("ROOT_LOCAL_RUNTIME_REQUIRED")
        if (os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION", "false").lower() == "true"
                or os.environ.get("SHADOW_FULL_FLOW_ALLOW_LIVE_LLM", "false").lower() == "true"):
            raise ArchiveBlocked("LIVE_EXECUTION_FLAGS_FORBIDDEN")
        manifest = _archive_manifest(ARCHIVE_DIR, args.manifest, args.source_project_ref)
        archive = validated_archive(manifest, args.source_project_ref, ARCHIVE_DIR)
        prefix = docker_executable()
        pinned = image_id(prefix, IMAGE_TAG)
        print("BENCHMARK_ARCHIVE_DIGEST=PASS")
        print("BENCHMARK_IMAGE_PINNED=PASS")
        if args.plan:
            print("BENCHMARK_PLAN=PASS")
            print("BENCHMARK_SOURCE_DATA_READ=false")
            return 0
        if not sys.stdin.isatty():
            raise ArchiveBlocked("LOCAL_TTY_REQUIRED")
        if input("Digite RECOVER-LEGACY-BENCHMARK-63: ") != "RECOVER-LEGACY-BENCHMARK-63":
            raise ArchiveBlocked("BENCHMARK_OPERATOR_CONFIRMATION_REQUIRED")
        password = getpass.getpass("Senha do arquivo G5 (sem eco): ")
        documents = _recover_memory(archive, password, prefix, pinned)
        folder = _save(documents)
        print("BENCHMARK_RECOVERY=PASS")
        print("BENCHMARK_CASES=" + str(len(documents[0]["cases"])))
        print("BENCHMARK_OFFICIAL_SQL_PRESENT=" + str(sum(
            bool(c.get("official_sql")) for c in documents[0]["cases"])))
        print("BENCHMARK_ISOLATED_CONTAINER_CLEANUP=PASS")
        print("BENCHMARK_OUTPUT_PRIVATE=PASS")
        print("BENCHMARK_OUTPUT_DIR=" + str(folder))
        print("BENCHMARK_FINANCIAL_SQL_EXECUTED=false")
        print("BENCHMARK_LLM_CALLS=0")
        return 0
    except Exception as exc:
        reason = str(exc) if isinstance(exc, ArchiveBlocked) else "UNCLASSIFIED"
        print("BENCHMARK_RECOVERY=BLOCKED")
        print("BENCHMARK_BLOCK_REASON=" + reason)
        print("BENCHMARK_FINANCIAL_SQL_EXECUTED=false")
        print("BENCHMARK_LLM_CALLS=0")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
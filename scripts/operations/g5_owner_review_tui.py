"""Private, resumable owner review of G5/P3 originals (NEVER an approval).

Sensitive source fields are rendered ONLY to /dev/tty. Standard output
contains sanitized progress counts, never source values. The operator can
prepare individual, unapproved mappings, not activate them. The compiler
and separate independent approval stage remain required.

No customer-specific accounting logic, SQL, network or LLM dependencies.
"""
from __future__ import annotations

import argparse
import copy
try:
    import fcntl
except ImportError:  # Windows CI imports the module but review stays POSIX-only.
    fcntl = None
import json
import os
import re
import stat
import sys
import tempfile
import unicodedata
from pathlib import Path
from collections.abc import Mapping
from typing import TextIO

from scripts.operations.g5_financial_crosswalk_review import (
    FinancialReviewBlocked, draft,
)
from scripts.operations.g5_financial_crosswalk_review_cli import private_bytes, private_json
from scripts.operations.g5_financial_review_worksheet_offline import build_review_templates
from scripts.operations.g5_p3_original_physical_worklist import physical_index
from scripts.operations.g5_targeted_financial_review_offline import (
    ReviewBlocked, select_verified_seal, verify_decrypted_packet,
    write_private_once,
)

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}\Z")


def deny(reason: str) -> None:
    raise FinancialReviewBlocked(reason)


def safe_terminal(value: object) -> str:
    """No terminal escapes, bidi overrides or control characters from source."""
    raw = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    return "".join(
        c if c in ("\n", "\t") or unicodedata.category(c) not in ("Cc", "Cf") else "?"
        for c in raw
    )


def private_file_location(path: Path, private_dir: Path, *, exists: bool) -> None:
    if (
        os.name != "posix"
        or not path.is_absolute() or not private_dir.is_absolute()
        or path.parent != private_dir
        or private_dir.is_symlink()
        or stat.S_IMODE(private_dir.stat().st_mode) != 0o700
        or private_dir.stat().st_uid != os.geteuid()
        or path.is_symlink()
    ):
        deny("G5_OWNER_REVIEW_PRIVATE_PATH_REQUIRED")
    if exists:
        if not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
            deny("G5_OWNER_REVIEW_PRIVATE_FILE_REQUIRED")
    elif path.exists():
        deny("G5_OWNER_REVIEW_REFUSE_OVERWRITE")


def atomic_private_update(path: Path, private_dir: Path, payload: dict) -> None:
    private_file_location(path, private_dir, exists=path.exists())
    blob = (json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n").encode()
    if not 0 < len(blob) <= 5_000_000:
        deny("G5_OWNER_REVIEW_OUTPUT_INVALID")
    fd, name = tempfile.mkstemp(prefix=".owner-draft-", dir=str(private_dir))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(blob)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
        dirfd = os.open(str(private_dir), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def initial_state(packet: Mapping, packet_sha: str, p3_bytes: bytes) -> dict:
    workbook, remap = build_review_templates(
        packet=packet, packet_sha256=packet_sha,
        financial_draft=draft(packet, packet_sha), p3_bytes=p3_bytes,
    )
    return {
        "contract": "g5-owner-private-review-session-v1",
        "packet_plaintext_sha256": packet_sha,
        "p3_snapshot_sha256": packet["origin"]["p3_snapshot_sha256"],
        "actions": 0,
        "workbook": workbook,
        "remap": remap,
    }


def validate_state(state: dict, template: dict, physical: Mapping) -> None:
    if (
        not isinstance(state, dict) or set(state) != set(template)
        or state.get("contract") != template["contract"]
        or state.get("packet_plaintext_sha256") != template["packet_plaintext_sha256"]
        or state.get("p3_snapshot_sha256") != template["p3_snapshot_sha256"]
        or type(state.get("actions")) is not int or not 0 <= state["actions"] <= 1000000
    ):
        deny("G5_OWNER_SESSION_SOURCE_OR_VERSION_CHANGED")
    work, base = state.get("workbook"), template["workbook"]
    remap, base_remap = state.get("remap"), template["remap"]
    if (
        not isinstance(work, Mapping) or set(work) != set(base)
        or not isinstance(remap, Mapping) or set(remap) != set(base_remap)
    ):
        deny("G5_OWNER_SESSION_SCHEMA_CHANGED")
    editable = {"tenant_id", "semantic_agent_version", "context_fingerprint",
                "reviewer_id", "prepared_by", "financial_source_rows",
                "physical_binding_decisions"}
    remap_editable = {"tenant_id", "semantic_agent_version",
                      "reviewer_id", "prepared_by", "remaps"}
    if any(work[k] != base[k] for k in base if k not in editable):
        deny("G5_OWNER_SESSION_WORKBOOK_PROVENANCE_CHANGED")
    if any(remap[k] != base_remap[k] for k in base_remap if k not in remap_editable):
        deny("G5_OWNER_SESSION_REMAP_PROVENANCE_CHANGED")
    for name in ("tenant_id", "semantic_agent_version", "reviewer_id", "prepared_by"):
        value = work[name]
        if value is not None and (not isinstance(value, str) or not _ID.fullmatch(value)):
            deny("G5_OWNER_SESSION_IDENTITY_INVALID")
        if value != remap[name]:
            deny("G5_OWNER_SESSION_IDENTITIES_DIFFER")
    if (work["context_fingerprint"] is not None and (
        not isinstance(work["context_fingerprint"], str)
        or not re.fullmatch("[0-9a-f]{64}", work["context_fingerprint"]))):
        deny("G5_OWNER_SESSION_FINGERPRINT_INVALID")
    if not isinstance(work["financial_source_rows"], list) or len(work["financial_source_rows"]) != len(base["financial_source_rows"]):
        deny("G5_OWNER_SESSION_FINANCIAL_ROWS_INCOMPLETE")
    for row, original in zip(work["financial_source_rows"], base["financial_source_rows"]):
        if (
            not isinstance(row, Mapping)
            or set(row) != set(original)
            or any(row[k] != original[k] for k in ("collection", "source_row_sha256"))
            or row["classification"] not in ("UNRESOLVED", "STRUCTURAL", "FORBIDDEN")
            or not isinstance(row["destinations"], list)
            or len(row["destinations"]) > 24
        ):
            deny("G5_OWNER_SESSION_FINANCIAL_ROW_INVALID")
        if row["classification"] in ("UNRESOLVED", "STRUCTURAL") and row["destinations"]:
            deny("G5_OWNER_SESSION_DESTINATION_NOT_ALLOWED")
        seen = set()
        for target in row["destinations"]:
            if (
                not isinstance(target, Mapping) or set(target) != {"collection", "index"}
                or not isinstance(target["collection"], str)
                or not _IDENT.fullmatch(target["collection"])
                or type(target["index"]) is not int or target["index"] < 0
                or (target["collection"], target["index"]) in seen
            ):
                deny("G5_OWNER_SESSION_INVALID_CATALOG_TARGET")
            seen.add((target["collection"], target["index"]))
    choices = work["physical_binding_decisions"]
    rationales = remap["remaps"]
    if (
        not isinstance(choices, list)
        or not isinstance(rationales, list)
        or len(choices) != len(base["physical_binding_decisions"])
        or len(rationales) != len(base_remap["remaps"])
    ):
        deny("G5_OWNER_SESSION_PHYSICAL_ROWS_INCOMPLETE")
    for decision, template_decision, reason, template_reason in zip(
        choices, base["physical_binding_decisions"],
        rationales, base_remap["remaps"],
    ):
        if (
            not isinstance(decision, Mapping) or set(decision) != set(template_decision)
            or not isinstance(reason, Mapping) or set(reason) != set(template_reason)
            or any(decision[k] != template_decision[k] for k in template_decision
                   if k not in ("qualified_table", "target_column"))
            or any(reason[k] != template_reason[k] for k in template_reason
                   if k not in ("qualified_table", "target_column", "review_rationale"))
            or decision["qualified_table"] != reason["qualified_table"]
            or decision["target_column"] != reason["target_column"]
        ):
            deny("G5_OWNER_SESSION_PHYSICAL_ORIGIN_CHANGED")
        chosen = decision["qualified_table"]
        col = decision["target_column"]
        if chosen is None:
            if col is not None or reason["review_rationale"] is not None:
                deny("G5_OWNER_SESSION_INCOMPLETE_PHYSICAL_SELECTION")
            continue
        if (
            not isinstance(chosen, str)
            or chosen.count(".") != 1 or tuple(chosen.split(".")) not in physical
            or (decision["source_column"] is None and col is not None)
            or (decision["source_column"] is not None
                and (not isinstance(col, str) or col not in physical[tuple(chosen.split("."))]))
        ):
            deny("G5_OWNER_SESSION_PHYSICAL_TARGET_UNVERIFIED")
        old_schema, old_table, old_col = (
            decision["source_schema"], decision["source_table"], decision["source_column"]
        )
        schema, table = chosen.split(".")
        remapped = table != old_table or (
            old_schema is not None and schema != old_schema
        ) or col != old_col
        rationale = reason["review_rationale"]
        if remapped and (not isinstance(rationale, str) or not rationale.strip()
                         or len(rationale) > 4096):
            deny("G5_OWNER_SESSION_REMAP_JUSTIFICATION_REQUIRED")
        if not remapped and rationale is not None:
            deny("G5_OWNER_SESSION_UNNECESSARY_JUSTIFICATION")


def counts(state: dict) -> dict[str, int]:
    work = state["workbook"]
    financial = work["financial_source_rows"]
    physical = work["physical_binding_decisions"]
    return {
        "financial_total": len(financial),
        "financial_classified": sum(r["classification"] != "UNRESOLVED" for r in financial),
        "financial_destinations_needed": sum(
            r["classification"] == "FORBIDDEN" and not r["destinations"] for r in financial
        ),
        "physical_total": len(physical),
        "physical_selected": sum(r["qualified_table"] is not None for r in physical),
        "session_actions": state["actions"],
    }


def _line(tty: TextIO, prompt: str) -> str:
    tty.write(prompt)
    tty.flush()
    answer = tty.readline()
    if not answer:
        return "q"
    return answer.strip()


def edit_financial(state: dict, packet: Mapping, index: int, tty: TextIO) -> bool:
    rows = state["workbook"]["financial_source_rows"]
    if not 0 <= index < len(rows):
        return False
    row = rows[index]
    source = [
        item["source_fields_unreviewed"]
        for item in packet["collections"][row["collection"]]
        if item["source_row_sha256"] == row["source_row_sha256"]
    ]
    if len(source) != 1:
        deny("G5_OWNER_SOURCE_RECORD_MISSING")
    data = safe_terminal(source[0])
    if len(data) > 16000:
        tty.write("Registro muito longo: consultar dossie privado; nenhuma decisao gravada.\n")
        return False
    tty.write(f"\n[FINANCEIRO {index+1}/{len(rows)}] {row['collection']} SHA {row['source_row_sha256']}\n")
    tty.write(data + "\n")
    tty.write("Atual: "+row["classification"]+" | "+safe_terminal(row["destinations"])+"\n")
    choice = _line(tty, "S=estrutura generica, B=negocio no catalogo, ?=pendente: ").lower()
    if choice not in ("s", "b", "?"):
        return False
    if choice == "s":
        classification, destinations = "STRUCTURAL", []
    elif choice == "?":
        classification, destinations = "UNRESOLVED", []
    else:
        classification = "FORBIDDEN"
        raw = _line(tty, "Destinos CANONICOS revisados (colecao:indice, separados por virgula; vazio=pendente): ")
        destinations = []
        if raw:
            for entry in raw.split(","):
                parts = entry.strip().rsplit(":", 1)
                if len(parts) != 2 or not _IDENT.fullmatch(parts[0]) or not parts[1].isdigit():
                    tty.write("Formato de destino invalido. Nenhuma decisao gravada.\n")
                    return False
                destinations.append({"collection": parts[0], "index": int(parts[1])})
    row["classification"] = classification
    row["destinations"] = destinations
    return True


def edit_physical(state: dict, physical: Mapping, index: int, tty: TextIO) -> bool:
    decisions = state["workbook"]["physical_binding_decisions"]
    reasons = state["remap"]["remaps"]
    if not 0 <= index < len(decisions):
        return False
    row = decisions[index]
    tty.write(f"\n[FISICO {index+1}/{len(decisions)}] {row['collection']} SHA {row['source_row_sha256']}\n")
    tty.write("Origem legada (nao aprovada): " + safe_terminal({
        "schema":row["source_schema"],"table":row["source_table"],"column":row["source_column"]
    })+"\n")
    ordered = sorted(physical.items())
    for i, ((schema, table), cols) in enumerate(ordered, 1):
        label = "MESMO_NOME" if table == row["source_table"] else "RENOMEADA?"
        tty.write(f"{i:02d} {schema}.{table} ({len(cols)} colunas) {label}\n")
    selected = _line(tty, "Escolha numero da tabela P3 fisica, ?=pendente: ")
    if selected == "?":
        row["qualified_table"], row["target_column"] = None, None
        reasons[index]["qualified_table"] = None
        reasons[index]["target_column"] = None
        reasons[index]["review_rationale"] = None
        return True
    if not selected.isdigit() or not 1 <= int(selected) <= len(ordered):
        return False
    (schema, table), columns = ordered[int(selected)-1]
    chosen_col = None
    if row["source_column"] is not None:
        col_names = sorted(columns)
        for i, name in enumerate(col_names, 1):
            tty.write(f"  {i:02d} {name} [{columns[name]}]"
                      + (" MESMO_NOME" if name == row["source_column"] else "") + "\n")
        selected_col = _line(tty, "Escolha numero da COLUNA P3: ")
        if not selected_col.isdigit() or not 1 <= int(selected_col) <= len(col_names):
            return False
        chosen_col = col_names[int(selected_col)-1]
    remapped = (
        table != row["source_table"]
        or (row["source_schema"] is not None and schema != row["source_schema"])
        or chosen_col != row["source_column"]
    )
    reason = None
    if remapped:
        reason = _line(tty, "Justificativa FINANCEIRA original da mudanca (minimo uma frase): ")
        if not reason.strip() or reason.lower() == "q" or len(reason) > 4096:
            tty.write("Justificativa ausente ou invalida; nenhuma decisao gravada.\n")
            return False
    name = schema + "." + table
    row["qualified_table"], row["target_column"] = name, chosen_col
    reasons[index]["qualified_table"] = name
    reasons[index]["target_column"] = chosen_col
    reasons[index]["review_rationale"] = reason
    return True


def set_identity(state: dict, tty: TextIO) -> bool:
    fields = (
        "tenant_id", "semantic_agent_version", "prepared_by",
        "reviewer_id", "context_fingerprint"
    )
    data = {}
    for key in fields:
        entry = _line(tty, key+" (valor aprovado; vazio=pendente): ")
        if entry and (
            (key == "context_fingerprint" and not re.fullmatch("[0-9a-f]{64}",entry))
            or (key != "context_fingerprint" and not _ID.fullmatch(entry))
        ):
            return False
        data[key] = entry or None
    if data["prepared_by"] == data["reviewer_id"] and data["prepared_by"] is not None:
        tty.write("Autor da proposta e autoridade revisora precisam ser diferentes.\n")
        return False
    for key, val in data.items():
        state["workbook"][key] = val
        if key in state["remap"]:
            state["remap"][key] = val
    return True


def review_loop(*, state: dict, template: dict, packet: Mapping, physical: Mapping,
                private_dir: Path, session_path: Path, tty: TextIO) -> None:
    tty.write("G5/P3 — REVISAO PRIVADA DO RESPONSAVEL. NUNCA E APROVACAO OU EXECUCAO.\n")
    tty.write("f = proximo financeiro | p = proximo fisico | f N / p N = item especifico\n")
    tty.write("i = identidade | s = progresso | e = exportar UNSIGNED completo | q = sair\n")
    while True:
        choice = _line(tty, "G5 revisao> ").strip().lower()
        if choice in ("q", "sair", "exit"):
            return
        if choice in ("s", "status"):
            tty.write(safe_terminal(counts(state))+"\n")
            continue
        proposed = copy.deepcopy(state)
        if choice == "i":
            modified = set_identity(proposed, tty)
        elif choice == "e":
            try:
                export_unsigned_draft(
                    state=state, template=template, physical=physical,
                    private_dir=private_dir,
                    output_workbook=private_dir / "g5-owner-completed-worksheet-unsigned.json",
                    output_remap=private_dir / "g5-owner-completed-remap-unsigned.json",
                )
            except FinancialReviewBlocked:
                tty.write("EXPORT_BLOCKED: ha pendencias ou arquivos de saida existentes.\n")
            else:
                tty.write("EXPORT_UNSIGNED=PASS; ACCOUNTING_APPROVED=false; SQL_EXECUTED=false\n")
            continue
        else:
            parts = choice.split()
            if len(parts) == 1 and parts[0] in ("f", "p"):
                if parts[0] == "f":
                    wanted = next((
                        i for i, row in enumerate(state["workbook"]["financial_source_rows"])
                        if row["classification"] == "UNRESOLVED"
                        or (row["classification"] == "FORBIDDEN" and not row["destinations"])
                    ), None)
                else:
                    wanted = next((
                        i for i, row in enumerate(state["workbook"]["physical_binding_decisions"])
                        if row["qualified_table"] is None
                    ), None)
                if wanted is None:
                    tty.write("Nenhum item pendente nesta etapa.\n")
                    continue
                parts.append(str(wanted+1))
            if len(parts)!=2 or parts[0] not in ("f","p") or not parts[1].isdigit():
                tty.write("Comando nao reconhecido. Exemplo: f; p; f 1; p 1; e; s; i; q.\n")
                continue
            idx = int(parts[1])-1
            modified = (
                edit_financial(proposed, packet, idx, tty) if parts[0]=="f"
                else edit_physical(proposed, physical, idx, tty)
            )
        if not modified:
            tty.write("Sem alteracoes.\n")
            continue
        proposed["actions"] += 1
        try:
            validate_state(proposed, template, physical)
        except FinancialReviewBlocked:
            tty.write("Entrada rejeitada pelo contrato. Nada foi gravado.\n")
            continue
        atomic_private_update(session_path, private_dir, proposed)
        state.clear()
        state.update(proposed)
        tty.write("DECISAO_GRAVADA_EM_DRAFT; APROVACAO=false; SQL_EXECUTED=false\n")


def export_unsigned_draft(*, state: dict, template: dict,
                          physical: Mapping, private_dir: Path,
                          output_workbook: Path, output_remap: Path) -> None:
    """Two human-filled but still UNSIGNED artifacts for external validation."""
    validate_state(state, template, physical)
    totals = counts(state)
    workbook = state["workbook"]
    if (
        totals["financial_total"] != totals["financial_classified"]
        or totals["financial_destinations_needed"] != 0
        or totals["physical_total"] != totals["physical_selected"]
        or not all(workbook.get(k) is not None for k in (
            "tenant_id", "semantic_agent_version", "prepared_by",
            "reviewer_id", "context_fingerprint"
        ))
        or workbook["prepared_by"] == workbook["reviewer_id"]
    ):
        deny("G5_OWNER_REVIEW_INCOMPLETE_NO_EXPORT")
    if output_workbook == output_remap:
        deny("G5_OWNER_EXPORT_COLLISION")
    for path in (output_workbook, output_remap):
        private_file_location(path, private_dir, exists=False)
    # Not an approval: the compiler will verify a real tenant context and
    # the independent financial signer has a separate approval gate.
    assert workbook["accounting_approved"] is False
    assert workbook["financial_sql_executed"] is False
    from scripts.operations.g5_targeted_financial_review_offline import write_private_once
    for path, value in ((output_workbook, workbook), (output_remap, state["remap"])):
        raw = (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")) + "\n").encode()
        write_private_once(path, raw)


def open_review(*, manifest_path: Path, source_version: str,
                packet_path: Path, p3_path: Path, session_path: Path,
                tty: TextIO | None = None, status_only: bool = False,
                export_paths: tuple[Path, Path] | None = None) -> dict:
    if os.name != "posix":
        deny("G5_OWNER_REVIEW_POSIX_ONLY")
    private_dir = packet_path.parent
    private_file_location(packet_path, private_dir, exists=True)
    private_file_location(p3_path, private_dir, exists=True)
    private_file_location(session_path, private_dir, exists=session_path.exists())
    seal = select_verified_seal(private_json(manifest_path), source_version)
    packet, report = verify_decrypted_packet(private_bytes(packet_path), seal)
    p3_bytes = private_bytes(p3_path, 3_000_000)
    physical, _rows = physical_index(p3_bytes, packet["origin"]["p3_snapshot_sha256"])
    base = initial_state(packet, report["packet_plaintext_sha256"], p3_bytes)
    if session_path.exists():
        state = private_json(session_path)
    else:
        state = base
    validate_state(state, base, physical)
    if export_paths is not None:
        if not status_only or not session_path.exists():
            deny("G5_OWNER_REVIEW_EXPORT_SESSION_REQUIRED")
        export_unsigned_draft(
            state=state, template=base, physical=physical, private_dir=private_dir,
            output_workbook=export_paths[0], output_remap=export_paths[1],
        )
    if not status_only:
        if tty is None:
            deny("G5_OWNER_REVIEW_INTERACTIVE_TTY_REQUIRED")
        lock_path = private_dir / ".g5-owner-review.lock"
        if lock_path.is_symlink():
            deny("G5_OWNER_REVIEW_LOCK_SYMLINK")
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT |
                     getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            if stat.S_IMODE(os.fstat(fd).st_mode) != 0o600:
                deny("G5_OWNER_REVIEW_LOCK_PERMISSIONS")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Re-read after claiming lock to prevent stale parallel overwrite.
            if session_path.exists():
                state = private_json(session_path)
                validate_state(state, base, physical)
            review_loop(
                state=state, template=base, packet=packet, physical=physical,
                private_dir=private_dir, session_path=session_path, tty=tty,
            )
        finally:
            os.close(fd)
    return counts(state)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--source-version-sha256", required=True)
    parser.add_argument("--packet-file", required=True, type=Path)
    parser.add_argument("--p3-file", required=True, type=Path)
    parser.add_argument("--session-file", required=True, type=Path)
    parser.add_argument("--status", action="store_true",
                        help="Only summary counts; never output source values")
    parser.add_argument("--export-workbook", type=Path,
                        help="Write UNSIGNED completed reviewer workbook 0600")
    parser.add_argument("--export-remap", type=Path,
                        help="Write UNSIGNED completed physical rationale draft 0600")
    args = parser.parse_args(argv)
    try:
        if args.status or args.export_workbook or args.export_remap:
            if bool(args.export_workbook) != bool(args.export_remap):
                deny("G5_OWNER_EXPORT_REQUIRES_BOTH_FILES")
            totals = open_review(
                manifest_path=args.manifest,
                source_version=args.source_version_sha256,
                packet_path=args.packet_file, p3_path=args.p3_file,
                session_path=args.session_file, status_only=True,
                export_paths=(args.export_workbook, args.export_remap)
                if args.export_workbook else None,
            )
        else:
            if not sys.stdin.isatty() or not os.path.exists("/dev/tty"):
                deny("G5_OWNER_REVIEW_REAL_TTY_REQUIRED")
            with open("/dev/tty", "r+", encoding="utf-8") as tty:
                totals = open_review(
                    manifest_path=args.manifest,
                    source_version=args.source_version_sha256,
                    packet_path=args.packet_file, p3_path=args.p3_file,
                    session_path=args.session_file, tty=tty,
                )
    except (OSError, FinancialReviewBlocked, ReviewBlocked, ValueError, BlockingIOError):
        print("G5_OWNER_REVIEW=BLOCKED")
        print("CONTEXT_ACTIVATED=false")
        print("SQL_EXECUTED=false")
        return 2
    print("G5_OWNER_REVIEW=DRAFT_ONLY")
    for key, number in sorted(totals.items()):
        print("G5_"+key.upper()+"="+str(number))
    print("ACCOUNTING_APPROVED=false")
    print("CONTEXT_ACTIVATED=false")
    print("SQL_EXECUTED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

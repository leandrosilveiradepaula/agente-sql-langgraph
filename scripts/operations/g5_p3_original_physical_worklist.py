"""G5/P3 original metadata: root-only, non-approved human physical worklist.

No financial interpretation, automatic table selection, SQL or LLM use.
The P3 bytes must exactly match the original G5 packet SHA.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import stat
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

from scripts.operations.g5_financial_crosswalk_review import (
    FinancialReviewBlocked, source_ids,
)
from scripts.operations.g5_financial_crosswalk_review_cli import (
    private_bytes, private_json,
)
from scripts.operations.g5_physical_source_evidence import original_physical_reference
from scripts.operations.g5_targeted_financial_review_offline import (
    ReviewBlocked, select_verified_seal, verify_decrypted_packet,
    write_private_once,
)

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}\Z")


def deny(reason: str) -> None:
    raise FinancialReviewBlocked(reason)


def physical_index(payload: bytes, expected_sha: str):
    if hashlib.sha256(payload).hexdigest() != expected_sha:
        deny("G5_P3_ORIGINAL_HASH_MISMATCH")
    try:
        metadata = json.loads(payload)
    except (TypeError, ValueError, UnicodeError):
        deny("G5_P3_JSON_INVALID")
    if (
        not isinstance(metadata, dict)
        or metadata.get("contract") != "p3-metadata-snapshot-v1"
        or metadata.get("sql_executed") is not False
        or metadata.get("llm_calls") != 0
        or not isinstance(metadata.get("physical"), list)
        or not 0 < len(metadata["physical"]) <= 100_000
    ):
        deny("G5_P3_METADATA_INVALID")
    tables = {}
    for record in metadata["physical"]:
        if (
            not isinstance(record, list) or len(record) != 4
            or not all(isinstance(x, str) and x for x in record)
            or not all(_IDENT.fullmatch(x) for x in record[:3])
        ):
            deny("G5_P3_COLUMN_FORMAT_INVALID")
        schema, table, column, dtype = record
        cols = tables.setdefault((schema, table), {})
        if column in cols and cols[column] != dtype:
            deny("G5_P3_CONFLICTING_COLUMN_TYPE")
        cols[column] = dtype
    return tables, len(metadata["physical"])


def make_worklist(packet: Mapping, p3_bytes: bytes):
    origin = packet.get("origin", {})
    expected_sha = origin.get("p3_snapshot_sha256")
    if not isinstance(expected_sha, str) or not re.fullmatch("[0-9a-f]{64}", expected_sha):
        deny("G5_P3_SOURCE_DIGEST_INVALID")
    tables, physical_rows = physical_index(p3_bytes, expected_sha)
    hints = packet.get("physical_identifier_hints_unapproved")
    if not isinstance(hints, list) or not hints or len(hints) > 50_000:
        deny("G5_P3_SOURCE_HINTS_INVALID")
    known = source_ids(packet)
    seen = set()
    rows = []
    totals = Counter()
    for hint in hints:
        if (
            not isinstance(hint, Mapping)
            or hint.get("accounting_equivalence") != "NOT_ATTESTED"
            or hint.get("source_version_sha256") != origin.get("source_version_sha256")
        ):
            deny("G5_P3_HINT_UNTRUSTED")
        key = (hint.get("collection"), hint.get("source_record_sha256"))
        if key not in known or key in seen:
            deny("G5_P3_HINT_NOT_AN_ORIGINAL_ROW")
        seen.add(key)
        old_schema, old_table, old_column = original_physical_reference(packet, hint)
        options = []
        for (schema, table), columns in sorted(tables.items()):
            if table != old_table:
                continue
            options.append({
                "qualified_table": schema + "." + table,
                "original_schema_name_equal": schema == old_schema if old_schema else None,
                "legacy_column_name_exists": old_column in columns if old_column else None,
                "legacy_column_type_if_present": columns.get(old_column) if old_column else None,
                "physical_columns_unapproved": [
                    {"name": name, "data_type": dtype}
                    for name, dtype in sorted(columns.items())
                ],
            })
        matching_cols = sum(
            v["legacy_column_name_exists"] is True for v in options
        )
        if old_column:
            totals["alias_or_column_refs"] += 1
            if matching_cols == 0:
                status = "NO_SAME_NAMED_PHYSICAL_COLUMN"
                totals["columns_missing_exact_name"] += 1
            elif matching_cols == 1:
                status = "ONE_LITERAL_COLUMN_CANDIDATE_UNAPPROVED"
                totals["columns_one_literal_match"] += 1
            else:
                status = "MULTIPLE_LITERAL_COLUMN_CANDIDATES_UNAPPROVED"
                totals["columns_multiple_literal_matches"] += 1
        else:
            totals["table_only_refs"] += 1
            if len(options) == 0:
                status = "NO_SAME_NAMED_PHYSICAL_TABLE"
            elif len(options) == 1:
                status = "ONE_LITERAL_TABLE_CANDIDATE_UNAPPROVED"
                totals["tables_one_literal_match"] += 1
            else:
                status = "MULTIPLE_LITERAL_TABLE_CANDIDATES_UNAPPROVED"
                totals["tables_multiple_literal_matches"] += 1
        if old_schema and not any(
            option["original_schema_name_equal"] is True for option in options
        ):
            totals["original_schema_missing"] += 1
        rows.append({
            "collection": key[0],
            "source_row_sha256": key[1],
            "legacy_schema": old_schema,
            "legacy_table": old_table,
            "legacy_column": old_column,
            "literal_match_status": status,
            "physical_options_not_selected": options,
            "approved": False,
            "selected_physical_binding": None,
            "financial_remap_evidence_sha256": None,
        })
    rows.sort(key=lambda r: (r["collection"], r["source_row_sha256"]))
    totals["original_hint_rows"] = len(rows)
    document = {
        "contract": "g5-p3-original-private-physical-worklist-v1",
        "source_version_sha256": origin["source_version_sha256"],
        "p3_snapshot_sha256": expected_sha,
        "p3_physical_row_count": physical_rows,
        "p3_physical_table_count": len(tables),
        "status": "UNAPPROVED_HUMAN_REVIEW_ONLY",
        "financial_meaning_approved": False,
        "physical_binding_approved": False,
        "generator_context_eligible": False,
        "sql_executed": False,
        "benchmark_used": False,
        "physical_references": rows,
    }
    return document, totals


def html_view(worklist: Mapping, totals: Counter) -> bytes:
    escape = lambda x: html.escape(str(x), quote=True)
    sections = ["""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>G5 P3 - lista privada NAO APROVADA</title>
<style>body{font:14px/1.5 sans-serif;max-width:1060px;margin:30px auto;padding:0 15px}
section{border:1px solid #cbd5e1;border-radius:10px;padding:16px;margin:12px 0}
strong{color:#92400e}dl{display:grid;grid-template-columns:230px 1fr}
dt,dd{border-bottom:1px solid #ddd;padding:4px;margin:0;overflow-wrap:anywhere}
summary{cursor:pointer}code{overflow-wrap:anywhere}</style></head><body>
<h1>Vinculos fisicos G5/P3 - para revisao humana</h1>
<strong>NAO APROVADO. As opcoes sao correspondencias LITERAIS, nao mapeamentos financeiros.</strong>
"""]
    sections.append("<p>G5 " + escape(worklist["source_version_sha256"])
      + " / P3 " + escape(worklist["p3_snapshot_sha256"])
      + ". Linhas fisicas: " + str(worklist["p3_physical_row_count"])
      + " / Referencias: " + str(totals["original_hint_rows"]) + ".</p>")
    for number, record in enumerate(worklist["physical_references"], 1):
        sections.append("<section><h2>Referencia "+str(number)+"</h2><p>SHA fonte: <code>"
          +escape(record["source_row_sha256"])+"</code></p><p><strong>"
          +escape(record["literal_match_status"])+"</strong> - nunca selecionado</p><dl>")
        for key in ("collection","legacy_schema","legacy_table","legacy_column"):
            sections.append("<dt>"+escape(key)+"</dt><dd>"+escape(record[key])+"</dd>")
        sections.append("</dl>")
        for opt in record["physical_options_not_selected"]:
            sections.append("<details><summary>Opcao nao aprovada: "
             +escape(opt["qualified_table"])+"</summary><dl>")
            for column in opt["physical_columns_unapproved"]:
                sections.append("<dt>"+escape(column["name"])+"</dt><dd>"
                 +escape(column["data_type"])+"</dd>")
            sections.append("</dl></details>")
        sections.append("</section>")
    sections.append("<strong>0 aprovacoes; 0 SQL financeira; 0 contexto ativado.</strong></body></html>")
    result="".join(sections).encode("utf-8")
    if len(result)>8_000_000: deny("G5_P3_HTML_TOO_LARGE")
    return result


def build(manifest: Path, version: str, packet_path: Path, p3_path: Path,
          output_json: Path, output_html: Path) -> Counter:
    if os.name != "posix":
        deny("G5_P3_POSIX_PRIVATE_ONLY")
    seal=select_verified_seal(private_json(manifest),version)
    packet,_=verify_decrypted_packet(private_bytes(packet_path),seal)
    document,counts=make_worklist(packet,private_bytes(p3_path,3_000_000))
    if output_json==output_html: deny("G5_P3_OUTPUT_PATH_COLLISION")
    for path in (output_json,output_html):
        if (not path.is_absolute() or path.exists() or path.is_symlink()
            or path.parent!=packet_path.parent
            or stat.S_IMODE(path.parent.stat().st_mode)!=0o700
            or path.parent.stat().st_uid!=os.geteuid()):
            deny("G5_P3_PRIVATE_OUTPUT_REQUIRED")
    data=(json.dumps(document,sort_keys=True,ensure_ascii=True,separators=(",",":"))+"\n").encode()
    if len(data)>4_000_000: deny("G5_P3_JSON_TOO_LARGE")
    view=html_view(document,counts)
    write_private_once(output_json,data)
    write_private_once(output_html,view)
    return counts


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("manifest","version-sha256","packet-file","p3-file","output-json","output-html"):
        parser.add_argument("--"+name,required=True)
    args=parser.parse_args(argv)
    try:
        counts=build(Path(args.manifest),args.version_sha256,
            Path(args.packet_file),Path(args.p3_file),
            Path(args.output_json),Path(args.output_html))
    except (FinancialReviewBlocked,ReviewBlocked,OSError,ValueError,TypeError):
        print("G5_P3_WORKLIST=BLOCKED")
        print("SQL_EXECUTED=false")
        return 2
    print("G5_P3_WORKLIST=PASS")
    for key,value in sorted(counts.items()):
        print("G5_P3_"+key.upper()+"="+str(value))
    print("G5_P3_FINANCIAL_APPROVED=false")
    print("G5_P3_PHYSICAL_BINDINGS_APPROVED=false")
    print("LANGGRAPH_CONTEXT_ACTIVATED=false")
    print("SQL_EXECUTED=false")
    return 0


if __name__=="__main__":
    raise SystemExit(main())

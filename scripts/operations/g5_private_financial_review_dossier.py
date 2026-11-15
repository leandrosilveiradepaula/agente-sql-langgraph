"""Offline, private human review of already authenticated, UNAPPROVED G5 source.

This tool never selects accounting meaning, creates context, generates SQL,
activates a source, or emits source values to stdout or remote services.
"""
from __future__ import annotations

import argparse
import html
import os
import stat
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

from scripts.operations.g5_financial_crosswalk_review import (
    FinancialReviewBlocked, draft, source_ids,
)
from scripts.operations.g5_financial_crosswalk_review_cli import (
    private_bytes, private_json,
)
from scripts.operations.g5_targeted_financial_review_offline import (
    ReviewBlocked, select_verified_seal, verify_decrypted_packet,
    write_private_once,
)


def denied(code: str) -> None:
    raise FinancialReviewBlocked(code)


def review_rows(packet: Mapping, review: Mapping, sha: str) -> tuple[list[dict], Counter]:
    """Every source SHA must have an unmodified PENDING review row."""
    if review != draft(packet, sha):
        denied("G5_REVIEW_DRAFT_MODIFIED_OR_APPROVED")
    expected = source_ids(packet)
    hints = packet.get("physical_identifier_hints_unapproved", [])
    if not isinstance(hints, list) or len(hints) > len(expected):
        denied("G5_PHYSICAL_HINTS_INVALID")
    lookup = {}
    for item in hints:
        if not isinstance(item, Mapping):
            denied("G5_PHYSICAL_HINT_INVALID")
        key = (item.get("collection"), item.get("source_record_sha256"))
        if key not in expected or key in lookup:
            denied("G5_PHYSICAL_HINT_UNKNOWN_OR_DUPLICATED")
        lookup[key] = dict(item)

    rows = []
    counts = Counter()
    for collection, records in packet["collections"].items():
        for item in records:
            key = (collection, item["source_row_sha256"])
            fields = item.get("source_fields_unreviewed")
            if not isinstance(fields, Mapping) or not all(
                isinstance(k, str)
                and (v is None or isinstance(v, (str, int, float, bool)))
                for k, v in fields.items()
            ):
                denied("G5_SOURCE_FIELD_FORMAT_UNSAFE")
            hint = lookup.get(key)
            status = str(hint.get("candidate_status", "UNKNOWN")) if hint else "NO_HINT"
            counts["pending"] += 1
            if hint:
                counts["physical_hint_rows"] += 1
                if status == "AMBIGUOUS_TABLE_NAME":
                    counts["ambiguous_physical_tables"] += 1
                if hint.get("column_status") == "COLUMN_UNRESOLVED":
                    counts["unresolved_physical_columns"] += 1
            rows.append({
                "collection": collection, "sha": item["source_row_sha256"],
                "fields": dict(fields), "hint": hint, "status": status,
            })
    rows.sort(key=lambda r: (r["collection"], r["sha"]))
    if len(rows) != len(expected) or counts["pending"] != len(review["rows"]):
        denied("G5_REVIEW_ROW_COVERAGE_MISMATCH")
    return rows, counts


def safe(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_html(rows: list[dict], counts: Counter, source_sha: str, packet_sha: str) -> bytes:
    """Static local HTML with CSP and escaped original values; no JavaScript."""
    parts = ["""<!doctype html><html lang="pt-BR"><head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Revisão financeira G5 — NÃO APROVADA</title>
<style>
body{font:15px/1.5 system-ui,sans-serif;max-width:1040px;margin:32px auto;padding:0 20px;background:#f8fafc;color:#1e293b}
h1{font-size:1.7rem}h2{font-size:1.1rem;margin:4px 0}
section,.summary{background:#fff;border:1px solid #cbd5e1;border-radius:10px;margin:14px 0;padding:16px}
.summary{border-color:#d97706}.warning{color:#92400e;font-weight:700}
code,dd{overflow-wrap:anywhere}
dl{display:grid;grid-template-columns:minmax(160px,210px) 1fr;gap:0 12px}
dt,dd{margin:0;padding:7px 0;border-bottom:1px solid #e2e8f0;white-space:pre-wrap}
dt{font-weight:600;color:#475569}details{margin:12px 0}summary{cursor:pointer}
</style></head><body><h1>Revisão de registros financeiros — arquivo privado</h1>
<p class="warning">NÃO APROVADO · NÃO IMPORTAR · NÃO USAR COMO CONTEXTO LLM · NÃO EXECUTAR SQL</p>
"""]
    parts.append(
        '<div class="summary"><p>Versão original: <code>' + safe(source_sha)
        + '</code></p><p>Hash do plaintext: <code>' + safe(packet_sha)
        + '</code></p><p>Registros aguardando homologação: <b>'
        + str(counts["pending"]) + '</b> · Tabelas físicas ambíguas no P3: <b>'
        + str(counts["ambiguous_physical_tables"])
        + '</b> · Colunas físicas não resolvidas: <b>'
        + str(counts["unresolved_physical_columns"])
        + '</b></p><p>O vínculo com o catálogo legado não comprova a tabela física,'
        ' tipos, grãos ou significado contábil. Todos os registros são PENDING.</p></div>'
    )
    for number, row in enumerate(rows, 1):
        parts.append(
            '<section><h2>Registro ' + str(number) + '/' + str(len(rows))
            + '</h2><p>Coleção: <code>' + safe(row["collection"])
            + '</code> · Fonte SHA: <code>' + safe(row["sha"])
            + '</code></p><p class="warning">Classificação: UNRESOLVED '
            '· Sem atestação financeira · Vínculo P3: ' + safe(row["status"])
            + '</p>'
        )
        if row["hint"] is not None:
            parts.append("<details><summary>Indícios P3 NÃO aprovados</summary><dl>")
            for key, val in sorted(row["hint"].items()):
                parts.append("<dt>" + safe(key) + "</dt><dd>" + safe(val) + "</dd>")
            parts.append("</dl></details>")
        parts.append("<details open><summary>Campos originais confidenciais</summary><dl>")
        for key, val in sorted(row["fields"].items()):
            parts.append("<dt>" + safe(key) + "</dt><dd>" + safe(val) + "</dd>")
        parts.append("</dl></details></section>")
    parts.append('<p class="warning">FIM DO PACOTE · 0 APROVAÇÕES CONTÁBEIS</p></body></html>')
    content = "".join(parts).encode("utf-8")
    if not 0 < len(content) <= 8_000_000:
        denied("G5_DOSSIER_SIZE_INVALID")
    return content


def build(
    *, manifest_path: Path, version_sha256: str,
    packet_path: Path, review_path: Path, output_path: Path,
) -> dict[str, int]:
    seal = select_verified_seal(private_json(manifest_path), version_sha256)
    packet, report = verify_decrypted_packet(private_bytes(packet_path), seal)
    rows, counts = review_rows(
        packet, private_json(review_path), report["packet_plaintext_sha256"],
    )
    if (
        not output_path.is_absolute() or output_path.exists()
        or output_path.is_symlink() or output_path.parent != packet_path.parent
        or stat.S_IMODE(output_path.parent.stat().st_mode) != 0o700
        or output_path.parent.stat().st_uid != os.geteuid()
    ):
        denied("G5_DOSSIER_OUTPUT_LOCATION_UNSAFE")
    write_private_once(
        output_path, render_html(
            rows, counts, seal["source_version_sha256"],
            report["packet_plaintext_sha256"],
        ),
    )
    return {
        "records": len(rows),
        "physical_hint_rows": counts["physical_hint_rows"],
        "ambiguous_physical_tables": counts["ambiguous_physical_tables"],
        "unresolved_physical_columns": counts["unresolved_physical_columns"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--version-sha256", required=True)
    parser.add_argument("--packet-file", required=True, type=Path)
    parser.add_argument("--review-file", required=True, type=Path)
    parser.add_argument("--output-html", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = build(
            manifest_path=args.manifest,
            version_sha256=args.version_sha256,
            packet_path=args.packet_file, review_path=args.review_file,
            output_path=args.output_html,
        )
    except (FinancialReviewBlocked, ReviewBlocked, OSError, ValueError, TypeError):
        print("G5_PRIVATE_REVIEW_DOSSIER=BLOCKED")
        return 2
    print("G5_PRIVATE_REVIEW_DOSSIER=PASS")
    for key, count in sorted(result.items()):
        print("G5_" + key.upper() + "=" + str(count))
    print("G5_ACCOUNTING_APPROVED=false")
    print("G5_GENERATOR_CONTEXT_USED=false")
    print("SQL_EXECUTED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

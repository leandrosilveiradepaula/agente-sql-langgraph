"""No-approval, data-private reviewer worksheet proof (synthetic fixtures)."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import stat
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.operations.g5_financial_crosswalk_review import (
    FinancialReviewBlocked, draft,
)
from scripts.operations.g5_financial_review_worksheet_offline import (
    build_review_templates, prepare, main,
)
from testar_g5_p3_original_physical_worklist import inputs
from testar_g5_physical_source_evidence import fixture


def reject(func):
    try:
        func()
    except (FinancialReviewBlocked, OSError, ValueError):
        return
    raise AssertionError("An incomplete or unsafe human-review worksheet was accepted.")


def test_source_bound_worksheet_for_two_distinct_tenants_contains_no_approvals():
    for alternate in (False, True):
        packet, sha, review, _context, _bytes, _seal, p3 = fixture(other=alternate)
        original = draft(packet, sha)
        worksheet, remap = build_review_templates(
            packet=packet, packet_sha256=sha,
            financial_draft=original, p3_bytes=p3,
        )
        assert worksheet["original_financial_row_count"] == 1
        assert worksheet["original_physical_binding_count"] == 1
        assert worksheet["accounting_approved"] is False
        assert worksheet["financial_sql_executed"] is False
        assert worksheet["independent_financial_signature_file"] is None
        assert worksheet["physical_binding_decisions"][0]["qualified_table"] is None
        assert worksheet["financial_source_rows"][0]["classification"] == "UNRESOLVED"
        assert remap["contract"] == "g5-physical-remap-evidence-DRAFT-unapproved-v1"
        assert remap["remaps"][0]["target_column"] is None
        assert remap["remaps"][0]["review_rationale"] is None
        assert remap["prepared_by"] is None
        assert "source_fields_unreviewed" not in json.dumps(worksheet)
        assert "source_fields_unreviewed" not in json.dumps(remap)


def test_77_financial_rows_require_exact_unique_source_coverage():
    packet, _sha, _review, _context, _bytes, _seal, p3 = fixture()
    sample=packet["collections"]["semantic_rules"][0]
    packet["collections"]["semantic_rules"]=[
        {"source_row_sha256":format(i+1,"064x"),
         "source_fields_unreviewed":dict(sample["source_fields_unreviewed"])}
        for i in range(77)
    ]
    # First row SHA changes, so the physical hint must remain source-pinned.
    packet["physical_identifier_hints_unapproved"][0]["source_record_sha256"] = format(1, "064x")
    packet["row_counts"]["semantic_rules"] = 77
    sha=hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()
    worksheet, evidence = build_review_templates(
        packet=packet,packet_sha256=sha,
        financial_draft=draft(packet,sha),p3_bytes=p3,
    )
    assert len(worksheet["financial_source_rows"]) == 77
    assert len(worksheet["physical_binding_decisions"]) == 1
    assert len(evidence["remaps"]) == 1
    assert all(r["classification"] == "UNRESOLVED"
               for r in worksheet["financial_source_rows"])


def test_stale_review_and_p3_do_not_generate_templates():
    packet,sha,_review,_context,_raw,_seal,p3=fixture()
    old=draft(packet,sha)
    changed=deepcopy(old)
    changed["rows"][0]["classification"]="STRUCTURAL"
    reject(lambda: build_review_templates(
        packet=packet,packet_sha256=sha,financial_draft=changed,p3_bytes=p3,
    ))
    reject(lambda: build_review_templates(
        packet=packet,packet_sha256=sha,financial_draft=old,p3_bytes=p3+b" ",
    ))


def private_files(root: Path, *, alternate=False):
    files,packet,p3=inputs(root,alternate=alternate)
    sha=hashlib.sha256(files["packet"].read_bytes()).hexdigest()
    review=root/"financial-crosswalk-review-draft.json"
    review.write_text(json.dumps(draft(packet,sha)))
    review.chmod(0o600)
    files["financial_draft"]=review
    files["workbook"]=root/"worksheet-private.json"
    files["remap"]=root/"remap-evidence-private.json"
    return files


def generate(files):
    return prepare(
        manifest=files["manifest"],
        source_version=files["version"],
        packet_path=files["packet"],
        p3_path=files["p3"],
        financial_draft_path=files["financial_draft"],
        workbook_out=files["workbook"],
        remap_out=files["remap"],
    )


def test_private_posix_files_no_overwrite_or_original_values():
    if os.name!="posix":return
    for alt in (False,True):
        with TemporaryDirectory() as name:
            files=private_files(Path(name),alternate=alt)
            assert generate(files)=={
                "original_source_rows":1,
                "original_physical_binding_rows":1,
            }
            for key in ("workbook","remap"):
                assert stat.S_IMODE(files[key].stat().st_mode)==0o600
                data=json.loads(files[key].read_bytes())
                assert data["tenant_id"] is None
                assert data["reviewer_id"] is None
            reject(lambda:generate(files))


def test_cli_and_symlink_fail_closed_no_raw_stdout():
    if os.name!="posix":return
    with TemporaryDirectory() as name:
        files=private_files(Path(name))
        data=io.StringIO()
        with contextlib.redirect_stdout(data):
            result=main([
                "--manifest",str(files["manifest"]),
                "--source-version-sha256",files["version"],
                "--packet-file",str(files["packet"]),
                "--p3-file",str(files["p3"]),
                "--financial-draft-file",str(files["financial_draft"]),
                "--output-workbook",str(files["workbook"]),
                "--output-remap-draft",str(files["remap"]),
            ])
        assert result==0
        assert "G5_PRIVATE_REVIEW_WORKSHEETS=PASS" in data.getvalue()
        for forbidden in ("value", "schema_test", "synthetic_terms"):
            assert forbidden not in data.getvalue()
    with TemporaryDirectory() as name:
        files=private_files(Path(name))
        fake=Path(name)/"packet-link.json"
        fake.symlink_to(files["packet"])
        files["packet"]=fake
        reject(lambda:generate(files))
        assert not files["workbook"].exists()


def test_non_posix_creation_is_denied():
    if os.name=="posix":return
    with TemporaryDirectory() as name:
        files=private_files(Path(name))
        reject(lambda:generate(files))


if __name__=="__main__":
    tests=sorted((n,f) for n,f in globals().items()
                 if n.startswith("test_") and callable(f))
    for name,fn in tests:
        fn()
        print("PASS",name)
    print("TOTAL_TESTS",len(tests))

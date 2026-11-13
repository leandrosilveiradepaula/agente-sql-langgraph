"""Synthetic-only, fail-closed checks for sealed G5/P3 physical review worklist."""
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

from scripts.operations.g5_financial_crosswalk_review import FinancialReviewBlocked
from scripts.operations.g5_p3_original_physical_worklist import (
    build, html_view, make_worklist,
)
from testar_g5_physical_source_evidence import fixture
from testar_g5_targeted_financial_review_offline import fixture as manifest_fixture


def denied(fn):
    try:
        fn()
    except (FinancialReviewBlocked, ValueError):
        return
    raise AssertionError("untrusted G5/P3 worklist accepted")


def inputs(root: Path, *, alternate: bool = False):
    packet, _sha, _review, _ctx, _raw, seal, p3 = fixture(other=alternate)
    raw = (json.dumps(packet, sort_keys=True, separators=(",", ":"))+"\n").encode()
    _, _, manifest = manifest_fixture(alternate=alternate)
    assert seal["source_version_sha256"]==manifest["versions"][0]["source_version_sha256"]
    seal["plaintext_sha256"] = hashlib.sha256(raw).hexdigest()
    manifest["versions"][0]["plaintext_sha256"] = seal["plaintext_sha256"]
    root.chmod(0o700)
    files={}
    for name, content in (
        ("manifest",json.dumps(manifest).encode()),
        ("packet",raw),
        ("p3",p3),
    ):
        target=root/(name+".json")
        target.write_bytes(content)
        target.chmod(0o600)
        files[name]=target
    files["version"]=seal["source_version_sha256"]
    files["output_json"]=root/"physical-worklist.json"
    files["output_html"]=root/"physical-worklist.html"
    return files,packet,p3


def write(files):
    return build(
        files["manifest"], files["version"], files["packet"],
        files["p3"], files["output_json"], files["output_html"],
    )


def test_two_distinct_tenants_get_all_literal_candidates_but_no_approval():
    for other in (False,True):
        packet,_,_,_,_,_,p3=fixture(other=other)
        worklist,counts=make_worklist(packet,p3)
        assert counts["original_hint_rows"]==1
        assert counts["alias_or_column_refs"]==1
        assert counts["columns_multiple_literal_matches"]==1
        assert worklist["physical_binding_approved"] is False
        assert worklist["financial_meaning_approved"] is False
        assert worklist["generator_context_eligible"] is False
        assert worklist["sql_executed"] is False
        assert len(worklist["physical_references"][0]["physical_options_not_selected"])==2


def test_original_packet_and_metadata_digest_cannot_be_replaced():
    packet,_,_,_,_,_,p3=fixture()
    denied(lambda: make_worklist(packet,p3+b" "))
    changed=deepcopy(packet)
    changed["physical_identifier_hints_unapproved"][0]["source_record_sha256"]="0"*64
    denied(lambda: make_worklist(changed,p3))
    changed=deepcopy(packet)
    changed["physical_identifier_hints_unapproved"] *= 2
    denied(lambda: make_worklist(changed,p3))


def test_type_conflict_is_rejected_even_if_p3_digest_is_updated():
    packet,_,_,_,_,_,p3=fixture()
    changed=json.loads(p3)
    changed["physical"].append([
        *changed["physical"][0][:3], "incompatible_type"
    ])
    raw=json.dumps(changed,sort_keys=True).encode()
    packet["origin"]["p3_snapshot_sha256"]=hashlib.sha256(raw).hexdigest()
    denied(lambda: make_worklist(packet,raw))


def test_alias_with_no_exact_column_is_never_auto_reassigned():
    packet,_,_,_,_,_,p3=fixture()
    source=packet["collections"]["semantic_rules"][0]["source_fields_unreviewed"]
    source["target_table"]=packet["physical_identifier_hints_unapproved"][0]["source_table_ref"]
    source["target_column"]="unmapped_legacy_column"
    packet["physical_identifier_hints_unapproved"][0]["source_column_ref"]="unmapped_legacy_column"
    worklist,counts=make_worklist(packet,p3)
    assert counts["columns_missing_exact_name"]==1
    ref=worklist["physical_references"][0]
    assert ref["selected_physical_binding"] is None
    assert ref["literal_match_status"]=="NO_SAME_NAMED_PHYSICAL_COLUMN"
    assert ref["physical_options_not_selected"]


def test_html_escapes_private_values_and_never_contains_rule_body():
    packet,_,_,_,_,_,p3=fixture()
    worklist,counts=make_worklist(packet,p3)
    worklist["physical_references"][0]["legacy_table"]="<script>leak()</script>"
    view=html_view(worklist,counts).decode()
    assert "<script>leak()</script>" not in view
    assert "&lt;script&gt;leak()&lt;/script&gt;" in view
    assert "default-src 'none'" in view
    assert "source_fields_unreviewed" not in view
    assert "some_metric" not in json.dumps(worklist)


def test_posix_root_private_review_and_no_replay():
    if os.name != "posix":
        return
    for other in (False,True):
        with TemporaryDirectory() as folder:
            files,_,_=inputs(Path(folder),alternate=other)
            stats=write(files)
            assert stats["original_hint_rows"]==1
            for key in ("output_json","output_html"):
                assert stat.S_IMODE(files[key].stat().st_mode)==0o600
            doc=json.loads(files["output_json"].read_bytes())
            assert doc["status"]=="UNAPPROVED_HUMAN_REVIEW_ONLY"
            denied(lambda: write(files))  # Never overwrite private data.


def test_private_symlink_or_tampered_input_is_blocked_without_output():
    if os.name!="posix":
        return
    with TemporaryDirectory() as folder:
        files,_,_=inputs(Path(folder))
        files["p3"].write_bytes(files["p3"].read_bytes()+b" ")
        denied(lambda: write(files))
        assert not files["output_json"].exists()
    with TemporaryDirectory() as folder:
        files,_,_=inputs(Path(folder))
        shortcut=Path(folder)/"p3-link.json"
        shortcut.symlink_to(files["p3"])
        files["p3"]=shortcut
        denied(lambda: write(files))
        assert not files["output_json"].exists()


def test_cli_stdout_contains_only_counts_and_flags():
    if os.name!="posix":
        return
    from scripts.operations.g5_p3_original_physical_worklist import main
    with TemporaryDirectory() as folder:
        files,_,_=inputs(Path(folder))
        out=io.StringIO()
        with contextlib.redirect_stdout(out):
            status=main([
                "--manifest",str(files["manifest"]),
                "--version-sha256",files["version"],
                "--packet-file",str(files["packet"]),
                "--p3-file",str(files["p3"]),
                "--output-json",str(files["output_json"]),
                "--output-html",str(files["output_html"]),
            ])
        assert status==0
        output=out.getvalue()
        assert "G5_P3_WORKLIST=PASS" in output
        for forbidden in ("schema_test","value","other_schema_with_same_table"):
            assert forbidden not in output


if __name__=="__main__":
    tests=sorted((key,func) for key,func in globals().items()
                 if key.startswith("test_") and callable(func))
    for key,func in tests:
        func()
        print("PASS",key)
    print("TOTAL_TESTS",len(tests))

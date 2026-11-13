"""Synthetic tests for the private G5 financial-owner TTY review workflow."""
from __future__ import annotations

import io
import json
import os
import stat
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.operations.g5_financial_crosswalk_review import FinancialReviewBlocked
from scripts.operations.g5_owner_review_tui import (
    atomic_private_update, counts, edit_financial, edit_physical,
    export_unsigned_draft, initial_state, open_review,
    private_file_location, safe_terminal, validate_state,
)
from scripts.operations.g5_p3_original_physical_worklist import physical_index
from testar_g5_p3_original_physical_worklist import inputs


class FakeTTY:
    def __init__(self, input_text: str):
        self.items = iter(input_text.splitlines(keepends=True))
        self.output = []

    def write(self, text):
        self.output.append(text)

    def readline(self):
        return next(self.items, "")

    def flush(self):
        pass

    def getvalue(self):
        return "".join(self.output)


def fixture(root: Path, alt=False):
    files, packet, p3 = inputs(root, alternate=alt)
    packet_sha = __import__("hashlib").sha256(files["packet"].read_bytes()).hexdigest()
    state = initial_state(packet, packet_sha, p3)
    table, _rows = physical_index(p3, packet["origin"]["p3_snapshot_sha256"])
    session = root / "owner-unapproved-session.json"
    return files, packet, p3, state, table, session


def refused(fn):
    try:
        fn()
    except (FinancialReviewBlocked, ValueError):
        return
    raise AssertionError("An unsafe owner review/edit/export was allowed")


def start(files, session, *, tty=None, status_only=False, export_paths=None):
    return open_review(
        manifest_path=files["manifest"],
        source_version=files["version"],
        packet_path=files["packet"],
        p3_path=files["p3"],
        session_path=session,
        tty=tty, status_only=status_only,
        export_paths=export_paths,
    )


def test_status_reports_counts_only_and_does_not_create_session():
    if os.name != "posix": return
    for alternate in (False, True):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            files, packet, p3, state, physical, session = fixture(root, alt=alternate)
            result = start(files,session,status_only=True)
            assert result["financial_total"]==1
            assert result["financial_classified"]==0
            assert result["physical_total"]==1
            assert result["physical_selected"]==0
            assert not session.exists()


def test_tty_owner_classifies_source_with_explicit_choice_and_resumes_safely():
    if os.name != "posix":return
    with TemporaryDirectory() as folder:
        root = Path(folder)
        files, packet, p3, state, physical, session = fixture(root)
        fake = FakeTTY("f\ns\ns\nq\n")
        result=start(files,session,tty=fake)
        assert result["financial_classified"]==1
        assert result["physical_selected"]==0
        assert session.exists()
        assert stat.S_IMODE(session.stat().st_mode)==0o600
        saved=json.loads(session.read_bytes())
        assert saved["workbook"]["financial_source_rows"][0]["classification"]=="STRUCTURAL"
        assert saved["workbook"]["accounting_approved"] is False
        assert saved["workbook"]["financial_sql_executed"] is False
        assert "DECISAO_GRAVADA_EM_DRAFT" in fake.getvalue()
        resumed=start(files,session,status_only=True)
        assert resumed["financial_classified"]==1


def test_tty_never_saves_duplicate_destinations_or_bad_p3_selection():
    if os.name!="posix":return
    with TemporaryDirectory() as folder:
        root=Path(folder)
        files,packet,p3,state,physical,session=fixture(root)
        fake=FakeTTY("f 1\nb\nrules:0,rules:0\np 1\n999\nq\n")
        progress=start(files,session,tty=fake)
        assert progress["financial_classified"]==0
        assert progress["physical_selected"]==0
        assert not session.exists()
        assert "Entrada rejeitada" in fake.getvalue()


def test_physical_pick_requires_explicit_column_and_true_remap_justification():
    for alt in (False,True):
        with TemporaryDirectory() as folder:
            files,p,p3,state,physical,_ = fixture(Path(folder),alt=alt)
            expected = state["workbook"]["physical_binding_decisions"][0]
            names=sorted(physical)
            target_idx=next((i for i,key in enumerate(names,1)
                             if key[1]==expected["source_table"]), 1)
            target=names[target_idx-1]
            col_names=sorted(physical[target])
            old_col=expected["source_column"]
            col_idx=col_names.index(old_col)+1 if old_col in col_names else 1
            chosen_col=col_names[col_idx-1]
            remapped=(
                target[1]!=expected["source_table"]
                or (expected["source_schema"] is not None and target[0]!=expected["source_schema"])
                or old_col!=chosen_col
            )
            commands=str(target_idx)+"\n"+str(col_idx)+"\n"
            if remapped:commands += "Owner confirms physical remapping after source review.\n"
            tty=FakeTTY(commands)
            assert edit_physical(state,physical,0,tty) is True
            validate_state(state,initial_state(p,__import__("hashlib").sha256(files["packet"].read_bytes()).hexdigest(),p3),physical)
            assert state["workbook"]["physical_binding_decisions"][0]["qualified_table"]==".".join(target)
            assert state["remap"]["remaps"][0]["qualified_table"]==".".join(target)
            assert state["workbook"]["accounting_approved"] is False


def test_incomplete_never_exports_worksheet_for_compiler():
    if os.name!="posix":return
    with TemporaryDirectory() as folder:
        root=Path(folder)
        files,packet,p3,state,physical,session=fixture(root)
        a,b=root/"completed-workbook.json",root/"completed-remap.json"
        refused(lambda:export_unsigned_draft(
            state=state,template=deepcopy(state),physical=physical,
            private_dir=root,output_workbook=a,output_remap=b,
        ))
        assert not a.exists() and not b.exists()


def test_fully_completed_one_row_owner_review_exports_only_unsigned_json():
    if os.name!="posix":return
    with TemporaryDirectory() as folder:
        root=Path(folder)
        files,packet,p3,state,physical,session=fixture(root)
        initial=deepcopy(state)
        f=state["workbook"]["financial_source_rows"][0]
        f["classification"]="FORBIDDEN"
        f["destinations"]=[{"collection":"rules","index":0}]
        r=state["workbook"]["physical_binding_decisions"][0]
        source_table=r["source_table"]
        old_schema=r["source_schema"]
        old_col=r["source_column"]
        candidates=[(k,v) for k,v in sorted(physical.items())
                    if k[1]==source_table and old_col in v]
        if not candidates:
            candidates=[(k,v) for k,v in sorted(physical.items()) if old_col in v]
        assert candidates
        (schema,table), cols=candidates[0]
        name=schema+"."+table
        remap=table!=source_table or (
            old_schema is not None and schema!=old_schema
        )
        r["qualified_table"]=name
        r["target_column"]=old_col
        e=state["remap"]["remaps"][0]
        e["qualified_table"]=name
        e["target_column"]=old_col
        e["review_rationale"]="Independently reviewed synthetic example mapping." if remap else None
        w=state["workbook"]
        for k,v in (
            ("tenant_id","synthetic_client"),
            ("semantic_agent_version","synthetic-v1"),
            ("prepared_by","synthetic_technical_author"),
            ("reviewer_id","synthetic_owner"),
            ("context_fingerprint","f"*64),
        ):
            w[k]=v
            if k in state["remap"]:state["remap"][k]=v
        state["actions"]=3
        validate_state(state,initial,physical)
        atomic_private_update(session,root,state)
        output_a=root/"export-worksheet.json"
        output_b=root/"export-remap.json"
        exported=start(files,session,status_only=True,export_paths=(output_a,output_b))
        assert exported["financial_classified"]==1
        assert exported["physical_selected"]==1
        assert stat.S_IMODE(output_a.stat().st_mode)==0o600
        assert stat.S_IMODE(output_b.stat().st_mode)==0o600
        assert json.loads(output_a.read_bytes())["accounting_approved"] is False
        assert json.loads(output_b.read_bytes())["contract"].endswith("DRAFT-unapproved-v1")
        refused(lambda: start(files,session,status_only=True,export_paths=(output_a,output_b)))


def test_tampered_session_origin_and_permissions_fail_closed():
    if os.name!="posix":return
    with TemporaryDirectory() as folder:
        root=Path(folder)
        files,packet,p3,state,physical,session=fixture(root)
        atomic_private_update(session,root,state)
        original=session.read_bytes()
        data=json.loads(original)
        data["packet_plaintext_sha256"]="a"*64
        session.write_text(json.dumps(data))
        refused(lambda:start(files,session,status_only=True))
        session.write_bytes(original)
        session.chmod(0o644)
        refused(lambda:start(files,session,status_only=True))
        session.chmod(0o600)
        link=root/"session-link.json"
        link.symlink_to(session)
        refused(lambda:private_file_location(link,root,exists=True))


def test_terminal_escape_and_bidi_control_are_filtered():
    display=safe_terminal({"legacy_value":"\u001b[31mPRIVATE\u202esecret"})
    assert "\x1b" not in display
    assert "\u202e" not in display
    assert "PRIVATE" in display


def test_owner_and_author_identical_is_not_accepted_as_independent_roles():
    with TemporaryDirectory() as folder:
        files,packet,p3,state,physical,session=fixture(Path(folder))
        state["workbook"]["prepared_by"]="same_person"
        state["workbook"]["reviewer_id"]="same_person"
        state["remap"]["prepared_by"]="same_person"
        state["remap"]["reviewer_id"]="same_person"
        refused(lambda:export_unsigned_draft(
            state=state,template=initial_state(packet,__import__("hashlib").sha256(files["packet"].read_bytes()).hexdigest(),p3),
            physical=physical,private_dir=Path(folder),
            output_workbook=Path(folder)/"a.json",output_remap=Path(folder)/"b.json",
        ))


def test_real_private_source_is_written_only_to_explicit_tty_not_stdout():
    if os.name != "posix":return
    import contextlib
    with TemporaryDirectory() as folder:
        files,packet,p3,state,physical,session=fixture(Path(folder))
        tty=FakeTTY("f 1\n?\nq\n")
        capture=io.StringIO()
        with contextlib.redirect_stdout(capture):
            start(files,session,tty=tty)
        assert capture.getvalue() == ""
        assert "source_fields_unreviewed" not in capture.getvalue()
        assert packet["collections"]["semantic_rules"][0]["source_fields_unreviewed"]
        assert "DECISAO_GRAVADA_EM_DRAFT" in tty.getvalue()


def test_session_altered_approval_flags_are_rejected():
    if os.name!="posix":return
    with TemporaryDirectory() as folder:
        root=Path(folder)
        files,packet,p3,state,physical,session=fixture(root)
        state["workbook"]["accounting_approved"]=True
        atomic_private_update(session,root,state)
        refused(lambda:start(files,session,status_only=True))


def test_real_size_77_by_48_synthetic_review_is_resumable_without_auto_approving():
    from testar_g5_physical_source_evidence import fixture as one
    from scripts.operations.g5_financial_crosswalk_review import draft
    import hashlib
    packet, sha, review, ctx, raw, seal, p3=one()
    source=packet["collections"]["semantic_rules"][0]
    physical_hint=packet["physical_identifier_hints_unapproved"][0]
    packet["collections"]["semantic_rules"]=[
        {"source_row_sha256":format(i+1,"064x"),
         "source_fields_unreviewed":dict(source["source_fields_unreviewed"])}
        for i in range(77)
    ]
    packet["row_counts"]["semantic_rules"]=77
    packet["physical_identifier_hints_unapproved"]=[
        {**physical_hint,"source_record_sha256":format(i+1,"064x")}
        for i in range(48)
    ]
    sha=hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()
    state=initial_state(packet,sha,p3)
    physical,_=physical_index(p3,packet["origin"]["p3_snapshot_sha256"])
    validate_state(state,deepcopy(state),physical)
    assert counts(state)["financial_total"]==77
    assert counts(state)["physical_total"]==48
    assert counts(state)["financial_classified"]==0
    assert counts(state)["physical_selected"]==0
    assert not state["workbook"]["accounting_approved"]
    assert not state["workbook"]["context_activated"]
    if os.name=="posix":
        with TemporaryDirectory() as folder:
            root=Path(folder);root.chmod(0o700)
            session=root/"private-77x48-session.json"
            atomic_private_update(session,root,state)
            saved=json.loads(session.read_bytes())
            validate_state(saved,state,physical)
            assert stat.S_IMODE(session.stat().st_mode)==0o600


if __name__=="__main__":
    cases=sorted((k,v) for k,v in globals().items()
                 if k.startswith("test_") and callable(v))
    for k,v in cases:
        v()
        print("PASS",k)
    print("TOTAL_TESTS",len(cases))

"""Private G5 review HTTP boundary tests: synthetic, no socket and no SQL."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.operations.g5_owner_review_http_contract import (
    PrivateG5OwnerReviewService, ReviewConfig, _private_audit_path,
)
from testar_g5_p3_original_physical_worklist import inputs


TOKEN="a"*48


def setup(root: Path, *, alt=False, enabled=True):
    files, packet, p3 = inputs(root, alternate=alt)
    config=ReviewConfig(
        manifest=files["manifest"],version_sha256=files["version"],
        packet=files["packet"],p3=files["p3"],
        session=root/"owner-review-session.json",
        s2s_token=TOKEN, expected_tenant_id=(
            "synthetic_tenant_b" if alt else "synthetic_tenant_a"
        ), enabled=enabled,
    )
    return PrivateG5OwnerReviewService(config),files


def req(service,kind="status", *,payload=None, auth=True,actor="admin_synthetic"):
    paths={
        "status":"/v1/internal/g5-owner-review/status",
        "item":"/v1/internal/g5-owner-review/item",
        "decision":"/v1/internal/g5-owner-review/decision",
    }
    headers={"x-g5-product-role":"admin",
             "x-g5-product-tenant":service.config.expected_tenant_id}
    if auth:headers["Authorization"]="Bearer "+TOKEN
    result=service.handle(
        method="POST" if kind=="decision" else "GET",path=paths[kind],
        headers=headers,actor_id=actor,request=payload,
    )
    return result, json.loads(result["body"])


def test_feature_flag_blocks_even_valid_admin_and_never_loads_packet():
    with TemporaryDirectory() as d:
        s,f=setup(Path(d),enabled=False)
        result,body=req(s)
        assert result["status_code"]==404
        assert body["status"]=="blocked"
        assert not s.config.session.exists()


def test_authorization_is_explicit_and_rejects_browser_cookie_bypass():
    with TemporaryDirectory() as d:
        s,f=setup(Path(d))
        result,_=req(s,auth=False)
        assert result["status_code"]==403
        result,_=req(s,actor="invalid actor whitespace")
        assert result["status_code"]==403
        result=s.handle(method="GET",path="/v1/internal/g5-owner-review/status",
             headers={"Authorization":"Bearer "+TOKEN,
                      "x-g5-product-role":"viewer",
                      "x-g5-product-tenant":s.config.expected_tenant_id},
             actor_id="viewer",request={})
        assert result["status_code"]==403
        result=s.handle(method="GET",path="/v1/internal/g5-owner-review/status",
             headers={"Authorization":"Bearer "+TOKEN,
                      "x-g5-product-role":"admin",
                      "x-g5-product-tenant":s.config.expected_tenant_id,
                      "Cookie":"bad"},actor_id="admin",request={})
        assert result["status_code"]==403
        result=s.handle(method="GET",path="/v1/internal/g5-owner-review/status",
             headers={"Authorization":"Bearer "+TOKEN,
                      "x-g5-product-role":"admin",
                      "x-g5-product-tenant":s.config.expected_tenant_id,
                      "Origin":"https://evil.example"},actor_id="admin",request={})
        assert result["status_code"]==403


def test_status_contains_no_business_values_or_sql_and_creates_no_session():
    for alt in (False,True):
        with TemporaryDirectory() as d:
            s,f=setup(Path(d),alt=alt)
            result,body=req(s)
            assert result["status_code"]==200
            assert body["counts"]["financial_total"]==1
            assert body["counts"]["physical_total"]==1
            assert body["counts"]["session_actions"]==0
            assert body["accounting_approved"] is False
            assert body["context_activated"] is False
            assert body["sql_executed"] is False
            assert "no-store" in result["headers"]["Cache-Control"]
            assert "source_fields_unreviewed" not in result["body"].decode()
            assert not s.config.session.exists()


def test_item_can_be_read_only_with_separate_admin_s2s_credential():
    with TemporaryDirectory() as d:
        s,f=setup(Path(d))
        result,body=req(s,kind="item",payload={"kind":"financial","index":0})
        assert result["status_code"]==200
        assert body["kind"]=="financial"
        assert body["source"]
        assert body["accounting_approved"] is False
        assert not s.config.session.exists()
        result,physical=req(s,kind="item",payload={"kind":"physical","index":0})
        assert result["status_code"]==200
        assert len(physical["decision"]["physical_options_unapproved"])==2
        assert physical["decision"]["qualified_table"] is None
        result,_=req(s,kind="item",payload={"kind":"financial","index":True})
        assert result["status_code"]==404


def test_financial_decision_is_audited_draft_only_and_replay_conflicts():
    if os.name!="posix":return
    with TemporaryDirectory() as d:
        root=Path(d)
        s,f=setup(root)
        _,before=req(s)
        expected=before["revision"]
        payload={"kind":"financial","index":0,
                 "decision":{"classification":"STRUCTURAL","destinations":[]},
                 "expected_revision":expected}
        result,body=req(s,"decision",payload=payload)
        assert result["status_code"]==200
        assert body["status"]=="draft_saved"
        assert body["audit_sequence"]==1
        assert body["accounting_approved"] is False
        assert body["sql_executed"] is False
        assert body["revision"]!=expected
        assert stat.S_IMODE(s.config.session.stat().st_mode)==0o600
        audit=_private_audit_path(s.config.session)
        assert audit.exists() and stat.S_IMODE(audit.stat().st_mode)==0o600
        assert len(audit.read_text().splitlines())==2
        conflict,body=req(s,"decision",payload=payload)
        assert conflict["status_code"]==409
        _,status=req(s)
        assert status["counts"]["session_actions"]==1
        assert status["counts"]["financial_classified"]==1


def test_physical_decision_requires_real_type_and_individual_justification():
    if os.name!="posix":return
    with TemporaryDirectory() as d:
        s,f=setup(Path(d))
        _,status=req(s)
        _,item=req(s,"item",payload={"kind":"physical","index":0})
        row=item["decision"]
        physical=[v for v in row["physical_options_unapproved"]
                  if any(c["name"]==row["source_column"] for c in v["columns"])]
        assert physical
        destination=physical[0]["qualified_table"]
        base={"kind":"physical","index":0,"expected_revision":status["revision"]}
        without={"qualified_table":destination,
                 "target_column":row["source_column"],"review_rationale":None}
        if row["source_table"]!=destination.split(".")[1] or (
            row["source_schema"] and row["source_schema"]!=destination.split(".")[0]
        ):
            fail,_=req(s,"decision",payload={**base,"decision":without})
            assert fail["status_code"]==409
            without["review_rationale"]="Confirmed independently, synthetic source mapping."
        good,body=req(s,"decision",payload={**base,"decision":without})
        assert good["status_code"]==200
        assert body["counts"]["physical_selected"]==1
        assert body["context_activated"] is False


def test_unapproved_financial_destinations_and_broken_type_are_denied():
    if os.name!="posix":return
    with TemporaryDirectory() as d:
        s,f=setup(Path(d))
        _,status=req(s)
        rev=status["revision"]
        invalid={"kind":"financial","index":0,"expected_revision":rev,
                 "decision":{"classification":"UNRESOLVED",
                             "destinations":[{"collection":"rules","index":0}]}}
        r,_=req(s,"decision",payload=invalid)
        assert r["status_code"]==409
        bad={"kind":"physical","index":0,"expected_revision":rev,
             "decision":{"qualified_table":"untrusted.fake",
                         "target_column":"value","review_rationale":"arbitrary"}}
        r,_=req(s,"decision",payload=bad)
        assert r["status_code"]==409
        assert not s.config.session.exists()


def test_audit_corruption_or_uncommitted_event_fails_closed():
    if os.name!="posix":return
    with TemporaryDirectory() as d:
        s,f=setup(Path(d))
        _,status=req(s)
        ok,_=req(s,"decision",payload={
            "kind":"financial","index":0,"expected_revision":status["revision"],
            "decision":{"classification":"STRUCTURAL","destinations":[]},
        })
        assert ok["status_code"]==200
        audit=_private_audit_path(s.config.session)
        lines=audit.read_text().splitlines()
        audit.write_text(lines[0]+"\n")
        r,_=req(s)
        assert r["status_code"]==409
        assert "source_fields_unreviewed" not in r["body"].decode()


def test_cross_tenant_revision_and_source_cannot_be_replayed():
    if os.name!="posix":return
    with TemporaryDirectory() as a, TemporaryDirectory() as b:
        first,_=setup(Path(a),alt=False)
        second,_=setup(Path(b),alt=True)
        _,one=req(first);_,two=req(second)
        assert one["p3_snapshot_sha256"]!=two["p3_snapshot_sha256"]
        assert one["revision"]!=two["revision"]
        r,_=req(second,"decision",payload={
            "kind":"financial","index":0,"expected_revision":one["revision"],
            "decision":{"classification":"STRUCTURAL","destinations":[]},
        })
        # A source-agnostic initial workbook revision could otherwise coincide
        # across tenants; here the sealed source digest differs.
        assert r["status_code"]==409


if __name__=="__main__":
    tests=sorted((k,v) for k,v in globals().items()
                 if k.startswith("test_") and callable(v))
    for name,fn in tests:
        fn()
        print("PASS",name)
    print("TOTAL_TESTS",len(tests))

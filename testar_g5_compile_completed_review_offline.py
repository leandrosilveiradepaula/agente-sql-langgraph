"""End-to-end synthetic tests of human COMPLETED but UNSIGNED G5 review.

Never use real G5 plaintext, n8n benchmarks or customer-specific semantics.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import stat
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.operations.g5_compile_completed_review_offline import (
    compile_completed_review, compile_private,
)
from scripts.operations.g5_financial_crosswalk_review import (
    FinancialReviewBlocked, digest, draft, verified_review,
)
from scripts.operations.g5_financial_review_worksheet_offline import build_review_templates
from scripts.operations.g5_physical_source_evidence import physical_approval_claims
from testar_g5_physical_source_evidence import (
    TEST_VERIFIER_KEY, _historic_changed_table, fixture,
)
from testar_g5_financial_crosswalk_review import receipt_for
from testar_g5_targeted_financial_review_offline import fixture as manifest_fixture


def example(*, alt=False, changed=True):
    instance = _historic_changed_table(alternate=alt) if changed else fixture(other=alt)
    packet, sha, review, context, raw, seal, p3 = instance[:7]
    workbook, remap_draft = build_review_templates(
        packet=packet, packet_sha256=sha, financial_draft=draft(packet, sha),
        p3_bytes=p3,
    )
    workbook["tenant_id"] = review["tenant_id"]
    workbook["semantic_agent_version"] = review["semantic_agent_version"]
    workbook["reviewer_id"] = review["reviewer_id"]
    workbook["prepared_by"] = "synthetic_mapper" if not alt else "different_synthetic_mapper"
    workbook["context_fingerprint"] = review["context_fingerprint"]
    workbook["financial_source_rows"] = deepcopy(review["rows"])
    target_decision = review["physical_binding_decisions"][0]
    workbook["physical_binding_decisions"][0]["qualified_table"] = target_decision["qualified_table"]
    workbook["physical_binding_decisions"][0]["target_column"] = target_decision["target_column"]
    for key in ("tenant_id", "semantic_agent_version", "reviewer_id", "prepared_by"):
        remap_draft[key] = workbook[key]
    remap_draft["remaps"][0]["qualified_table"] = target_decision["qualified_table"]
    remap_draft["remaps"][0]["target_column"] = target_decision["target_column"]
    remap_draft["remaps"][0]["review_rationale"] = (
        "Independently reviewed synthetic physical remapping."
    ) if changed else None
    return instance, workbook, remap_draft


def run(instance, wb, rm):
    p,sha,review,context,raw,seal,p3=instance[:7]
    return compile_completed_review(
        packet=p,packet_sha256=sha,p3_bytes=p3,
        filled_workbook=wb,filled_remap_draft=rm,
        approved_context=context,
    )


def refused(fn):
    try:
        fn()
    except (FinancialReviewBlocked, ValueError):
        return
    raise AssertionError("Incomplete, self-signed or cross-tenant candidate accepted")


def test_two_synthetic_tenants_compile_and_verify_independent_unsigned_candidate():
    candidates = []
    for alt in (False, True):
        instance, wb, rm = example(alt=alt, changed=True)
        reviewed, physical_evidence = run(instance, wb, rm)
        p, sha, initial, ctx, raw, seal, p3 = instance[:7]
        assert reviewed["accounting_approved"] is False
        assert reviewed["ready_for_generation"] is False
        assert reviewed["financial_sql_executed"] is False
        assert physical_evidence["contract"] == "g5-physical-remap-review-evidence-v1"
        assert len(reviewed["physical_binding_decisions"]) == 1
        assert len(physical_evidence["remaps"]) == 1
        assert reviewed["physical_binding_decisions"][0][
            "physical_remap_evidence_sha256"
        ] == digest(physical_evidence["remaps"][0])
        from app.domain.context_normalizer import normalize_context_snapshot
        claims = physical_approval_claims(
            packet=p, review=reviewed,
            approved_catalog=normalize_context_snapshot(ctx)["table_catalog"],
            p3_bytes=p3, remap_evidence=physical_evidence,
        )
        # A DIFFERENT synthetic signer acts only in test; the compiler never signs.
        receipt = receipt_for(p, sha, reviewed)
        receipt["claims"].update(claims)
        receipt["hmac_sha256"] = hmac.new(
            TEST_VERIFIER_KEY, digest(receipt["claims"]).encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        verified = verified_review(
            packet=p,packet_sha256=sha,source_packet_bytes=raw,
            trusted_seal=seal,review=reviewed,raw_context=ctx,
            approval_receipt=receipt,verifier_key=TEST_VERIFIER_KEY,
            p3_snapshot_bytes=p3,physical_remap_evidence=physical_evidence,
        )
        assert verified["status"] == "G5_FINANCIAL_MAPPING_CANDIDATE_NOT_ACTIVATED"
        assert verified["activation_authorized"] is False
        assert verified["context_persisted"] is False
        assert verified["financial_sql_executed"] is False
        assert verified["reviewed_rows"] == 1
        candidates.append(verified["context_fingerprint"])
    assert candidates[0] != candidates[1]


def test_default_private_77_line_draft_is_never_a_completed_review():
    t, wb, rm = example()
    wb["financial_source_rows"] = draft(t[0],t[1])["rows"]
    refused(lambda:run(t,wb,rm))
    t,wb,rm = example()
    wb["physical_binding_decisions"][0]["qualified_table"] = None
    refused(lambda:run(t,wb,rm))
    t,wb,rm = example()
    rm["remaps"][0]["review_rationale"]=None
    refused(lambda:run(t,wb,rm))


def test_unchanged_name_tenant_compiles_without_fake_remap_evidence():
    t,wb,rm=example(changed=False)
    reviewed,evidence=run(t,wb,rm)
    assert evidence is None
    assert "physical_remap_evidence_sha256" not in reviewed["physical_binding_decisions"][0]
    assert reviewed["accounting_approved"] is False


def test_reviewer_cannot_supply_an_arbitrary_64_hex_signature_or_replace_source():
    t,wb,rm=example()
    wb["physical_binding_decisions"][0]["physical_remap_evidence_sha256"]="f"*64
    refused(lambda:run(t,wb,rm))
    t,wb,rm=example()
    wb["financial_source_rows"][0]["source_row_sha256"]="b"*64
    refused(lambda:run(t,wb,rm))
    t,wb,rm=example()
    wb["physical_binding_decisions"][0]["source_table"]="tampered"
    refused(lambda:run(t,wb,rm))
    t,wb,rm=example()
    rm["remaps"][0]["source_column"]="faked"
    refused(lambda:run(t,wb,rm))


def test_tenant_and_approved_context_fingerprint_cannot_be_replayed():
    first,wb,rm=example()
    other,_,_=example(alt=True)
    refused(lambda:compile_completed_review(
        packet=first[0],packet_sha256=first[1],p3_bytes=first[6],
        filled_workbook=wb,filled_remap_draft=rm,approved_context=other[3],
    ))
    t,wb,rm=example()
    wb["context_fingerprint"]="0"*64
    refused(lambda:run(t,wb,rm))
    t,wb,rm=example()
    wb["prepared_by"]=wb["reviewer_id"]
    rm["prepared_by"]=wb["prepared_by"]
    refused(lambda:run(t,wb,rm))


def test_unresolved_target_or_invalid_financial_destination_never_compiles():
    t,wb,rm=example()
    wb["financial_source_rows"][0]["destinations"]=[]
    refused(lambda:run(t,wb,rm))
    t,wb,rm=example()
    wb["financial_source_rows"][0]["destinations"]=[{
        "collection":"rules","index":999999,
    }]
    refused(lambda:run(t,wb,rm))
    t,wb,rm=example()
    wb["financial_source_rows"][0]["classification"]="TRANSITIONAL"
    refused(lambda:run(t,wb,rm))


def test_posix_private_cli_produces_only_unsigned_0600_artifacts():
    if os.name!="posix":
        return
    t,wb,rm=example()
    p,sha,review,ctx,raw,seal,p3=t[:7]
    _,_,manifest=manifest_fixture()
    manifest["versions"][0]["plaintext_sha256"]=sha
    with TemporaryDirectory() as folder:
        root=Path(folder)
        root.chmod(0o700)
        source={
            "manifest":manifest,
            "packet":p, "p3":json.loads(p3), "workbook":wb,
            "remap":rm, "context":ctx,
        }
        paths={}
        for key,value in source.items():
            path=root/(key+".json")
            path.write_bytes(raw if key=="packet" else
                             p3 if key=="p3" else json.dumps(value).encode("utf-8"))
            path.chmod(0o600)
            paths[key]=path
        output_review=root/"unsigned-reviewed.json"
        output_evidence=root/"unsigned-remap.json"
        args=dict(
            manifest_path=paths["manifest"],source_version=seal["source_version_sha256"],
            packet_path=paths["packet"],p3_path=paths["p3"],
            completed_workbook_path=paths["workbook"],
            completed_remap_path=paths["remap"],
            approved_context_path=paths["context"],
            output_review_path=output_review,
            output_evidence_path=output_evidence,
        )
        result=compile_private(**args)
        assert result=={"reviewed_rows":1,"physical_rows":1,"remapped_rows":1}
        assert stat.S_IMODE(output_review.stat().st_mode)==0o600
        assert stat.S_IMODE(output_evidence.stat().st_mode)==0o600
        assert json.loads(output_review.read_bytes())["accounting_approved"] is False
        assert "hmac_sha256" not in output_review.read_text()
        assert "hmac_sha256" not in output_evidence.read_text()
        refused(lambda:compile_private(**args))


def test_private_cli_refuses_incomplete_workbook_and_never_creates_output():
    if os.name!="posix":
        return
    t,wb,rm=example()
    p,sha,review,ctx,raw,seal,p3=t[:7]
    _,_,manifest=manifest_fixture()
    manifest["versions"][0]["plaintext_sha256"]=sha
    wb["financial_source_rows"]=draft(p,sha)["rows"]
    with TemporaryDirectory() as folder:
        root=Path(folder)
        root.chmod(0o700)
        items={
            "manifest":manifest, "packet":p,
            "p3":json.loads(p3), "workbook":wb,"remap":rm,"context":ctx,
        }
        paths={}
        for key,value in items.items():
            path=root/(key+".json")
            path.write_bytes(raw if key=="packet" else
                 p3 if key=="p3" else json.dumps(value).encode("utf-8"))
            path.chmod(0o600);paths[key]=path
        a=root/"must-not-appear.json"
        b=root/"must-not-appear-remap.json"
        refused(lambda:compile_private(
            manifest_path=paths["manifest"],source_version=seal["source_version_sha256"],
            packet_path=paths["packet"],p3_path=paths["p3"],
            completed_workbook_path=paths["workbook"],
            completed_remap_path=paths["remap"],
            approved_context_path=paths["context"],
            output_review_path=a,output_evidence_path=b,
        ))
        assert not a.exists() and not b.exists()


def test_full_77_by_48_synthetic_coverage_compiles_without_approving_or_activating():
    # Different generated source IDs, no business facts/benchmarks from G5.
    instance=fixture(other=False)
    p,sha,review,ctx,raw,seal,p3=instance[:7]
    first=p["collections"]["semantic_rules"][0]
    seed_hint=p["physical_identifier_hints_unapproved"][0]
    p["collections"]["semantic_rules"]=[
        {
            "source_row_sha256":format(i+1,"064x"),
            "source_fields_unreviewed":dict(first["source_fields_unreviewed"]),
        }
        for i in range(77)
    ]
    p["row_counts"]["semantic_rules"]=77
    p["physical_identifier_hints_unapproved"]=[
        {
            **seed_hint,
            "source_record_sha256":format(i+1,"064x"),
        }
        for i in range(48)
    ]
    sha=hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest()
    base=draft(p,sha)
    wb,rd=build_review_templates(
        packet=p,packet_sha256=sha,financial_draft=base,p3_bytes=p3,
    )
    for k in ("tenant_id","semantic_agent_version","reviewer_id"):
        wb[k]=review[k]
        rd[k]=review[k]
    wb["prepared_by"]="synthetic_mapper"
    rd["prepared_by"]="synthetic_mapper"
    wb["context_fingerprint"]=review["context_fingerprint"]
    for row in wb["financial_source_rows"]:
        row["classification"]="FORBIDDEN"
        row["destinations"]=deepcopy(review["rows"][0]["destinations"])
    for row in wb["physical_binding_decisions"]:
        row["qualified_table"]=review["physical_binding_decisions"][0]["qualified_table"]
        row["target_column"]=review["physical_binding_decisions"][0]["target_column"]
    for row in rd["remaps"]:
        row["qualified_table"]=review["physical_binding_decisions"][0]["qualified_table"]
        row["target_column"]=review["physical_binding_decisions"][0]["target_column"]
    compiled,remap=compile_completed_review(
        packet=p,packet_sha256=sha,p3_bytes=p3,
        filled_workbook=wb,filled_remap_draft=rd,approved_context=ctx,
    )
    assert len(compiled["rows"])==77
    assert len(compiled["physical_binding_decisions"])==48
    assert remap is None
    assert compiled["accounting_approved"] is False
    assert compiled["ready_for_generation"] is False
    from app.domain.context_normalizer import normalize_context_snapshot
    claims=physical_approval_claims(
        packet=p,review=compiled,
        approved_catalog=normalize_context_snapshot(ctx)["table_catalog"],
        p3_bytes=p3,
    )
    # Test-only independent signer; no production approval is created.
    receipt=receipt_for(p,sha,compiled)
    receipt["claims"].update(claims)
    receipt["hmac_sha256"]=hmac.new(
        TEST_VERIFIER_KEY,digest(receipt["claims"]).encode("ascii"),hashlib.sha256,
    ).hexdigest()
    raw=json.dumps(p,sort_keys=True).encode()
    seal["plaintext_sha256"]=sha
    result=verified_review(
        packet=p,packet_sha256=sha,source_packet_bytes=raw,
        trusted_seal=seal,review=compiled,raw_context=ctx,
        approval_receipt=receipt,verifier_key=TEST_VERIFIER_KEY,
        p3_snapshot_bytes=p3,
    )
    assert result["reviewed_rows"]==77
    assert result["financial_sql_executed"] is False
    assert result["context_persisted"] is False
    assert result["activation_authorized"] is False


if __name__=="__main__":
    tests=sorted((n,f) for n,f in globals().items()
                 if n.startswith("test_") and callable(f))
    for name,fn in tests:
        fn()
        print("PASS",name)
    print("TOTAL_TESTS",len(tests))

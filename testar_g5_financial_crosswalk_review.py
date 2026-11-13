"""Synthetic tests for explicit G5 row reviews and independent attestation."""
from __future__ import annotations

import hashlib
import hmac
import json
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import os

from app.domain.context_normalizer import normalize_context_snapshot
from scripts.operations.g5_financial_crosswalk_review import (
    FinancialReviewBlocked, digest, draft, source_ids, verified_review,
)
from testar_g5_targeted_financial_review_offline import fixture
from testar_postgres_context_repository import _physical_snapshot

TEST_VERIFIER_KEY = b"offline-synthetic-key-never-for-production-" * 2


def context(*, tenant: str = "review-tenant", version: str = "review-v1",
            alternate: bool = False) -> dict:
    raw = _physical_snapshot()
    for entry in raw["padroes"]:
        entry.update(
            source_use="APPROVED_SEMANTIC_STRUCTURAL",
            sql_pattern="", business_question_examples=[], notes=None,
        )
    raw["regras"][0]["rule_content"].update(
        ambiguity_margin=20, applied_confidence=0.95,
        fallback_to_previous_intent=False,
    )
    raw.update(
        tenant_id=tenant, semantic_agent_version=version,
        source_approval_status="APPROVED",
        historical_evaluation_sql_excluded=True,
    )
    if alternate:
        table = raw["catalogo"][0]
        table["schema_name"] = "tenant_other_schema"
        table["table_name"] = "other_fact_stream"
        raw["padroes"][0]["required_tables"] = [
            "tenant_other_schema.other_fact_stream",
        ]
    return raw


def case(*, other: bool = False, version_sha: str = "f" * 64):
    raw_bytes, seal, _manifest = fixture(version=version_sha, alternate=other)
    packet = json.loads(raw_bytes)
    packet_sha = hashlib.sha256(raw_bytes).hexdigest()
    review = draft(packet, packet_sha)
    review["tenant_id"] = "tenant-two" if other else "tenant-one"
    review["semantic_agent_version"] = "version-two" if other else "version-one"
    review["reviewer_id"] = "synthetic-accountant"
    ctx = context(
        tenant=review["tenant_id"],
        version=review["semantic_agent_version"],
        alternate=other,
    )
    review["context_fingerprint"] = normalize_context_snapshot(ctx)["fingerprint"]
    # The one private synthetic record is assumed business-only for this test.
    review["rows"][0]["classification"] = "FORBIDDEN"
    review["rows"][0]["destinations"] = [{"collection": "rules", "index": 0}]
    return packet, packet_sha, review, ctx, raw_bytes, seal


def receipt_for(packet: dict, packet_sha: str, review: dict):
    rows_sha = digest(sorted(
        review["rows"],
        key=lambda row: (row["collection"], row["source_row_sha256"]),
    ))
    claims = {
        "decision": "APPROVE_G5_FINANCIAL_CROSSWALK",
        "tenant_id": review["tenant_id"],
        "semantic_agent_version": review["semantic_agent_version"],
        "reviewer_id": review["reviewer_id"],
        "context_fingerprint": review["context_fingerprint"],
        "source_version_sha256": packet["origin"]["source_version_sha256"],
        "packet_plaintext_sha256": packet_sha,
        "review_rows_sha256": rows_sha,
    }
    return {
        "contract": "g5-independent-financial-approval-v1",
        "claims": claims,
        "hmac_sha256": hmac.new(
            TEST_VERIFIER_KEY, digest(claims).encode("ascii"), hashlib.sha256,
        ).hexdigest(),
    }


def assert_rejected(*, packet: dict, packet_sha: str, review: dict,
                    ctx: dict, receipt: dict, raw_bytes: bytes, seal: dict,
                    key=TEST_VERIFIER_KEY):
    try:
        verified_review(
            packet=packet, packet_sha256=packet_sha,
            source_packet_bytes=raw_bytes, trusted_seal=seal,
            review=review, raw_context=ctx,
            approval_receipt=receipt, verifier_key=key,
        )
    except FinancialReviewBlocked:
        return
    raise AssertionError("Unapproved or tampered financial mapping accepted")


def test_two_distinct_tenants_and_source_versions_with_independent_signatures():
    candidates=[]
    for other,version_sha in ((False,"f"*64),(True,"a"*64)):
        packet,packet_sha,review,ctx,raw_bytes,seal=case(
            other=other,version_sha=version_sha,
        )
        receipt=receipt_for(packet,packet_sha,review)
        outcome=verified_review(
            packet=packet,packet_sha256=packet_sha,
            source_packet_bytes=raw_bytes,trusted_seal=seal,review=review,
            raw_context=ctx,approval_receipt=receipt,
            verifier_key=TEST_VERIFIER_KEY,
        )
        assert outcome["status"]=="G5_FINANCIAL_MAPPING_CANDIDATE_NOT_ACTIVATED"
        assert outcome["activation_authorized"] is False
        assert outcome["context_persisted"] is False
        assert outcome["financial_sql_executed"] is False
        assert outcome["benchmark_used"] is False
        assert outcome["reviewed_rows"]==1
        assert outcome["classifications"]=={"STRUCTURAL":0,"FORBIDDEN":1}
        assert "source_fields_unreviewed" not in json.dumps(outcome)
        candidates.append(outcome["context_fingerprint"])
    assert candidates[0]!=candidates[1]


def test_source_values_never_enter_private_review_draft():
    packet,packet_sha,review,ctx,raw_bytes,seal=case()
    original = json.dumps(packet)
    public = json.dumps(draft(packet,packet_sha))
    assert "some_metric" in original
    assert "some_metric" not in public
    assert "ledger_records" not in public
    assert "source_fields_unreviewed" not in public
    assert "sql_pattern" not in public
    assert len(source_ids(packet)) == 1
    assert review["accounting_approved"] is False
    assert review["ready_for_generation"] is False


def test_bad_or_missing_independent_accounting_approval_fails_closed():
    packet,packet_sha,review,ctx,raw_bytes,seal=case()
    receipt=receipt_for(packet,packet_sha,review)
    for key,approval in (
        (None,receipt),
        (b"x"*32,None),
        (b"x"*32,receipt),
        (TEST_VERIFIER_KEY,None),
    ):
        assert_rejected(
            packet=packet, packet_sha=packet_sha, review=review, ctx=ctx,
            raw_bytes=raw_bytes, seal=seal, receipt=approval,key=key,
        )
    changed=deepcopy(receipt)
    changed["claims"]["reviewer_id"]="other-reviewer"
    assert_rejected(
        packet=packet,packet_sha=packet_sha,review=review,
        ctx=ctx,raw_bytes=raw_bytes,seal=seal,receipt=changed,
    )
    changed=deepcopy(review)
    changed["tenant_id"]="foreign-tenant"
    assert_rejected(
        packet=packet,packet_sha=packet_sha,review=changed,
        ctx=ctx,raw_bytes=raw_bytes,seal=seal,receipt=receipt,
    )
    changed=deepcopy(ctx)
    changed["catalogo"][0]["schema_name"]="altered_schema"
    assert_rejected(
        packet=packet,packet_sha=packet_sha,review=review,
        ctx=changed,raw_bytes=raw_bytes,seal=seal,receipt=receipt,
    )
    assert_rejected(
        packet=packet,packet_sha=packet_sha,review=review,
        ctx=ctx,raw_bytes=raw_bytes+b" ",seal=seal,receipt=receipt,
    )
    changed=deepcopy(seal)
    changed["source_version_sha256"]="0"*64
    assert_rejected(
        packet=packet,packet_sha=packet_sha,review=review,
        ctx=ctx,raw_bytes=raw_bytes,seal=changed,receipt=receipt,
    )


def test_accounting_review_rows_cannot_be_missing_duplicated_or_pending():
    packet,packet_sha,review,ctx,raw_bytes,seal=case()
    mutations = (
        lambda r: r["rows"][0].__setitem__("classification","TRANSITIONAL"),
        lambda r: r["rows"][0].__setitem__("classification","UNRESOLVED"),
        lambda r: r["rows"][0].__setitem__("destinations",[]),
        lambda r: r["rows"][0].__setitem__("destinations",[{
            "collection":"rules","index":9999,
        }]),
        lambda r: r["rows"][0].__setitem__("destinations",[{
            "collection":"other_tenant","index":0,
        }]),
        lambda r: r["rows"][0].__setitem__("source_row_sha256","0"*64),
        lambda r: r["rows"][0].__setitem__("classification",["FORBIDDEN"]),
        lambda r: r["rows"][0].__setitem__("source_row_sha256",[]),
        lambda r: r["rows"][0].__setitem__("collection",[]),
        lambda r: r["rows"].clear(),
    )
    for mutate in mutations:
        modified=deepcopy(review)
        mutate(modified)
        # Even a receipt issued for malicious data cannot bypass structural
        # coverage and semantic destination verification.
        signed=receipt_for(packet,packet_sha,modified)
        assert_rejected(
            packet=packet,packet_sha=packet_sha,review=modified,
            ctx=ctx,raw_bytes=raw_bytes,seal=seal,receipt=signed,
        )


def test_full_77_row_synthetic_review_requires_exact_individual_coverage():
    packet,_,_,ctx,_,seal=case()
    collections={"stream_one":[],"stream_two":[]}
    for number in range(77):
        name="stream_one" if number % 2 else "stream_two"
        collections[name].append({
            "source_row_sha256":hashlib.sha256(
                ("synthetic-event-"+str(number)).encode(),
            ).hexdigest(),
            "source_fields_unreviewed":{
                "private_opaque_value":"not for generation",
            },
        })
    packet["collections"]=collections
    packet["row_counts"]={name:len(values) for name,values in collections.items()}
    raw_bytes=json.dumps(packet,sort_keys=True).encode()
    packet_sha=hashlib.sha256(raw_bytes).hexdigest()
    seal["plaintext_sha256"]=packet_sha
    review=draft(packet,packet_sha)
    review.update(
        tenant_id=ctx["tenant_id"],
        semantic_agent_version=ctx["semantic_agent_version"],
        context_fingerprint=normalize_context_snapshot(ctx)["fingerprint"],
        reviewer_id="independent-synthetic-reviewer",
    )
    for item in review["rows"]:
        item.update(classification="FORBIDDEN",
                    destinations=[{"collection":"rules","index":0}])
    receipt=receipt_for(packet,packet_sha,review)
    result=verified_review(
        packet=packet,packet_sha256=packet_sha,
        source_packet_bytes=raw_bytes,trusted_seal=seal,review=review,
        raw_context=ctx,approval_receipt=receipt,
        verifier_key=TEST_VERIFIER_KEY,
    )
    assert result["reviewed_rows"]==77
    assert result["classifications"]["FORBIDDEN"]==77
    assert result["activation_authorized"] is False
    assert "private_opaque_value" not in json.dumps(result)
    incomplete=deepcopy(review)
    incomplete["rows"].pop()
    assert_rejected(
        packet=packet,packet_sha=packet_sha,review=incomplete,
        ctx=ctx,raw_bytes=raw_bytes,seal=seal,
        receipt=receipt_for(packet,packet_sha,incomplete),
    )
    duplicated=deepcopy(review)
    duplicated["rows"][-1]=deepcopy(duplicated["rows"][0])
    assert_rejected(
        packet=packet,packet_sha=packet_sha,review=duplicated,
        ctx=ctx,raw_bytes=raw_bytes,seal=seal,
        receipt=receipt_for(packet,packet_sha,duplicated),
    )




def test_private_cli_checks_signed_review_without_touching_financial_sql():
    from scripts.operations.g5_financial_crosswalk_review_cli import (
        verify_private_review, private_bytes,
    )
    packet,packet_sha,review,ctx,raw_bytes,seal=case()
    approval=receipt_for(packet,packet_sha,review)
    with TemporaryDirectory() as base:
        root=Path(base)
        if os.name != "posix":
            return
        root.chmod(0o700)
        files = {
            "manifest.json": {
                "contract":"g5-private-source-review-manifest-v1",
                "status":"ENCRYPTED_NOT_APPROVED",
                "approved_for_generation":False,
                "approved_for_import":False,
                "financial_sql_executed":False,
                "context_activated":False,
                "versions":[seal],
            },
            "source-packet.json": raw_bytes,
            "n8n-binding.json": {
                "contract": "legacy-semantic-static-coupling-audit-v1",
                "status": "SOURCE_REVIEW_ONLY_NOT_FINANCIAL_EQUIVALENCE",
                "node_count": 68,
                "pinned_source_version_reconciliation": {
                    "status": "PINNED_VERSION_MATCHES_SEALED_G5",
                    "pinned_version_hashes": [seal["source_version_sha256"]],
                    "matching_source_version_sha256": seal["source_version_sha256"],
                    "matching_manifest_row_counts": seal["row_counts"],
                    "accounting_definition_approved": False,
                    "source_plaintext_reviewed": False,
                },
            },
            "review.json":review,
            "context.json":ctx,
            "approval.json":approval,
            "verify-key.txt":TEST_VERIFIER_KEY.hex().encode("ascii"),
        }
        ciphertext=b"synthetic-ciphertext-do-not-use"
        seal["ciphertext_sha256"]=hashlib.sha256(ciphertext).hexdigest()
        # A manifest seal is independent from the reviewed plain packet.
        files["ciphertext-file"]=ciphertext
        for name,payload in files.items():
            filename=seal["file"] if name=="ciphertext-file" else name
            path=root/filename
            encoded=payload if isinstance(payload,bytes) else json.dumps(
                payload,sort_keys=True,
            ).encode()
            path.write_bytes(encoded)
            path.chmod(0o600)
        def check():
            return verify_private_review(
                manifest_path=root/"manifest.json",
                source_version_sha256=seal["source_version_sha256"],
                packet_path=root/"source-packet.json",
                n8n_binding_evidence_path=root/"n8n-binding.json",
                review_path=root/"review.json",
                context_path=root/"context.json",
                approval_path=root/"approval.json",
                verification_key_path=root/"verify-key.txt",
            )
        result=check()
        assert result["status"]=="G5_FINANCIAL_MAPPING_CANDIDATE_NOT_ACTIVATED"
        assert result["activation_authorized"] is False
        assert private_bytes(root/"source-packet.json")==raw_bytes
        n8n_path = root/"n8n-binding.json"
        original = n8n_path.read_bytes()
        changed = json.loads(original)
        changed["pinned_source_version_reconciliation"]["pinned_version_hashes"] = ["a"*64]
        n8n_path.write_text(json.dumps(changed))
        try:
            check()
        except FinancialReviewBlocked:
            pass
        else:
            raise AssertionError("Wrong n8n pinned source version accepted")
        n8n_path.write_bytes(original)
        (root/"verify-key.txt").chmod(0o644)
        try:
            check()
        except FinancialReviewBlocked:
            pass
        else:
            raise AssertionError("World-readable signature verifier accepted")
        (root/"verify-key.txt").chmod(0o600)
        (root/"approval.json").write_text('{"wrong":"signature"}')
        try:
            check()
        except FinancialReviewBlocked:
            pass
        else:
            raise AssertionError("Untrusted independent approval accepted")


if __name__ == "__main__":
    tests=sorted((n,fn) for n,fn in globals().items()
                 if n.startswith("test_") and callable(fn))
    for name,fn in tests:
        fn()
        print("PASS",name)
    print("TOTAL_TESTS",len(tests))

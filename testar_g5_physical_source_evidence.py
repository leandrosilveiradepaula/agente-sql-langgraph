"""Generic G5 physical identity proof. All tables/values are synthetic."""
from __future__ import annotations

import hashlib
import hmac
import json
from copy import deepcopy

from app.domain.context_normalizer import normalize_context_snapshot
from scripts.operations.g5_financial_crosswalk_review import (
    FinancialReviewBlocked, digest, verified_review,
)
from scripts.operations.g5_physical_source_evidence import (
    physical_approval_claims,
)
from testar_g5_financial_crosswalk_review import (
    TEST_VERIFIER_KEY, case, receipt_for,
)


def fixture(other: bool = False):
    packet, packet_sha, review, context, raw_bytes, seal = case(other=other)
    catalog = context["catalogo"][0]
    schema = catalog["schema_name"]
    table = catalog["table_name"]
    catalog["columns"] = [
        {"name": "id", "data_type": "integer", "nullable": False},
        {"name": "value", "data_type": "numeric", "nullable": False},
        {"name": "event_date", "data_type": "date", "nullable": False},
    ]
    snapshot = {
        "contract": "p3-metadata-snapshot-v1",
        "sql_executed": False,
        "llm_calls": 0,
        "physical": [
            [schema, table, "id", "integer"],
            [schema, table, "value", "numeric"],
            [schema, table, "event_date", "date"],
            ["other_schema_with_same_table", table, "value", "numeric"],
        ],
    }
    p3_bytes = (json.dumps(snapshot, sort_keys=True, separators=(",", ":")) + "\n").encode()
    packet["origin"]["p3_snapshot_sha256"] = hashlib.sha256(p3_bytes).hexdigest()
    source_row = packet["collections"]["semantic_rules"][0]["source_row_sha256"]
    packet["physical_identifier_hints_unapproved"] = [{
        "collection": "semantic_rules",
        "source_record_sha256": source_row,
        "source_version_sha256": packet["origin"]["source_version_sha256"],
        "source_table_ref": table,
        "source_column_ref": "value",
        "physical_schema_candidate": None,
        "candidate_status": "AMBIGUOUS_TABLE_NAME",
        "column_status": "COLUMN_UNRESOLVED",
        "accounting_equivalence": "NOT_ATTESTED",
    }]
    raw_bytes = json.dumps(packet, sort_keys=True).encode()
    packet_sha = hashlib.sha256(raw_bytes).hexdigest()
    seal["plaintext_sha256"] = packet_sha
    review["packet_plaintext_sha256"] = packet_sha
    review["context_fingerprint"] = normalize_context_snapshot(context)["fingerprint"]
    review["physical_binding_decisions"] = [{
        "collection": "semantic_rules",
        "source_row_sha256": source_row,
        "qualified_table": f"{schema}.{table}",
        "target_column": "value",
    }]
    return packet, packet_sha, review, context, raw_bytes, seal, p3_bytes


def approval(packet, packet_sha, review, context, p3_bytes):
    receipt = receipt_for(packet, packet_sha, review)
    physical = physical_approval_claims(
        packet=packet, review=review,
        approved_catalog=normalize_context_snapshot(context)["table_catalog"],
        p3_bytes=p3_bytes,
    )
    assert physical["physical_binding_rows"] == 1
    receipt["claims"].update(physical)
    receipt["hmac_sha256"] = hmac.new(
        TEST_VERIFIER_KEY,
        digest(receipt["claims"]).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return receipt


def verify(t, receipt=None, *, p3_bytes=None):
    packet, packet_sha, review, context, raw_bytes, seal, original = t
    return verified_review(
        packet=packet,
        packet_sha256=packet_sha,
        source_packet_bytes=raw_bytes,
        trusted_seal=seal,
        review=review,
        raw_context=context,
        approval_receipt=receipt if receipt is not None else approval(
            packet, packet_sha, review, context, original,
        ),
        verifier_key=TEST_VERIFIER_KEY,
        p3_snapshot_bytes=original if p3_bytes is None else p3_bytes,
    )


def deny(function):
    try:
        function()
    except FinancialReviewBlocked:
        return
    raise AssertionError("Unproven physical identity accepted")


def test_two_tenants_explicitly_disambiguate_identical_physical_table_names():
    for other in (False, True):
        t = fixture(other)
        result = verify(t)
        assert result["status"] == "G5_FINANCIAL_MAPPING_CANDIDATE_NOT_ACTIVATED"
        assert result["financial_sql_executed"] is False
        assert result["context_persisted"] is False
        assert result["activation_authorized"] is False
        assert result["reviewed_rows"] == 1
        assert "source_fields_unreviewed" not in json.dumps(result)


def test_p3_snapshot_must_be_exactly_sealed_even_with_signed_review():
    t = fixture()
    receipt = approval(t[0], t[1], t[2], t[3], t[6])
    deny(lambda: verify(t, receipt, p3_bytes=b"no snapshot"))
    deny(lambda: verified_review(
        packet=t[0], packet_sha256=t[1],
        source_packet_bytes=t[4], trusted_seal=t[5],
        review=t[2], raw_context=t[3],
        approval_receipt=receipt, verifier_key=TEST_VERIFIER_KEY,
    ))


def test_ambiguous_table_selection_requires_exact_approved_schema():
    t = fixture()
    bad = deepcopy(t[2])
    bad["physical_binding_decisions"][0]["qualified_table"] = (
        "other_schema_with_same_table." + t[3]["catalogo"][0]["table_name"]
    )
    deny(lambda: physical_approval_claims(
        packet=t[0], review=bad,
        approved_catalog=normalize_context_snapshot(t[3])["table_catalog"],
        p3_bytes=t[6],
    ))


def test_wrong_column_case_and_type_are_never_accepted():
    t = fixture()
    bad = deepcopy(t[2])
    bad["physical_binding_decisions"][0]["target_column"] = "VALUE"
    deny(lambda: physical_approval_claims(
        packet=t[0], review=bad,
        approved_catalog=normalize_context_snapshot(t[3])["table_catalog"],
        p3_bytes=t[6],
    ))
    changed_context = deepcopy(t[3])
    changed_context["catalogo"][0]["columns"][1]["data_type"] = "text"
    deny(lambda: physical_approval_claims(
        packet=t[0], review=t[2],
        approved_catalog=normalize_context_snapshot(changed_context)["table_catalog"],
        p3_bytes=t[6],
    ))


def test_independent_signature_must_commit_to_physical_choice():
    t = fixture()
    receipt = approval(t[0], t[1], t[2], t[3], t[6])
    altered = deepcopy(receipt)
    altered["claims"]["physical_binding_decisions_sha256"] = "0" * 64
    deny(lambda: verify(t, altered))
    altered = deepcopy(receipt)
    altered["claims"].pop("p3_snapshot_sha256")
    deny(lambda: verify(t, altered))


def test_no_llm_or_sql_in_approved_metadata_snapshot():
    t = fixture()
    modified = json.loads(t[6])
    modified["sql_executed"] = True
    tampered = json.dumps(modified, sort_keys=True).encode()
    deny(lambda: physical_approval_claims(
        packet=t[0], review=t[2],
        approved_catalog=normalize_context_snapshot(t[3])["table_catalog"],
        p3_bytes=tampered,
    ))


def test_missing_or_duplicate_decision_is_blocked():
    t = fixture()
    missing = deepcopy(t[2])
    del missing["physical_binding_decisions"]
    deny(lambda: physical_approval_claims(
        packet=t[0], review=missing,
        approved_catalog=normalize_context_snapshot(t[3])["table_catalog"],
        p3_bytes=t[6],
    ))
    duplicate = deepcopy(t[2])
    duplicate["physical_binding_decisions"] *= 2
    deny(lambda: physical_approval_claims(
        packet=t[0], review=duplicate,
        approved_catalog=normalize_context_snapshot(t[3])["table_catalog"],
        p3_bytes=t[6],
    ))


def _historic_changed_table(*, alternate=False, table_only=True):
    """Synthetic old customer layout differs from P3 in schema/table/column."""
    packet, packet_sha, review, ctx, raw, seal, p3 = fixture(other=alternate)
    fields = packet["collections"]["semantic_rules"][0]["source_fields_unreviewed"]
    hint = packet["physical_identifier_hints_unapproved"][0]
    if table_only:
        fields["schema_name"] = "old_ledger_schema"
        fields["table_name"] = "old_fact_table"
        hint["source_table_ref"] = None  # Real G5 table-catalog hint shape.
        hint["source_column_ref"] = None
        review["physical_binding_decisions"][0]["target_column"] = None
    else:
        fields["target_table"] = "old_fact_table"
        fields["target_column"] = "old_measure"
        hint["source_table_ref"] = "old_fact_table"
        hint["source_column_ref"] = "old_measure"
        review["physical_binding_decisions"][0]["target_column"] = "value"
    review["physical_binding_decisions"][0][
        "physical_remap_evidence_sha256"
    ] = hashlib.sha256(b"synthetic independent financial reviewer evidence").hexdigest()
    raw = json.dumps(packet, sort_keys=True).encode()
    packet_sha = hashlib.sha256(raw).hexdigest()
    seal["plaintext_sha256"] = packet_sha
    review["packet_plaintext_sha256"] = packet_sha
    return packet, packet_sha, review, ctx, raw, seal, p3


def test_sealed_table_catalog_row_with_null_hint_can_be_reviewed_when_renamed():
    for alt in (False, True):
        t = _historic_changed_table(alternate=alt)
        result = verify(t)
        assert result["status"] == "G5_FINANCIAL_MAPPING_CANDIDATE_NOT_ACTIVATED"
        assert result["context_persisted"] is False
        assert result["activation_authorized"] is False
        assert result["financial_sql_executed"] is False


def test_renamed_legacy_column_requires_independently_signed_remap_evidence():
    t = _historic_changed_table(table_only=False)
    result = verify(t)
    assert result["status"] == "G5_FINANCIAL_MAPPING_CANDIDATE_NOT_ACTIVATED"
    missing = deepcopy(t[2])
    missing["physical_binding_decisions"][0].pop(
        "physical_remap_evidence_sha256"
    )
    deny(lambda: physical_approval_claims(
        packet=t[0], review=missing,
        approved_catalog=normalize_context_snapshot(t[3])["table_catalog"],
        p3_bytes=t[6],
    ))
    bogus = deepcopy(t[2])
    bogus["physical_binding_decisions"][0][
        "physical_remap_evidence_sha256"
    ] = "bad-justification"
    deny(lambda: physical_approval_claims(
        packet=t[0], review=bogus,
        approved_catalog=normalize_context_snapshot(t[3])["table_catalog"],
        p3_bytes=t[6],
    ))


def test_physical_remap_evidence_is_bound_to_independent_hmac_receipt():
    t = _historic_changed_table()
    original_receipt = approval(t[0], t[1], t[2], t[3], t[6])
    altered = deepcopy(t[2])
    altered["physical_binding_decisions"][0][
        "physical_remap_evidence_sha256"
    ] = hashlib.sha256(b"changed explanation").hexdigest()
    p, sha, _review, ctx, raw, seal, p3 = t
    deny(lambda: verified_review(
        packet=p, packet_sha256=sha, source_packet_bytes=raw,
        trusted_seal=seal, review=altered, raw_context=ctx,
        approval_receipt=original_receipt,
        verifier_key=TEST_VERIFIER_KEY, p3_snapshot_bytes=p3,
    ))


def test_source_hint_cannot_replace_original_private_table_name():
    t = _historic_changed_table()
    bad = deepcopy(t[0])
    bad["physical_identifier_hints_unapproved"][0][
        "source_table_ref"
    ] = "unrelated_table"
    deny(lambda: physical_approval_claims(
        packet=bad, review=t[2],
        approved_catalog=normalize_context_snapshot(t[3])["table_catalog"],
        p3_bytes=t[6],
    ))


def test_exact_source_binding_rejects_spurious_remap_evidence():
    t = fixture()
    review = deepcopy(t[2])
    review["physical_binding_decisions"][0][
        "physical_remap_evidence_sha256"
    ] = hashlib.sha256(b"not actually remapped").hexdigest()
    deny(lambda: physical_approval_claims(
        packet=t[0], review=review,
        approved_catalog=normalize_context_snapshot(t[3])["table_catalog"],
        p3_bytes=t[6],
    ))


if __name__ == "__main__":
    tests = sorted(
        (name, func) for name, func in globals().items()
        if name.startswith("test_") and callable(func)
    )
    for name, fn in tests:
        fn()
        print("PASS", name)
    print("TOTAL_TESTS", len(tests))

"""No-network synthetic ASGI transport tests for private Product-only G5 review."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.operations.g5_owner_review_asgi import G5ReviewAsgiApplication
from testar_g5_owner_review_http_contract import setup, TOKEN


def run(app, *, path="/v1/internal/g5-owner-review/status", method="GET",
        query=b"", body=b"", headers=None, scheme="https", chunks=None):
    config=app._review.config
    h=[
        (b"authorization",("Bearer "+TOKEN).encode()),
        (b"x-g5-product-role",b"admin"),
        (b"x-g5-product-tenant",config.expected_tenant_id.encode()),
        (b"x-g5-product-actor",b"synthetic_user"),
        (b"accept",b"application/json"),
    ]
    if method=="POST":h.append((b"content-type",b"application/json"))
    if headers is not None:h.extend(headers)
    if chunks is None:chunks=[body]
    events=[
        {"type":"http.request","body":part,"more_body":i<len(chunks)-1}
        for i,part in enumerate(chunks)
    ]
    recorded=[]
    async def receive():
        if not events:
            raise ValueError("unexpected read")
        return events.pop(0)
    async def send(message):
        recorded.append(message)
    scope={
        "type":"http","path":path,"method":method,
        "scheme":scheme,"root_path":"","query_string":query,
        "headers":h,
    }
    asyncio.run(app(scope,receive,send))
    assert len(recorded)==2
    assert recorded[0]["type"]=="http.response.start"
    assert recorded[1]["type"]=="http.response.body"
    content=recorded[1]["body"]
    response=json.loads(content)
    return recorded[0]["status"],response,recorded


def test_disabled_adapter_no_private_files_touched():
    with TemporaryDirectory() as path:
        service,files=setup(Path(path),enabled=False)
        app=G5ReviewAsgiApplication(service.config)
        code,body,_=run(app)
        assert code==404 and body["error"]=="G5_REVIEW_DISABLED"
        assert not service.config.session.exists()


def test_status_and_item_through_exact_product_transport_two_tenants():
    if os.name!="posix":return
    for alt in (False,True):
        with TemporaryDirectory() as path:
            service,files=setup(Path(path),alt=alt)
            app=G5ReviewAsgiApplication(service.config)
            code,status,wire=run(app)
            assert code==200 and status["status"]=="unapproved"
            assert status["counts"]["financial_total"]==1
            assert status["accounting_approved"] is False
            assert status["sql_executed"] is False
            assert b"no-store" in dict(wire[0]["headers"])[b"cache-control"]
            code,item,_=run(app,path="/v1/internal/g5-owner-review/item",
                query=b"kind=financial&index=0")
            assert code==200
            assert item["source"]
            assert item["kind"]=="financial"
            assert item["accounting_approved"] is False
            code,physical,_=run(app,path="/v1/internal/g5-owner-review/item",
                query=b"kind=physical&index=0")
            assert code==200 and physical["decision"]["physical_options_unapproved"]


def test_post_explicit_draft_write_then_old_revision_is_blocked():
    if os.name!="posix":return
    with TemporaryDirectory() as path:
        service,files=setup(Path(path))
        app=G5ReviewAsgiApplication(service.config)
        _,initial,_=run(app)
        data={
            "kind":"financial","index":0,
            "expected_revision":initial["revision"],
            "decision":{"classification":"STRUCTURAL","destinations":[]},
        }
        raw=json.dumps(data).encode()
        code,saved,_=run(app,path="/v1/internal/g5-owner-review/decision",
            method="POST",body=raw)
        assert code==200 and saved["status"]=="draft_saved"
        assert saved["audit_sequence"]==1
        assert saved["sql_executed"] is False
        code,conflict,_=run(app,path="/v1/internal/g5-owner-review/decision",
            method="POST",body=raw)
        assert code==409 and conflict["status"]=="blocked"
        code,current,_=run(app)
        assert code==200
        assert current["counts"]["financial_classified"]==1


def test_malformed_queries_duplicates_and_untrusted_methods_fail_closed():
    if os.name!="posix":return
    with TemporaryDirectory() as path:
        service,files=setup(Path(path))
        app=G5ReviewAsgiApplication(service.config)
        base="/v1/internal/g5-owner-review/item"
        for query in (
            b"kind=financial&index=0&index=1",
            b"kind=financial&index=0&path=%2Fetc%2Fpasswd",
            b"kind=financial&index=-1",
            b"kind=financial&index=000",
            b"kind=physical&index=abc",
        ):
            code,body,_=run(app,path=base,query=query)
            assert code==400
        code,body,_=run(app,path=base,query=b"kind=financial&index=0",
            headers=[(b"authorization",b"Bearer "+TOKEN.encode())])
        assert code==400
        code,body,_=run(app,method="POST")
        assert code==404
        code,body,_=run(app,path=base,query=b"kind=financial&index=0",
            headers=[(b"cookie",b"credential=untrusted")])
        assert code==400
        assert not service.config.session.exists()


def test_insecure_transport_bodies_and_unapproved_input_never_commit():
    if os.name!="posix":return
    with TemporaryDirectory() as path:
        service,files=setup(Path(path))
        app=G5ReviewAsgiApplication(service.config)
        code,body,_=run(app,scheme="http")
        assert code==403
        code,body,_=run(app,path="/v1/internal/g5-owner-review/item",
            query=b"kind=financial&index=0",body=b"bad-data")
        assert code==400
        code,body,_=run(app,path="/v1/internal/g5-owner-review/decision",
            method="POST",body=b"z"*9000)
        assert code==400
        code,body,_=run(app,path="/v1/internal/g5-owner-review/decision",
            method="POST",body=b'{"accounting_approved":true}')
        assert code==409 or code==400
        code,body,_=run(app,path="/v1/internal/g5-owner-review/decision",
            method="POST",body=b"not json")
        assert code==400
        assert not service.config.session.exists()


def test_duplicate_json_keys_are_rejected_before_financial_draft_write():
    if os.name!="posix":return
    with TemporaryDirectory() as path:
        service,files=setup(Path(path))
        app=G5ReviewAsgiApplication(service.config)
        _,current,_=run(app)
        body=(
            '{"kind":"financial","kind":"physical","index":0,'
            '"expected_revision":"'+current["revision"]+'",'
            '"decision":{"classification":"STRUCTURAL","destinations":[]}}'
        ).encode("ascii")
        code,response,_=run(app,path="/v1/internal/g5-owner-review/decision",
            method="POST",body=body)
        assert code==400
        assert not service.config.session.exists()


def test_chunked_post_rejected_for_extra_non_json_fields():
    if os.name!="posix":return
    with TemporaryDirectory() as path:
        service,files=setup(Path(path))
        app=G5ReviewAsgiApplication(service.config)
        _,initial,_=run(app)
        data=json.dumps({
            "kind":"financial","index":0,
            "expected_revision":initial["revision"],
            "decision":{"classification":"STRUCTURAL","destinations":[]},
            "sql_executed":True,
        }).encode()
        code,body,_=run(app,path="/v1/internal/g5-owner-review/decision",
            method="POST",chunks=[data[:35],data[35:]])
        assert code==400
        assert not service.config.session.exists()


if __name__=="__main__":
    tests=sorted((key,fn) for key,fn in globals().items() if key.startswith("test_") and callable(fn))
    for name,fn in tests:
        fn()
        print("PASS",name)
    print("TOTAL_TESTS",len(tests))

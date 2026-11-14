"""Standalone ASGI adapter for the private, explicitly opted-in G5 review.

NO server listen, registry mutation, deploy, credentials, or SQL execution.
Do not mount this adapter in the ordinary SQL/shadow ASGI application.
It is intended only for a separately authenticated private Product BFF
transport, after operator approval and network segregation.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl

from scripts.operations.g5_owner_review_http_contract import (
    PrivateG5OwnerReviewService,
    ReviewConfig,
    _deny,
)

_ROUTES = frozenset({
    "/v1/internal/g5-owner-review/status",
    "/v1/internal/g5-owner-review/item",
    "/v1/internal/g5-owner-review/decision",
})
_MAX_BODY = 8192
_MAX_HEADERS = 20
_MAX_HEADER_VALUE = 2048
_MAX_RESPONSE = 400_000
_ALLOW_HEADERS = frozenset({
    "authorization",
    "accept",
    "content-type",
    "content-length",
    "x-g5-product-role",
    "x-g5-product-tenant",
    "x-g5-product-actor",
    "host",
})
_NO_BODY = frozenset({
    "/v1/internal/g5-owner-review/status",
    "/v1/internal/g5-owner-review/item",
})


def _no_duplicate_json_fields(pairs: list[tuple[str, Any]]) -> dict:
    output={}
    for key,value in pairs:
        if key in output:
            raise ValueError("duplicate JSON field")
        output[key]=value
    return output


class G5ReviewAsgiApplication:
    """Strict transport. Backend independently authenticates every request."""

    def __init__(self, config: ReviewConfig) -> None:
        self._review = PrivateG5OwnerReviewService(config)

    async def __call__(self, scope: Mapping, receive: Any, send: Any) -> None:
        if scope.get("type") == "lifespan":
            while True:
                m=await receive()
                if m.get("type")=="lifespan.startup":
                    await send({"type":"lifespan.startup.complete"})
                elif m.get("type")=="lifespan.shutdown":
                    await send({"type":"lifespan.shutdown.complete"})
                    return
                else:
                    return
        if scope.get("type") == "websocket":
            await send({"type":"websocket.close","code":1008})
            return
        if scope.get("type") != "http":
            return
        try:
            output=await self._process(scope,receive)
        except Exception:
            output=_deny(400,"G5_REVIEW_INVALID_TRANSPORT")
        await _send(send,output)

    async def _process(self, scope: Mapping, receive: Any) -> dict:
        # Default OFF prevents any private file read and does not even parse
        # untrusted browser input.
        if not self._review.config.enabled:
            return _deny(404,"G5_REVIEW_DISABLED")
        path=scope.get("path")
        method=scope.get("method")
        if (
            not isinstance(path,str) or path not in _ROUTES
            or method not in ("GET","POST")
            or (path in _NO_BODY and method!="GET")
            or (path not in _NO_BODY and method!="POST")
            or scope.get("root_path") not in (None,"")
        ):
            return _deny(404,"G5_REVIEW_ROUTE_BLOCKED")
        if scope.get("scheme") not in ("https",):
            # HTTPS is mandatory on the isolated ASGI ingress; the private
            # proxy must provide trusted ASGI scope scheme, not X-Forwarded-*.
            return _deny(403,"G5_REVIEW_HTTPS_REQUIRED")
        raw_headers=scope.get("headers")
        if not isinstance(raw_headers,list) or len(raw_headers)>_MAX_HEADERS:
            return _deny(400,"G5_REVIEW_HEADERS_INVALID")
        header_map={}
        for entry in raw_headers:
            if (
                not isinstance(entry,(tuple,list)) or len(entry)!=2
                or not isinstance(entry[0],bytes) or not isinstance(entry[1],bytes)
                or len(entry[0])>64 or len(entry[1])>_MAX_HEADER_VALUE
            ):
                return _deny(400,"G5_REVIEW_HEADERS_INVALID")
            try:
                name=entry[0].decode("ascii").casefold()
                value=entry[1].decode("ascii")
            except UnicodeError:
                return _deny(400,"G5_REVIEW_HEADERS_INVALID")
            if name not in _ALLOW_HEADERS or name in header_map:
                return _deny(400,"G5_REVIEW_FORBIDDEN_HEADER")
            header_map[name]=value
        if header_map.get("accept") not in (None,"application/json"):
            return _deny(406,"G5_REVIEW_ACCEPT_REQUIRED")
        if method=="POST" and header_map.get("content-type")!="application/json":
            return _deny(415,"G5_REVIEW_JSON_REQUIRED")
        actor=header_map.get("x-g5-product-actor","")
        query_raw=scope.get("query_string",b"")
        if not isinstance(query_raw,bytes) or len(query_raw)>400:
            return _deny(400,"G5_REVIEW_QUERY_INVALID")
        if path in _NO_BODY:
            body=await _read_body(receive)
            if body:
                return _deny(400,"G5_REVIEW_GET_BODY_FORBIDDEN")
            if path.endswith("/status"):
                if query_raw:
                    return _deny(400,"G5_REVIEW_STATUS_QUERY_FORBIDDEN")
                params=None
            else:
                try:
                    pairs=parse_qsl(query_raw.decode("ascii"),keep_blank_values=True,strict_parsing=True)
                except (ValueError, UnicodeError):
                    return _deny(400,"G5_REVIEW_ITEM_QUERY_INVALID")
                if len(pairs)!=2 or {k for k,v in pairs}!={"kind","index"}:
                    return _deny(400,"G5_REVIEW_ITEM_QUERY_INVALID")
                vals=dict(pairs)
                if (
                    vals["kind"] not in ("financial","physical")
                    or not vals["index"].isascii() or not vals["index"].isdigit()
                    or len(vals["index"])>6 or int(vals["index"])>100000
                    or (len(vals["index"])>1 and vals["index"][0]=="0")
                ):
                    return _deny(400,"G5_REVIEW_ITEM_QUERY_INVALID")
                params={"kind":vals["kind"],"index":int(vals["index"])}
        else:
            if query_raw:
                return _deny(400,"G5_REVIEW_POST_QUERY_FORBIDDEN")
            body=await _read_body(receive)
            if not body:
                return _deny(400,"G5_REVIEW_BODY_REQUIRED")
            try:
                pairs=json.loads(body,object_pairs_hook=_no_duplicate_json_fields)
            except (ValueError,UnicodeError):
                return _deny(400,"G5_REVIEW_BODY_INVALID")
            if not isinstance(pairs,dict):
                return _deny(400,"G5_REVIEW_BODY_INVALID")
            params=pairs
        # Pure handler enforces independent admin/tenant/token authorization.
        return self._review.handle(
            method=method,path=path,headers=header_map,
            actor_id=actor,request=params,
        )


async def _read_body(receive: Any) -> bytes:
    chunks=[]
    total=0
    for _ in range(16):
        event=await receive()
        if not isinstance(event,Mapping) or event.get("type")!="http.request":
            raise ValueError("invalid asgi body")
        data=event.get("body",b"")
        more=event.get("more_body",False)
        if not isinstance(data,bytes) or type(more) is not bool:
            raise ValueError("invalid asgi body")
        total+=len(data)
        if total>_MAX_BODY:
            raise ValueError("body too large")
        chunks.append(data)
        if not more:return b"".join(chunks)
    raise ValueError("too many chunks")


async def _send(send: Any, output: Mapping) -> None:
    body=output.get("body",b"")
    status=output.get("status_code")
    raw=output.get("headers",{})
    if (
        not isinstance(body,bytes) or len(body)>_MAX_RESPONSE
        or type(status) is not int or not 100<=status<=599
        or not isinstance(raw,Mapping)
    ):
        output=_deny(413,"G5_REVIEW_RESPONSE_LIMIT")
        body=output["body"]
        status=output["status_code"]
        raw=output["headers"]
    headers=[(str(k).lower().encode("ascii"),str(v).encode("ascii"))
             for k,v in raw.items()]
    headers.append((b"content-length",str(len(body)).encode("ascii")))
    await send({"type":"http.response.start","status":status,"headers":headers})
    await send({"type":"http.response.body","body":body,"more_body":False})

"""G5/P3 private review backend contract for an authenticated Product BFF.

This module does NOT start a server, open a network port, or register any
runtime endpoint. All operations default to DISABLED and require an explicit,
isolated admin S2S credential. The Next.js Product is the authority for user
authentication and policies. No business interpretation or SQL execution.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import stat
from datetime import datetime, timezone
try:
    import fcntl
except ImportError:  # Windows CI import; operational review is POSIX only.
    fcntl = None
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from scripts.operations.g5_financial_crosswalk_review import FinancialReviewBlocked
from scripts.operations.g5_owner_review_tui import (
    atomic_private_update, counts, initial_state, private_file_location,
    validate_state,
)
from scripts.operations.g5_p3_original_physical_worklist import physical_index
from scripts.operations.g5_targeted_financial_review_offline import (
    select_verified_seal, verify_decrypted_packet,
)
from scripts.operations.g5_financial_crosswalk_review_cli import (
    private_bytes, private_json,
)

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_STATUS = "/v1/internal/g5-owner-review/status"
_ITEM = "/v1/internal/g5-owner-review/item"
_DECISION = "/v1/internal/g5-owner-review/decision"


@dataclass(frozen=True)
class ReviewConfig:
    manifest: Path
    version_sha256: str
    packet: Path
    p3: Path
    session: Path
    s2s_token: str
    expected_tenant_id: str = ""
    enabled: bool = False


def _response(status: int, data: Mapping) -> dict[str, Any]:
    return {
        "status_code": status,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store, private, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
        },
        "body": json.dumps(data, ensure_ascii=True, separators=(",", ":")).encode(),
    }


def _deny(status: int, code: str) -> dict[str, Any]:
    return _response(status, {"status": "blocked", "error": code, "sql_executed": False})


def _sha(payload: Mapping) -> str:
    data=json.dumps(payload,sort_keys=True,ensure_ascii=True,separators=(",",":")).encode()
    return hashlib.sha256(data).hexdigest()


def _int(value: object, maximum: int) -> int | None:
    if type(value) is int and 0 <= value < maximum:
        return value
    return None


def _headers(raw: Mapping[str, str]) -> dict[str, str]:
    return {str(k).casefold(): str(v) for k,v in raw.items()}


def _private_audit_path(session: Path) -> Path:
    return session.with_name(session.name + ".audit.jsonl")


def _append_audit(path: Path, obj: Mapping) -> None:
    """Append-only, no business data; fsync before acknowledging."""
    directory=path.parent
    if (
        directory.is_symlink() or stat.S_IMODE(directory.stat().st_mode)!=0o700
        or directory.stat().st_uid!=os.geteuid() or path.is_symlink()
    ):
        raise FinancialReviewBlocked("G5_REVIEW_AUDIT_LOCATION_UNSAFE")
    fd=os.open(str(path), os.O_WRONLY|os.O_APPEND|os.O_CREAT|
               getattr(os,"O_NOFOLLOW",0),0o600)
    try:
        if stat.S_IMODE(os.fstat(fd).st_mode)!=0o600:
            raise FinancialReviewBlocked("G5_REVIEW_AUDIT_PERMISSIONS_UNSAFE")
        line=(json.dumps(obj,sort_keys=True,ensure_ascii=True,separators=(",",":"))+"\n").encode()
        if len(line)>1200:
            raise FinancialReviewBlocked("G5_REVIEW_AUDIT_EVENT_OVERSIZE")
        os.write(fd,line)
        os.fsync(fd)
    finally:
        os.close(fd)


def _verify_audit(path: Path, state_revision: str) -> int:
    if not path.exists():
        if path.is_symlink():
            raise FinancialReviewBlocked("G5_REVIEW_AUDIT_SYMLINK")
        return 0
    if (
        path.is_symlink() or stat.S_IMODE(path.stat().st_mode)!=0o600
        or path.stat().st_size>250000 or not path.is_file()
    ):
        raise FinancialReviewBlocked("G5_REVIEW_AUDIT_UNTRUSTED")
    lines=path.read_bytes().splitlines()
    if len(lines)%2:
        raise FinancialReviewBlocked("G5_REVIEW_AUDIT_UNCOMMITTED")
    prev=None
    for index in range(0,len(lines),2):
        try:
            prepare=json.loads(lines[index]);commit=json.loads(lines[index+1])
        except ValueError:
            raise FinancialReviewBlocked("G5_REVIEW_AUDIT_CORRUPTED")
        if (
            not isinstance(prepare,dict) or not isinstance(commit,dict)
            or set(prepare)!={"kind","index","actor_id","prev_revision","next_revision","at","status"}
            or set(commit)!={"prepared_sha256","status"}
            or prepare["status"]!="prepared" or commit["status"]!="committed"
            or commit["prepared_sha256"]!=_sha(prepare)
            or (prev is not None and prepare["prev_revision"]!=prev)
        ):
            raise FinancialReviewBlocked("G5_REVIEW_AUDIT_CHAIN_INVALID")
        prev=prepare["next_revision"]
    if prev is not None and prev!=state_revision:
        raise FinancialReviewBlocked("G5_REVIEW_AUDIT_STATE_MISMATCH")
    return len(lines)//2


class PrivateG5OwnerReviewService:
    """Pure handler. Mounting and networking require a distinct human deployment gate."""

    def __init__(self, config: ReviewConfig) -> None:
        self.config=config

    def _load(self):
        config=self.config
        private_dir=config.packet.parent
        for f in (config.packet, config.p3):
            private_file_location(f,private_dir,exists=True)
        private_file_location(config.session,private_dir,exists=config.session.exists())
        manifest=private_json(config.manifest)
        seal=select_verified_seal(manifest,config.version_sha256)
        packet,report=verify_decrypted_packet(private_bytes(config.packet),seal)
        p3data=private_bytes(config.p3,3_000_000)
        physical,_=physical_index(p3data,packet["origin"]["p3_snapshot_sha256"])
        template=initial_state(packet,report["packet_plaintext_sha256"],p3data)
        state=private_json(config.session) if config.session.exists() else template
        validate_state(state,template,physical)
        _verify_audit(_private_audit_path(config.session),_sha(state))
        return packet,physical,template,state

    def _authorize(self,headers: Mapping[str,str],actor_id: str) -> bool:
        config=self.config
        if (
            not config.enabled or
            not isinstance(config.expected_tenant_id,str)
            or not _ID.fullmatch(config.expected_tenant_id)
            or not isinstance(config.s2s_token,str) or len(config.s2s_token)<32 or
            len(config.s2s_token)>512 or not _ID.fullmatch(actor_id)
        ):
            return False
        h=_headers(headers)
        if any(k in h for k in ("cookie","origin","x-forwarded-authorization","x-agent-sql")):
            return False
        if (
            h.get("x-g5-product-role") != "admin"
            or h.get("x-g5-product-tenant") != config.expected_tenant_id
        ):
            return False
        presented=h.get("authorization","")
        prefix="Bearer "
        if not presented.startswith(prefix) or len(presented)!=len(prefix)+len(config.s2s_token):
            return False
        return hmac.compare_digest(
            presented[len(prefix):].encode(),
            config.s2s_token.encode(),
        )

    def handle(self,*,method: str,path: str,headers: Mapping[str,str],
               actor_id: str,request: Mapping[str,Any] | None=None) -> dict[str,Any]:
        """Never accept filesystem paths, tenant identity or approval flags from request."""
        if not self.config.enabled:
            return _deny(404,"G5_REVIEW_DISABLED")
        if not self._authorize(headers,actor_id):
            return _deny(403,"G5_REVIEW_FORBIDDEN")
        if method not in ("GET","POST") or path not in (_STATUS,_ITEM,_DECISION):
            return _deny(404,"G5_REVIEW_ROUTE_NOT_FOUND")
        if path==_DECISION and method!="POST":
            return _deny(405,"G5_REVIEW_METHOD_INVALID")
        if path!=_DECISION and method!="GET":
            return _deny(405,"G5_REVIEW_METHOD_INVALID")
        try:
            packet,physical,template,state=self._load()
            revision=_sha(state)
            if path==_STATUS:
                if request is not None and request:
                    return _deny(400,"G5_REVIEW_BODY_NOT_ALLOWED")
                return _response(200,{
                    "status":"unapproved",
                    "counts":counts(state),
                    "revision":revision,
                    "source_version_sha256":packet["origin"]["source_version_sha256"],
                    "p3_snapshot_sha256":packet["origin"]["p3_snapshot_sha256"],
                    "accounting_approved":False,
                    "context_activated":False,
                    "sql_executed":False,
                })
            payload=request if isinstance(request,Mapping) else {}
            if path==_ITEM:
                if set(payload)!= {"kind","index"}:
                    return _deny(400,"G5_REVIEW_ITEM_SELECTOR_INVALID")
                kind=payload["kind"]
                if kind=="financial":
                    rows=state["workbook"]["financial_source_rows"]
                elif kind=="physical":
                    rows=state["workbook"]["physical_binding_decisions"]
                else:
                    return _deny(400,"G5_REVIEW_KIND_INVALID")
                index=_int(payload["index"],len(rows))
                if index is None:return _deny(404,"G5_REVIEW_ITEM_NOT_FOUND")
                item=deepcopy(rows[index])
                if kind=="financial":
                    matched=[
                        r["source_fields_unreviewed"]
                        for r in packet["collections"][item["collection"]]
                        if r["source_row_sha256"]==item["source_row_sha256"]
                    ]
                    if len(matched)!=1:
                        return _deny(409,"G5_REVIEW_SOURCE_MISSING")
                    original=matched[0]
                else:
                    original={
                        "schema":item["source_schema"],
                        "table":item["source_table"],
                        "column":item["source_column"],
                    }
                    item["physical_options_unapproved"]=[
                        {"qualified_table":schema+"."+table,
                         "columns":[{"name":c,"type":t}
                                    for c,t in sorted(cols.items())]}
                        for (schema,table),cols in sorted(physical.items())
                    ]
                    item["review_rationale"]=state["remap"]["remaps"][index]["review_rationale"]
                return _response(200,{
                    "status":"unapproved","kind":kind,"index":index,
                    "source":original,"decision":item,"revision":revision,
                    "accounting_approved":False,
                })
            if set(payload)!={"kind","index","decision","expected_revision"}:
                return _deny(400,"G5_REVIEW_DECISION_SHAPE_INVALID")
            if not isinstance(payload["expected_revision"],str) or not _SHA.fullmatch(payload["expected_revision"]):
                return _deny(400,"G5_REVIEW_REVISION_INVALID")
            if payload["expected_revision"] != revision:
                return _deny(409,"G5_REVIEW_STALE_REVISION")
            kind=payload["kind"]
            decision=payload["decision"]
            if not isinstance(decision,Mapping):
                return _deny(400,"G5_REVIEW_DECISION_INVALID")
            updated=deepcopy(state)
            if kind=="financial":
                rows=updated["workbook"]["financial_source_rows"]
                index=_int(payload["index"],len(rows))
                if index is None:return _deny(404,"G5_REVIEW_ITEM_NOT_FOUND")
                if set(decision)!={"classification","destinations"}:
                    return _deny(400,"G5_REVIEW_FINANCIAL_SHAPE_INVALID")
                rows[index]["classification"]=decision["classification"]
                rows[index]["destinations"]=decision["destinations"]
            elif kind=="physical":
                rows=updated["workbook"]["physical_binding_decisions"]
                index=_int(payload["index"],len(rows))
                if index is None:return _deny(404,"G5_REVIEW_ITEM_NOT_FOUND")
                if set(decision)!={"qualified_table","target_column","review_rationale"}:
                    return _deny(400,"G5_REVIEW_PHYSICAL_SHAPE_INVALID")
                rows[index]["qualified_table"]=decision["qualified_table"]
                rows[index]["target_column"]=decision["target_column"]
                updated["remap"]["remaps"][index]["qualified_table"]=decision["qualified_table"]
                updated["remap"]["remaps"][index]["target_column"]=decision["target_column"]
                updated["remap"]["remaps"][index]["review_rationale"]=decision["review_rationale"]
            else:
                return _deny(400,"G5_REVIEW_KIND_INVALID")
            updated["actions"]+=1
            validate_state(updated,template,physical)
            if os.name!="posix" or fcntl is None:
                return _deny(503,"G5_REVIEW_POSIX_REQUIRED")
            private_dir=self.config.packet.parent
            lock_path=private_dir/".g5-owner-review.lock"
            if lock_path.is_symlink():
                return _deny(409,"G5_REVIEW_LOCK_UNSAFE")
            fd=os.open(str(lock_path),os.O_RDWR|os.O_CREAT|
                       getattr(os,"O_NOFOLLOW",0),0o600)
            try:
                if stat.S_IMODE(os.fstat(fd).st_mode)!=0o600:
                    return _deny(409,"G5_REVIEW_LOCK_UNSAFE")
                fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
                _,_,baseline,latest=self._load()
                if _sha(latest)!=revision or baseline!=template:
                    return _deny(409,"G5_REVIEW_STALE_REVISION")
                seq=_verify_audit(_private_audit_path(self.config.session),revision)
                next_revision=_sha(updated)
                event={
                    "status":"prepared","kind":kind,"index":index,
                    "actor_id":actor_id,"prev_revision":revision,
                    "next_revision":next_revision,
                    "at":datetime.now(timezone.utc).isoformat(),
                }
                audit_path=_private_audit_path(self.config.session)
                _append_audit(audit_path,event)
                atomic_private_update(self.config.session,private_dir,updated)
                _append_audit(audit_path,{
                    "status":"committed","prepared_sha256":_sha(event),
                })
                return _response(200,{
                    "status":"draft_saved","revision":next_revision,
                    "audit_sequence":seq+1,"counts":counts(updated),
                    "accounting_approved":False,
                    "context_activated":False,"sql_executed":False,
                })
            finally:
                os.close(fd)
        except (FinancialReviewBlocked,OSError,ValueError,TypeError):
            return _deny(409,"G5_REVIEW_PRIVATE_STATE_INVALID")
        except Exception:
            return _deny(500,"G5_REVIEW_UNEXPECTED_ERROR")

"""Fixed, read-only J1 research evidence projections for the existing VPS MCP.

No arbitrary paths, process commands, network requests, financial SQL or secrets.
This module is deployed root-owned with the MCP broker, NOT imported from the
mutable Crypto Intelligence Agent checkout. All externally visible failures are
fixed codes, and data returned contains only counts / booleans / UTC milliseconds.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
from pathlib import Path
import pwd
import re
import sqlite3
import socket
import stat
import subprocess

DB = Path(
    "/home/cia-probe/agent/j1-rest-m3-20261109/canary/"
    "j1-rest-hourly-research.sqlite"
)
SERVICE = "cia-j1-rest-hourly.service"
TIMER = "cia-j1-rest-hourly.timer"
START = datetime(2026, 11, 9, 19, tzinfo=timezone.utc)
LAST = datetime(2026, 11, 10, 18, tzinfo=timezone.utc)
HOUR_MS = 3_600_000
EXPECT = tuple(int((START + timedelta(hours=n)).timestamp() * 1000) for n in range(24))
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_SYM = re.compile(r"[A-Z0-9]{1,28}USDT\Z")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,29})(?:\.[0-9]{1,24})?(?:[eE][+-]?[0-9]{1,3})?\Z")
MAX_DB_BYTES = 8 * 1024 * 1024
MAX_JOURNAL_BYTES = 256 * 1024


class Rejected(Exception):
    """Never expose exception internals, SQL, paths, symbols or raw logs."""


def _fail(reason: str) -> dict:
    return {"status": "blocked", "reason": reason,
            "trading_enabled": False, "marketwide_top50_verified": False}


def _run_fixed(argv: tuple[str, ...]) -> str:
    """Callers supply fixed argv only, never provider/ChatGPT text."""
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, check=False, timeout=15,
            shell=False, env={"PATH": "/usr/bin:/bin", "LANG": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Rejected from exc
    if result.returncode or len(result.stdout.encode("utf-8")) > MAX_JOURNAL_BYTES:
        raise Rejected
    return result.stdout


def timer_status() -> dict:
    """systemctl show with fixed unit names; only enum/boolean outputs."""
    try:
        a = _run_fixed((
            "/usr/bin/systemctl", "show", TIMER, "-p", "LoadState",
            "-p", "ActiveState", "-p", "SubState", "-p", "NextElapseUSecRealtime",
        ))
        b = _run_fixed((
            "/usr/bin/systemctl", "show", SERVICE, "-p", "Result",
            "-p", "ExecMainStatus",
        ))
        def parse(text: str, allowed: set[str]) -> dict[str, str]:
            fields = {}
            for line in text.splitlines():
                k, sep, value = line.partition("=")
                if sep != "=" or k not in allowed or k in fields or len(value) > 100:
                    raise Rejected
                fields[k] = value
            if set(fields) != allowed:
                raise Rejected
            return fields
        timer = parse(a, {"LoadState", "ActiveState", "SubState",
                          "NextElapseUSecRealtime"})
        service = parse(b, {"Result", "ExecMainStatus"})
        if timer["LoadState"] not in {"loaded", "not-found"} or timer["ActiveState"] not in {
            "active", "inactive", "failed"} or timer["SubState"] not in {
            "waiting", "dead", "failed", "elapsed", "running"}:
            raise Rejected
        if service["Result"] not in {"success", "exit-code", "timeout",
                                     "signal", "resources", "protocol"}:
            raise Rejected
        exit_code = service["ExecMainStatus"]
        if not exit_code.isdecimal() or int(exit_code) > 255:
            raise Rejected
        return {
            "status": "ok", "timer_loaded": timer["LoadState"] == "loaded",
            "timer_active": timer["ActiveState"] == "active",
            "timer_waiting": timer["SubState"] == "waiting",
            "next_schedule_present": bool(timer["NextElapseUSecRealtime"]),
            "last_service_success": service["Result"] == "success" and exit_code == "0",
            "last_service_exit_code": int(exit_code),
            "trading_enabled": False, "marketwide_top50_verified": False,
        }
    except (Rejected, ValueError):
        return _fail("systemd_status_unavailable")


def journal_summary() -> dict:
    """Exactly 24 expected research JSON records, without returning journal text."""
    try:
        output = _run_fixed((
            "/usr/bin/journalctl", "-u", SERVICE,
            "--since", "2026-11-09 19:00:00 UTC",
            "--until", "2026-11-10 18:30:00 UTC",
            "-o", "cat", "--no-pager",
        ))
        records = []
        for line in output.splitlines():
            if len(line) > 4096:
                raise Rejected
            try:
                obj = json.loads(line)
            except (ValueError, TypeError):
                continue
            if type(obj) is dict and obj.get("schema_version") == "j1-m1-rest-hourly-research-v1":
                records.append(obj)
                if len(records) > 24:
                    raise Rejected
        actual = [r.get("decision_end_ms") for r in records]
        success = all(
            r.get("status") == "research_sample_closed_hour_persisted"
            and r.get("failure_category") is None
            and r.get("selected_research_contracts") == 2
            and r.get("contracts_at_decision") == 2
            and r.get("orders_sent") is False
            and r.get("marketwide_top50_verified") is False
            and type(r.get("requests_attempted")) is int
            and type(r.get("new_closed_candles")) is int
            for r in records
        )
        gets = sum(r.get("requests_attempted", 0) for r in records if
                   type(r.get("requests_attempted")) is int)
        candles = sum(r.get("new_closed_candles", 0) for r in records if
                      type(r.get("new_closed_candles")) is int)
        passed = len(records) == 24 and actual == list(EXPECT) and success and (
            gets == 48 and candles == 50)
        return {
            "status": "pass" if passed else "incomplete",
            "recorded_runs": len(records),
            "successful_runs": sum(r.get("status") == "research_sample_closed_hour_persisted"
                                   for r in records),
            "expected_runs": 24, "all_expected_utc_hours": actual == list(EXPECT),
            "new_candles": candles, "public_gets": gets,
            "trading_enabled": False, "marketwide_top50_verified": False,
        }
    except (Rejected, ValueError, TypeError, OverflowError):
        return _fail("journal_audit_unavailable")


def _private_file() -> None:
    try:
        owner = pwd.getpwnam("cia-probe").pw_uid
        for directory in (DB.parent.parent, DB.parent):
            info = directory.lstat()
            if (not stat.S_ISDIR(info.st_mode) or info.st_uid != owner
                    or stat.S_IMODE(info.st_mode) != 0o700):
                raise Rejected
        info = DB.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != owner
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_nlink != 1 or not 0 < info.st_size <= MAX_DB_BYTES):
            raise Rejected
    except (OSError, KeyError, ValueError) as exc:
        raise Rejected from exc


def _number(text: object) -> Decimal:
    if type(text) is not str or len(text) > 96 or _DECIMAL.fullmatch(text) is None:
        raise Rejected
    m = re.search(r"[eE]([+-]?[0-9]{1,3})\Z", text)
    if m is not None and abs(int(m.group(1))) > 48:
        raise Rejected
    try:
        x = Decimal(text)
    except InvalidOperation as exc:
        raise Rejected from exc
    if not x.is_finite() or x < 0:
        raise Rejected
    return x


def _verify_candle(symbol: str, row: tuple, expected_open: int) -> None:
    if len(row) != 9:
        raise Rejected
    opened, op, hi, lo, close, base, quote, receipt, digest = row
    if (type(opened) is not int or opened != expected_open
            or type(receipt) is not int or receipt < opened + HOUR_MS
            or type(digest) is not str or _SHA.fullmatch(digest) is None):
        raise Rejected
    vals = (_number(op), _number(hi), _number(lo), _number(close),
            _number(base), _number(quote))
    if (min(vals[:4]) <= 0 or vals[1] < max(vals[0], vals[3])
            or vals[2] > min(vals[0], vals[3]) or vals[2] > vals[1]):
        raise Rejected
    recorded = [str(opened), op, hi, lo, close, base, quote]
    reference = sha256(json.dumps(
        [symbol, recorded], sort_keys=True,
        separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")).hexdigest()
    if digest != reference:
        raise Rejected


def sqlite_audit() -> dict:
    """Read SQLite URI only in read-only mode, replay all candle digests."""
    try:
        _private_file()
        with closing(sqlite3.connect(
            DB.as_uri() + "?mode=ro", uri=True, timeout=0.25,
        )) as db:
            db.execute("PRAGMA query_only=ON")
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise Rejected
            scope = db.execute(
                "SELECT scope_digest,members_json,initial_end_ms,halted_reason "
                "FROM scope WHERE id=1"
            ).fetchone()
            if scope is None:
                raise Rejected
            scope_hash, members_json, initial, halted = scope
            if (type(scope_hash) is not str or _SHA.fullmatch(scope_hash) is None
                    or type(members_json) is not str or type(initial) is not int
                    or initial % HOUR_MS or halted is not None):
                raise Rejected
            members = json.loads(members_json)
            if (type(members) is not list or len(members) != 2
                    or any(type(s) is not str or _SYM.fullmatch(s) is None
                           for s in members) or len(set(members)) != 2):
                raise Rejected
            expected_publications = [
                (initial, 2), (initial + HOUR_MS, 2),
                *[(end, 2) for end in EXPECT],
            ]
            if initial != EXPECT[0] - 3 * HOUR_MS:
                raise Rejected
            pubs = db.execute(
                "SELECT end_ms,observed_contracts FROM published_hour ORDER BY end_ms"
            ).fetchall()
            if pubs != expected_publications:
                raise Rejected
            for symbol in members:
                cursor = db.execute(
                    "SELECT next_open_ms FROM cursor WHERE symbol=?", (symbol,)
                ).fetchone()
                if cursor != (EXPECT[-1],):
                    raise Rejected
                rows = db.execute(
                    "SELECT open_ms,open,high,low,close,base_volume,quote_turnover,"
                    "received_at_ms,digest_sha256 FROM candles WHERE symbol=? "
                    "ORDER BY open_ms", (symbol,),
                ).fetchall()
                if len(rows) != 50:
                    raise Rejected
                start = initial - 24 * HOUR_MS
                for i, row in enumerate(rows):
                    _verify_candle(symbol, row, start + i * HOUR_MS)
            return {
                "status": "pass", "contracts": 2, "stored_candles": 100,
                "published_checkpoints": len(pubs),
                "last_published_end_ms": EXPECT[-1],
                "sqlite_integrity": True, "contiguous_candles": True,
                "digest_replay": True, "halted": False,
                "trading_enabled": False, "marketwide_top50_verified": False,
            }
    except (Rejected, OSError, sqlite3.Error, ValueError, TypeError,
            OverflowError, UnicodeError):
        return _fail("sqlite_audit_unavailable")


# The financial broker deliberately has no DAC capabilities and cannot enter
# the owner-only data tree. All DB reading happens in the separate cia-probe
# sidecar, without relaxing the broker's systemd sandbox.
OWNER_SOCKET = "/run/cia-j1-owner/readonly.sock"


def sqlite_audit_via_owner() -> dict:
    """Proxy one fixed audit request; never accept caller paths/SQL or raw rows."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(15)
            client.connect(OWNER_SOCKET)
            client.sendall(b'{"op":"cia_sqlite"}\\n'.replace(b"\\\\n", b"\\n"))
            chunks = bytearray()
            while b"\\n" not in chunks and len(chunks) <= 4096:
                block = client.recv(min(1024, 4097-len(chunks)))
                if not block:
                    break
                chunks.extend(block)
        if len(chunks) > 4096 or chunks.count(b"\\n") != 1 or not chunks.endswith(b"\\n"):
            raise Rejected
        report = json.loads(bytes(chunks[:-1]))
        if (type(report) is not dict or report.get("trading_enabled") is not False
                or report.get("marketwide_top50_verified") is not False):
            raise Rejected
        if report.get("status") == "pass":
            expected = {
                "status": "pass", "contracts": 2, "stored_candles": 100,
                "published_checkpoints": 26, "last_published_end_ms": EXPECT[-1],
                "sqlite_integrity": True, "contiguous_candles": True,
                "digest_replay": True, "halted": False,
                "trading_enabled": False, "marketwide_top50_verified": False,
            }
            if report != expected:
                raise Rejected
            return expected
        if report.get("status") == "blocked":
            return _fail("sqlite_owner_audit_blocked")
        raise Rejected
    except (OSError, TimeoutError, Rejected, ValueError, TypeError,
            OverflowError, UnicodeError):
        return _fail("sqlite_owner_service_unavailable")

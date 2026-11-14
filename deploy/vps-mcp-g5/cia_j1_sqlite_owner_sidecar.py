"""Single-capability, local Unix socket reader for the private J1 SQLite.

Runs as Unix user cia-probe, NEVER as the financial MCP broker. The only
accepted wire operation is the constant literal 'cia_sqlite'. No paths, SQL,
symbol names or timestamps are caller-controlled. No network or writes.
"""
from __future__ import annotations

import json
import subprocess
import os
import pwd
import grp
import socket
import stat
import struct
import sys

from crypto_j1_readonly import sqlite_audit
from crypto_j1_ws_d323 import validate_ws_d323_report

SOCKET = "/run/cia-j1-owner/readonly.sock"
MAX_REQUEST = 128
MAX_REPLY = 4096
CLIENT_GROUP = "agente-mcp"
WS_D323_CODE = "/home/cia-probe/agent/j1-n50-ws-70dec97d0a39-code-20261113T014549Z"
WS_D323_PY = "/home/cia-probe/agent/ws-venv/bin/python"
WS_D323_SCRIPT = "scripts/audit_j1_n50_ws_24h_once.py"


def _denied() -> dict[str, object]:
    return {
        "status": "blocked", "reason": "owner_audit_request_denied",
        "trading_enabled": False, "marketwide_top50_verified": False,
    }


def _authorized(raw: bytes, peer_uid: int) -> bool:
    if peer_uid != 0 or len(raw) > MAX_REQUEST or not raw.endswith(b"\n"):
        return False
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError, UnicodeError):
        return False
    return type(obj) is dict and obj in (
        {"op": "cia_sqlite"}, {"op": "cia_ws_d323"},
    )


def ws_d323_audit() -> dict[str, object]:
    """Execute exactly one owner-pinned, read-only D323 witness; no caller args."""
    denied = {
        "status": "blocked", "reason": "ws_d323_owner_audit_unavailable",
        "trading_enabled": False, "marketwide_top50_verified": False,
    }
    try:
        owner = pwd.getpwnam("cia-probe").pw_uid
        root = os.lstat(WS_D323_CODE)
        script = os.lstat(os.path.join(WS_D323_CODE, WS_D323_SCRIPT))
        if (os.getuid() != owner or os.geteuid() != owner
                or not stat.S_ISDIR(root.st_mode) or root.st_uid != owner
                or stat.S_IMODE(root.st_mode) != 0o700
                or not stat.S_ISREG(script.st_mode) or script.st_uid != owner
                or script.st_nlink != 1):
            return denied
        run = subprocess.run(
            (
                WS_D323_PY, "-B", "-m", "scripts.audit_j1_n50_ws_24h_once",
                "--allow-private-readonly-audit", "--enable-ws-24h-witness",
            ),
            cwd=WS_D323_CODE, env={
                "PATH": "/usr/bin:/bin", "LANG": "C",
                "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
            }, stdin=subprocess.DEVNULL, capture_output=True,
            timeout=90, shell=False, check=False,
        )
        raw = run.stdout
        if (run.returncode not in (0, 65)
                or not 1 <= len(raw) <= MAX_REPLY
                or raw.count(b"\n") != 1 or not raw.endswith(b"\n")):
            return denied
        report = json.loads(raw[:-1])
        if not validate_ws_d323_report(report):
            return denied
        passed = report["status"] == "ws_24h_local_evidence_verified"
        if (run.returncode == 0) != passed:
            return denied
        return report
    except (OSError, ValueError, TypeError, UnicodeError,
            subprocess.TimeoutExpired):
        return denied


def _serve_client(conn: socket.socket) -> None:
    try:
        conn.settimeout(30.0)
        peer = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        _pid, uid, _gid = struct.unpack("3i", peer)
        raw = bytearray()
        while len(raw) <= MAX_REQUEST:
            block = conn.recv(MAX_REQUEST + 1 - len(raw))
            if not block:
                break
            raw.extend(block)
            if b"\n" in block:
                break
        if not _authorized(bytes(raw), uid):
            result = _denied()
        elif json.loads(bytes(raw))["op"] == "cia_ws_d323":
            result = ws_d323_audit()
        else:
            result = sqlite_audit()
    except (OSError, TimeoutError, ValueError, TypeError):
        result = _denied()
    data = json.dumps(result, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"
    if len(data) > MAX_REPLY:
        data = json.dumps(_denied(), separators=(",", ":")).encode("ascii") + b"\n"
    try:
        conn.sendall(data)
    except (OSError, TimeoutError):
        pass


def main() -> None:
    """Serve exactly the one fd3 listener allocated by systemd root.

    No filesystem bind/chown, no ownership of the financial Unix group.
    """
    expected_uid = pwd.getpwnam("cia-probe").pw_uid
    expected_gid = pwd.getpwnam("cia-probe").pw_gid
    if (os.getuid() != expected_uid or os.geteuid() != expected_uid
            or os.getgid() != expected_gid or os.getegid() != expected_gid):
        raise RuntimeError("owner_user_and_group_required")
    if (os.environ.get("LISTEN_FDS") != "1"
            or os.environ.get("LISTEN_PID") != str(os.getpid())):
        raise RuntimeError("systemd_socket_activation_required")
    directory = os.path.dirname(SOCKET)
    dstat = os.lstat(directory)
    statinfo = os.lstat(SOCKET)
    if (not stat.S_ISDIR(dstat.st_mode) or dstat.st_uid != 0
            or stat.S_IMODE(dstat.st_mode) != 0o755
            or not stat.S_ISSOCK(statinfo.st_mode)
            or statinfo.st_uid != 0
            or statinfo.st_gid != grp.getgrnam(CLIENT_GROUP).gr_gid
            or stat.S_IMODE(statinfo.st_mode) != 0o660):
        raise RuntimeError("systemd_socket_untrusted")
    with socket.socket(fileno=3) as server:
        if server.family != socket.AF_UNIX or server.getsockname() != SOCKET:
            raise RuntimeError("unexpected_listener")
        print("cia_j1_owner_sidecar=ready", flush=True)
        while True:
            conn, _addr = server.accept()
            with conn:
                _serve_client(conn)


if __name__ == "__main__":
    main()
